"""HTTP actions own async Nordic UART and saved completion, without radio access."""

import unittest

from aiohttp.test_utils import TestClient, TestServer
from eucwatch import Application, ManualClock
from eucwatch.configuration import default_configuration
from eucwatch.live import LiveSession
from eucwatch.nordic import NusTransport
from eucwatch.persistence import MemoryStore
from eucwatch.server import create_app
from eucwatch.simulator import Simulator
from eucwatch.transfer_protocol import SimulatedWatch, decode
from test_live import ADDRESS, Clients, Scanner
from test_nordic import FakeClient, FakeScanner


class NordicHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.application = Application(clock=ManualClock())
        self.watch = MemoryStore(default_configuration())
        self.endpoint = SimulatedWatch(self.watch)
        self.operations = []
        self.clients = []
        self.fault = {"commit": False, "finish": False, "disconnect": False}
        endpoint, operations, clients = self.endpoint, self.operations, self.clients
        fault = self.fault

        class Client(FakeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                clients.append(self)

            async def write_gatt_char(self, characteristic, data, *, response):
                self.writes.append((bytes(data), response))
                self.buffer += bytes(data)
                if self.buffer.endswith(b"\n"):
                    message, self.buffer = self.buffer, b""
                    operations.append(decode(message)["op"])
                    output = endpoint.exchange(message)
                    if fault.get(decode(message)["op"], False):
                        return
                    for offset in range(0, len(output), 20):
                        self.receiver(characteristic, output[offset : offset + 20])

            async def disconnect(self):
                operations.append("disconnect")
                if fault["disconnect"]:
                    raise OSError("Controlled failed watch disconnect")
                await super().disconnect()

        self.wheel_clients = Clients()
        self.live = LiveSession(
            self.application, scanner=Scanner(), client_factory=self.wheel_clients
        )
        self.nus = NusTransport(
            self.application,
            self.live,
            scanner=FakeScanner,
            client_factory=Client,
            timeout=0.2,
        )
        self.client = TestClient(
            TestServer(create_app(self.application, live=self.live, nus=self.nus))
        )
        await self.client.start_server()
        self.session = await (await self.client.get("/api/session")).json()
        self.headers = {
            "Origin": str(self.client.make_url("/")).rstrip("/"),
            "X-EucWatch-Key": self.session["credential"],
        }
        self.sequence = 0

    async def asyncTearDown(self):
        await self.client.close()

    async def action(self, name, expected=200, **payload):
        self.sequence += 1
        response = await self.client.post(
            "/api/action",
            headers=self.headers,
            json={
                "controller": self.session["controller"],
                "id": str(self.sequence),
                "epoch": self.application.session,
                "action": name,
                **payload,
            },
        )
        self.assertEqual(response.status, expected, await response.text())
        return await response.json()

    async def test_explicit_nordic_review_send_finishes_and_disconnects_before_exiting(
        self,
    ):
        await self.action("nordic_discover", expected=400)
        self.assertEqual(self.clients, [])
        await self.action("swipe", direction="down", from_top=True)
        await self.action("transfer_begin")
        state = await self.action("nordic_discover")
        self.assertEqual(state["nordic"]["devices"][0]["address"], "watch-1")
        state = await self.action("nordic_select", address="watch-1")
        self.assertTrue(state["nordic"]["connected"])
        self.assertIn("Dedicated watch", state["transfer"]["endpoint"])
        self.assertEqual(state["transfer"]["status"], "review")
        for action in (
            "live_discover",
            "simulator_start",
            "replay_start",
            "scenario_start",
        ):
            await self.action(action, expected=400)
        state = await self.action("transfer_send")
        self.assertEqual(state["mode"], "idle")
        self.assertEqual(state["config"], self.watch.load())
        self.assertFalse(state["fresh"])
        self.assertFalse(state["nordic"]["connected"])
        self.assertEqual(self.operations[-2:], ["finish", "disconnect"])
        self.assertEqual(state["command_events"], [])
        self.assertIsNone(state["confirmed_preset"])
        await self.action(
            "transfer_activate", expected=400, config=default_configuration()
        )

    async def enter_watch(self):
        await self.action("swipe", direction="down", from_top=True)
        await self.action("transfer_begin")
        await self.action("nordic_discover")
        return await self.action("nordic_select", address="watch-1")

    async def test_second_real_transfer_enters_cleanly_after_previous_completion(self):
        await self.enter_watch()
        await self.action("transfer_send")
        await self.enter_watch()
        state = await self.action("transfer_send")
        self.assertEqual(state["mode"], "idle")
        self.assertFalse(state["transfer"]["active"])
        self.assertEqual(self.operations.count("commit"), 2)
        self.assertEqual(state["config"], self.watch.load())

    async def test_lost_commit_ack_requires_reconnect_and_readback_without_second_commit(
        self,
    ):
        await self.enter_watch()
        self.fault["commit"] = True
        state = await self.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "unknown")
        self.assertEqual(state["mode"], "transfer")
        self.assertEqual(state["config"], default_configuration())
        self.assertFalse(state["nordic"]["connected"])
        await self.action("transfer_send", expected=400)
        self.fault["commit"] = False
        state = await self.action("nordic_select", address="watch-1")
        self.assertEqual(state["transfer"]["status"], "unknown")
        state = await self.action("transfer_reconcile")
        self.assertEqual(state["mode"], "idle")
        self.assertEqual(state["config"], self.watch.load())
        self.assertEqual(self.operations.count("commit"), 1)

    async def test_actual_transfer_from_live_reconnects_wheel_only_after_verified_nus_disconnect(
        self,
    ):
        await self.action("live_discover")
        await self.action("live_select", address=ADDRESS)
        wheel = self.wheel_clients.created[0]
        simulator = Simulator()
        simulator.configure({"speed_kmh": 0})
        wheel.emit(b"".join(simulator.notifications()))
        await self.enter_watch()
        self.assertFalse(wheel.is_connected)
        state = await self.action("transfer_send")
        self.assertEqual(state["mode"], "live")
        self.assertFalse(state["fresh"])
        self.assertFalse(self.clients[0].is_connected)
        self.assertEqual(len(self.wheel_clients.created), 2)
        wheel.emit(b"".join(simulator.notifications()))
        self.assertFalse(self.application.view()["fresh"])
        self.wheel_clients.created[1].emit(b"".join(simulator.notifications()))
        self.assertTrue(self.application.view()["fresh"])
        self.assertEqual(self.application.view()["command_events"], [])
        self.assertEqual(state["command_events"], [])

    async def test_verified_config_finish_loss_or_failed_disconnect_keeps_transfer_and_offers_return(
        self,
    ):
        await self.enter_watch()
        self.fault["finish"] = True
        state = await self.action("transfer_send")
        self.assertEqual(state["transfer"]["status"], "return_failed")
        self.assertEqual(state["mode"], "transfer")
        self.assertEqual(state["config"], self.watch.load())
        await self.action("transfer_send", expected=400)
        self.fault["finish"] = False
        await self.action("nordic_select", address="watch-1")
        self.fault["disconnect"] = True
        state = await self.action("transfer_return")
        self.assertEqual(state["mode"], "transfer")
        self.assertEqual(state["transfer"]["status"], "return_failed")
        await self.action("live_discover", expected=400)
        self.fault["disconnect"] = False
        await self.action("nordic_disconnect")
        await self.action("nordic_select", address="watch-1")
        state = await self.action("transfer_return")
        self.assertEqual(state["mode"], "idle")
        self.assertEqual(self.operations.count("commit"), 1)
