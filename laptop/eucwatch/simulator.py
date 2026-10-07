"""Synthetic protocol traffic, with no wheel transport or command capability."""

import math
import zlib
from typing import Any

from .protocol import FRAME_LENGTHS
from .control import FIELDS


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
            "control_submission": "normal", "control_fail_after": 1,
            "control_submission_delay_s": 0.0, "control_readback": "normal",
            "control_delay_s": 0.0,
        }
        self.settings = {"pedal_sensitivity": 30, "dynamic_assist": 25,
                         "pedal_dip_compensation": 10}
        self.settings_ready_s = 0.0

    def submit(self, packet: bytes, index: int, now: float) -> str:
        if self.values["control_submission"] == "hang":
            return "pending"
        if self.values["control_submission"] == "fail" and index >= self.values["control_fail_after"]:
            return "failed"
        if packet[:4] != b"LdAp" or zlib.crc32(packet[:-4]) != int.from_bytes(packet[-4:], "big"):
            return "failed"
        for name, (identifier, offset, _readback) in FIELDS.items():
            if packet[4] == identifier and len(packet) == offset + 5 and packet[offset] <= 100:
                self.settings[name] = packet[offset]
                self.settings_ready_s = now + self.values["control_delay_s"]
                return "accepted"
        return "failed"

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
        if proposed["control_submission"] not in ("normal", "fail", "hang") or proposed["control_readback"] not in ("normal", "missing", "mismatch", "partial"):
            raise ValueError("Invalid simulator control scenario")
        if type(proposed["control_fail_after"]) is not int or not 0 <= proposed["control_fail_after"] <= 3:
            raise ValueError("Invalid simulator failure position")
        for name in ("control_delay_s", "control_submission_delay_s"):
            value = proposed[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 60:
                raise ValueError("Invalid simulator control delay")
        self.values = proposed

    def notifications(self, *, corrupt: bool = False, now: float = 0.0) -> list[bytes]:
        frame = bytearray(self.values["frame_length"] - 4)
        frame[:4] = b"\xdc\x5a\x5c" + bytes([len(frame)])
        frame[4:6] = round(self.values["voltage_V"] * 100).to_bytes(2, "big")
        frame[6:8] = round(self.values["speed_kmh"] * 10).to_bytes(
            2, "big", signed=True
        )
        frame[28:30] = (6010).to_bytes(2, "big")
        frame[34:36] = round(self.values["pwm_percent"] * 100).to_bytes(2, "big")
        readback = self.values["control_readback"]
        if readback != "missing" and now >= self.settings_ready_s:
            frame[46] = 8
            for index, (name, offset) in enumerate((("pedal_sensitivity", 50), ("dynamic_assist", 66), ("pedal_dip_compensation", 68))):
                value = self.settings[name]
                if readback == "mismatch":
                    value = (value + 1) % 101
                elif readback == "partial" and index > 0:
                    value = 0x80
                frame[offset] = value
        frame.extend(zlib.crc32(frame).to_bytes(4, "big"))
        if corrupt:
            frame[4] ^= 1
        size = self.values["fragment_size"]
        return [bytes(frame[pos : pos + size]) for pos in range(0, len(frame), size)]
