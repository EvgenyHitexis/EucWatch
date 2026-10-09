"""Configuration backup through explicit application actions and real storage."""
from preset_fixture import save_preset


import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore, MemoryStore
from eucwatch.recording import Replay


class BackupTests(unittest.TestCase):
    def test_export_and_restoration_exclude_a_real_simulator_confirmation(self):
        app = self.configured()
        app.action("simulator_start", controlled=True)
        app.action("preset_apply", slot=3)
        app.action("advance", seconds=0.2)
        state = app.action("advance", seconds=0.2)
        self.assertIsNotNone(state["confirmed_preset"])
        commands = state["command_events"]
        exported = app.action("configuration_export")["configuration_export"]
        self.assertEqual(set(exported), {"version", "revision", "presets", "alerts"})
        app.action("configuration_import_prepare", content=json.dumps(exported))
        restored = app.action("configuration_import_commit")
        self.assertIsNone(restored["confirmed_preset"])
        self.assertEqual(restored["command_events"], commands)

    def test_restored_alert_settings_govern_fresh_behavior_without_wheel_commands(self):
        app = self.configured()
        app.action("simulator_configure", pwm_percent=80)
        app.action("simulator_start", controlled=True)
        commands = app.view()["command_events"]
        restored = deepcopy(app.view()["config"])
        restored["alerts"]["pwm"] = {"enabled": True, "threshold": 70}
        app.action("configuration_import_prepare", content=json.dumps(restored))
        self.assertIsNone(app.view()["vibration"]["current"])
        state = app.action("configuration_import_commit")
        self.assertEqual(state["vibration"]["current"]["alert"], "pwm")
        self.assertEqual(state["vibration"]["current"]["duration_s"], 0.15)
        self.assertEqual(state["command_events"], commands)

    def test_ambiguous_deeply_nested_and_multibyte_oversized_content_requires_review(
        self,
    ):
        app = self.configured()
        original = app.view()["config"]
        duplicate = json.dumps(original)[:-1] + ',"version":999}'
        for content in (duplicate, "[" * 1100 + "0" + "]" * 1100, "界" * 12000):
            with self.subTest(content=content[:20]), self.assertRaises(ValueError):
                app.action("configuration_import_prepare", content=content)
            self.assertEqual(app.view()["config"], original)
            self.assertIsNone(app.view()["configuration_preview"])

    def test_import_review_is_an_ongoing_operation_until_explicit_cancel(self):
        clock = ManualClock()
        app = Application(clock=clock)
        content = json.dumps(self.configured().view()["config"])
        app.action("configuration_import_prepare", content=content)
        clock.advance(31)
        self.assertTrue(app.view()["awake"])
        app.action("configuration_import_cancel")
        clock.advance(31)
        self.assertFalse(app.view()["awake"])

    def configured(self, store=None, **options):
        app = Application(clock=ManualClock(), store=store, **options)
        save_preset(app, slot=3, name="Daily", pedal_sensitivity=30, dynamic_assist=25)
        return app

    def test_restoration_stops_unsent_preset_writes_and_ignores_late_transport_result(
        self,
    ):
        output = []
        app = self.configured(command_output=output.append)
        app.action("simulator_start", controlled=True)
        attempt = app.action("preset_apply", slot=3)
        self.assertEqual(len(output), 1)
        restored = deepcopy(app.view()["config"])
        restored["presets"][2]["name"] = "Restored definition"
        app.action("configuration_import_prepare", content=json.dumps(restored))
        state = app.action("configuration_import_commit")
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertIsNone(state["confirmed_preset"])
        self.assertIn("changed", state["preset_attempt"]["reason"])
        app.action(
            "command_result",
            attempt=attempt["preset_attempt"]["id"],
            session=attempt["session"],
            index=0,
            success=True,
        )
        self.assertEqual(len(output), 1)
        self.assertEqual(
            len(
                [
                    event
                    for event in app.view()["command_events"]
                    if event["event"] == "submission"
                ]
            ),
            1,
        )

    def test_backup_operations_in_replay_preserve_mode_and_emit_no_wheel_commands(self):
        source = self.configured()
        content = json.dumps(
            source.action("configuration_export")["configuration_export"]
        )
        fixture = (
            Path(__file__).resolve().parents[1]
            / "experiments/laptop-feasibility/evidence/fixture-recording.jsonl"
        )
        app = Application(clock=ManualClock())
        app.action("replay_start", recording=Replay.load(fixture))
        commands = app.view()["command_events"]
        app.action("configuration_export")
        app.action("configuration_import_prepare", content=content)
        app.action("configuration_import_cancel")
        app.action("configuration_import_prepare", content=content)
        state = app.action("configuration_import_commit")
        self.assertEqual(state["mode"], "replay")
        self.assertEqual(state["command_events"], commands)
        self.assertIsNone(state["confirmed_preset"])
        self.assertEqual(state["config"]["presets"], source.view()["config"]["presets"])

    def test_export_review_cancel_restore_and_restart_preserve_meaning(self):
        source = self.configured()
        exported = source.action("configuration_export")["configuration_export"]
        self.assertEqual(set(exported), {"version", "revision", "presets", "alerts"})
        store = MemoryStore()
        target = Application(clock=ManualClock(), store=store)
        initial = target.view()["config"]
        state = target.action(
            "configuration_import_prepare", content=json.dumps(exported)
        )
        self.assertEqual(state["config"], initial)
        self.assertEqual(state["configuration_preview"]["content"], exported)
        self.assertEqual(
            state["configuration_preview"]["migration"],
            {"from": 1, "to": 1, "changes": []},
        )
        target.action("configuration_import_cancel")
        self.assertEqual(target.view()["config"], initial)
        target.action("configuration_import_prepare", content=json.dumps(exported))
        state = target.action("configuration_import_commit")
        self.assertEqual(state["config"]["presets"], exported["presets"])
        self.assertEqual(state["config"]["alerts"], exported["alerts"])
        self.assertIsNone(state["confirmed_preset"])
        self.assertIsNone(state["configuration_preview"])
        self.assertEqual(
            Application(clock=ManualClock(), store=store).view()["config"],
            state["config"],
        )

    def test_invalid_incomplete_unsupported_oversized_import_preserves_active(self):
        app = self.configured()
        initial = app.view()["config"]
        invalid = []
        for mutation in (
            lambda c: c.update(version=999),
            lambda c: c.pop("alerts"),
            lambda c: c["presets"].pop(),
            lambda c: c["presets"][0].update(id=4),
            lambda c: c.update(confirmed_preset=3),
            lambda c: c["alerts"]["speed"].update(enabled=True, threshold=None),
        ):
            content = deepcopy(initial)
            mutation(content)
            invalid.append(json.dumps(content))
        invalid.extend(["{}", "null", "invalid", " " * 32769])
        for content in invalid:
            with self.subTest(content=content[:40]), self.assertRaises(ValueError):
                app.action("configuration_import_prepare", content=content)
            self.assertEqual(app.view()["config"], initial)
        self.assertIsNone(app.view()["configuration_preview"])

    def test_preview_revision_change_requires_new_review(self):
        app = self.configured()
        content = json.dumps(app.view()["config"])
        app.action("configuration_import_prepare", content=content)
        app.action("alerts_begin")
        app.action("alerts_update", alert="lost", enabled=False)
        app.action("alerts_save")
        saved = app.view()["config"]
        with self.assertRaisesRegex(ValueError, "changed"):
            app.action("configuration_import_commit")
        self.assertEqual(app.view()["config"], saved)

    def test_interrupted_active_replacement_keeps_saved_copy_and_visible_failure(self):
        class InterruptedStore(FileStore):
            interrupt = False

            def _replace(self, path, data):
                if self.interrupt and path == self.path:
                    raise OSError("Controlled interruption before activation")
                super()._replace(path, data)

        with tempfile.TemporaryDirectory() as directory:
            store = InterruptedStore(Path(directory) / "configuration.json")
            app = self.configured(store)
            initial = app.view()["config"]
            imported = deepcopy(initial)
            imported["presets"][2]["name"] = "Replacement"
            app.action("configuration_import_prepare", content=json.dumps(imported))
            store.interrupt = True
            state = app.action("configuration_import_commit")
            self.assertIn("interruption", state["persistence_error"])
            self.assertEqual(state["config"], initial)
            self.assertIsNotNone(state["configuration_preview"])
            restarted = Application(clock=ManualClock(), store=FileStore(store.path))
            self.assertEqual(restarted.view()["config"], initial)
            store.path.write_text("corrupt")
            recovered = Application(clock=ManualClock(), store=FileStore(store.path))
            self.assertEqual(recovered.view()["config"], initial)
            self.assertIn("Recovered", recovered.view()["persistence_error"])
