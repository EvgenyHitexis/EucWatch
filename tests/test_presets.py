"""Fixed saved slots retain identity across application restarts."""
import tempfile
import unittest
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore


class PresetTests(unittest.TestCase):
    def test_four_initial_slots_have_editable_owner_defaults(self):
        app = Application(clock=ManualClock())
        menu = app.view()["presets_menu"]
        self.assertEqual([slot["id"] for slot in menu], [1, 2, 3, 4])
        self.assertEqual([slot["name"] for slot in menu],
                         ["Jump", "Forest", "Road", "Drag"])
        self.assertTrue(all(slot["configured"] and not slot["available"] for slot in menu))

    def test_direct_edit_restart_retains_definitions_without_commands_or_confirmation(self):
        from test_control import settings_frame
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "configuration.json")
            clock = ManualClock()
            app = Application(clock=clock, store=store)
            app.action("connect")
            app.receive(app.session, settings_frame())
            app.action("preset_begin", slot=4)
            clock.advance(.1); app.receive(app.session, settings_frame())
            app.action("preset_update", name="City")
            app.action("preset_update", dynamic_assist=26)
            for _ in range(2):
                clock.advance(.1); app.action("simulator_emit")
            saved = app.view()["config"]
            restarted = Application(clock=ManualClock(), store=FileStore(store.path)).view()
            self.assertEqual(restarted["config"], saved)
            self.assertIsNone(restarted["preset_editor"])
            self.assertIsNone(restarted["preset_attempt"])
            self.assertIsNone(restarted["confirmed_preset"])
            self.assertEqual(restarted["command_events"], [])
            self.assertEqual(restarted["mode"], "idle")
