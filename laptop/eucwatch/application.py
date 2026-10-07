"""Behavior entered through explicit actions, raw notifications and time."""

import math
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .clock import Clock, ManualClock, SystemClock
from .protocol import CHARACTERISTIC, Assembler, Telemetry, decode
from .simulator import Simulator
from .recording import Replay


def rounded(value: float, places: int = 0) -> str:
    return str(
        Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    )


def battery_percent(voltage: float) -> int:
    if voltage <= 119.02:
        return 0
    if voltage >= 148.05:
        return 100
    return max(0, min(100, int(rounded((voltage - 119.02) / 0.2903))))


class Application:
    def __init__(
        self,
        clock: Clock | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.clock = clock or SystemClock()
        self.host_clock = self.clock
        self.controlled = False
        self.mode = "idle"
        self.session = 0
        self.connected = False
        self.last_valid: float | None = None
        self.telemetry: Telemetry | None = None
        self.parser = Assembler()
        self.valid_frames = 0
        self.simulator = Simulator()
        self.simulating = False
        self.last_emission = 0.0
        self.time_offset = 0.0
        self.previous_clock = self.clock.read()
        self.resume_events = 0
        self.screen = "dashboard"
        self.awake = True
        self.button_down = False
        self.wake_cycle = False
        self.button_started: float | None = None
        self.recovery = False
        self.feedback = ""
        self.last_interaction = self.elapsed()
        self.established_connection = False
        self.event_sink = event_sink
        self.recording_error: str | None = None
        self.replay: Replay | None = None
        self.replay_source_session: int | str | None = None

    def _event(self, event: str, **values: Any) -> None:
        if self.event_sink is not None:
            try:
                self.event_sink(
                    {
                        "event": event,
                        "session": self.session,
                        "receipt_elapsed_s": self.host_clock.read()[0],
                        "behavior_elapsed_s": self.elapsed(),
                        "source": self.mode,
                        **values,
                    }
                )
            except (OSError, ValueError) as exc:
                self.recording_error = f"Recording failed: {type(exc).__name__}: {exc}"

    def elapsed(self) -> float:
        return self.clock.read()[0] + self.time_offset

    def action(self, name: str, **payload: Any) -> dict[str, Any]:
        self.tick()
        self._event("intent", action=name, payload={k:v for k,v in payload.items() if k != 'recording'})
        if self.mode == 'replay' and name not in ('replay_start', 'replay_step', 'stop', 'simulator_start', 'swipe', 'sleep', 'button_down', 'button_up', 'button_hold', 'interact'):
            raise ValueError('Replay is read-only; no wheel commands or simulator input')
        if name in ("connect", "simulator_start"):
            self.replay = None
            mode = payload.get("mode", "simulator")
            if mode != "simulator":
                raise ValueError("Only simulator connections are available")
            controlled = payload.get(
                "controlled", self.controlled if name == "connect" else False
            )
            if type(controlled) is not bool:
                raise ValueError("Controlled simulator time must be true or false")
            self.controlled = controlled
            self.clock = ManualClock() if controlled else self.host_clock
            self.time_offset = 0
            self.previous_clock = self.clock.read()
            self.mode = mode
            self.session += 1
            self.connected = True
            self.established_connection = True
            self.awake = True
            self.last_interaction = self.elapsed()
            # Time-source changes cannot create a button-hold interval.
            if self.button_down:
                self.button_started = self.elapsed()
            self.last_valid = None
            self.parser = Assembler()
            self.simulating = name == "simulator_start"
            self._event("transport", transition="connected")
            if self.simulating:
                self._emit()
        elif name in ("disconnect", "stop"):
            self.connected = False
            self.session += 1
            self.last_valid = None
            self.parser = Assembler()
            self.simulating = False
            if name == "stop":
                self.mode = "idle"
                self.replay = None
            self._event(
                "transport", transition="stopped" if name == "stop" else "disconnected"
            )
        elif name == "simulator_configure":
            self.simulator.configure(payload)
        elif name == "simulator_emit":
            if self.mode != "simulator" or not self.connected:
                raise ValueError("Simulator is not connected")
            self._emit()
        elif name == "advance":
            seconds = payload.get("seconds")
            if (
                self.mode != "simulator"
                or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds)
                or not 0 <= seconds <= 3600
            ):
                raise ValueError(
                    "Controlled advance requires simulator mode and 0–3600 seconds"
                )
            self.time_offset += seconds
            self.tick()
        elif name == 'replay_start':
            recording = payload.get('recording')
            if not isinstance(recording, Replay):
                raise ValueError('A validated wheel recording is required')
            self.session += 1
            self.mode = 'replay'
            self.simulating = False
            self.connected = False
            self.last_valid = None
            self.parser = Assembler()
            first = recording.rows[0]
            initial_time = first.get('behavior_elapsed_s', first['receipt_elapsed_s'])
            self.clock = ManualClock(initial_time)
            self.time_offset = 0
            self.previous_clock = self.clock.read()
            self.replay = recording
            self.replay_source_session = None
            self.screen = 'dashboard'
            self.awake = True
            self.last_interaction = initial_time
            self.button_down = False
            self.button_started = None
            self.wake_cycle = False
        elif name == 'replay_step':
            if self.mode != 'replay' or self.replay is None:
                raise ValueError('No replay is loaded')
            row = self.replay.next_event()
            if row is not None:
                stamp = row.get('behavior_elapsed_s', row['receipt_elapsed_s'])
                if not isinstance(self.clock, ManualClock):
                    raise ValueError('Replay requires a virtual clock')
                self.clock.elapsed = stamp
                self.clock.monotonic = stamp
                self.previous_clock = self.clock.read()
                self.tick()
                event = row['event']
                if event == 'transport':
                    self.session += 1
                    self.parser = Assembler()
                    self.last_valid = None
                    self.replay_source_session = row['session']
                    if row['transition'] != 'resume':
                        self.connected = row['transition'] == 'connected'
                    self.button_down = False
                    self.wake_cycle = False
                    self.button_started = None
                    self.established_connection |= self.connected
                    if self.connected:
                        self.awake = True
                        self.last_interaction = self.elapsed()
                elif event == 'notification':
                    if self.replay_source_session is None:
                        self.replay_source_session = row['session']
                        self.connected = True
                        self.established_connection = True
                    if row['session'] == self.replay_source_session:
                        self.receive(self.session, bytes.fromhex(row['raw_hex']))
                # Recorded intents/submissions/results are evidence, never actions.
        elif name == "swipe":
            direction = payload.get("direction")
            if direction not in ("left", "right", "down", "up"):
                raise ValueError("Invalid swipe direction")
            if self.awake:
                if direction == "left" and self.screen == "dashboard":
                    self.screen = "presets"
                elif direction == "down" and payload.get("from_top", True):
                    self.screen = "settings"
                elif direction == "right" and self.screen != "dashboard":
                    self.screen = "dashboard"
        elif name == "sleep":
            if not self.awake or self.screen != "settings":
                raise ValueError("Sleep screen is available inside Settings")
            self.awake = False
        elif name == "button_down":
            if not self.button_down:
                self.button_down = True
                self.button_started = self.elapsed()
                self.wake_cycle = not self.awake
                self.awake = True
                if self.wake_cycle:
                    self.feedback = "Wake only"
                elif self.recovery:
                    self.feedback = "Horn unavailable in recovery"
                else:
                    self.feedback = "Horn control not implemented"
        elif name == "button_up":
            self.button_down = False
            self.wake_cycle = False
            self.button_started = None
        elif name in ("button_hold", "interact"):
            pass
        else:
            raise ValueError(f"Unknown action: {name}")
        if name not in ("advance", "simulator_emit") and self.awake:
            self.last_interaction = self.elapsed()
        return self.view()

    def tick(self) -> None:
        self._check_resume()
        if (
            self.button_down
            and self.button_started is not None
            and self.elapsed() - self.button_started >= 30 - 1e-9
        ):
            self.recovery = True
            self.awake = True
            self.feedback = "Recovery mode"
        if (
            self.awake
            and not self.established_connection
            and not self.button_down
            and not self.recovery
            and self.elapsed() - self.last_interaction >= 30 - 1e-9
        ):
            self.awake = False
        if (
            self.simulating
            and self.connected
            and self.elapsed() - self.last_emission >= 0.2
            and self.simulator.values["traffic"] != "paused"
        ):
            self._emit()

    def _check_resume(self) -> None:
        boot, mono = self.clock.read()
        previous_boot, previous_mono = self.previous_clock
        self.previous_clock = boot, mono
        if boot - previous_boot - (mono - previous_mono) > 0.1:
            self.resume_events += 1
            self.session += 1
            self.last_valid = None
            self.parser = Assembler()
            # No missed synthetic notifications are delivered after resume.
            self.last_emission = self.elapsed()
            self.button_down = False
            self.wake_cycle = False
            self.button_started = None
            self._event("transport", transition="resume")

    def _emit(self) -> None:
        self.last_emission = self.elapsed()
        corrupt = self.simulator.values["traffic"] == "corrupt"
        for raw in self.simulator.notifications(corrupt=corrupt):
            self.receive(self.session, raw)

    def receive(self, session: int, raw: bytes) -> None:
        self._check_resume()
        self._event(
            "notification",
            session=session,
            characteristic=CHARACTERISTIC,
            raw_hex=raw.hex(),
        )
        if session != self.session or not self.connected:
            return
        for frame in self.parser.feed(raw):
            telemetry = decode(frame)
            if telemetry is not None:
                self.telemetry = telemetry
                self.last_valid = self.elapsed()
                self.valid_frames += 1
            else:
                self.parser.rejected += 1

    def fresh(self) -> bool:
        return (
            self.connected
            and self.last_valid is not None
            and self.elapsed() - self.last_valid < 1.0
        )

    def view(self) -> dict[str, Any]:
        self.tick()
        live = self.fresh()
        values = self.telemetry
        return {
            "mode": self.mode,
            "screen": self.screen,
            "awake": self.awake,
            "button": {"down": self.button_down, "wake_cycle": self.wake_cycle},
            "recovery": self.recovery,
            "established_connection": self.established_connection,
            "feedback": self.feedback,
            "recording_error": self.recording_error,
            'replay': None if self.replay is None else self.replay.status(),
            "session": self.session,
            "connected": self.connected,
            "fresh": live,
            "elapsed_s": self.elapsed(),
            "simulator": dict(self.simulator.values),
            "controlled": self.controlled,
            "diagnostics": {
                "valid_frames": self.valid_frames,
                "rejected_frames": self.parser.rejected,
                "resume_events": self.resume_events,
            },
            "telemetry": None
            if values is None
            else {
                "voltage_V": values.voltage_V,
                "speed_kmh": values.speed_kmh,
                "pwm_percent": values.pwm_percent,
                "firmware": values.firmware,
            },
            "dashboard": {
                "speed": rounded(abs(values.speed_kmh)) if values and live else "—",
                "pwm": rounded(values.pwm_percent) if values and live else "—",
                "wheel_battery_percent": str(battery_percent(values.voltage_V))
                if values
                else "—",
                "average_cell_voltage": rounded(values.voltage_V / 36, 2)
                if values
                else "—",
                "wheel_battery_dimmed": not live,
                "watch_battery_percent": rounded(
                    self.simulator.values["watch_battery_percent"]
                ),
                "watch_battery_simulated": True,
                "connection": (
                    "Connected"
                    if live
                    else "Telemetry lost"
                    if self.connected and self.last_valid is not None
                    else "Waiting for telemetry"
                    if self.connected
                    else "Disconnected"
                    if self.mode != "idle"
                    else "Not connected"
                ),
            },
        }
