"""Wheel-owned editing through the agreed application/action/raw-frame seam."""
import unittest

from eucwatch import Application, ManualClock
from test_control import settings_frame


class PresetEditorTests(unittest.TestCase):
    def prepared(self, **options):
        clock = ManualClock()
        app = Application(clock=clock, **options)
        app.action("connect")
        app.receive(app.session, settings_frame())
        return app, clock

    def test_open_waits_for_new_complete_settings_and_seeds_external_values(self):
        app, clock = self.prepared()
        state = app.action("preset_begin", slot=2, source="watch")
        self.assertEqual(state["preset_editor"]["status"], "waiting")
        self.assertIsNone(state["preset_draft"])
        frame = settings_frame(sensitivity=44, assist=55, dip=66)
        app.receive(app.session, frame[:40])
        self.assertIsNone(app.view()["preset_draft"])
        clock.advance(.1)
        app.receive(app.session, frame[40:])
        state = app.view()
        self.assertEqual(state["preset_editor"]["status"], "ready")
        self.assertEqual(state["preset_draft"], {"id": 2, "name": "Preset 2", "configured": True,
                                               "pedal_sensitivity": 44, "dynamic_assist": 55})
        self.assertEqual(state["command_events"], [])
        self.assertFalse(state["config"]["presets"][1]["configured"])

    def open(self, app, clock, slot=1):
        app.action("preset_begin", slot=slot, source="watch")
        clock.advance(.1)
        app.receive(app.session, settings_frame())

    def test_completed_edit_writes_one_evidenced_packet_and_saves_only_selected_slot(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        self.open(app, clock, slot=3)
        before = app.view()["config"]
        state = app.action("preset_update", pedal_sensitivity=44, source="watch")
        self.assertEqual([row["packet_hex"] for row in output], ["4c6441700f01028080802c4883b125"])
        self.assertEqual(state["config"]["presets"][2]["pedal_sensitivity"], 44)
        self.assertEqual([row for row in state["config"]["presets"] if row["id"] != 3],
                         [row for row in before["presets"] if row["id"] != 3])
        self.assertEqual(state["preset_attempt"]["kind"], "editor")
        self.assertIsNone(state["preset_attempt"]["fields"]["pedal_sensitivity"]["submitted_s"])
        row = output[0]
        clock.advance(.1)
        app.action("command_result", attempt=row["attempt"], session=row["session"], index=0, success=True)
        self.assertIsNone(app.view()["confirmed_preset"])
        for _ in range(2):
            clock.advance(.1)
            app.receive(app.session, settings_frame(sensitivity=44))
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")
        self.assertIsNone(app.view()["confirmed_preset"])

    def test_cached_preopen_partial_corrupt_speed_and_old_session_cannot_open(self):
        app, clock = self.prepared()
        old = app.session
        app.receive(old, settings_frame()[:40])
        app.action("preset_begin", slot=1)
        app.receive(old, settings_frame()[40:])
        corrupt = bytearray(settings_frame()); corrupt[50] ^= 1
        for session, frame in ((old, bytes(corrupt)), (old, settings_frame(subtype=0)),
                               (old, settings_frame(dip=128)), (old - 1, settings_frame())):
            clock.advance(.1)
            app.receive(session, frame)
            self.assertIsNone(app.view()["preset_draft"])
        for _ in range(50):
            clock.advance(.1)
            app.receive(old, settings_frame(subtype=0))
        self.assertEqual(app.view()["preset_editor"]["status"], "unavailable")
        app.receive(old, settings_frame())
        self.assertIsNone(app.view()["preset_draft"])
        self.assertEqual(app.view()["command_events"], [])

    def test_invalid_unfinished_and_multi_field_adjustments_emit_nothing(self):
        app, clock = self.prepared()
        app.action("preset_begin", slot=1)
        with self.assertRaises(ValueError):
            app.action("preset_update", pedal_sensitivity=20)
        clock.advance(.1); app.receive(app.session, settings_frame())
        before = app.view()["config"]
        for change in ({"pedal_sensitivity": None}, {"pedal_sensitivity": True},
                       {"dynamic_assist": 20.5}, {"dynamic_assist": -1},
                       {"pedal_dip_compensation": 101}, {"name": ""},
                       {"name": "x" * 25}, {"id": 4},
                       {"pedal_sensitivity": 30, "dynamic_assist": 20}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                app.action("preset_update", **change)
        self.assertEqual(app.view()["config"], before)
        self.assertEqual(app.view()["command_events"], [])

    def test_all_four_slots_create_rename_include_omit_and_clear_locally(self):
        app, clock = self.prepared()
        for slot in range(1, 5):
            self.open(app, clock, slot)
            app.action("preset_save")  # Explicitly create from readback.
            app.action("preset_update", name=f"Road {slot}")
            app.action("preset_include_dip", included=True)
            self.assertEqual(app.view()["config"]["presets"][slot-1]["pedal_dip_compensation"], 10)
            app.action("preset_include_dip", included=False)
            self.assertNotIn("pedal_dip_compensation", app.view()["config"]["presets"][slot-1])
            app.action("preset_cancel")
        self.assertEqual(app.view()["command_events"], [])
        before = app.view()["config"]
        for slot in range(1, 5):
            state = app.action("preset_clear", slot=slot)
            self.assertEqual(state["config"]["presets"][slot-1],
                             {"id": slot, "name": f"Road {slot}", "configured": False})
            self.assertEqual(state["config"]["presets"][slot:], before["presets"][slot:])
        self.assertEqual(app.view()["command_events"], [])

    def test_serialization_cancel_disconnect_and_replacement_never_replay(self):
        output = []
        app, clock = self.prepared(command_output=output.append)
        self.open(app, clock)
        app.action("preset_update", dynamic_assist=26)
        with self.assertRaises(ValueError):
            app.action("preset_update", pedal_sensitivity=31)
        first = output[0]
        app.action("preset_cancel")
        app.action("command_result", attempt=first["attempt"], session=first["session"], index=0, success=True)
        self.assertFalse(app.view()["preset_attempt"]["pending"])
        self.assertIn("not undone", app.view()["preset_attempt"]["reason"])
        self.open(app, clock)
        app.action("preset_update", pedal_sensitivity=44)
        app.action("disconnect")
        self.assertEqual(app.view()["preset_editor"]["status"], "unavailable")
        app.action("connect")
        app.receive(first["session"], settings_frame())
        clock.advance(.1); app.receive(app.session, settings_frame())
        self.assertIsNone(app.view()["preset_draft"])
        self.assertEqual(len(output), 2)

    def test_simulated_edit_changes_wheel_and_confirmation_requires_two_frames(self):
        app, clock = self.prepared()
        self.open(app, clock)
        app.action("preset_include_dip", included=True)
        for field, value in (("pedal_sensitivity", 31), ("dynamic_assist", 26),
                             ("pedal_dip_compensation", 11)):
            state = app.action("preset_update", **{field: value})
            self.assertEqual(state["preset_attempt"]["status"], "confirming")
            clock.advance(.1); app.action("simulator_emit")
            self.assertTrue(app.view()["preset_attempt"]["pending"])
            clock.advance(.1); app.action("simulator_emit")
            self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")
            self.assertEqual(app.view()["actual_settings"][field], value)
        packets = [row["packet_hex"] for row in app.view()["command_events"] if row["event"] == "submission"]
        self.assertEqual(packets, ["4c6441700f01028080801ff753d033",
                                  "4c6441701f0102808080808080808080808080808080808080801aba3c7b2f",
                                  "4c6441702101028080808080808080808080808080808080808080800b672ed25c"])

    def test_missing_mismatched_and_hung_submission_have_bounded_unknown_outcomes(self):
        for options, reason in (({"control_readback": "missing"}, "Confirmation timeout"),
                                ({"control_readback": "mismatch"}, "Confirmation timeout"),
                                ({"control_submission": "hang"}, "Submission timeout"),
                                ({"control_submission": "fail", "control_fail_after": 0}, "Transport submission failed")):
            with self.subTest(options=options):
                app, clock = self.prepared()
                self.open(app, clock)
                app.action("simulator_configure", **options)
                app.action("preset_update", dynamic_assist=26)
                for _ in range(60):
                    clock.advance(.2); app.action("simulator_emit")
                state = app.view()
                self.assertFalse(state["preset_attempt"]["pending"])
                self.assertEqual(state["preset_attempt"]["reason"], reason)
                self.assertEqual(len([row for row in state["command_events"] if row["event"] == "submission"]), 1)

    def test_save_failure_keeps_last_valid_configuration_and_does_not_undo_wheel(self):
        from eucwatch.persistence import MemoryStore
        class FailingStore(MemoryStore):
            def save(self, config):
                raise OSError("Disk full")
        app, clock = self.prepared(store=FailingStore())
        self.open(app, clock)
        before = app.view()["config"]
        app.action("preset_update", dynamic_assist=26)
        for _ in range(2):
            clock.advance(.1); app.action("simulator_emit")
        state = app.view()
        self.assertEqual(state["config"], before)
        self.assertEqual(state["preset_draft"]["dynamic_assist"], 26)
        self.assertEqual(state["actual_settings"]["dynamic_assist"], 26)
        self.assertEqual(state["preset_attempt"]["status"], "Confirmed")
        self.assertIn("Disk full", state["persistence_error"])
        self.assertIn("not undone", state["persistence_error"])

    def test_editor_confirmation_is_lost_on_external_change_or_staleness(self):
        app, clock = self.prepared()
        self.open(app, clock)
        app.action("preset_update", dynamic_assist=26)
        for _ in range(2):
            clock.advance(.1); app.action("simulator_emit")
        self.assertTrue(app.view()["preset_editor"]["current_confirmation"])
        clock.advance(.1); app.receive(app.session, settings_frame(assist=27))
        self.assertFalse(app.view()["preset_editor"]["current_confirmation"])
        self.assertEqual(app.view()["preset_editor"]["wheel_values"]["dynamic_assist"], 27)
        self.assertEqual(app.view()["preset_attempt"]["status"], "Confirmed")
        app.action("preset_update", dynamic_assist=26)
        for _ in range(2):
            clock.advance(.1); app.action("simulator_emit")
        self.assertTrue(app.view()["preset_editor"]["current_confirmation"])
        clock.advance(1)
        self.assertFalse(app.view()["preset_editor"]["current_confirmation"])
