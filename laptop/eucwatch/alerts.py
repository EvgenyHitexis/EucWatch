"""Deterministic nonoverlapping tactile patterns and simulated pulse output."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .configuration import ALERTS, validate_alerts

PRIORITY = {"lost": 0, "pwm": 1, "speed": 2, "battery": 3}
PATTERNS = {
    "lost": (0.15,),
    "pwm": (0.15, 0.15, 0.15),
    "speed": (0.15, 0.15),
    "battery": (0.5,),
}
REPEATS = {"pwm": 2.0, "speed": 5.0}
GAP = 0.15
EPSILON = 1e-9


class AlertScheduler:
    def __init__(
        self,
        settings: dict[str, Any],
        output: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.settings = validate_alerts(settings)
        self.output = output
        self.events: list[dict[str, Any]] = []
        self.queue: list[tuple[str, bool]] = []
        self.pattern: dict[str, Any] | None = None
        self.active = {name: False for name in ALERTS}
        self.next_repeat: dict[str, float] = {}
        self.battery_armed = True
        self.battery_rearm_since: float | None = None
        self.had_fresh = False
        self.lost_reported = False
        self.fresh = False

    def configure(self, settings: dict[str, Any], now: float) -> None:
        proposed = validate_alerts(settings)
        for name in ALERTS:
            if proposed[name] != self.settings[name]:
                self.active[name] = False
                self.next_repeat.pop(name, None)
                self.queue = [
                    entry for entry in self.queue if entry[0] != name or entry[1]
                ]
                if (
                    self.pattern
                    and self.pattern["alert"] == name
                    and not self.pattern["test"]
                ):
                    self._cancel_pattern(now)
                if name == "battery":
                    self.battery_armed = True
                    self.battery_rearm_since = None
        self.settings = proposed

    def reset(self, now: float, *, clear_trace: bool = False) -> None:
        self._cancel_pattern(now)
        self.queue.clear()
        self.active = {name: False for name in ALERTS}
        self.next_repeat.clear()
        self.battery_armed = True
        self.battery_rearm_since = None
        self.had_fresh = False
        self.lost_reported = False
        self.fresh = False
        if clear_trace:
            self.events.clear()

    def _event(self, phase: str, at: float) -> None:
        assert self.pattern is not None
        row = {
            "alert": self.pattern["alert"],
            "test": self.pattern["test"],
            "phase": phase,
            "at_s": at,
            "duration_s": PATTERNS[self.pattern["alert"]][self.pattern["index"]],
        }
        self.events.append(row)
        del self.events[:-256]
        if self.output is not None:
            self.output(deepcopy(row))

    def _enqueue(self, name: str, test: bool = False) -> None:
        entry = (name, test)
        if entry not in self.queue and not (
            self.pattern
            and self.pattern["alert"] == name
            and self.pattern["test"] == test
        ):
            self.queue.append(entry)

    def _cancel_pattern(self, now: float) -> None:
        if self.pattern is not None and self.pattern["on"]:
            self._event("stop", min(now, self.pattern["deadline"]))
        self.pattern = None

    def evaluate(
        self,
        now: float,
        *,
        fresh: bool,
        pwm: float | None = None,
        speed: float | None = None,
        battery: int | None = None,
    ) -> None:
        # Cancel invalid measurements before consuming any overdue motor work.
        self.fresh = fresh
        if not fresh:
            self.queue = [
                entry for entry in self.queue if entry[0] == "lost" or entry[1]
            ]
            if (
                self.pattern
                and self.pattern["alert"] != "lost"
                and not self.pattern["test"]
            ):
                self._cancel_pattern(now)
            for name in ("pwm", "speed", "battery"):
                self.active[name] = False
            self.next_repeat.clear()
            self.battery_rearm_since = None
            if (
                self.had_fresh
                and not self.lost_reported
                and self.settings["lost"]["enabled"]
            ):
                self._enqueue("lost")
                self.lost_reported = True
        else:
            self.had_fresh = True
            self.lost_reported = False
            for name, value, hysteresis in (("pwm", pwm, 3), ("speed", speed, 2)):
                setting = self.settings[name]
                if not setting["enabled"] or value is None:
                    continue
                threshold = setting["threshold"]
                if self.active[name] and value <= threshold - hysteresis:
                    self.active[name] = False
                    self.next_repeat.pop(name, None)
                    self.queue = [
                        entry for entry in self.queue if entry != (name, False)
                    ]
                    if (
                        self.pattern
                        and self.pattern["alert"] == name
                        and not self.pattern["test"]
                    ):
                        self._cancel_pattern(now)
                elif not self.active[name] and value >= threshold:
                    self.active[name] = True
                    self._enqueue(name)
            setting = self.settings["battery"]
            if setting["enabled"] and battery is not None:
                threshold = setting["threshold"]
                if battery <= threshold and self.battery_armed:
                    self.battery_armed = False
                    self.battery_rearm_since = None
                    self._enqueue("battery")
                elif battery >= threshold + 3:
                    if self.battery_rearm_since is None:
                        self.battery_rearm_since = now
                    if now - self.battery_rearm_since >= 5 - EPSILON:
                        self.battery_armed = True
                else:
                    self.battery_rearm_since = None
        self.tick(now)

    def test(self, name: str, now: float) -> None:
        if name not in PATTERNS:
            raise ValueError("Unknown alert pattern")
        self._enqueue(name, True)
        self.tick(now)

    def _start_next(self, now: float) -> None:
        if self.pattern is not None or not self.queue:
            return
        self.queue.sort(key=lambda entry: PRIORITY[entry[0]])
        name, test = self.queue.pop(0)
        self.pattern = {
            "alert": name,
            "test": test,
            "index": 0,
            "on": True,
            "started_s": now,
            "deadline": now + PATTERNS[name][0],
        }
        if not test and name in REPEATS:
            self.next_repeat[name] = now + REPEATS[name]
        self._event("start", now)

    def tick(self, now: float) -> None:
        # Timed pattern phases are replayable output events. Actual resume calls
        # reset rather than replaying expired pulses.
        while self.pattern is not None and now + EPSILON >= self.pattern["deadline"]:
            deadline = self.pattern["deadline"]
            if self.pattern["on"]:
                self._event("stop", deadline)
                self.pattern["on"] = False
                if self.pattern["index"] + 1 == len(PATTERNS[self.pattern["alert"]]):
                    self.pattern = None
                    self._start_next(deadline)
                else:
                    self.pattern["deadline"] = deadline + GAP
            else:
                self.pattern["index"] += 1
                self.pattern["on"] = True
                self.pattern["started_s"] = deadline
                self.pattern["deadline"] = (
                    deadline + PATTERNS[self.pattern["alert"]][self.pattern["index"]]
                )
                self._event("start", deadline)
        if self.fresh:
            for name, deadline in list(self.next_repeat.items()):
                if self.active[name] and now + EPSILON >= deadline:
                    self._enqueue(name)
        self._start_next(now)

    def view(self) -> dict[str, Any]:
        current = None
        if self.pattern and self.pattern["on"]:
            current = {
                "alert": self.pattern["alert"],
                "test": self.pattern["test"],
                "started_s": self.pattern["started_s"],
                "duration_s": PATTERNS[self.pattern["alert"]][self.pattern["index"]],
            }
        return {
            "simulated": True,
            "current": current,
            "events": deepcopy(self.events),
            "queued": [name for name, _test in self.queue],
        }
