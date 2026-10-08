"""Actual application ownership and serialized Nordic UART bytes, with fake BLE."""

import asyncio
import unittest
from types import SimpleNamespace

from eucwatch import Application, ManualClock
from eucwatch.nordic import NusTransport
from eucwatch.transfer_protocol import NUS_NOTIFY, NUS_SERVICE, NUS_WRITE, encode


class FakeScanner:
    @staticmethod
    async def discover(**kwargs):
        device = SimpleNamespace(address="watch-1", name="P22")
        advertisement = SimpleNamespace(
            local_name="Dedicated watch", service_uuids=[NUS_SERVICE], rssi=-40
        )
        return {device.address: (device, advertisement)}


class FakeClient:
    def __init__(self, device, **kwargs):
        self.is_connected = False
        self.callback = kwargs["disconnected_callback"]
        self.write = SimpleNamespace(
            uuid=NUS_WRITE,
            service_uuid=NUS_SERVICE,
            properties=["write-without-response"],
        )
        self.notify = SimpleNamespace(
            uuid=NUS_NOTIFY, service_uuid=NUS_SERVICE, properties=["notify"]
        )
        self.services = SimpleNamespace(
            get_service=lambda uuid: object(),
            get_characteristic=lambda uuid: (
                self.write if uuid == NUS_WRITE else self.notify
            ),
        )
        self.writes = []
        self.buffer = b""
        self.receiver = None
        self.respond = True

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, characteristic, callback, **kwargs):
        self.receiver = callback

    async def stop_notify(self, characteristic):
        pass

    async def write_gatt_char(self, characteristic, data, *, response):
        self.writes.append((bytes(data), response))
        self.buffer += bytes(data)
        if self.buffer.endswith(b"\n"):
            self.buffer = b""
            if self.respond:
                line = encode({"ok": True, "op": "abort", "aborted": True})
                self.receiver(characteristic, line[:7])
                self.receiver(characteristic, line[7:])


class NordicTests(unittest.IsolatedAsyncioTestCase):
    def application(self):
        application = Application(clock=ManualClock())
        application.action("simulator_configure", speed_kmh=0)
        application.action("simulator_start")
        application.action("swipe", direction="down", from_top=True)
        application.action("transfer_begin")
        return application

    async def test_explicit_discovery_connect_and_chunked_request_have_no_wheel_effects(
        self,
    ):
        app = self.application()
        transport = NusTransport(
            app,
            SimpleNamespace(client=None, worker=None, desired=False),
            scanner=FakeScanner,
            client_factory=FakeClient,
        )
        devices = await transport.discover()
        self.assertEqual(devices[0]["address"], "watch-1")
        await transport.connect("watch-1")
        response = await transport.exchange(encode({"op": "abort"}))
        self.assertEqual(response, encode({"ok": True, "op": "abort", "aborted": True}))
        client = transport.client
        self.assertTrue(
            all(len(data) <= 20 and mode is False for data, mode in client.writes)
        )
        self.assertEqual(app.view()["command_events"], [])
        await transport.close()
        self.assertFalse(client.is_connected)

    async def test_timeout_discards_old_notification_and_requires_new_explicit_connection(
        self,
    ):
        app = self.application()
        transport = NusTransport(
            app,
            SimpleNamespace(client=None, worker=None, desired=False),
            scanner=FakeScanner,
            client_factory=FakeClient,
            timeout=0.02,
        )
        await transport.discover()
        await transport.connect("watch-1")
        old = transport.client
        old.respond = False
        with self.assertRaises(TimeoutError):
            await transport.exchange(encode({"op": "abort"}))
        self.assertFalse(old.is_connected)
        old.receiver(None, encode({"ok": True, "op": "abort", "aborted": True}))
        with self.assertRaises(OSError):
            await transport.exchange(encode({"op": "abort"}))
        await transport.connect("watch-1")
        old.receiver(None, b"poison\n")
        self.assertEqual(
            await transport.exchange(encode({"op": "abort"})),
            encode({"ok": True, "op": "abort", "aborted": True}),
        )
        await transport.close()

    async def test_wheel_ownership_blocks_all_nordic_access_and_discovered_write_properties_are_required(
        self,
    ):
        app = self.application()
        live = SimpleNamespace(client=object(), worker=None, desired=False)
        transport = NusTransport(
            app, live, scanner=FakeScanner, client_factory=FakeClient
        )
        with self.assertRaises(ValueError):
            await transport.discover()
        live.client = None
        await transport.discover()

        class MissingWrite(FakeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.write.properties = ["read"]

        transport.client_factory = MissingWrite
        with self.assertRaises(ValueError):
            await transport.connect("watch-1")
        self.assertIsNone(transport.client)
        await transport.close()

    async def test_request_response_mode_is_explicit_and_oversized_response_fails_closed(
        self,
    ):
        app = self.application()

        class RequestWrite(FakeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.write.properties = ["write"]

        transport = NusTransport(
            app,
            SimpleNamespace(client=None, worker=None, desired=False),
            scanner=FakeScanner,
            client_factory=RequestWrite,
        )
        await transport.discover()
        await transport.connect("watch-1")
        await transport.exchange(encode({"op": "abort"}))
        self.assertTrue(all(mode is True for _, mode in transport.client.writes))
        old = transport.client

        async def oversized(*args, **kwargs):
            old.receiver(None, b"x" * 513)

        old.write_gatt_char = oversized
        with self.assertRaises(OSError):
            await transport.exchange(encode({"op": "abort"}))
        self.assertFalse(old.is_connected)
        await transport.close()

    async def test_ended_application_epoch_cancels_pending_response_and_old_callbacks_are_inert(
        self,
    ):
        app = self.application()
        transport = NusTransport(
            app,
            SimpleNamespace(client=None, worker=None, desired=False),
            scanner=FakeScanner,
            client_factory=FakeClient,
            timeout=0.1,
        )
        await transport.discover()
        await transport.connect("watch-1")
        client = transport.client
        client.respond = False
        pending = asyncio.create_task(transport.exchange(encode({"op": "abort"})))
        await asyncio.sleep(0)
        app.action("transfer_return")
        transport.tick()
        client.receiver(None, encode({"ok": True, "op": "abort", "aborted": True}))
        with self.assertRaises(OSError):
            await pending
        self.assertFalse(client.is_connected)
        self.assertEqual(app.view()["command_events"], [])
        await transport.close()

    async def test_blocked_chunk_has_bounded_timeout_and_uncertain_cleanup_retains_client(
        self,
    ):
        app = self.application()

        class Blocked(FakeClient):
            async def write_gatt_char(self, *args, **kwargs):
                self.writes.append((bytes(args[1]), kwargs["response"]))
                await asyncio.Event().wait()

            async def disconnect(self):
                raise OSError("Controlled failed disconnect")

        transport = NusTransport(
            app,
            SimpleNamespace(client=None, worker=None, desired=False),
            scanner=FakeScanner,
            client_factory=Blocked,
            timeout=0.02,
        )
        await transport.discover()
        await transport.connect("watch-1")
        client = transport.client
        with self.assertRaises(TimeoutError):
            await transport.exchange(encode({"op": "abort"}))
        self.assertEqual(len(client.writes), 1)
        self.assertIs(transport.client, client)
        self.assertIn("unknown", transport.status()["error"])
        with self.assertRaises(ValueError):
            await transport.discover()
        await transport.close()
