"""Bounded feasibility evidence, not an application or general wheel parser.

The only hardware operation is --scan: advertise discovery, without connecting.
All packet and command-lifecycle checks use synthetic/source-fixture inputs.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
import zlib

CHUNKS = [bytes.fromhex(s) for s in (
    "dc5a5c53397afffe0aa400000df10000000a0b3d",
    "0e0e0000037a035217730064000e00b480c80000",
    "808080808080058080808080800ff30ff50ff50f",
    "f50ff50fef0ff20ff30ff30ff30ff30fed0ff30f",
    "f40ff5378c5145",
)]
FRAME = b"".join(CHUNKS)
CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"


class Assembler:
    """Accept only the evidenced 83+4-byte fixture format; bounded recovery."""

    def __init__(self):
        self.buffer = bytearray()
        self.rejected = 0

    def feed(self, chunk):
        frames = []
        for byte in chunk:
            self.buffer.append(byte)
            while self.buffer:
                if len(self.buffer) < 3:
                    break
                if self.buffer[:3] != b"\xdc\x5a\x5c":
                    del self.buffer[0]
                    continue
                if len(self.buffer) < 4:
                    break
                if self.buffer[3] != 83:
                    self.rejected += 1
                    del self.buffer[0]
                    continue
                if len(self.buffer) < 87:
                    break
                frame = bytes(self.buffer[:87])
                if zlib.crc32(frame[:83]) != int.from_bytes(frame[83:], "big"):
                    self.rejected += 1
                    del self.buffer[0]
                    continue
                frames.append(frame)
                del self.buffer[:87]
            assert len(self.buffer) < 87
        return frames


def decode(frame):
    return {
        "firmware_word": int.from_bytes(frame[28:30], "big"),
        "voltage_V": int.from_bytes(frame[4:6], "big") / 100,
        "speed_kmh": int.from_bytes(frame[6:8], "big", signed=True) / 10,
        "pwm_percent": int.from_bytes(frame[34:36], "big") / 100,
    }


class Core:
    """Small demonstrator of clock/session ownership; no BLE write path.

    One-second expiry and 100ms suspend detection are probe constants, not
    product policy. 'submitted' is an in-memory fake transport spy.
    """

    def __init__(self, clock):
        self.clock = clock
        self.previous = clock()
        self.epoch = 0
        self.parser = Assembler()
        self.connected = True
        self.last_valid = None
        self.values = None
        self.pending = []
        self.submitted = []
        self.seen = set()
        self.frames = 0
        self.resume_events = 0

    def invalidate(self):
        self.epoch += 1
        self.pending.clear()
        self.last_valid = None
        self.parser = Assembler()

    def tick(self):
        boot, mono = self.clock()
        boot_gap, mono_gap = boot - self.previous[0], mono - self.previous[1]
        if boot_gap - mono_gap > 0.1 or mono_gap > 1.0:
            self.resume_events += 1
            self.invalidate()
        self.previous = boot, mono
        self.pending = [p for p in self.pending if boot < p[2]]

    def receive(self, epoch, chunk):
        self.tick()
        if not self.connected or epoch != self.epoch:
            return
        for frame in self.parser.feed(chunk):
            self.values = decode(frame)
            self.last_valid = self.clock()[0]
            self.frames += 1

    def fresh(self):
        self.tick()
        return (self.connected and self.last_valid is not None
                and self.clock()[0] - self.last_valid < 1.0)

    def disconnect(self):
        self.connected = False
        self.invalidate()

    def reconnect(self):
        self.connected = True
        self.invalidate()

    def enqueue_fake_intent(self, key):
        self.tick()
        if self.fresh() and key not in self.seen:
            self.seen.add(key)
            self.pending.append((key, self.epoch, self.clock()[0] + 1.0))

    def dispatch_fake_intents(self):
        self.tick()
        if self.fresh():
            self.submitted.extend(key for key, epoch, _ in self.pending
                                  if epoch == self.epoch)
        self.pending.clear()


def clocks():
    return time.clock_gettime(time.CLOCK_BOOTTIME), time.monotonic()


def versions():
    return {
        "python": platform.python_version(), "kernel": platform.release(),
        "uid": os.getuid(),
        "packages": {name: importlib.metadata.version(name) for name in
                     ("bleak", "dbus-fast", "aiohttp")},
        "boottime_available": hasattr(time, "CLOCK_BOOTTIME"),
    }


def offline(output):
    expected = {"firmware_word": 6003, "voltage_V": 147.14,
                "speed_kmh": -0.2, "pwm_percent": 1.8}
    assert decode(FRAME) == expected
    for split in range(1, len(FRAME)):
        parser = Assembler()
        assert parser.feed(FRAME[:split]) == []
        assert parser.feed(FRAME[split:]) == [FRAME]
    parser = Assembler()
    assert [f for b in FRAME for f in parser.feed(bytes([b]))] == [FRAME]
    assert Assembler().feed(FRAME * 3) == [FRAME] * 3
    for pos in range(len(FRAME)):
        for bit in range(8):
            corrupt = bytearray(FRAME)
            corrupt[pos] ^= 1 << bit
            assert Assembler().feed(corrupt + FRAME) == [FRAME]
    assert Assembler().feed(b"\xdc\x5a\x5c\xff" + b"x" * 10000 + FRAME) == [FRAME]

    # Save raw callback boundaries and virtual host receipt times before parsing.
    now = [0.0, 0.0]
    core = Core(lambda: tuple(now))
    rows, states = [], []
    corrupt = bytearray(FRAME)
    corrupt[4] ^= 1
    chunks = [*CHUNKS, bytes(corrupt), b"noise", FRAME, *CHUNKS]
    times = [i * 0.02 for i in range(7)] + [2.0, 2.02, 2.04, 2.06, 2.08, 2.10]
    assert len(times) == len(chunks)
    with (output / "fixture-recording.jsonl").open("w") as handle:
        for seq, (stamp, chunk) in enumerate(zip(times, chunks)):
            row = {"schema": 1, "source": "upstream-fixture/synthetic-timing",
                   "session": "fixture-1", "sequence": seq,
                   "characteristic": CHARACTERISTIC, "receipt_elapsed_s": stamp,
                   "raw_hex": chunk.hex()}
            handle.write(json.dumps(row) + "\n")
            rows.append(row)
            now[:] = [stamp, stamp]
            core.tick()
            core.receive(core.epoch, chunk)
            states.append((core.frames, core.fresh(), core.values))
    replay = Core(lambda: tuple(now))
    now[:] = [0.0, 0.0]
    replay.previous = (0.0, 0.0)
    loaded = [json.loads(line) for line in (output / "fixture-recording.jsonl").read_text().splitlines()]
    assert loaded == rows
    replay_states = []
    for row in loaded:
        stamp = row["receipt_elapsed_s"]
        now[:] = [stamp, stamp]
        replay.tick()
        replay.receive(replay.epoch, bytes.fromhex(row["raw_hex"]))
        replay_states.append((replay.frames, replay.fresh(), replay.values))
    assert replay_states == states
    assert core.frames == 3

    # Virtual suspend: boottime advances, monotonic does not.
    now[:] = [0.0, 0.0]
    core = Core(lambda: tuple(now))
    core.receive(core.epoch, FRAME)
    core.enqueue_fake_intent("before-suspend")
    assert len(core.pending) == 1
    old_epoch = core.epoch
    now[:] = [60.0, 0.01]
    assert not core.fresh()
    core.dispatch_fake_intents()
    assert core.submitted == [] and core.pending == []
    core.receive(old_epoch, FRAME)  # Late callback cannot restore freshness.
    assert not core.fresh()
    core.receive(core.epoch, FRAME)
    assert core.fresh()
    core.enqueue_fake_intent("before-disconnect")
    assert len(core.pending) == 1
    old_epoch = core.epoch
    core.disconnect()
    core.reconnect()
    core.receive(old_epoch, FRAME)
    core.dispatch_fake_intents()
    assert not core.fresh() and core.submitted == []
    core.receive(core.epoch, FRAME)
    core.enqueue_fake_intent("new-explicit-request")
    core.enqueue_fake_intent("new-explicit-request")
    core.dispatch_fake_intents()
    assert core.submitted == ["new-explicit-request"]
    core.enqueue_fake_intent("expires")
    now[:] = [60.6, 0.61]
    core.tick()
    now[:] = [61.2, 1.21]
    core.receive(core.epoch, FRAME)
    core.dispatch_fake_intents()
    assert core.submitted == ["new-explicit-request"]

    result = {"status": "pass", "fixture": expected, "split_positions": 86,
              "single_bit_corruption_recovery_cases": 696,
              "recorded_notifications": len(rows), "replayed_valid_frames": 3,
              "raw_bytes_boundaries_timestamps_preserved": True,
              "replay_state_equivalent": True,
              "synthetic_suspend_stale_and_intent_cancel": True,
              "synthetic_disconnect_late_callback_and_dedup": True,
              "actual_system_suspend_tested": False}
    (output / "offline.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


async def scan(output):
    from bleak import BleakScanner

    count = 0
    def detected(_device, _advertisement):
        nonlocal count
        count += 1

    started = time.monotonic()
    scanner = BleakScanner(detected)
    try:
        async with scanner:
            await asyncio.sleep(5)
        result = {"status": "pass", "duration_s": time.monotonic() - started,
                  "advertisement_callbacks": count,
                  "unique_devices": len(scanner.discovered_devices),
                  "backend": str(scanner.backend_id), "connected": False,
                  "identities_retained": False}
    except Exception as exc:
        result = {"status": "fail", "error_type": type(exc).__name__, "error": str(exc)}
    (output / "scan.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "environment.json").write_text(json.dumps(versions(), indent=2) + "\n")
    print(json.dumps(asyncio.run(scan(args.output)) if args.scan else offline(args.output), indent=2))
