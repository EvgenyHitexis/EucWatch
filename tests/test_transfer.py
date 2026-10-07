"""Saved configuration transfer through public actions and encoded transport."""

import base64
import json
import tempfile
import unittest
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.configuration import default_configuration
from eucwatch.persistence import FileStore, MemoryStore
from eucwatch.transfer_protocol import SimulatedWatch


class Wire:
    """Narrow byte-transport spy/fault adapter, without application logic."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.messages = []
        self.corrupt = False

    def __call__(self, message):
        self.messages.append(message)
        row = json.loads(message)
        if self.corrupt and row["op"] == "chunk":
            row["crc32"] ^= 1
            message = (json.dumps(row) + "\n").encode()
        return self.endpoint.exchange(message)


class TransferTests(unittest.TestCase):
    def test_transfer_terminates_pending_preset_and_button_cannot_submit_horn(self):
        output = []
        app = Application(clock=ManualClock(), command_output=output.append)
        app.action("preset_begin", slot=1)
        app.action(
            "preset_update", name="Road", pedal_sensitivity=31, dynamic_assist=26
        )
        app.action("preset_save")
        app.action("simulator_configure", speed_kmh=0)
        app.action("simulator_start")
        attempt = app.action("preset_apply", slot=1)
        self.assertEqual(len(output), 1)
        app.action("swipe", direction="down")
        entered = app.action("transfer_begin")
        self.assertFalse(entered["preset_attempt"]["pending"])
        self.assertIsNone(entered["confirmed_preset"])
        app.action("button_down")
        app.action("button_up")
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "success")
        self.assertFalse(state["fresh"])
        app.action(
            "command_result",
            attempt=attempt["preset_attempt"]["id"],
            session=attempt["session"],
            index=0,
            success=True,
        )
        self.assertEqual(len(output), 1)
        self.assertFalse(
            any(
                row["event"] == "horn_submission"
                for row in app.view()["command_events"]
            )
        )

    def test_failed_saved_watch_read_is_visible_and_application_can_return_to_riding(
        self,
    ):
        class UnreadableStore(MemoryStore):
            def load(self):
                raise OSError("Controlled watch persistence read failure")

        app = Application(clock=ManualClock(), watch_store=UnreadableStore())
        self.assertIn("read failure", app.view()["transfer"]["error"])
        app.action("swipe", direction="down")
        state = app.action("transfer_begin")
        self.assertEqual(state["transfer"]["status"], "failed")
        self.assertTrue(state["transfer"]["active"])
        self.assertIsNone(state["transfer"]["preview"])
        self.assertEqual(state["command_events"], [])
        returned = app.action("transfer_return")
        self.assertEqual(returned["mode"], "idle")
        self.assertFalse(returned["transfer"]["active"])

    def test_encoded_bounded_upload_rejects_corrupt_chunk_before_saved_activation(self):
        watch_store, shared_store = MemoryStore(), MemoryStore()
        wire = Wire(SimulatedWatch(watch_store))
        app = Application(
            clock=ManualClock(),
            watch_store=watch_store,
            shared_store=shared_store,
            transfer_transport=wire,
        )
        app.action("preset_begin", slot=2)
        app.action(
            "preset_update", name="Rain", pedal_sensitivity=31, dynamic_assist=26
        )
        app.action("preset_save")
        app.action("swipe", direction="down")
        preview = app.action("transfer_begin")
        wire.corrupt = True
        failed = app.action("transfer_send")
        self.assertEqual(failed["transfer"]["status"], "failed")
        self.assertIn("CRC", failed["transfer"]["error"])
        self.assertTrue(failed["transfer"]["active"])
        self.assertEqual(
            failed["transfer"]["watch_config"], preview["transfer"]["watch_config"]
        )
        self.assertIsNone(watch_store.load())
        self.assertIsNone(shared_store.load())
        self.assertEqual(failed["command_events"], [])
        wire.corrupt = False
        app.action("transfer_preview")
        saved = app.action("transfer_send")
        self.assertEqual(saved["transfer"]["status"], "success")
        self.assertEqual(watch_store.load(), saved["config"])
        rows = [json.loads(message) for message in wire.messages]
        self.assertTrue(
            all(
                message.endswith(b"\n") and len(message) <= 512
                for message in wire.messages
            )
        )
        chunks = [base64.b64decode(row["data"]) for row in rows if row["op"] == "chunk"]
        self.assertTrue(chunks)
        self.assertTrue(all(0 < len(chunk) <= 64 for chunk in chunks))
        commit = next(index for index, row in enumerate(rows) if row["op"] == "commit")
        self.assertEqual(rows[commit - 1]["op"], "validate")
        self.assertEqual(rows[commit + 1]["op"], "read")
        self.assertGreater(len(rows[commit + 2 :]), 1)

    def test_saved_watch_edit_after_preview_is_reread_and_not_overwritten(self):
        watch_store = MemoryStore(default_configuration())
        app = Application(clock=ManualClock(), watch_store=watch_store)
        app.action("swipe", direction="down")
        app.action("transfer_begin")
        watch_editor = Application(clock=ManualClock(), store=watch_store)
        watch_editor.action("alerts_begin")
        watch_editor.action("alerts_update", alert="speed", enabled=True, threshold=35)
        saved = watch_editor.action("alerts_save")["config"]
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "failed")
        self.assertIn("changed", state["transfer"]["error"])
        self.assertEqual(watch_store.load(), saved)
        state = app.action("transfer_preview")
        self.assertEqual(state["transfer"]["watch_config"], saved)

    def test_first_transfer_reviews_different_alert_values_and_preserves_watch_choice(
        self,
    ):
        watch_config = default_configuration()
        watch_config["revision"] = 3
        watch_config["alerts"]["speed"] = {"enabled": True, "threshold": 35}
        watch_store, shared_store = MemoryStore(watch_config), MemoryStore()
        app = Application(
            clock=ManualClock(), watch_store=watch_store, shared_store=shared_store
        )
        app.action("preset_begin", slot=1)
        app.action(
            "preset_update", name="Road", pedal_sensitivity=31, dynamic_assist=26
        )
        app.action("preset_save")
        app.action("swipe", direction="down")
        state = app.action("transfer_begin")
        preview = state["transfer"]["preview"]
        self.assertEqual(preview["watch_revision"], 3)
        self.assertEqual(
            set(preview["choices"]), {"alerts.speed.enabled", "alerts.speed.threshold"}
        )
        self.assertIsNone(preview["candidate"])
        with self.assertRaisesRegex(ValueError, "resolve"):
            app.action("transfer_send")
        self.assertEqual(watch_store.load(), watch_config)
        app.action("transfer_choose", path="alerts.speed.enabled", side="watch")
        self.assertIsNone(app.view()["transfer"]["preview"]["candidate"])
        app.action("transfer_choose", path="alerts.speed.threshold", side="watch")
        saved = app.action("transfer_send")
        self.assertEqual(
            saved["config"]["alerts"]["speed"], {"enabled": True, "threshold": 35}
        )
        self.assertEqual(saved["config"]["presets"][0]["name"], "Road")
        self.assertEqual(saved["config"]["revision"], 4)
        self.assertEqual(shared_store.load(), saved["config"])
        self.assertEqual(saved["command_events"], [])

    def test_laptop_edit_after_preview_rejects_stale_transfer_without_touching_watch(
        self,
    ):
        watch_store = MemoryStore()
        app = Application(clock=ManualClock(), watch_store=watch_store)
        app.action("swipe", direction="down")
        entered = app.action("transfer_begin")
        app.action("preset_begin", slot=1)
        app.action("preset_update", name="New saved definition")
        changed = app.action("preset_save")
        self.assertEqual(
            changed["transfer"]["watch_config"], entered["transfer"]["watch_config"]
        )
        with self.assertRaisesRegex(ValueError, "changed"):
            app.action("transfer_send")
        self.assertIsNone(watch_store.load())
        app.action("transfer_preview")
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "success")
        self.assertEqual(
            watch_store.load()["presets"][0]["name"], "New saved definition"
        )

    def test_transfer_entry_requires_settings_and_stopped_evidence_not_stale_zero(self):
        clock = ManualClock()
        app = Application(clock=clock)
        with self.assertRaisesRegex(ValueError, "Settings"):
            app.action("transfer_begin")
        with self.assertRaises(ValueError):
            app.action("transfer_return")
        app.action("simulator_configure", speed_kmh=5)
        app.action("simulator_start")
        app.action("swipe", direction="down")
        with self.assertRaisesRegex(ValueError, "stopped"):
            app.action("transfer_begin")
        app.action("simulator_configure", speed_kmh=0, traffic="paused")
        app.action("simulator_emit")
        clock.advance(1)
        with self.assertRaisesRegex(ValueError, "stopped"):
            app.action("transfer_begin")
        self.assertEqual(app.view()["mode"], "simulator")
        self.assertFalse(app.view()["transfer"]["active"])
        app.action("simulator_emit")
        app.action("transfer_begin")
        cancelled = app.action("transfer_cancel")
        self.assertTrue(cancelled["transfer"]["active"])
        state = app.action("transfer_return")
        self.assertEqual(state["mode"], "simulator")
        self.assertFalse(state["fresh"])
        self.assertEqual(state["dashboard"]["speed"], "—")
        app.action("simulator_emit")
        self.assertTrue(app.view()["fresh"])

    def test_review_cancel_then_verified_exchange_persists_all_three_saved_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "configuration.json")
            app = Application(clock=ManualClock(), store=store)
            app.action("preset_begin", slot=2)
            app.action(
                "preset_update", name="Rain", pedal_sensitivity=31, dynamic_assist=26
            )
            app.action("preset_save")
            app.action("swipe", direction="down")
            state = app.action("transfer_begin")
            old_watch = state["transfer"]["watch_config"]
            self.assertEqual(
                state["transfer"]["preview"]["candidate"]["presets"][1]["name"], "Rain"
            )
            self.assertTrue(state["transfer"]["preview"]["changes"])
            self.assertEqual(state["transfer"]["watch_config"], old_watch)
            cancelled = app.action("transfer_cancel")
            self.assertIsNone(cancelled["transfer"]["preview"])
            self.assertEqual(cancelled["transfer"]["watch_config"], old_watch)
            app.action("transfer_preview")
            state = app.action("transfer_send")
            self.assertEqual(state["transfer"]["status"], "success")
            self.assertFalse(state["transfer"]["active"])
            self.assertEqual(state["mode"], "idle")
            self.assertFalse(state["fresh"])
            self.assertEqual(state["transfer"]["watch_config"], state["config"])
            self.assertEqual(state["transfer"]["watch_revision"], 2)
            self.assertEqual(state["config"]["presets"][1]["name"], "Rain")
            self.assertEqual(state["command_events"], [])
            self.assertIsNone(state["confirmed_preset"])
            restarted = Application(
                clock=ManualClock(), store=FileStore(store.path)
            ).view()
            self.assertEqual(restarted["config"], state["config"])
            self.assertEqual(restarted["transfer"]["watch_config"], state["config"])
            shared = FileStore(Path(directory) / "shared_configuration.json").load()
            self.assertEqual(shared, state["config"])

    def test_explicit_stopped_entry_disconnects_and_keeps_transfer_awake(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action("simulator_configure", speed_kmh=0)
        app.action("simulator_start")
        old = app.view()
        app.action("swipe", direction="down")
        state = app.action("transfer_begin")
        self.assertEqual(state["mode"], "transfer")
        self.assertEqual(state["screen"], "transfer")
        self.assertEqual(state["transfer"]["endpoint"], "Simulated watch")
        self.assertTrue(state["transfer"]["active"])
        self.assertFalse(state["connected"])
        self.assertFalse(state["fresh"])
        self.assertGreater(state["session"], old["session"])
        self.assertEqual(state["dashboard"]["speed"], "—")
        self.assertIn("transfer", state["feedback"].lower())
        self.assertEqual(state["command_events"], old["command_events"])
        lost = [
            event
            for event in state["vibration"]["events"]
            if event.get("alert") == "lost" and event["phase"] == "start"
        ]
        self.assertEqual(len(lost), 1)
        clock.advance(60)
        self.assertTrue(app.view()["awake"])
        app.receive(old["session"], bytes.fromhex("dc5a5c"))
        self.assertFalse(app.view()["fresh"])


if __name__ == "__main__":
    unittest.main()
