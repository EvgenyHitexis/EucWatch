"""Behavior entered through explicit actions, raw notifications and time."""

import math
from collections.abc import Callable
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .alerts import AlertScheduler
from .clock import Clock, ManualClock, SystemClock
from .control import PresetControl
from .horn import HornRequests
from .configuration import (
    default_configuration,
    validate_alerts,
    validate_configuration,
)
from .persistence import ConfigStore, MemoryStore
from . import backup, presets
from .protocol import CHARACTERISTIC, Assembler, Telemetry, decode, decode_settings
from .recording import Replay
from .simulator import Simulator


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
        store: ConfigStore | None = None,
        vibration_output: Callable[[dict[str, Any]], None] | None = None,
        command_output: Callable[[dict[str, Any]], None] | None = None,
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
        self.store = store or MemoryStore()
        self.persistence_error: str | None = None
        self.config = default_configuration()
        try:
            loaded = self.store.load()
            if loaded is not None:
                self.config = validate_configuration(loaded)
            self.persistence_error = self.store.warning
        except (OSError, ValueError) as exc:
            self.persistence_error = f"Saved configuration requires review: {exc}"
        self.alerts_draft: dict[str, Any] | None = None
        self.preset_draft: dict[str, Any] | None = None
        self.confirmed_preset: dict[str, Any] | None = None
        self.configuration_preview: dict[str, Any] | None = None
        self.configuration_export: dict[str, Any] | None = None
        self.alerts = AlertScheduler(self.config["alerts"], output=vibration_output)
        self.command_output = command_output
        self.command_events: list[dict[str, Any]] = []
        self.control = PresetControl(self._submit_control, self._control_event)
        self.simulated_receipts: list[dict[str, Any]] = []
        self.control_status: tuple[int, str] | None = None
        self.horn = HornRequests(self._control_event)

    def _request_horn(self) -> None:
        reason = None
        if self.recovery:
            reason = "recovery mode"
        elif self.control.pending:
            reason = "preset applying"
        elif not self.awake or not self.fresh() or self.mode not in ("simulator", "live"):
            reason = "connection unavailable"
        elif self.mode == "live" and self.command_output is None:
            reason = "live control transport unavailable"
        if reason:
            self.horn.show(f"Horn unavailable: {reason}", self.elapsed(), self.session)
        else:
            row = self.horn.request(self.elapsed(), self.session)
            if self.command_output is None:
                self.horn.result(row["request"], row["session"], True, self.elapsed())
            else:
                try:
                    self.command_output(deepcopy(row))
                except (OSError, ValueError) as exc:
                    self.horn.result(row["request"], row["session"], False, self.elapsed(), str(exc))
        if self.horn.feedback:
            self.feedback = self.horn.feedback["message"]

    def _control_event(self, row: dict[str, Any]) -> None:
        self.command_events.append(deepcopy(row))
        del self.command_events[:-128]
        self._event(row["event"], **{key: value for key, value in row.items() if key != "event"})

    def _submit_control(self, row: dict[str, Any]) -> None:
        if self.command_output is not None:
            try:
                self.command_output(deepcopy(row))
            except (OSError, ValueError) as exc:
                self.control.result(row["attempt"], row["session"], row["index"], False, self.elapsed(), str(exc))
            return
        status = self.simulator.submit(bytes.fromhex(row["packet_hex"]), row["index"], self.elapsed())
        if status == "pending":
            return
        receipt = {**row, "due_s": self.elapsed() + self.simulator.values["control_submission_delay_s"], "success": status == "accepted"}
        if receipt["due_s"] <= self.elapsed():
            self._control_result(receipt)
        else:
            self.simulated_receipts.append(receipt)

    def _control_result(self, receipt: dict[str, Any]) -> None:
        before = self.control.attempt["status"] if self.control.attempt else None
        self.control.result(receipt["attempt"], receipt["session"], receipt["index"], receipt["success"], self.elapsed(), receipt.get("error", ""))
        if before == "submitting" and self.control.pending and self.control.attempt and self.control.attempt["status"] == "confirming":
            # A frame begun before submission completion is not fresh evidence.
            self.parser = Assembler()

    def _update_control(self) -> None:
        self.control.tick(self.elapsed(), fresh=self.fresh(), session=self.session, revision=self.config["revision"])
        due = [row for row in self.simulated_receipts if row["due_s"] <= self.elapsed() + 1e-9]
        self.simulated_receipts = [row for row in self.simulated_receipts if row["due_s"] > self.elapsed() + 1e-9]
        for row in due:
            self._control_result(row)
        if self.confirmed_preset is not None and self.control.confirmed is None:
            self.feedback = "Wheel confirmation unavailable" if not self.fresh() else "Settings changed"
        self.confirmed_preset = deepcopy(self.control.confirmed)
        attempt = self.control.attempt
        if attempt is not None:
            status = (attempt["id"], attempt["status"])
            if status != self.control_status:
                self.control_status = status
                self.feedback = f"{attempt['name']} · {'Applying' if attempt['pending'] else attempt['status']}"

    def _update_alerts(self) -> None:
        now = self.elapsed()
        # Process ordinary virtual-time gaps through the freshness deadline.
        # Resume takes a separate cancellation path and never replays pulses.
        if self.alerts.fresh and not self.fresh() and self.last_valid is not None:
            expiry = min(now, self.last_valid + 1)
            self.alerts.tick(expiry, inclusive=False)
            self.alerts.evaluate(expiry, fresh=False)
        values = self.telemetry
        self.alerts.evaluate(
            now,
            fresh=self.fresh(),
            pwm=None if values is None else values.pwm_percent,
            speed=None if values is None else abs(values.speed_kmh),
            battery=None if values is None else battery_percent(values.voltage_V),
        )

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

    def action(self, action_name: str, **payload: Any) -> dict[str, Any]:
        name = action_name
        self.tick()
        self._event(
            "intent",
            action=name,
            payload={k: v for k, v in payload.items() if k != "recording"},
        )
        if self.mode == "replay" and name not in (
            "replay_start",
            "replay_step",
            "stop",
            "simulator_start",
            "live_start",
            "swipe",
            "sleep",
            "button_down",
            "button_up",
            "button_hold",
            "interact",
            "alerts_begin",
            "alerts_update",
            "alerts_save",
            "alerts_cancel",
            "alert_test",
            "preset_begin", "preset_update", "preset_save", "preset_cancel", "preset_clear",
            "configuration_export", "configuration_import_prepare",
            "configuration_import_cancel", "configuration_import_commit",
        ):
            raise ValueError(
                "Replay is read-only; no wheel commands or simulator input"
            )
        if name == "live_start":
            self.alerts.reset(self.elapsed(), clear_trace=True)
            self.replay = None
            self.simulating = False
            self.controlled = False
            self.clock = self.host_clock
            self.time_offset = 0
            self.previous_clock = self.clock.read()
            self.mode = "live"
            self.session += 1
            self.connected = False
            self.last_valid = None
            self.parser = Assembler()
            self.button_down = False
            self.button_started = None
            self.wake_cycle = False
            self._event("transport", transition="connecting")
        elif name == "live_connected":
            if self.mode == "live" and payload.get("session") == self.session:
                self.connected = True
                self.established_connection = True
                self.awake = True
                self._event("transport", transition="connected")
        elif name == "live_disconnected":
            if self.mode == "live" and payload.get("session") == self.session:
                self.connected = False
                self.session += 1
                self.last_valid = None
                self.parser = Assembler()
                self._event("transport", transition="disconnected", reason=payload.get("reason"))
        elif name in ("connect", "simulator_start"):
            self.replay = None
            mode = payload.get("mode", "simulator")
            if mode != "simulator":
                raise ValueError("Only simulator connections are available")
            controlled = payload.get(
                "controlled", self.controlled if name == "connect" else False
            )
            if type(controlled) is not bool:
                raise ValueError("Controlled simulator time must be true or false")
            self.alerts.reset(self.elapsed(), clear_trace=True)
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
        elif name == "replay_start":
            recording = payload.get("recording")
            if not isinstance(recording, Replay):
                raise ValueError("A validated wheel recording is required")
            self.alerts.reset(self.elapsed(), clear_trace=True)
            self.session += 1
            self.mode = "replay"
            self.simulating = False
            self.connected = False
            self.last_valid = None
            self.parser = Assembler()
            first = recording.rows[0]
            initial_time = first.get("behavior_elapsed_s", first["receipt_elapsed_s"])
            self.clock = ManualClock(initial_time)
            self.time_offset = 0
            self.previous_clock = self.clock.read()
            self.replay = recording
            self.replay_source_session = None
            self.screen = "dashboard"
            self.awake = True
            self.last_interaction = initial_time
            self.button_down = False
            self.button_started = None
            self.wake_cycle = False
        elif name == "replay_step":
            if self.mode != "replay" or self.replay is None:
                raise ValueError("No replay is loaded")
            row = self.replay.next_event()
            if row is not None:
                stamp = row.get("behavior_elapsed_s", row["receipt_elapsed_s"])
                if not isinstance(self.clock, ManualClock):
                    raise ValueError("Replay requires a virtual clock")
                self.clock.elapsed = stamp
                self.clock.monotonic = stamp
                self.previous_clock = self.clock.read()
                if row["event"] == "transport" and row["transition"] == "resume":
                    had_fresh = self.alerts.had_fresh
                    self.alerts.reset(self.elapsed())
                    self.alerts.had_fresh = had_fresh
                    self.last_valid = None
                self.tick()
                event = row["event"]
                if event == "transport":
                    self.session += 1
                    self.parser = Assembler()
                    self.last_valid = None
                    self.replay_source_session = row["session"]
                    if row["transition"] != "resume":
                        self.connected = row["transition"] == "connected"
                    self.button_down = False
                    self.wake_cycle = False
                    self.button_started = None
                    self.established_connection |= self.connected
                    if row["transition"] == "connected":
                        self.alerts.reset(self.elapsed())
                    if self.connected:
                        self.awake = True
                        self.last_interaction = self.elapsed()
                elif event == "notification":
                    if self.replay_source_session is None:
                        self.replay_source_session = row["session"]
                        self.connected = True
                        self.established_connection = True
                    if row["session"] == self.replay_source_session:
                        self.receive(self.session, bytes.fromhex(row["raw_hex"]))
                # Recorded intents/submissions/results are evidence, never actions.
        elif name == "preset_apply":
            slot = presets.validate_slot(payload.get("slot"))
            if self.control.pending:
                return self.view()
            preset = self.config["presets"][slot - 1]
            if not preset["configured"]:
                raise ValueError("This preset slot is unconfigured")
            if not self.awake:
                raise ValueError("Wake the screen before selecting a riding preset")
            if not self.fresh() or self.recovery or self.mode not in ("simulator", "live"):
                raise ValueError("A healthy fresh wheel connection is required")
            if self.mode == "live" and self.command_output is None:
                raise ValueError("Live control transport is unavailable")
            self.screen = "dashboard"
            self.parser = Assembler()
            self.control.start(preset, self.config["revision"], self.session, self.elapsed())
        elif name == "command_result":
            if (type(payload.get("success")) is not bool
                    or any(type(payload.get(key)) is not int for key in ("attempt", "session", "index"))
                    or payload["attempt"] < 1 or payload["session"] < 0
                    or not 0 <= payload["index"] <= 2
                    or not isinstance(payload.get("error", ""), str)):
                raise ValueError("An explicit command result is required")
            self._control_result(payload)
        elif name == "horn_result":
            if (type(payload.get("success")) is not bool
                    or type(payload.get("request")) is not int or payload["request"] < 1
                    or type(payload.get("session")) is not int or payload["session"] < 0
                    or not isinstance(payload.get("error", ""), str)):
                raise ValueError("An explicit horn transport result is required")
            self.horn.result(payload["request"], payload["session"], payload["success"], self.elapsed(), payload.get("error", ""))
            if self.horn.feedback:
                self.feedback = self.horn.feedback["message"]
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
                    self.alerts_draft = None
        elif name == "alerts_begin":
            self.alerts_draft = deepcopy(self.config["alerts"])
        elif name == "configuration_export":
            self.configuration_export = backup.export(self.config)
        elif name == "configuration_import_prepare":
            self.configuration_preview = backup.prepare(payload.get("content"), self.config["revision"])
        elif name == "configuration_import_cancel":
            self.configuration_preview = None
        elif name == "configuration_import_commit":
            if self.configuration_preview is None:
                raise ValueError("Review a configuration import before committing")
            proposed = backup.replacement(self.configuration_preview, self.config["revision"])
            try:
                self.store.save(proposed)
            except (OSError, ValueError) as exc:
                self.persistence_error = f"Configuration save failed: {exc}"
            else:
                self.config = proposed
                self.confirmed_preset = None
                self.configuration_preview = None
                self.persistence_error = None
                self.alerts.configure(proposed["alerts"], self.elapsed())
                self._update_alerts()
        elif name in ("preset_begin", "preset_update", "preset_save", "preset_cancel", "preset_clear"):
            if payload.pop("source", "panel") != "panel":
                raise ValueError("Preset definitions can only be edited in the laptop panel")
            if name == "preset_begin":
                self.preset_draft = presets.begin(self.config, payload.get("slot"))
            elif name == "preset_update":
                if self.preset_draft is None:
                    raise ValueError("Open the preset editor before editing")
                self.preset_draft = presets.update(self.preset_draft, payload)
            elif name == "preset_clear":
                self.preset_draft = presets.cleared(self.config, payload.get("slot"))
            elif name == "preset_cancel":
                self.preset_draft = None
            elif name == "preset_save":
                if self.preset_draft is None:
                    raise ValueError("No preset draft is open")
                proposed = presets.replacement(self.config, self.preset_draft)
                try:
                    self.store.save(proposed)
                except (OSError, ValueError) as exc:
                    self.persistence_error = f"Configuration save failed: {exc}"
                else:
                    if proposed["presets"] != self.config["presets"]:
                        self.confirmed_preset = None
                    self.config = proposed
                    self.preset_draft = None
                    self.persistence_error = None
        elif name == "alerts_update":
            alert = payload.pop("alert", None)
            if self.alerts_draft is None:
                raise ValueError("Open the alert editor before editing")
            if (
                alert not in self.alerts_draft
                or not payload
                or set(payload)
                - ({"enabled"} if alert == "lost" else {"enabled", "threshold"})
            ):
                raise ValueError("Invalid alert draft field")
            self.alerts_draft[alert].update(payload)
        elif name == "alerts_save":
            if self.alerts_draft is None:
                raise ValueError("No alert draft is open")
            alerts = validate_alerts(self.alerts_draft)
            proposed = deepcopy(self.config)
            proposed["alerts"] = alerts
            proposed["revision"] += 1
            proposed = validate_configuration(proposed)
            try:
                self.store.save(proposed)
            except (OSError, ValueError) as exc:
                self.persistence_error = f"Configuration save failed: {exc}"
            else:
                self.config = proposed
                self.alerts_draft = None
                self.persistence_error = None
                self.alerts.configure(alerts, self.elapsed())
                self._update_alerts()
        elif name == "alerts_cancel":
            self.alerts_draft = None
        elif name == "alert_test":
            alert = payload.get("alert")
            if not isinstance(alert, str):
                raise ValueError("An alert pattern is required")
            self.alerts.test(alert, self.elapsed())
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
                else:
                    self._request_horn()
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
        previous_horn = self.horn.feedback
        self.horn.tick(self.elapsed(), self.session)
        if previous_horn and self.horn.feedback is None and self.feedback == previous_horn["message"]:
            self.feedback = ""
        self._update_control()
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
            and self.alerts_draft is None
            and self.preset_draft is None
            and self.configuration_preview is None
            and self.elapsed() - self.last_interaction >= 30 - 1e-9
        ):
            self.awake = False
        if (
            self.simulating
            and self.connected
            and self.elapsed() - self.last_emission >= 0.2 - 1e-9
            and self.simulator.values["traffic"] != "paused"
        ):
            self._emit()
        self._update_alerts()
        self._update_control()

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
            had_fresh = self.alerts.had_fresh
            self.alerts.reset(self.elapsed())
            self.alerts.had_fresh = had_fresh
            self._event("transport", transition="resume")

    def _emit(self) -> None:
        self.last_emission = self.elapsed()
        corrupt = self.simulator.values["traffic"] == "corrupt"
        for raw in self.simulator.notifications(corrupt=corrupt, now=self.elapsed()):
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
        self._update_control()
        self._update_alerts()
        for frame in self.parser.feed(raw):
            telemetry = decode(frame)
            if telemetry is not None:
                self.telemetry = telemetry
                self.last_valid = self.elapsed()
                self.valid_frames += 1
                self._update_alerts()
                settings = decode_settings(frame)
                if settings is not None:
                    self.control.observe(settings, self.elapsed(), session)
                self._update_control()
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
            "config": deepcopy(self.config),
            "alerts_draft": deepcopy(self.alerts_draft),
            "preset_draft": deepcopy(self.preset_draft),
            "configuration_preview": deepcopy(self.configuration_preview),
            "configuration_export": deepcopy(self.configuration_export),
            "confirmed_preset": deepcopy(self.confirmed_preset),
            "preset_attempt": self.control.view(),
            "actual_settings": deepcopy(self.control.actual),
            "command_events": deepcopy(self.command_events),
            "horn_feedback": deepcopy(self.horn.feedback),
            "presets_menu": [{"id": preset["id"], "name": preset["name"],
                              "configured": preset["configured"], "available": bool(preset["configured"] and live and not self.control.pending and not self.recovery and self.mode in ("simulator", "live") and (self.mode == "simulator" or self.command_output is not None)),
                              "revision": self.config["revision"]}
                             for preset in self.config["presets"]],
            "persistence_error": self.persistence_error,
            "vibration": self.alerts.view(),
            "replay": None if self.replay is None else self.replay.status(),
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
