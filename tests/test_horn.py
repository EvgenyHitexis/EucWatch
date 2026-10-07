"""Modeled button requests at the public Application boundary; no audio claims."""

import unittest
import zlib
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.recording import Replay


class HornTests(unittest.TestCase):
    def connected(self, **options):
        clock = ManualClock()
        app = Application(clock=clock, **options)
        app.action("simulator_start")
        return app, clock

    def test_fresh_awake_press_submits_one_researched_packet_with_brief_sent_feedback(self):
        app, clock = self.connected()
        before = app.view()["vibration"]["events"]
        state = app.action("button_down")
        requests = [row for row in state["command_events"] if row.get("kind") == "horn" and row["event"] == "submission"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["packet_hex"], "4c6b41700e0080808001ca87e66f")
        packet = bytes.fromhex(requests[0]["packet_hex"])
        self.assertEqual(zlib.crc32(packet[:-4]), int.from_bytes(packet[-4:], "big"))
        self.assertEqual(state["horn_feedback"]["message"], "Horn request sent")
        self.assertEqual(state["feedback"], "Horn request sent")
        self.assertEqual(state["vibration"]["events"], before)
        clock.advance(2)
        self.assertIsNone(app.view()["horn_feedback"])
        self.assertNotEqual(app.view()["feedback"], "Horn request sent")

    def test_unavailable_presses_show_specific_reasons_and_are_discarded(self):
        cases = ("initial", "no-data", "stale", "disconnected", "preset", "recovery")
        for case in cases:
            with self.subTest(case=case):
                clock = ManualClock()
                app = Application(clock=clock)
                if case == "no-data":
                    app.action("connect")
                elif case != "initial":
                    app.action("simulator_start")
                if case == "stale":
                    app.action("simulator_configure", traffic="paused")
                    clock.advance(1)
                elif case == "disconnected":
                    app.action("disconnect")
                elif case == "preset":
                    app.action("preset_begin", slot=1)
                    app.action("preset_update", pedal_sensitivity=30, dynamic_assist=25)
                    app.action("preset_save")
                    app.action("preset_apply", slot=1)
                elif case == "recovery":
                    app.action("swipe", direction="down")
                    app.action("sleep")
                    app.action("button_down")
                    clock.advance(30)
                    app.action("button_hold")
                    app.action("button_up")
                state = app.action("button_down")
                self.assertEqual([row for row in state["command_events"] if row.get("kind") == "horn"], [])
                expected = "Horn unavailable: recovery mode" if case == "recovery" else "Horn unavailable: preset applying" if case == "preset" else "Horn unavailable: connection unavailable"
                self.assertEqual(state["horn_feedback"]["message"], expected)
                app.action("button_up")
                app.action("connect")
                app.action("simulator_emit")
                self.assertEqual([row for row in app.view()["command_events"] if row.get("kind") == "horn"], [])

    def test_whole_sleeping_cycle_is_wake_only_and_holding_never_repeats(self):
        app, clock = self.connected()
        app.action("swipe", direction="down")
        app.action("sleep")
        for name in ("button_down", "button_down", "button_hold", "button_up", "button_up"):
            app.action(name)
        self.assertTrue(app.view()["awake"])
        self.assertEqual(app.view()["command_events"], [])
        app.action("button_down")
        for _ in range(20):
            app.action("button_down")
            clock.advance(0.2)
            app.action("button_hold")
        app.action("button_up")
        app.action("button_up")
        submissions = [row for row in app.view()["command_events"] if row["event"] == "submission"]
        self.assertEqual(len(submissions), 1)
        app.action("button_down")
        self.assertEqual(len([row for row in app.view()["command_events"] if row["event"] == "submission"]), 2)

    def test_blocked_held_cycle_does_not_play_after_preset_confirmation(self):
        app, clock = self.connected()
        app.action("preset_begin", slot=1)
        app.action("preset_update", pedal_sensitivity=30, dynamic_assist=25)
        app.action("preset_save")
        app.action("preset_apply", slot=1)
        app.action("button_down")
        for _ in range(2):
            clock.advance(0.2)
            app.tick()
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")
        app.action("button_hold")
        app.action("button_down")
        app.action("button_up")
        self.assertEqual([row for row in app.view()["command_events"] if row.get("kind") == "horn"], [])
        state = app.action("button_down")
        self.assertEqual(state["horn_feedback"]["message"], "Horn request sent")

    def test_output_adapter_reports_submission_result_without_audio_claim_or_retry(self):
        output = []
        app, clock = self.connected(command_output=output.append)
        state = app.action("button_down")
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["kind"], "horn")
        self.assertEqual(output[0]["session"], state["session"])
        self.assertEqual(output[0]["packet_hex"], "4c6b41700e0080808001ca87e66f")
        self.assertEqual(state["horn_feedback"]["message"], "Horn request submitting")
        self.assertEqual(len([row for row in state["command_events"] if row["event"] == "result"]), 0)
        state = app.action("horn_result", request=output[0]["request"], session=output[0]["session"], success=False, error="Controlled write failure")
        self.assertEqual(state["horn_feedback"]["message"], "Horn request failed: Controlled write failure")
        for _ in range(5):
            clock.advance(0.2)
            app.tick()
        app.action("button_up")
        self.assertEqual(len(output), 1)
        app.action("button_down")
        state = app.action("horn_result", request=output[1]["request"], session=output[1]["session"], success=True)
        self.assertEqual(state["horn_feedback"]["message"], "Horn request sent")
        self.assertNotIn("sound", state["horn_feedback"]["message"].lower())

    def test_old_session_transport_result_and_suspend_never_restore_a_request(self):
        output = []
        app, clock = self.connected(command_output=output.append)
        app.action("button_down")
        old = output[0]
        app.action("disconnect")
        state = app.action("horn_result", request=old["request"], session=old["session"], success=True)
        self.assertIsNone(state["horn_feedback"])
        app.action("connect")
        app.action("simulator_emit")
        app.action("button_down")
        self.assertEqual(len(output), 1)
        app.action("button_up")
        app.action("button_down")
        self.assertEqual(len(output), 2)
        clock.advance(60, suspended=True)
        state = app.view()
        self.assertFalse(state["button"]["down"])
        app.action("horn_result", request=output[1]["request"], session=output[1]["session"], success=True)
        self.assertIsNone(app.view()["horn_feedback"])
        self.assertEqual(len(output), 2)

    def test_read_only_replay_has_no_horn_capability_even_with_fresh_parsed_data(self):
        fixture = Path(__file__).resolve().parents[1] / "experiments/laptop-feasibility/evidence/fixture-recording.jsonl"
        app = Application(clock=ManualClock())
        replay = Replay.load(fixture)
        app.action("replay_start", recording=replay)
        for _ in range(6):
            app.action("replay_step")
        self.assertTrue(app.view()["fresh"])
        state = app.action("button_down")
        self.assertEqual(state["command_events"], [])
        self.assertEqual(state["horn_feedback"]["message"], "Horn unavailable: connection unavailable")
        with self.assertRaises(ValueError):
            app.action("horn_request")

    def test_callback_failure_is_visible_without_retry_and_press_works_on_each_menu(self):
        def unavailable(_row):
            raise OSError("Controlled adapter unavailable")
        app, _clock = self.connected(command_output=unavailable)
        state = app.action("button_down")
        self.assertEqual(state["horn_feedback"]["message"], "Horn request failed: Controlled adapter unavailable")
        self.assertEqual(len([row for row in state["command_events"] if row["event"] == "submission"]), 1)
        app.action("button_hold")
        app.action("button_up")
        self.assertEqual(len([row for row in app.view()["command_events"] if row["event"] == "submission"]), 1)
        app, _clock = self.connected()
        for action in (("swipe", {"direction": "left"}), ("swipe", {"direction": "down"}), ("alerts_begin", {})):
            app.action(action[0], **action[1])
            screen = app.view()["screen"]
            state = app.action("button_down")
            self.assertEqual(state["horn_feedback"]["message"], "Horn request sent")
            self.assertEqual(state["screen"], screen)
            app.action("button_up")
        self.assertEqual(len([row for row in app.view()["command_events"] if row["event"] == "submission"]), 3)

    def test_malformed_transport_results_cannot_create_feedback_or_submission(self):
        app, _clock = self.connected()
        for payload in ({}, {"request": True, "session": 1, "success": True}, {"request": 1, "session": "1", "success": True}, {"request": 1, "session": 1, "success": 1}, {"request": 1, "session": 1, "success": True, "error": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                app.action("horn_result", **payload)
        self.assertEqual(app.view()["command_events"], [])
        self.assertIsNone(app.view()["horn_feedback"])

    def test_duplicate_receipt_does_not_extend_feedback_and_old_receipt_cannot_replace_a_new_request(self):
        output = []
        app, clock = self.connected(command_output=output.append)
        app.action("button_down")
        first = output[0]
        app.action("horn_result", request=first["request"], session=first["session"], success=True)
        clock.advance(1)
        app.action("horn_result", request=first["request"], session=first["session"], success=True)
        self.assertEqual(app.view()["horn_feedback"]["expires_s"], 2)
        app.action("button_up")
        app.action("button_down")
        second = output[1]
        app.action("button_up")
        app.action("button_down")
        app.action("horn_result", request=second["request"], session=second["session"], success=False, error="Older write failed")
        self.assertEqual(app.view()["horn_feedback"]["message"], "Horn request submitting")
        self.assertEqual(len(output), 3)


if __name__ == "__main__":
    unittest.main()
