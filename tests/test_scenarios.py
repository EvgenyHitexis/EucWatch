"""Reproducible scenario intents drive the actual application/parser path."""

import json
import tempfile
import unittest
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.recording import Replay
from eucwatch.scenarios import FileScenarioStore, MemoryScenarioStore, ScenarioLibrary


class ScenarioTests(unittest.TestCase):
    def test_export_review_and_explicit_start_reproduce_raw_telemetry_stale_and_recovery(self):
        source = Application(clock=ManualClock())
        source.action("simulator_configure", speed_kmh=25, voltage_V=148.05, pwm_percent=45)
        library = ScenarioLibrary(MemoryScenarioStore())
        steps = [{"action": "simulator_configure", "traffic": "paused"},
                 {"action": "advance", "seconds": 1.1},
                 {"action": "simulator_configure", "traffic": "normal"},
                 {"action": "simulator_emit"}, {"action": "disconnect"},
                 {"action": "connect"}, {"action": "simulator_emit"}]
        library.save_current(source.view()["simulator"], "Freshness and recovery", steps)
        retained = library.export()
        rows = []
        app = Application(clock=ManualClock(), event_sink=rows.append)
        imported = ScenarioLibrary(MemoryScenarioStore())
        imported.review(retained)
        self.assertEqual(app.view()["mode"], "idle")
        self.assertIsNone(imported.view()["definition"])
        imported.start(app)
        self.assertEqual(app.view()["dashboard"]["speed"], "25")
        self.assertEqual(app.view()["dashboard"]["wheel_battery_percent"], "100")
        imported.step(app)
        imported.step(app)
        self.assertEqual(app.view()["dashboard"]["speed"], "—")
        self.assertTrue(app.view()["dashboard"]["wheel_battery_dimmed"])
        imported.step(app)
        imported.step(app)
        self.assertTrue(app.view()["fresh"])
        imported.step(app)
        self.assertFalse(app.view()["fresh"])
        imported.step(app)
        self.assertFalse(app.view()["fresh"])
        imported.step(app)
        self.assertTrue(app.view()["fresh"])
        self.assertEqual(imported.view()["position"], 7)
        self.assertFalse(imported.view()["active"])
        self.assertTrue(any(row.get("event") == "notification" and row.get("raw_hex") for row in rows))
        self.assertEqual(app.view()["command_events"], [])

    def test_untrusted_definitions_cannot_add_commands_or_unknown_fields_and_preserve_review(self):
        app = Application(clock=ManualClock())
        library = ScenarioLibrary()
        library.save_current(app.view()["simulator"], "Original")
        good = json.loads(library.export())
        library.review(json.dumps(good))
        cases = []
        for field, value in [("version", 2), ("seed", True), ("clock", "host"), ("input", "decoded-values")]:
            cases.append(good | {field: value})
        cases.extend([good | {"unexpected": True}, good | {"steps": []}, good | {"steps": [{"action": "advance", "seconds": 1}] * 65},
                      good | {"steps": [{"action": "button_down"}]}, good | {"steps": [{"action": "preset_apply", "slot": 1}]},
                      good | {"steps": [{"action": "advance", "seconds": True}]},
                      good | {"simulator": {"speed_kmh": 25}},
                      good | {"steps": [{"action": "simulator_configure", "voltage_V": -1}]}])
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                library.review(json.dumps(content))
        with self.assertRaises(ValueError):
            library.review(json.dumps(good).replace('"version": 1', '"version": 1, "version": 1'))
        with self.assertRaises(ValueError):
            library.review(" " * 32769)
        self.assertEqual(library.view()["preview"], good)
        self.assertEqual(library.view()["definition"]["name"], "Original")
        self.assertEqual(app.view()["mode"], "idle")

    def test_scenario_start_replaces_replay_and_external_session_changes_end_without_commands(self):
        app = Application(clock=ManualClock())
        library = ScenarioLibrary()
        library.save_current(app.view()["simulator"], "Restart session")
        fixture = Path(__file__).resolve().parents[1] / "experiments/laptop-feasibility/evidence/fixture-recording.jsonl"
        app.action("replay_start", recording=Replay.load(fixture))
        old_session = app.view()["session"]
        library.start(app)
        self.assertEqual(app.view()["mode"], "simulator")
        self.assertTrue(app.view()["controlled"])
        self.assertGreater(app.view()["session"], old_session)
        app.action("connect")
        before = app.view()
        with self.assertRaisesRegex(ValueError, "session changed"):
            library.step(app)
        self.assertEqual(app.view()["session"], before["session"])
        self.assertEqual(app.view()["diagnostics"]["valid_frames"], before["diagnostics"]["valid_frames"])
        self.assertFalse(library.view()["active"])
        self.assertEqual(app.view()["command_events"], [])

    def test_exported_maximum_steps_remain_importable_and_durable_without_autostart(self):
        app = Application(clock=ManualClock())
        values = app.view()["simulator"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenarios/current.json"
            library = ScenarioLibrary(FileScenarioStore(path))
            library.save_current(values, "Bounded complete inputs", [{"action": "simulator_configure", **values}] * 64)
            exported = library.export()
            self.assertLessEqual(len(exported.encode()), 32768)
            reviewed = ScenarioLibrary()
            reviewed.review(exported)
            restored = ScenarioLibrary(FileScenarioStore(path))
            self.assertEqual(restored.view()["definition"], library.view()["definition"])
            self.assertFalse(restored.view()["active"])
            self.assertEqual(app.view()["mode"], "idle")
            path.write_text("incomplete saved data")
            invalid = ScenarioLibrary(FileScenarioStore(path))
            self.assertIn("could not be loaded", invalid.view()["persistence_error"])
            self.assertIsNone(invalid.view()["definition"])

    def test_storage_failure_is_visible_and_control_injections_are_distinguished(self):
        class Store(MemoryScenarioStore):
            fail = False
            def save(self, definition):
                if self.fail:
                    raise OSError("Controlled disk failure")
                super().save(definition)
        store = Store()
        library = ScenarioLibrary(store)
        app = Application(clock=ManualClock())
        library.save_current(app.view()["simulator"], "Retained")
        store.fail = True
        library.save_current(app.view()["simulator"], "Not saved")
        self.assertEqual(library.view()["definition"]["name"], "Retained")
        self.assertEqual(ScenarioLibrary(store).view()["definition"]["name"], "Retained")
        self.assertIn("disk failure", library.view()["persistence_error"])
        store.fail = False
        app.action("simulator_configure", control_submission="fail", control_readback="partial")
        library.save_current(app.view()["simulator"], "Injected control failure")
        self.assertIsNone(library.view()["persistence_error"])
        self.assertEqual(library.view()["higher_level_injections"], ["control_readback", "control_submission"])
        self.assertIn("no random generator", library.view()["provenance"])


if __name__ == "__main__":
    unittest.main()
