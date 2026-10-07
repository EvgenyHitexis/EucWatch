"""Behavior entered through explicit actions, raw notifications and time."""

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .clock import Clock, ManualClock, SystemClock
from .protocol import Assembler, Telemetry, decode
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
    def __init__(self, clock: Clock | None = None):
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

    def elapsed(self) -> float:
        return self.clock.read()[0] + self.time_offset

    def action(self, name: str, **payload: Any) -> dict[str, Any]:
        self.tick()
        if name in ("connect", "simulator_start"):
            mode = payload.get("mode", "simulator")
            if mode != "simulator":
                raise ValueError("Only simulator connections are available")
            controlled = payload.get("controlled", False)
            if type(controlled) is not bool:
                raise ValueError("Controlled simulator time must be true or false")
            self.controlled = controlled
            self.clock = ManualClock() if controlled else self.host_clock
            self.time_offset = 0
            self.previous_clock = self.clock.read()
            self.mode = mode
            self.session += 1
            self.connected = True
            self.last_valid = None
            self.parser = Assembler()
            self.simulating = name == "simulator_start"
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
        else:
            raise ValueError(f"Unknown action: {name}")
        return self.view()

    def tick(self) -> None:
        self._check_resume()
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

    def _emit(self) -> None:
        self.last_emission = self.elapsed()
        corrupt = self.simulator.values["traffic"] == "corrupt"
        for raw in self.simulator.notifications(corrupt=corrupt):
            self.receive(self.session, raw)

    def receive(self, session: int, raw: bytes) -> None:
        self._check_resume()
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
