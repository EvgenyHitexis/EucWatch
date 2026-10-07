"""Bounded CRC-valid Sherman L FFE1 stream decoding.

Offsets and source-fixture provenance are in docs/research/sherman-l-protocol.md.
Frame lengths are complete lengths observed from owner traffic or the source
fixture, not a claim about arbitrary Veteran-family extensions.
"""

import zlib
from dataclasses import dataclass

CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"
FRAME_LENGTHS = frozenset((75, 77, 87, 99))


@dataclass(frozen=True)
class Telemetry:
    voltage_V: float
    speed_kmh: float
    pwm_percent: float
    firmware_word: int

    @property
    def firmware(self) -> str:
        return f"{self.firmware_word // 1000:03}.{self.firmware_word % 1000 // 100}.{self.firmware_word % 100:02}"


class Assembler:
    """Retains at most 98 incomplete bytes regardless of notification size."""

    def __init__(self):
        self.buffer = bytearray()
        self.rejected = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        frames = []
        for byte in chunk:
            self.buffer.append(byte)
            while len(self.buffer) >= 3:
                if self.buffer[:3] != b"\xdc\x5a\x5c":
                    del self.buffer[0]
                    continue
                if len(self.buffer) < 4:
                    break
                total = self.buffer[3] + 4
                if total not in FRAME_LENGTHS:
                    self.rejected += 1
                    del self.buffer[0]
                    continue
                if len(self.buffer) < total:
                    break
                frame = bytes(self.buffer[:total])
                if zlib.crc32(frame[:-4]) != int.from_bytes(frame[-4:], "big"):
                    self.rejected += 1
                    del self.buffer[0]
                    continue
                frames.append(frame)
                del self.buffer[:total]
        return frames


def decode(frame: bytes) -> Telemetry | None:
    # Identity: family six and Leaperkim's zero high-version byte. Subtype
    # extensions are not required to decode these common telemetry fields.
    firmware = int.from_bytes(frame[28:30], "big")
    if firmware // 1000 != 6 or frame[30] != 0:
        return None
    return Telemetry(
        voltage_V=int.from_bytes(frame[4:6], "big") / 100,
        speed_kmh=int.from_bytes(frame[6:8], "big", signed=True) / 10,
        pwm_percent=int.from_bytes(frame[34:36], "big") / 100,
        firmware_word=firmware,
    )


def decode_settings(frame: bytes) -> dict[str, int | None] | None:
    if frame[46] != 8 or len(frame) - 4 <= 68:
        return None
    return {name: frame[offset] if frame[offset] <= 100 else None
            for name, offset in (("pedal_sensitivity", 50), ("dynamic_assist", 66),
                                 ("pedal_dip_compensation", 68))}
