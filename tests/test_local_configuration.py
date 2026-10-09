"""Withdrawn synchronization actions cannot change local configuration."""

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from eucwatch import Application, ManualClock
from eucwatch.configuration import default_configuration
from eucwatch.persistence import FileStore
from eucwatch.server import create_app


REMOVED_ACTIONS = (
    "transfer_begin", "transfer_preview", "transfer_choose", "transfer_send",
    "transfer_reconcile", "transfer_cancel", "transfer_return", "transfer_activate",
    "transfer_exit", "transfer_scenario", "transfer_watch_edit",
    "nordic_discover", "nordic_select", "nordic_disconnect",
)


def evidence(name, expected, observed):
    root = Path(__file__).resolve().parents[1]
    sources = ["laptop/eucwatch/application.py", "laptop/eucwatch/server.py",
               "laptop/eucwatch/persistence.py", "tests/test_local_configuration.py"]
    output = root / ".test-output"
    output.mkdir(exist_ok=True)
    (output / name).write_text(json.dumps({
        "issue": 40,
        "provenance": "aiohttp public API / actual Application and FileStore / temporary files / synthetic clock and wheel",
        "expected": expected, "observed": observed,
        "source_sha256": {source: hashlib.sha256((root / source).read_bytes()).hexdigest() for source in sources},
        "physical_operation": "none",
    }, indent=2) + "\n")


class LocalConfigurationHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_clients_cannot_replace_configuration_or_end_wheel_session(self):
        behavior = Application(clock=ManualClock())
        behavior.action("simulator_start", controlled=True)
        behavior.action("swipe", direction="down")
        client = TestClient(TestServer(create_app(behavior)))
        await client.start_server()
        try:
            session = await (await client.get("/api/session")).json()
            headers = {
                "Origin": str(client.make_url("/")).rstrip("/"),
                "X-EucWatch-Key": session["credential"],
            }
            original = await (await client.get("/api/state")).json()
            replacement = deepcopy(original["config"])
            replacement["presets"][0]["name"] = "Obsolete remote replacement"
            for name in REMOVED_ACTIONS:
                with self.subTest(action=name):
                    response = await client.post("/api/action", headers=headers, json={
                        "controller": session["controller"], "id": name,
                        "action": name, "epoch": original["session"],
                        "config": replacement, "address": "old-watch",
                    })
                    self.assertEqual(response.status, 400, await response.text())
                    state = await (await client.get("/api/state")).json()
                    self.assertEqual(state["config"], original["config"])
                    self.assertEqual(state["session"], original["session"])
                    self.assertEqual(state["mode"], "simulator")
                    self.assertTrue(state["connected"])
                    self.assertNotIn("transfer", state)
                    self.assertNotIn("nordic", state)
            evidence("local-configuration-actions.json",
                     "Every former transfer and Nordic action is rejected without replacing local content or ending the wheel session",
                     {"rejected_actions": list(REMOVED_ACTIONS), "status": 400,
                      "configuration_unchanged": True, "wheel_session_unchanged": True,
                      "transfer_and_nordic_state_absent": True})
        finally:
            await client.close()

    async def test_existing_local_presets_and_alerts_survive_restart_and_interrupted_save(self):
        class InterruptedStore(FileStore):
            interrupt = False

            def _replace(self, path, data):
                if self.interrupt and path == self.path:
                    raise OSError("Controlled interrupted active save")
                super()._replace(path, data)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.json"
            saved = default_configuration()
            saved["revision"] = 17
            saved["presets"][0] = {"id": 1, "name": "Laptop local", "configured": True,
                                    "pedal_sensitivity": 30, "dynamic_assist": 20}
            saved["alerts"]["pwm"] = {"enabled": True, "threshold": 70}
            path.write_text(json.dumps(saved))
            retired = Path(directory) / "shared_configuration.json"
            retired.write_text('{"pending": "historical transfer"}')
            historical = retired.read_bytes()

            async def host(store):
                client = TestClient(TestServer(create_app(store=store)))
                await client.start_server()
                self.addAsyncCleanup(client.close)
                session = await (await client.get("/api/session")).json()
                sequence = 0

                async def action(name, **payload):
                    nonlocal sequence
                    sequence += 1
                    current = await (await client.get("/api/state")).json()
                    response = await client.post("/api/action", headers={
                        "Origin": str(client.make_url("/")).rstrip("/"),
                        "X-EucWatch-Key": session["credential"],
                    }, json={"controller": session["controller"], "id": str(sequence),
                             "action": name, "epoch": current["session"], **payload})
                    self.assertEqual(response.status, 200, await response.text())
                    return await response.json()

                return client, action

            client, action = await host(FileStore(path))
            initial = await (await client.get("/api/state")).json()
            self.assertEqual(initial["config"], saved)
            exported = (await action("configuration_export"))["configuration_export"]
            self.assertEqual(exported, saved)
            await action("configuration_import_prepare", content=json.dumps(exported))
            cancelled = await action("configuration_import_cancel")
            self.assertEqual(cancelled["config"], saved)
            await action("alerts_begin")
            await action("alerts_update", alert="pwm", threshold=72)
            updated = (await action("alerts_save"))["config"]
            self.assertEqual(updated["presets"], saved["presets"])
            self.assertEqual(updated["alerts"]["pwm"], {"enabled": True, "threshold": 72})
            await client.close()

            store = InterruptedStore(path)
            restarted, action = await host(store)
            self.assertEqual((await (await restarted.get("/api/state")).json())["config"], updated)
            await action("configuration_import_prepare", content=json.dumps(exported))
            store.interrupt = True
            failed = await action("configuration_import_commit")
            self.assertIn("interrupted", failed["persistence_error"])
            self.assertEqual(failed["config"], updated)
            await restarted.close()
            path.write_text('{"partial"')
            recovered, _ = await host(FileStore(path))
            state = await (await recovered.get("/api/state")).json()
            self.assertEqual(state["config"], updated)
            self.assertIn("Recovered last-known-good", state["persistence_error"])
            self.assertEqual(retired.read_bytes(), historical)
            evidence("local-configuration-persistence.json",
                     "Existing schema-1 local slots/preferences need no re-entry; local edits survive restart; interrupted restore and corrupt active content recover last-known-good; retired reconciliation files are ignored",
                     {"existing_revision": 17, "retained_slot": "Laptop local",
                      "saved_pwm_threshold": 72, "restart_and_recovery": "passed",
                      "local_export_review_cancel": "passed", "historical_files_unchanged": True})
