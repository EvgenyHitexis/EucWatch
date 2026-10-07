"""Elapsed time adapters; Ubuntu boottime includes time spent suspended."""

import time
from typing import Protocol


class Clock(Protocol):
    def read(self) -> tuple[float, float]: ...


class SystemClock:
    def read(self) -> tuple[float, float]:
        return time.clock_gettime(time.CLOCK_BOOTTIME), time.monotonic()


class ManualClock:
    def __init__(self, elapsed: float = 0.0):
        self.elapsed = elapsed
        self.monotonic = elapsed

    def read(self) -> tuple[float, float]:
        return self.elapsed, self.monotonic

    def advance(self, seconds: float, *, suspended: bool = False) -> None:
        if seconds < 0:
            raise ValueError("Elapsed time cannot move backwards")
        self.elapsed += seconds
        if not suspended:
            self.monotonic += seconds
