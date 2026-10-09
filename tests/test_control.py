"""Preset control lifecycle through application actions and protocol input."""
from preset_fixture import save_preset

import unittest
import zlib

from eucwatch import Application, ManualClock
from eucwatch.recording import Replay


def settings_frame(sensitivity=31, assist=26, dip=10, subtype=8):
    frame = bytearray(71)
    frame[:4] = bytes.fromhex("dc5a5c47")
    frame[4:6] = (13500).to_bytes(2, "big")
    frame[6:8] = (250).to_bytes(2, "big", signed=True)
    frame[28:30] = (6010).to_bytes(2, "big")
    frame[46] = subtype
    frame[50], frame[66], frame[68] = sensitivity, assist, dip
    return bytes(frame) + zlib.crc32(frame).to_bytes(4, "big")


class ControlTests(unittest.TestCase):
    def prepared(self, **options):
        clock = ManualClock()
        app = Application(clock=clock, **options)
        save_preset(app, slot=1, name="Road", pedal_sensitivity=31, dynamic_assist=26)
        app.action("simulator_configure", speed_kmh=25)
        app.action("simulator_start")
        return app, clock

    def test_one_tap_while_moving_returns_dashboard_and_two_settings_frames_confirm(self):
        app, clock = self.prepared()
        app.action("swipe", direction="left")
        state = app.action("preset_apply", slot=1)
        self.assertEqual(state["screen"], "dashboard")
        self.assertEqual(state["preset_attempt"]["status"], "confirming")
        self.assertEqual(state["feedback"], "Road · Applying")
        self.assertIsNone(state["confirmed_preset"])
        clock.advance(0.2)
        self.assertTrue(app.view()["preset_attempt"]["pending"])
        clock.advance(0.2)
        state = app.view()
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertEqual(state["preset_attempt"]["status"], "Confirmed")
        self.assertEqual(state["confirmed_preset"]["slot"], 1)

    def test_verified_packets_are_serial_and_omitted_dip_sends_no_write(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        state = app.action("preset_apply", slot=1)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["packet_hex"], "4c6441700f01028080801ff753d033")
        clock.advance(0.1)
        app.action("command_result", attempt=state["preset_attempt"]["id"], session=state["session"], index=0, success=True)
        self.assertEqual(len(output), 2)
        self.assertEqual(output[1]["packet_hex"], "4c6441701f0102808080808080808080808080808080808080801aba3c7b2f")
        clock.advance(0.1)
        app.action("command_result", attempt=state["preset_attempt"]["id"], session=state["session"], index=1, success=True)
        self.assertEqual(len(output), 2)
        self.assertEqual(app.view()["preset_attempt"]["submitted_s"], 0.2)
        self.assertIsNone(app.view()["confirmed_preset"])

    def test_pending_extra_taps_are_discarded_and_stale_or_unconfigured_selection_is_rejected(self):
        app, clock = self.prepared()
        first = app.action("preset_apply", slot=1)
        second = app.action("preset_apply", slot=2)
        self.assertEqual(first["preset_attempt"]["id"], second["preset_attempt"]["id"])
        self.assertEqual(second["preset_attempt"]["slot"], 1)
        self.assertEqual(len([e for e in second["command_events"] if e["event"] == "submission"]), 2)
        app.action("simulator_configure", traffic="paused")
        clock.advance(1)
        with self.assertRaises(ValueError):
            app.action("preset_apply", slot=1)
        self.assertFalse(app.view()["preset_attempt"]["pending"])
        app.action("simulator_emit")
        with self.assertRaises(ValueError):
            app.action("preset_apply", slot=2)

    def test_confirmation_requires_two_consecutive_all_matching_frames_and_corruption_is_not_evidence(self):
        app, clock = self.prepared()
        app.action("simulator_configure", traffic="paused")
        app.action("preset_apply", slot=1)
        session = app.view()["session"]
        for elapsed, frame in ((0.1, settings_frame()), (0.1, settings_frame(assist=27)), (0.1, settings_frame())):
            clock.advance(elapsed)
            app.receive(session, frame)
            self.assertIsNone(app.view()["confirmed_preset"])
        corrupt = bytearray(settings_frame())
        corrupt[66] ^= 1
        clock.advance(0.1)
        app.receive(session, bytes(corrupt))
        self.assertIsNone(app.view()["confirmed_preset"])
        app.receive(session, settings_frame())
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")

    def test_missing_mismatched_and_partial_readbacks_timeout_with_known_field_states(self):
        for scenario, expected in (("missing", "Not confirmed"), ("mismatch", "Not confirmed"), ("partial", "Partially applied")):
            with self.subTest(scenario=scenario):
                app, clock = self.prepared()
                app.action("simulator_configure", control_readback=scenario)
                app.action("preset_apply", slot=1)
                for _ in range(50):
                    clock.advance(0.2)
                    app.tick()
                state = app.view()
                self.assertFalse(state["preset_attempt"]["pending"])
                self.assertEqual(state["preset_attempt"]["status"], expected)
                self.assertEqual(state["preset_attempt"]["reason"], "Confirmation timeout")
                fields = state["preset_attempt"]["fields"]
                self.assertEqual(fields["pedal_sensitivity"]["state"], "unknown" if scenario == "missing" else "mismatched" if scenario == "mismatch" else "confirmed")
                if scenario == "partial":
                    self.assertEqual(fields["dynamic_assist"]["state"], "unknown")

    def test_pre_ack_cached_and_partial_pre_submission_frames_cannot_confirm(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        app.action("simulator_configure", traffic="paused")
        # Actual settings matching the request before the request are only cache.
        app.receive(app.view()["session"], settings_frame())
        state = app.action("preset_apply", slot=1)
        attempt, session = state["preset_attempt"]["id"], state["session"]
        clock.advance(0.1)
        app.receive(session, settings_frame())
        self.assertTrue(all(f["state"] == "unknown" for f in app.view()["preset_attempt"]["fields"].values()))
        app.action("command_result", attempt=attempt, session=session, index=0, success=True)
        clock.advance(0.1)
        app.receive(session, settings_frame())
        clock.advance(0.1)
        app.receive(session, settings_frame())
        self.assertIsNone(app.view()["confirmed_preset"])
        frame = settings_frame()
        app.receive(session, frame[:40])
        clock.advance(0.1)
        app.action("command_result", attempt=attempt, session=session, index=1, success=True)
        clock.advance(0.1)
        app.receive(session, frame[40:])
        self.assertIsNone(app.view()["confirmed_preset"])
        app.receive(session, frame)
        self.assertIsNone(app.view()["confirmed_preset"])
        clock.advance(0.1)
        app.receive(session, frame)
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")

    def test_partial_evidence_then_transport_failure_stops_remaining_writes(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        save_preset(app, slot=1, pedal_dip_compensation=11)
        app.action("simulator_configure", traffic="paused")
        state = app.action("preset_apply", slot=1)
        attempt, session = state["preset_attempt"]["id"], state["session"]
        clock.advance(0.1)
        app.action("command_result", attempt=attempt, session=session, index=0, success=True)
        for _ in range(2):
            clock.advance(0.1)
            app.receive(session, settings_frame(assist=25))
        state = app.action("command_result", attempt=attempt, session=session, index=1, success=False, error="Second write failed")
        self.assertEqual(state["preset_attempt"]["status"], "Partially applied")
        self.assertEqual(state["preset_attempt"]["fields"]["pedal_sensitivity"]["state"], "confirmed")
        self.assertEqual(state["preset_attempt"]["fields"]["dynamic_assist"]["state"], "unknown")
        self.assertEqual(len(output), 2)
        clock.advance(0.1)
        app.receive(session, settings_frame(dip=11))
        self.assertEqual(app.view()["preset_attempt"]["status"], "Partially applied")
        self.assertEqual(app.view()["actual_settings"]["pedal_dip_compensation"], 11)
        self.assertEqual(len(output), 2)

    def test_submission_is_bounded_and_late_receipts_cannot_continue_writes(self):
        app, clock = self.prepared()
        app.action("simulator_configure", control_submission="hang")
        first = app.action("preset_apply", slot=1)
        for _ in range(25):
            clock.advance(0.2)
            app.tick()
        state = app.view()
        self.assertEqual(state["preset_attempt"]["reason"], "Submission timeout")
        self.assertFalse(state["preset_attempt"]["pending"])
        app.action("command_result", attempt=first["preset_attempt"]["id"], session=first["session"], index=0, success=True)
        self.assertEqual(len([e for e in app.view()["command_events"] if e["event"] == "submission"]), 1)

    def test_delayed_readback_preserves_timeout_and_retry_requires_a_fresh_explicit_selection(self):
        app, clock = self.prepared()
        app.action("simulator_configure", control_delay_s=12)
        first = app.action("preset_apply", slot=1)
        for _ in range(65):
            clock.advance(0.2)
            app.tick()
        state = app.view()
        self.assertEqual(state["preset_attempt"]["status"], "Not confirmed")
        self.assertEqual(state["actual_settings"]["dynamic_assist"], 26)
        self.assertIsNone(state["confirmed_preset"])
        self.assertEqual(len([e for e in state["command_events"] if e["event"] == "submission"]), 2)
        app.action("simulator_configure", control_delay_s=0)
        retried = app.action("preset_apply", slot=1)
        self.assertGreater(retried["preset_attempt"]["id"], first["preset_attempt"]["id"])
        for _ in range(2):
            clock.advance(0.2)
            app.tick()
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")

    def test_disconnect_old_sessions_definition_changes_and_divergence_remove_confirmation(self):
        app, clock = self.prepared()
        first = app.action("preset_apply", slot=1)
        state = app.action("disconnect")
        self.assertFalse(state["preset_attempt"]["pending"])
        app.receive(first["session"], settings_frame())
        self.assertIsNone(app.view()["actual_settings"])
        state = app.action("connect")
        app.receive(first["session"], settings_frame())
        self.assertFalse(app.view()["fresh"])
        app.action("simulator_emit")
        app.action("preset_apply", slot=1)
        for _ in range(2):
            clock.advance(0.1)
            app.receive(state["session"], settings_frame())
        self.assertIsNotNone(app.view()["confirmed_preset"])
        clock.advance(0.1)
        app.receive(state["session"], settings_frame(assist=27))
        self.assertIsNone(app.view()["confirmed_preset"])
        app.action("preset_apply", slot=1)
        state = save_preset(app, slot=1, name="Renamed")
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertEqual(state["preset_attempt"]["reason"], "Saved configuration changed")
        self.assertIsNone(state["confirmed_preset"])

    def test_optional_dip_is_third_verified_packet_and_transport_receipts_never_confirm(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        save_preset(app, slot=1, pedal_dip_compensation=11)
        state = app.action("preset_apply", slot=1)
        for index in range(3):
            self.assertEqual(len(output), index + 1)
            clock.advance(0.1)
            app.action("command_result", attempt=state["preset_attempt"]["id"], session=state["session"], index=index, success=True)
        self.assertEqual(output[2]["packet_hex"], "4c6441702101028080808080808080808080808080808080808080800b672ed25c")
        self.assertIsNone(app.view()["confirmed_preset"])
        self.assertEqual(app.view()["preset_attempt"]["status"], "confirming")

    def test_delayed_submission_starts_confirmation_limit_after_all_writes_complete(self):
        app, clock = self.prepared()
        app.action("simulator_configure", control_submission_delay_s=1, control_readback="missing")
        app.action("preset_apply", slot=1)
        for _ in range(50):
            clock.advance(0.2)
            app.tick()
        state = app.view()
        self.assertTrue(state["preset_attempt"]["pending"])
        self.assertAlmostEqual(state["preset_attempt"]["submitted_s"], 2)
        for _ in range(10):
            clock.advance(0.2)
            app.tick()
        state = app.view()
        self.assertEqual(state["preset_attempt"]["reason"], "Confirmation timeout")
        self.assertAlmostEqual(state["preset_attempt"]["finished_s"], 12)

    def test_simulated_failure_stops_unsent_optional_write_without_rollback_or_retry(self):
        app, clock = self.prepared()
        save_preset(app, slot=1, pedal_dip_compensation=11)
        app.action("simulator_configure", control_submission="fail", control_fail_after=1)
        state = app.action("preset_apply", slot=1)
        self.assertEqual(state["preset_attempt"]["status"], "Not confirmed")
        for _ in range(60):
            clock.advance(0.2)
            app.tick()
        state = app.view()
        submissions = [row for row in state["command_events"] if row["event"] == "submission"]
        self.assertEqual([row["field"] for row in submissions], ["pedal_sensitivity", "dynamic_assist"])
        self.assertEqual(state["actual_settings"], {"pedal_sensitivity": 31, "dynamic_assist": 25, "pedal_dip_compensation": 10})
        self.assertEqual(state["preset_attempt"]["status"], "Not confirmed")
        self.assertIsNone(state["confirmed_preset"])

    def test_stale_gap_terminates_before_new_frame_and_configuration_edit_stops_unsent_writes(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        first = app.action("preset_apply", slot=1)
        clock.advance(1)
        app.receive(first["session"], settings_frame())
        self.assertEqual(app.view()["preset_attempt"]["reason"], "Telemetry is stale or disconnected")
        self.assertTrue(app.view()["fresh"])
        app.action("command_result", attempt=first["preset_attempt"]["id"], session=first["session"], index=0, success=True)
        self.assertEqual(len(output), 1)
        second = app.action("preset_apply", slot=1)
        app.action("preset_clear", slot=1)
        app.action("command_result", attempt=second["preset_attempt"]["id"], session=second["session"], index=0, success=True)
        self.assertEqual(app.view()["preset_attempt"]["reason"], "Saved configuration changed")
        self.assertEqual(len(output), 2)
        self.assertIsNone(app.view()["confirmed_preset"])

    def test_replay_rejects_new_requests_and_never_replays_recorded_submissions(self):
        app, _clock = self.prepared()
        replay = Replay.from_text('{"schema":1,"event":"submission","sequence":0,"session":4,"source":"simulator","receipt_elapsed_s":0,"packet_hex":"4c6441700f01028080801ff753d033"}\n')
        app.action("replay_start", recording=replay)
        app.action("replay_step")
        with self.assertRaises(ValueError):
            app.action("preset_apply", slot=1)
        self.assertEqual(app.view()["command_events"], [])

    def test_duplicate_and_out_of_order_receipts_do_not_dispatch_extra_writes(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        state = app.action("preset_apply", slot=1)
        common = {"attempt": state["preset_attempt"]["id"], "session": state["session"], "success": True}
        app.action("command_result", **common, index=1)
        self.assertEqual(len(output), 1)
        clock.advance(0.1)
        app.action("command_result", **common, index=0)
        app.action("command_result", **common, index=0)
        self.assertEqual(len(output), 2)
        app.action("command_result", **common, index=1)
        app.action("command_result", **common, index=1)
        self.assertEqual(len(output), 2)
        self.assertEqual(app.view()["preset_attempt"]["status"], "confirming")

    def test_duplicate_receipt_does_not_discard_a_post_submission_settings_fragment(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        app.action("simulator_configure", traffic="paused")
        state = app.action("preset_apply", slot=1)
        common = {"attempt": state["preset_attempt"]["id"], "session": state["session"], "success": True}
        app.action("command_result", **common, index=0)
        app.action("command_result", **common, index=1)
        clock.advance(0.1)
        frame = settings_frame()
        app.receive(state["session"], frame[:40])
        app.action("command_result", **common, index=1)
        app.receive(state["session"], frame[40:])
        self.assertIsNone(app.view()["confirmed_preset"])
        clock.advance(0.1)
        app.receive(state["session"], frame)
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")

    def test_suspend_cancels_pending_submission_and_late_receipt_never_resumes_it(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        state = app.action("preset_apply", slot=1)
        clock.advance(60, suspended=True)
        resumed = app.view()
        self.assertFalse(resumed["preset_attempt"]["pending"])
        self.assertGreater(resumed["session"], state["session"])
        app.action("command_result", attempt=state["preset_attempt"]["id"], session=state["session"], index=0, success=True)
        self.assertEqual(len(output), 1)
        app.receive(state["session"], settings_frame())
        self.assertIsNone(app.view()["confirmed_preset"])

    def test_command_receipts_require_valid_explicit_metadata(self):
        app, _clock = self.prepared(command_output=lambda _row: None)
        state = app.action("preset_apply", slot=1)
        fields = {"attempt": state["preset_attempt"]["id"], "session": state["session"], "index": 0, "success": True}
        for wrong in ({"index": True}, {"index": -1}, {"index": 3}, {"attempt": "1"}, {"session": None}, {"success": 1}, {"error": []}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                app.action("command_result", **{**fields, **wrong})
        self.assertEqual(len([row for row in app.view()["command_events"] if row["event"] == "submission"]), 1)


if __name__ == "__main__":
    unittest.main()
