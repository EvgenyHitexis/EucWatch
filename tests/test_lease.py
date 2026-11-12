"""Controller lease rules driven through the module interface with a ManualClock."""
import asyncio
import json
from pathlib import Path
import unittest

from eucwatch import Application, ManualClock
from eucwatch.lease import ControllerLease
from eucwatch.scenarios import ScenarioLibrary


class FakeLive:
    def __init__(self):
        self.calls = []
        self.gate = None

    async def discover(self):
        self.calls.append(("discover",))

    async def connect(self, address):
        self.calls.append(("connect", address))

    async def disconnect(self):
        self.calls.append(("disconnect",))
        if self.gate is not None:
            await self.gate.wait()

    def status(self):
        return {"calls": len(self.calls)}


class LeaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = ManualClock()
        self.app = Application(clock=ManualClock())
        self.live = FakeLive()
        self.lease = ControllerLease(
            self.app, self.live, ScenarioLibrary(), self.clock, timeout=10.0
        )

    def test_one_controller_at_a_time_until_its_lease_expires(self):
        first = self.lease.acquire(None)
        self.assertIsNotNone(first)
        self.assertIsNone(self.lease.acquire(None))
        self.assertEqual(self.lease.acquire(first), first)
        self.clock.advance(10.5)
        replacement = self.lease.acquire(None)
        self.assertIsNotNone(replacement)
        self.assertNotEqual(replacement, first)

    def test_expired_lease_cancels_the_preset_draft_and_releases_the_side_button(self):
        self.lease.acquire(None)
        self.app.action("simulator_start")
        self.app.action("preset_begin", slot=1)
        self.assertIsNotNone(self.app.view()["preset_editor"])
        self.clock.advance(10.5)
        self.lease.tick()
        self.assertIsNone(self.app.view()["preset_editor"])

        owner = self.lease.acquire(None)
        self.app.action("button_down")
        self.clock.advance(10.5)
        # Acquiring checks expiry without the periodic abandoned-press release.
        self.assertNotEqual(self.lease.acquire(None), owner)
        self.assertFalse(self.app.view()["button"]["down"])
        self.assertEqual(self.app.mode, "simulator")

    def test_press_abandoned_for_two_seconds_is_released_while_the_lease_holds(self):
        from eucwatch.lease import ABANDONED_PRESS_S
        self.assertEqual(ABANDONED_PRESS_S, 2.0)
        owner = self.lease.acquire(None)
        self.app.action("simulator_start")
        self.app.action("button_down")
        self.clock.advance(1.5)
        self.lease.acquire(owner)  # The controlling browser is still polling.
        self.clock.advance(2.0)
        self.lease.tick()
        self.assertTrue(self.app.view()["button"]["down"])
        self.clock.advance(0.1)
        self.lease.tick()
        self.assertFalse(self.app.view()["button"]["down"])
        self.assertFalse(self.app.view()["recovery"])
        self.assertEqual(self.lease.acquire(owner), owner)

    def test_changed_document_cancels_the_preset_draft(self):
        owner = self.lease.acquire(None, document="tab-1")
        self.app.action("preset_begin", slot=1)
        self.lease.acquire(owner, document="tab-1")
        self.lease.acquire(owner, document="x" * 101)  # Oversized ids are ignored.
        self.lease.acquire(None, document="other-browser")
        self.assertIsNotNone(self.app.view()["preset_editor"])
        self.lease.acquire(owner, document="tab-2")  # Reload.
        self.assertIsNone(self.app.view()["preset_editor"])

    def test_state_polling_refreshes_the_owner_and_refuses_an_expired_controller(self):
        from eucwatch.lease import ControllerExpired
        owner = self.lease.acquire(None)
        self.lease.observe(None)  # Viewing without a controller is allowed.
        for _ in range(3):
            self.clock.advance(6)
            self.lease.observe(owner)
        self.assertEqual(self.lease.acquire(owner), owner)
        self.clock.advance(10.5)
        with self.assertRaisesRegex(ControllerExpired, "^Controller expired; reacquire current state$"):
            self.lease.observe(owner)

    def request(self, controller, identity, action, /, epoch=None, **payload):
        return {"controller": controller, "id": identity, "action": action,
                "epoch": self.app.session if epoch is None else epoch, **payload}

    async def test_duplicate_request_returns_the_earlier_result_without_acting_twice(self):
        owner = self.lease.acquire(None)
        await self.lease.act(self.request(owner, "start", "simulator_start"))
        first = await self.lease.act(self.request(owner, "press", "button_down"))
        self.assertTrue(first["button"]["down"])
        self.assertEqual(first["live"], {"calls": 1})
        self.assertIsNone(first["recording"])
        self.assertIn("scenario", first)
        await self.lease.act(self.request(owner, "release", "button_up"))
        events = len(self.app.view()["command_events"])
        self.assertEqual(await self.lease.act(self.request(owner, "press", "button_down")), first)
        self.assertFalse(self.app.view()["button"]["down"])
        self.assertEqual(len(self.app.view()["command_events"]), events)

    async def test_duplicate_whose_result_was_evicted_is_refused_not_repeated(self):
        from eucwatch.lease import Conflict
        lease = ControllerLease(self.app, self.live, ScenarioLibrary(), self.clock, result_limit=1)
        owner = lease.acquire(None)
        self.app.action("simulator_start")
        await lease.act(self.request(owner, "press", "button_down"))
        await lease.act(self.request(owner, "release", "button_up"))
        events = len(self.app.view()["command_events"])
        with self.assertRaisesRegex(Conflict, "^Duplicate action was already processed; its response expired$"):
            await lease.act(self.request(owner, "press", "button_down"))
        self.assertFalse(self.app.view()["button"]["down"])
        self.assertEqual(len(self.app.view()["command_events"]), events)

    async def test_request_carrying_a_stale_epoch_is_refused(self):
        from eucwatch.lease import Conflict
        owner = self.lease.acquire(None)
        old = self.app.session
        await self.lease.act(self.request(owner, "start", "simulator_start", epoch=old))
        self.assertGreater(self.app.session, old)
        for epoch in (old, None, "1", 1.0):
            with self.subTest(epoch=epoch):
                request = self.request(owner, f"press-{epoch!r}", "button_down")
                request["epoch"] = epoch if epoch != 1.0 else float(self.app.session)
                with self.assertRaisesRegex(Conflict, "^Application session changed; refresh before acting$"):
                    await self.lease.act(request)
        self.assertFalse(self.app.view()["button"]["down"])
        self.assertEqual(self.app.view()["command_events"], [])

    async def test_internal_transport_callbacks_are_refused_from_the_browser(self):
        owner = self.lease.acquire(None)
        self.app.action("connect")
        before = self.app.view()
        for name in ("live_start", "live_connected", "live_disconnected", "command_result", "horn_result"):
            with self.subTest(action=name):
                with self.assertRaisesRegex(ValueError, "^Transport callbacks are internal application inputs$"):
                    await self.lease.act(self.request(owner, name, name, session=self.app.session,
                                                      attempt=1, index=0, success=True))
        self.assertEqual(self.app.view(), before)
        self.assertEqual(self.live.calls, [])

    async def test_malformed_requests_are_refused_before_acting(self):
        owner = self.lease.acquire(None)
        cases = {
            "missing controller": ({"id": "a", "action": "simulator_start"}, KeyError),
            "missing action": ({"controller": owner, "id": "a"}, KeyError),
            "unnamed action": (self.request(owner, "a", 7), ValueError),
            "long action": (self.request(owner, "a", "x" * 65), ValueError),
            "unknown controller": (self.request("intruder", "a", "simulator_start"), ValueError),
            "empty identity": (self.request(owner, "", "simulator_start"), ValueError),
            "long identity": (self.request(owner, "x" * 129, "simulator_start"), ValueError),
            "numeric identity": (self.request(owner, 5, "simulator_start"), ValueError),
        }
        for label, (request, error) in cases.items():
            with self.subTest(label):
                with self.assertRaises(error):
                    await self.lease.act(request)
        self.assertEqual(self.app.mode, "idle")

    async def test_request_waiting_behind_another_is_refused_if_the_lease_expired_meanwhile(self):
        from eucwatch.lease import ControllerExpired
        owner = self.lease.acquire(None)
        self.live.gate = asyncio.Event()
        first = asyncio.create_task(self.lease.act(self.request(owner, "start", "simulator_start")))
        while not self.live.calls:
            await asyncio.sleep(0)
        waiting = asyncio.create_task(self.lease.act(self.request(owner, "press", "button_down")))
        await asyncio.sleep(0)
        self.clock.advance(10.5)
        self.assertIsNotNone(self.lease.acquire(None))
        self.live.gate.set()
        await first
        with self.assertRaisesRegex(ControllerExpired, "^Controller expired while action was waiting$"):
            await waiting
        self.assertFalse(self.app.view()["button"]["down"])

    async def act(self, owner, action, /, **payload):
        self.sequence = getattr(self, "sequence", 0) + 1
        return await self.lease.act(self.request(owner, str(self.sequence), action, **payload))

    async def test_live_actions_route_to_the_live_session(self):
        owner = self.lease.acquire(None)
        state = await self.act(owner, "live_discover")
        self.assertEqual(self.live.calls, [("discover",)])
        self.assertEqual(state["live"], {"calls": 1})
        await self.act(owner, "live_select", address="AA:BB")
        await self.act(owner, "live_disconnect")
        self.assertEqual(self.live.calls, [("discover",), ("connect", "AA:BB"), ("disconnect",)])
        with self.assertRaises(KeyError):
            await self.act(owner, "live_select")
        self.assertEqual(self.app.mode, "idle")

    async def test_listed_actions_disconnect_the_live_session_first(self):
        fixture = Path("experiments/laptop-feasibility/evidence/fixture-recording.jsonl").read_text()
        owner = self.lease.acquire(None)
        for name, payload in (("simulator_start", {}), ("stop", {}), ("connect", {}), ("disconnect", {}),
                              ("replay_start", {"recording": fixture, "name": "Imported fixture"})):
            with self.subTest(action=name):
                self.live.calls.clear()
                state = await self.act(owner, name, **payload)
                self.assertEqual(self.live.calls, [("disconnect",)])
        self.assertEqual(state["mode"], "replay")
        for name in ("interact", "replay_step"):
            with self.subTest(action=name):
                self.live.calls.clear()
                await self.act(owner, name)
                self.assertEqual(self.live.calls, [])

    async def test_scenario_actions_route_to_the_scenario_library(self):
        owner = self.lease.acquire(None)
        with self.assertRaisesRegex(ValueError, "^Save or review a scenario before export$"):
            await self.act(owner, "scenario_start")
        self.assertEqual(self.live.calls, [])  # A missing definition never disconnects.
        with self.assertRaisesRegex(ValueError, "^Unknown scenario action$"):
            await self.act(owner, "scenario_unknown")
        state = await self.act(owner, "scenario_save", name="Road test")
        self.assertEqual(state["scenario"]["definition"]["name"], "Road test")
        await self.act(owner, "scenario_export")
        reviewed = dict(state["scenario"]["definition"], name="Reviewed")
        state = await self.act(owner, "scenario_review", content=json.dumps(reviewed))
        self.assertEqual(state["scenario"]["preview"]["name"], "Reviewed")
        state = await self.act(owner, "scenario_start")
        self.assertEqual(self.live.calls, [("disconnect",)])
        self.assertEqual((state["mode"], state["controlled"]), ("simulator", True))
        state = await self.act(owner, "scenario_step")
        self.assertEqual(state["scenario"]["position"], 1)
