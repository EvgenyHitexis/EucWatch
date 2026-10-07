"""Raw recording evidence and replay at the public application boundary."""

import json
import tempfile
import unittest
from pathlib import Path

from eucwatch.recording import Recorder, Replay

FIXTURE = Path(__file__).resolve().parents[1] / (
    "experiments/laptop-feasibility/evidence/fixture-recording.jsonl"
)


class ReplayTests(unittest.TestCase):
    def test_invalid_or_reordered_recordings_are_rejected_before_replay(self):
        row = json.loads(FIXTURE.read_text().splitlines()[0])
        cases = [
            [{**row, "schema": 2}],
            [{**row, "schema": True}],
            [{**row, "raw_hex": "xx"}],
            [{**row, "raw_hex": "d"}],
            [{**row, "receipt_elapsed_s": -1}],
            [{**row, "receipt_elapsed_s": float("nan")}],
            [{**row, "session": []}],
            [{**row, "event": "command"}],
            [row, {**row, "sequence": 0}],
            [row, {**row, "sequence": 1, "receipt_elapsed_s": -0.1}],
            [row, []],
            [],
        ]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                Replay.from_text("\n".join(json.dumps(value) for value in rows))
        with self.assertRaises(ValueError):
            Replay.from_text(FIXTURE.read_text(), max_events=2)
        with self.assertRaises(ValueError):
            Replay.from_text(FIXTURE.read_text(), max_bytes=100)

    def test_sanitized_fixture_keeps_notification_order_boundaries_and_gaps(self):
        replay = Replay.load(FIXTURE)
        events = []
        while (row := replay.next_event()) is not None:
            events.append(row)
        self.assertEqual(len(events), 13)
        self.assertEqual([row["sequence"] for row in events], list(range(13)))
        self.assertEqual(events[0]["raw_hex"],
                         "dc5a5c53397afffe0aa400000df10000000a0b3d")
        self.assertEqual(events[6]["raw_hex"], "6e6f697365")
        self.assertEqual(events[6]["receipt_elapsed_s"], 0.12)
        self.assertEqual(events[7]["receipt_elapsed_s"], 2.0)
        self.assertEqual(events[0]["event"], "notification")
        self.assertTrue(replay.status()["finished"])
        self.assertEqual(replay.status()["source"], "upstream-fixture/synthetic-timing")


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_overflow_stops_capture_and_retains_queued_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            recorder = Recorder(path, max_queue=1)
            self.assertTrue(recorder.record("notification", raw_hex="dc5a"))
            self.assertFalse(recorder.record("notification", raw_hex="5c53"))
            self.assertIn("overflow", recorder.status()["error"])
            await recorder.drain()
            self.assertFalse(recorder.record("notification", raw_hex="39"))
            self.assertEqual(recorder.status()["rejected"], 2)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    async def test_storage_error_is_visible_and_future_capture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blocked"
            path.mkdir()
            recorder = Recorder(path)
            recorder.record("notification", raw_hex="dc5a")
            await recorder.close()
            self.assertIn("storage failed", recorder.status()["error"])
            self.assertEqual(recorder.status()["written"], 0)
            self.assertEqual(recorder.status()["rejected"], 1)
            self.assertFalse(recorder.record("notification", raw_hex="5c53"))

    async def test_append_only_capture_retains_corrupt_bytes_and_receipt_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            recorder = Recorder(path)
            recorder.record("transport", session=1, source="simulator",
                            receipt_elapsed_s=12.0, transition="connected")
            recorder.record("notification", session=1, source="simulator",
                            receipt_elapsed_s=12.02, characteristic="ffe1",
                            raw_hex="6e6f697365")
            await recorder.drain()
            first = path.read_bytes()
            recorder.record("notification", session=1, source="simulator",
                            receipt_elapsed_s=12.04, characteristic="ffe1",
                            raw_hex="dc5a")
            await recorder.close()
            self.assertTrue(path.read_bytes().startswith(first))
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([row["sequence"] for row in rows], [0, 1, 2])
            self.assertEqual(rows[1]["raw_hex"], "6e6f697365")
            self.assertEqual(rows[1]["receipt_elapsed_s"], 12.02)
            self.assertEqual(rows[1]["session"], 1)
            self.assertEqual(rows[1]["characteristic"], "ffe1")
            self.assertEqual(rows[1]["schema"], 1)
            self.assertTrue(rows[1]["receipt_wall_utc"].endswith("+00:00"))
            self.assertEqual(recorder.status()["written"], 3)
            self.assertIsNone(recorder.status()["error"])
