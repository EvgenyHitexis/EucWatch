"""Raw recording evidence and replay at the public application boundary."""

import json
import tempfile
import unittest
import asyncio
import threading
from pathlib import Path

from eucwatch.recording import Recorder, Replay
from eucwatch import Application, ManualClock

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
    async def test_replay_of_disconnected_resume_does_not_invent_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(Path(directory)/'resume.jsonl')
            clock = ManualClock()
            app = Application(clock=clock,event_sink=recorder.record)
            app.action('disconnect')
            clock.advance(60,suspended=True)
            self.assertFalse(app.view()['connected'])
            await recorder.close()
            replay = Replay.load(recorder.path)
            restored = Application(clock=ManualClock())
            restored.action('replay_start',recording=replay)
            for _ in replay.rows:
                restored.action('replay_step')
            self.assertFalse(restored.view()['connected'])
            self.assertFalse(restored.view()['fresh'])

    async def test_captured_application_states_replay_equivalently_with_corruption_and_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(Path(directory) / 'capture.jsonl')
            clock = ManualClock()
            app = Application(clock=clock, event_sink=recorder.record)
            session = app.action('connect')['session']
            expected = []
            for line in FIXTURE.read_text().splitlines():
                row = json.loads(line)
                clock.advance(row['receipt_elapsed_s'] - clock.elapsed)
                app.receive(session,bytes.fromhex(row['raw_hex']))
                expected.append(app.view()['dashboard'])
            await recorder.close()
            rows = [json.loads(line) for line in recorder.path.read_text().splitlines()]
            self.assertEqual([r['raw_hex'] for r in rows if r['event']=='notification'],
                [json.loads(line)['raw_hex'] for line in FIXTURE.read_text().splitlines()])
            replay = Replay.load(recorder.path)
            replay_app = Application(clock=ManualClock())
            replay_app.action('replay_start',recording=replay)
            observed = []
            for row in replay.rows:
                state = replay_app.action('replay_step')
                if row['event']=='notification':
                    observed.append(state['dashboard'])
            self.assertEqual(observed,expected)
            self.assertEqual(state['diagnostics']['valid_frames'],3)
            with self.assertRaises(ValueError):
                replay_app.action('simulator_emit')

    async def test_cancelled_drain_finishes_earlier_write_before_close_flushes_later_events(self):
        with tempfile.TemporaryDirectory() as directory:
            entered, release = threading.Event(), threading.Event()
            def writer(path, lines):
                if json.loads(lines[0])['sequence']==0:
                    entered.set()
                    release.wait(3)
                with path.open('a') as output:
                    output.writelines(lines)
            recorder = Recorder(Path(directory)/'ordered.jsonl',writer=writer)
            recorder.record('intent',session=1,source='simulator',receipt_elapsed_s=0)
            first = asyncio.create_task(recorder.drain())
            try:
                async with asyncio.timeout(2):
                    while not entered.is_set():
                        await asyncio.sleep(.01)
                recorder.record('intent',session=1,source='simulator',receipt_elapsed_s=1)
                first.cancel()
                close = asyncio.create_task(recorder.close())
                await asyncio.sleep(.05)
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                await close
                rows = [json.loads(line) for line in recorder.path.read_text().splitlines()]
                self.assertEqual([row['sequence'] for row in rows],[0,1])
                self.assertEqual(recorder.status()['written'],2)
            finally:
                release.set()
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
