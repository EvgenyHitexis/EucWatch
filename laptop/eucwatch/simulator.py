"""Synthetic protocol traffic, with no wheel transport or command capability."""

import math
import zlib
from typing import Any

from .protocol import FRAME_LENGTHS


class Simulator:
    def __init__(self):
        self.values: dict[str, Any] = {
            "speed_kmh": 0.0,
            "voltage_V": 135.0,
            "pwm_percent": 0.0,
            "watch_battery_percent": 80,
            "traffic": "normal",
            "frame_length": 87,
            "fragment_size": 20,
        }

    def configure(self, payload: dict[str, Any]) -> None:
        if set(payload) - self.values.keys():
            raise ValueError("Unknown simulator setting")
        proposed = self.values | payload
        for field, low, high in (
            ("speed_kmh", -3276.8, 3276.7),
            ("voltage_V", 0, 655.35),
            ("pwm_percent", 0, 655.35),
            ("watch_battery_percent", 0, 100),
        ):
            value = proposed[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"Invalid simulator {field}")
        if proposed["traffic"] not in ("normal", "paused", "corrupt"):
            raise ValueError("Invalid simulator traffic")
        for field in ("frame_length", "fragment_size"):
            if type(proposed[field]) is not int:
                raise ValueError(f"Invalid simulator {field}")
        if (
            proposed["frame_length"] not in FRAME_LENGTHS
            or not 1 <= proposed["fragment_size"] <= 1024
        ):
            raise ValueError("Invalid simulator frame or fragment size")
        self.values = proposed

    def notifications(self, *, corrupt: bool = False) -> list[bytes]:
        frame = bytearray(self.values["frame_length"] - 4)
        frame[:4] = b"\xdc\x5a\x5c" + bytes([len(frame)])
        frame[4:6] = round(self.values["voltage_V"] * 100).to_bytes(2, "big")
        frame[6:8] = round(self.values["speed_kmh"] * 10).to_bytes(
            2, "big", signed=True
        )
        frame[28:30] = (6010).to_bytes(2, "big")
        frame[34:36] = round(self.values["pwm_percent"] * 100).to_bytes(2, "big")
        frame.extend(zlib.crc32(frame).to_bytes(4, "big"))
        if corrupt:
            frame[4] ^= 1
        size = self.values["fragment_size"]
        return [bytes(frame[pos : pos + size]) for pos in range(0, len(frame), size)]
