"""Laptop preset editing verified through the public application boundary."""

import unittest
import tempfile
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore, MemoryStore


class PresetTests(unittest.TestCase):
    def test_four_initial_slots_have_names_without_invented_tunes(self):
        app = Application(clock=ManualClock())
        menu = app.view()["presets_menu"]
        self.assertEqual([slot["id"] for slot in menu], [1, 2, 3, 4])
        self.assertEqual([slot["name"] for slot in menu],
                         ["Preset 1", "Preset 2", "Preset 3", "Preset 4"])
        self.assertTrue(all(not slot["configured"] and not slot["available"] for slot in menu))
        self.assertIsNone(app.view()["preset_draft"])

    def test_save_and_cancel_preserve_definitions_and_optional_dip_is_absent(self):
        app = Application(clock=ManualClock())
        app.action("preset_begin", slot=2)
        app.action("preset_update", name="Rain", pedal_sensitivity=30, dynamic_assist=20)
        state = app.action("preset_save")
        preset = state["config"]["presets"][1]
        self.assertEqual(preset, {"id": 2, "name": "Rain", "configured": True,
                                  "pedal_sensitivity": 30, "dynamic_assist": 20})
        self.assertNotIn("pedal_dip_compensation", preset)
        self.assertEqual(state["presets_menu"][1]["name"], "Rain")
        self.assertEqual(state["config"]["revision"], 1)
        app.action("preset_begin", slot=2)
        app.action("preset_update", name="Changed", pedal_dip_compensation=7)
        state = app.action("preset_cancel")
        self.assertEqual(state["config"]["presets"][1], preset)
        self.assertIsNone(state["preset_draft"])

    def test_clear_is_a_draft_then_save_preserves_identity_position_and_name(self):
        app = Application(clock=ManualClock())
        app.action("preset_begin", slot=3)
        app.action("preset_update", name="Trail", pedal_sensitivity=45,
                   dynamic_assist=60, pedal_dip_compensation=7)
        saved = app.action("preset_save")["config"]["presets"][2]
        state = app.action("preset_clear", slot=3)
        self.assertEqual(state["preset_draft"], {"id": 3, "name": "Trail", "configured": False})
        self.assertEqual(state["config"]["presets"][2], saved)
        self.assertEqual(app.action("preset_cancel")["config"]["presets"][2], saved)
        app.action("preset_clear", slot=3)
        state = app.action("preset_save")
        self.assertEqual([slot["id"] for slot in state["config"]["presets"]], [1, 2, 3, 4])
        self.assertEqual(state["config"]["presets"][2], {"id": 3, "name": "Trail", "configured": False})
        self.assertFalse(state["presets_menu"][2]["available"])
        self.assertEqual(state["config"]["revision"], 2)

    def test_unconfigured_rename_and_optional_dip_removal_keep_meaning(self):
        app = Application(clock=ManualClock())
        app.action("preset_begin", slot=1)
        app.action("preset_update", name="Reserved")
        state = app.action("preset_save")
        self.assertEqual(state["config"]["presets"][0], {"id": 1, "name": "Reserved", "configured": False})
        app.action("preset_begin", slot=1)
        app.action("preset_update", pedal_sensitivity=0, dynamic_assist=100,
                   pedal_dip_compensation=0)
        self.assertEqual(app.action("preset_save")["config"]["presets"][0]["pedal_dip_compensation"], 0)
        app.action("preset_begin", slot=1)
        app.action("preset_update", pedal_dip_compensation=None)
        self.assertNotIn("pedal_dip_compensation", app.action("preset_save")["config"]["presets"][0])

    def test_invalid_values_and_missing_required_fields_never_save(self):
        app = Application(clock=ManualClock())
        for changes in ({"pedal_sensitivity": 30},
                        {"pedal_sensitivity": None, "dynamic_assist": 20},
                        {"pedal_sensitivity": True, "dynamic_assist": 20},
                        {"pedal_sensitivity": 30.5, "dynamic_assist": 20},
                        {"pedal_sensitivity": -1, "dynamic_assist": 20},
                        {"pedal_sensitivity": 30, "dynamic_assist": 101},
                        {"pedal_sensitivity": 30, "dynamic_assist": 20, "pedal_dip_compensation": 101},
                        {"name": ""}, {"name": "\nInvisible"}, {"name": "x" * 25}):
            with self.subTest(changes=changes):
                app.action("preset_begin", slot=1)
                app.action("preset_update", **changes)
                with self.assertRaises(ValueError):
                    app.action("preset_save")
                self.assertEqual(app.view()["config"]["revision"], 0)
                self.assertFalse(app.view()["config"]["presets"][0]["configured"])
        for slot in (True, 0, 5, "1", 1.0):
            with self.assertRaises(ValueError):
                app.action("preset_begin", slot=slot)
        for field in ("id", "configured", "revision"):
            with self.assertRaises(ValueError):
                app.action("preset_update", **{field: 2})

    def test_watch_definition_actions_are_rejected_and_editor_operations_send_no_commands(self):
        events = []
        app = Application(clock=ManualClock(), event_sink=events.append)
        app.action("simulator_start")
        app.action("preset_begin", slot=1)
        for action, values in (("preset_begin", {"slot": 1}),
                               ("preset_update", {"name": "Watch"}),
                               ("preset_save", {}), ("preset_clear", {"slot": 1})):
            with self.assertRaises(ValueError):
                app.action(action, source="watch", **values)
        app.action("preset_update", name="Road", pedal_sensitivity=30, dynamic_assist=20)
        app.action("preset_save")
        app.action("preset_clear", slot=1)
        app.action("preset_cancel")
        self.assertFalse(any(row["event"] in ("submission", "result") for row in events))
        self.assertIsNone(app.view()["confirmed_preset"])

    def test_saved_preset_restart_retains_slots_without_confirmation_or_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.json"
            app = Application(clock=ManualClock(), store=FileStore(path))
            app.action("preset_begin", slot=4)
            app.action("preset_update", name="City", pedal_sensitivity=30, dynamic_assist=20)
            state = app.action("preset_save")
            restarted = Application(clock=ManualClock(), store=FileStore(path))
            self.assertEqual(restarted.view()["config"], state["config"])
            self.assertIsNone(restarted.view()["preset_draft"])
            self.assertIsNone(restarted.view()["confirmed_preset"])
            self.assertEqual(restarted.view()["mode"], "idle")
            self.assertFalse(restarted.view()["connected"])

    def test_persistence_failure_preserves_active_slot_and_draft(self):
        class FailingStore(MemoryStore):
            def save(self, config):
                raise OSError("Disk full")

        app = Application(clock=ManualClock(), store=FailingStore())
        app.action("preset_begin", slot=1)
        app.action("preset_update", name="Road", pedal_sensitivity=30, dynamic_assist=20)
        state = app.action("preset_save")
        self.assertFalse(state["config"]["presets"][0]["configured"])
        self.assertEqual(state["preset_draft"]["name"], "Road")
        self.assertIn("Disk full", state["persistence_error"])


if __name__ == "__main__":
    unittest.main()
