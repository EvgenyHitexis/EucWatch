"""Reviewed saved configuration reconciliation at the Application boundary."""

import unittest
import tempfile
from pathlib import Path

from eucwatch import Application, ManualClock
from eucwatch.configuration import default_configuration
from eucwatch.persistence import MemoryStore, FileStore
from eucwatch.transfer_protocol import SimulatedWatch, decode


class ReconciliationTests(unittest.TestCase):
    def prepared(self, *, base=True):
        content = default_configuration()
        self.laptop = MemoryStore(content)
        self.watch = MemoryStore(content)
        self.shared = MemoryStore(content if base else None)
        self.app = Application(clock=ManualClock(), store=self.laptop,
                               watch_store=self.watch, shared_store=self.shared)
        return self.app

    def laptop_alert(self, alert, **values):
        self.app.action("alerts_begin")
        self.app.action("alerts_update", alert=alert, **values)
        self.app.action("alerts_save")

    def enter(self):
        self.app.action("swipe", direction="down")
        return self.app.action("transfer_begin")

    def test_one_sided_and_disjoint_alert_edits_merge_without_conflict_choices(self):
        app = self.prepared()
        self.laptop_alert("pwm", enabled=True, threshold=80)
        app.action("transfer_watch_edit", alert="speed", enabled=True, threshold=25)
        state = self.enter()
        preview = state["transfer"]["preview"]
        self.assertEqual(preview["conflicts"], [])
        self.assertEqual(preview["candidate"]["alerts"]["pwm"], {"enabled": True, "threshold": 80})
        self.assertEqual(preview["candidate"]["alerts"]["speed"], {"enabled": True, "threshold": 25})
        result = app.action("transfer_send")
        self.assertEqual(result["transfer"]["status"], "success")
        self.assertEqual(self.laptop.load(), self.watch.load())
        self.assertEqual(self.shared.load(), self.watch.load())
        self.assertEqual(result["command_events"], [])
        self.assertIsNone(result["confirmed_preset"])

    def test_interrupted_staging_preserves_all_saved_copies_until_explicit_retry(self):
        app = self.prepared()
        self.laptop_alert("pwm", enabled=True, threshold=80)
        state = self.enter()
        old_watch, old_shared = self.watch.load(), self.shared.load()
        app.action("transfer_scenario", stage="interrupt")
        failed = app.action("transfer_send")
        self.assertEqual(failed["transfer"]["status"], "failed")
        self.assertIn("interruption", failed["transfer"]["error"])
        self.assertEqual(self.watch.load(), old_watch)
        self.assertEqual(self.shared.load(), old_shared)
        self.assertEqual(failed["config"], state["config"])
        self.assertEqual(failed["command_events"], [])
        app.action("transfer_scenario", stage="normal")
        app.action("transfer_preview")
        self.assertEqual(app.action("transfer_send")["transfer"]["status"], "success")

    def test_identical_edits_need_no_choice_but_conflicting_field_shows_both_saved_values(self):
        app = self.prepared()
        self.laptop_alert("pwm", enabled=True, threshold=80)
        app.action("transfer_watch_edit", alert="pwm", enabled=True, threshold=80)
        self.assertEqual(self.enter()["transfer"]["preview"]["conflicts"], [])
        app.action("transfer_send")
        self.laptop_alert("pwm", threshold=90)
        app.action("transfer_watch_edit", alert="pwm", threshold=85)
        self.laptop_alert("speed", enabled=True, threshold=25)
        app.action("transfer_watch_edit", alert="speed", enabled=True, threshold=25)
        state = self.enter()
        self.assertEqual(state["transfer"]["preview"]["conflicts"], [
            {"path": "alerts.pwm.threshold", "laptop": 90, "watch": 85}])
        self.assertIsNone(state["transfer"]["preview"]["candidate"])
        laptop, watch = self.laptop.load(), self.watch.load()
        app.action("transfer_cancel")
        self.assertEqual(self.laptop.load(), laptop)
        self.assertEqual(self.watch.load(), watch)
        app.action("transfer_preview")
        chosen = app.action("transfer_choose", path="alerts.pwm.threshold", side="watch")
        self.assertEqual(chosen["transfer"]["preview"]["candidate"]["alerts"]["pwm"]["threshold"], 85)
        saved = app.action("transfer_send")
        self.assertEqual(saved["config"]["alerts"]["speed"]["threshold"], 25)
        self.assertEqual(self.shared.load(), self.watch.load())

    def test_lost_activation_acknowledgement_is_unknown_until_explicit_complete_readback(self):
        app = self.prepared()
        self.laptop_alert("pwm", enabled=True, threshold=80)
        preview = self.enter()["transfer"]["preview"]
        laptop, shared = self.laptop.load(), self.shared.load()
        app.action("transfer_scenario", commit="lost_ack")
        unknown = app.action("transfer_send")
        self.assertEqual(unknown["transfer"]["status"], "unknown")
        self.assertTrue(unknown["transfer"]["active"])
        self.assertEqual(self.watch.load(), preview["candidate"])
        self.assertEqual(self.laptop.load(), laptop)
        self.assertEqual(self.shared.load(), shared)
        with self.assertRaises(ValueError):
            app.action("transfer_send")
        with self.assertRaises(ValueError):
            app.action("transfer_cancel")
        app.action("transfer_scenario", readback="fail")
        failed_read = app.action("transfer_reconcile")
        self.assertEqual(failed_read["transfer"]["status"], "unknown")
        app.action("transfer_scenario", readback="normal")
        resolved = app.action("transfer_reconcile")
        self.assertEqual(resolved["transfer"]["status"], "success")
        self.assertEqual(resolved["config"], preview["candidate"])
        self.assertEqual(self.shared.load(), self.watch.load())
        self.assertEqual(resolved["command_events"], [])

    def test_unknown_transaction_survives_file_backed_restart_and_explicit_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("laptop.json", "watch.json", "shared.json")]
            stores = [FileStore(path) for path in paths]
            for store in stores:
                store.save(default_configuration())
            self.app = Application(clock=ManualClock(), store=stores[0], watch_store=stores[1], shared_store=stores[2])
            self.laptop_alert("speed", enabled=True, threshold=25)
            candidate = self.enter()["transfer"]["preview"]["candidate"]
            self.app.action("transfer_scenario", commit="lost_ack")
            self.assertEqual(self.app.action("transfer_send")["transfer"]["status"], "unknown")
            # The recovery companion retains the same pending evidence.
            (Path(directory) / "transfer_transaction.json").write_text("corrupt")
            self.app = Application(clock=ManualClock(), store=FileStore(paths[0]), watch_store=FileStore(paths[1]), shared_store=FileStore(paths[2]))
            self.assertEqual(self.app.view()["transfer"]["status"], "unknown")
            self.assertIsNotNone(self.enter()["transfer"]["pending"])
            resolved = self.app.action("transfer_reconcile")
            self.assertEqual(resolved["transfer"]["status"], "success")
            self.assertEqual(resolved["config"], candidate)
            restarted = Application(clock=ManualClock(), store=FileStore(paths[0]), watch_store=FileStore(paths[1]), shared_store=FileStore(paths[2]))
            self.assertIsNone(restarted.view()["transfer"]["pending"])
            self.assertEqual(restarted.view()["config"], candidate)
            self.assertEqual(restarted.view()["command_events"], [])

    def test_saved_edits_after_preview_refresh_reconciliation_without_overwriting_either_copy(self):
        app = self.prepared()
        self.enter()
        self.laptop_alert("speed", enabled=True, threshold=25)
        with self.assertRaisesRegex(ValueError, "changed"):
            app.action("transfer_send")
        self.assertEqual(app.view()["transfer"]["preview"]["laptop"], self.laptop.load())
        old_laptop = self.laptop.load()
        app.action("transfer_watch_edit", alert="pwm", enabled=True, threshold=80)
        state = app.action("transfer_send")
        self.assertIn("changed", state["transfer"]["error"])
        self.assertEqual(self.laptop.load(), old_laptop)
        self.assertEqual(state["transfer"]["preview"]["watch"], self.watch.load())
        self.assertEqual(state["transfer"]["preview"]["candidate"]["alerts"]["pwm"]["threshold"], 80)
        self.assertEqual(state["transfer"]["preview"]["candidate"]["alerts"]["speed"]["threshold"], 25)
        self.assertEqual(state["command_events"], [])

    def test_shared_base_save_failure_keeps_unknown_and_uses_the_verified_local_saved_copy(self):
        class FailingShared(MemoryStore):
            fail = True
            def save(self, value):
                if self.fail:
                    raise OSError("Controlled shared-base persistence failure")
                super().save(value)
        app = self.prepared()
        self.shared = FailingShared(default_configuration())
        self.app = app = Application(clock=ManualClock(), store=self.laptop, watch_store=self.watch, shared_store=self.shared)
        self.laptop_alert("pwm", enabled=True, threshold=80)
        candidate = self.enter()["transfer"]["preview"]["candidate"]
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "unknown")
        self.assertEqual(self.watch.load(), candidate)
        self.assertEqual(self.laptop.load(), candidate)
        self.assertEqual(state["config"], candidate)
        self.assertEqual(self.shared.load(), default_configuration())
        self.shared.fail = False
        state = app.action("transfer_reconcile")
        self.assertEqual(state["transfer"]["status"], "success")
        self.assertEqual(self.shared.load(), candidate)

    def test_absent_base_requires_owner_choice_and_invalid_combined_values_cannot_transfer(self):
        app = self.prepared(base=False)
        self.laptop_alert("pwm", enabled=True, threshold=80)
        app.action("transfer_watch_edit", alert="pwm", enabled=True, threshold=85)
        preview = self.enter()["transfer"]["preview"]
        self.assertIsNone(preview["base_revision"])
        self.assertEqual(preview["automatic"], {})
        self.assertEqual(preview["conflicts"], [{"path": "alerts.pwm.threshold", "laptop": 80, "watch": 85}])
        app.action("transfer_choose", path="alerts.pwm.threshold", side="laptop")
        self.assertEqual(app.action("transfer_send")["config"]["alerts"]["pwm"]["threshold"], 80)
        self.laptop_alert("pwm", enabled=False)
        app.action("transfer_watch_edit", alert="pwm", threshold=90)
        self.enter()
        self.assertEqual(app.view()["transfer"]["preview"]["candidate"]["alerts"]["pwm"], {"enabled": False, "threshold": 90})
        app.action("transfer_cancel")
        app.action("transfer_return")
        # Each saved copy is valid, but disjoint edits can combine incompatibly.
        base = default_configuration()
        base["alerts"]["pwm"]["threshold"] = 80
        self.laptop, self.watch, self.shared = MemoryStore(base), MemoryStore(base), MemoryStore(base)
        self.app = app = Application(clock=ManualClock(), store=self.laptop, watch_store=self.watch, shared_store=self.shared)
        self.laptop_alert("pwm", enabled=True)
        app.action("transfer_watch_edit", alert="pwm", threshold=None)
        state = self.enter()
        self.assertEqual(state["transfer"]["preview"]["conflicts"], [])
        self.assertIsNone(state["transfer"]["preview"]["candidate"])
        self.assertIn("invalid", state["transfer"]["error"])
        watch = self.watch.load()
        with self.assertRaises(ValueError):
            app.action("transfer_send")
        self.assertEqual(self.watch.load(), watch)

    def test_readback_of_old_active_copy_resolves_unknown_to_review_without_automatic_retry(self):
        self.prepared()
        endpoint = SimulatedWatch(self.watch)
        messages = []
        def interrupted(message):
            row = decode(message)
            messages.append(row["op"])
            if row["op"] == "commit":
                raise OSError("Controlled transport ended before activation")
            return endpoint.exchange(message)
        self.app = app = Application(clock=ManualClock(), store=self.laptop, watch_store=self.watch, shared_store=self.shared, transfer_transport=interrupted)
        self.laptop_alert("speed", enabled=True, threshold=25)
        self.enter()
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "unknown")
        before = messages.count("commit")
        state = app.action("transfer_reconcile")
        self.assertEqual(state["transfer"]["status"], "review")
        self.assertIsNone(state["transfer"]["pending"])
        self.assertEqual(self.watch.load(), default_configuration())
        self.assertEqual(messages.count("commit"), before)
        self.assertIsNotNone(state["transfer"]["preview"]["candidate"])

    def test_new_saved_edits_during_unknown_are_preserved_instead_of_finalizing_old_candidate(self):
        app = self.prepared()
        self.laptop_alert("pwm", enabled=True, threshold=80)
        self.enter()
        app.action("transfer_scenario", commit="lost_ack")
        app.action("transfer_send")
        self.laptop_alert("pwm", threshold=90)
        laptop = self.laptop.load()
        app.action("transfer_watch_edit", alert="pwm", threshold=85)
        watch = self.watch.load()
        state = app.action("transfer_reconcile")
        self.assertEqual(state["transfer"]["status"], "review")
        self.assertEqual(state["transfer"]["preview"]["conflicts"], [{"path": "alerts.pwm.threshold", "laptop": 90, "watch": 85}])
        self.assertEqual(self.laptop.load(), laptop)
        self.assertEqual(self.watch.load(), watch)
        self.assertEqual(self.shared.load(), default_configuration())
        self.assertEqual(state["command_events"], [])

    def test_failed_durable_transaction_marker_prevents_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            laptop, watch, shared = [FileStore(Path(directory) / name) for name in ("laptop.json", "watch.json", "shared.json")]
            for store in (laptop, watch, shared):
                store.save(default_configuration())
            self.app = app = Application(clock=ManualClock(), store=laptop, watch_store=watch, shared_store=shared)
            self.laptop_alert("speed", enabled=True, threshold=25)
            self.enter()
            blocked = Path(directory) / "transfer_transaction.last-good.json"
            blocked.mkdir()
            state = app.action("transfer_send")
            self.assertEqual(state["transfer"]["status"], "failed")
            self.assertIsNone(state["transfer"]["pending"])
            self.assertEqual(watch.load(), default_configuration())
            self.assertEqual(shared.load(), default_configuration())
            self.assertEqual(state["config"], laptop.load())
            blocked.rmdir()
            app.action("transfer_preview")
            self.assertEqual(app.action("transfer_send")["transfer"]["status"], "success")

    def test_laptop_saved_copy_changed_by_another_application_is_refreshed_before_transfer(self):
        app = self.prepared()
        self.enter()
        other = Application(clock=ManualClock(), store=self.laptop)
        other.action("alerts_begin")
        other.action("alerts_update", alert="speed", enabled=True, threshold=25)
        saved = other.action("alerts_save")["config"]
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "failed")
        self.assertEqual(state["config"], saved)
        self.assertEqual(state["transfer"]["preview"]["laptop"], saved)
        self.assertEqual(self.watch.load(), default_configuration())
        self.assertEqual(self.laptop.load(), saved)

    def test_other_application_saved_edit_survives_unknown_outcome_readback(self):
        app = self.prepared()
        self.laptop_alert("pwm", enabled=True, threshold=80)
        self.enter()
        app.action("transfer_scenario", commit="lost_ack")
        app.action("transfer_send")
        committed_watch = self.watch.load()
        other = Application(clock=ManualClock(), store=self.laptop)
        other.action("alerts_begin")
        other.action("alerts_update", alert="pwm", threshold=90)
        saved = other.action("alerts_save")["config"]
        state = app.action("transfer_reconcile")
        self.assertEqual(state["transfer"]["status"], "review")
        self.assertEqual(state["config"], saved)
        self.assertEqual(state["transfer"]["preview"]["laptop"], saved)
        self.assertEqual(self.laptop.load(), saved)
        self.assertEqual(self.watch.load(), committed_watch)
        self.assertEqual(self.shared.load(), default_configuration())
        self.assertEqual(state["command_events"], [])

    def test_laptop_saved_edit_during_encoded_staging_prevents_activation(self):
        self.prepared()
        endpoint = SimulatedWatch(self.watch)
        edited = []
        def exchange(message):
            if decode(message)["op"] == "validate" and not edited:
                other = Application(clock=ManualClock(), store=self.laptop)
                other.action("alerts_begin")
                other.action("alerts_update", alert="speed", enabled=True, threshold=25)
                edited.append(other.action("alerts_save")["config"])
            return endpoint.exchange(message)
        self.app = app = Application(clock=ManualClock(), store=self.laptop, watch_store=self.watch, shared_store=self.shared, transfer_transport=exchange)
        self.enter()
        state = app.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "failed")
        self.assertIsNone(state["transfer"]["pending"])
        self.assertEqual(state["config"], edited[0])
        self.assertEqual(state["transfer"]["preview"]["laptop"], edited[0])
        self.assertEqual(self.watch.load(), default_configuration())
        self.assertEqual(self.shared.load(), default_configuration())
