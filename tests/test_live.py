"""Live session acceptance with controlled transport, never real hardware."""

import asyncio
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.recording import Recorder, Replay

ADDRESS = "00:11:22:33:44:55"
SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"
SOURCE_FRAME = bytes.fromhex(
    "".join(
        json.loads(line)["raw_hex"]
        for line in (
            Path(__file__).resolve().parents[1]
            / "experiments/laptop-feasibility/evidence/fixture-recording.jsonl"
        )
        .read_text()
        .splitlines()[:5]
    )
)


class Scanner:
    def __init__(self):
        self.device = SimpleNamespace(address=ADDRESS, name="Selected wheel")
        self.calls = []

    async def discover(self, **options):
        self.calls.append(options)
        advertisement = SimpleNamespace(
            local_name="Selected wheel", rssi=-76, service_uuids=[SERVICE]
        )
        return {ADDRESS: (self.device, advertisement)}


class Client:
    def __init__(self, device, *, disconnected_callback, **options):
        self.device = device
        self.disconnected_callback = disconnected_callback
        self.is_connected = False
        self.calls = []
        self.notification = None
        self.characteristic = SimpleNamespace(
            uuid=CHARACTERISTIC, service_uuid=SERVICE, properties=["notify", "write"]
        )
        self.services = SimpleNamespace(
            get_service=lambda uuid: (
                SimpleNamespace(uuid=SERVICE) if uuid == SERVICE else None
            ),
            get_characteristic=lambda uuid: (
                self.characteristic if uuid == CHARACTERISTIC else None
            ),
        )

    async def connect(self):
        self.calls.append("connect")
        self.is_connected = True

    async def start_notify(self, characteristic, callback, **options):
        self.calls.append(("subscribe", characteristic.uuid, options))
        self.notification = callback

    async def disconnect(self):
        self.calls.append("disconnect")
        self.is_connected = False
        self.disconnected_callback(self)

    def emit(self, raw):
        self.notification(self.characteristic, bytearray(raw))

    def lose_link(self):
        self.is_connected = False
        self.disconnected_callback(self)


class Clients:
    def __init__(self):
        self.created = []

    def __call__(self, device, **options):
        client = Client(device, **options)
        self.created.append(client)
        return client


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_invalidates_old_transport_token_and_recovers_only_with_fresh_bytes(
        self,
    ):
        clock = ManualClock()
        app = Application(clock=clock)
        clients = Clients()
        live = LiveSession(
            app, scanner=Scanner(), client_factory=clients, reconnect_delay=0
        )
        await live.discover()
        try:
            await live.connect(ADDRESS)
            first = clients.created[0]
            first.emit(SOURCE_FRAME)
            clock.advance(60, suspended=True)
            live.tick()
            self.assertFalse(app.view()["fresh"])
            self.assertEqual(app.view()["diagnostics"]["resume_events"], 1)
            async with asyncio.timeout(1):
                while live.status()["link"] != "subscribed":
                    await asyncio.sleep(0.001)
            first.emit(SOURCE_FRAME)
            self.assertFalse(app.view()["fresh"])
            clients.created[1].emit(SOURCE_FRAME)
            self.assertTrue(app.view()["fresh"])
            self.assertEqual(live.status()["valid_frames"], 2)
        finally:
            await live.close()

    async def test_gatt_identifiers_alone_do_not_verify_sherman_l_identity(self):
        app = Application(clock=ManualClock())
        clients = Clients()
        live = LiveSession(app, scanner=Scanner(), client_factory=clients)
        await live.discover()
        try:
            await live.connect(ADDRESS)
            unrelated = bytearray(SOURCE_FRAME[:-4])
            unrelated[28:30] = (5010).to_bytes(2, "big")
            clients.created[0].emit(
                bytes(unrelated) + zlib.crc32(unrelated).to_bytes(4, "big")
            )
            self.assertFalse(app.view()["fresh"])
            self.assertIsNone(live.status()["firmware"])
            self.assertEqual(live.status()["rejected_frames"], 1)
            clients.created[0].emit(SOURCE_FRAME)
            self.assertTrue(app.view()["fresh"])
            self.assertEqual(live.status()["firmware"], "006.0.03")
        finally:
            await live.close()

    async def test_uncertain_cleanup_blocks_a_second_ble_client_until_disconnect_succeeds(
        self,
    ):
        app = Application(clock=ManualClock())
        clients = Clients()
        live = LiveSession(app, scanner=Scanner(), client_factory=clients)
        await live.discover()
        await live.connect(ADDRESS)
        first = clients.created[0]
        disconnect = first.disconnect

        async def fail():
            raise ConnectionError("Controlled cleanup failure")

        first.disconnect = fail
        try:
            await live.disconnect()
            self.assertEqual(live.status()["link"], "failed")
            self.assertIn("cleanup failed", live.status()["error"])
            await live.connect(ADDRESS)
            self.assertEqual(len(clients.created), 1)
            self.assertFalse(app.view()["connected"])
            first.disconnect = disconnect
            await live.disconnect()
            self.assertFalse(first.is_connected)
            await live.connect(ADDRESS)
            self.assertEqual(len(clients.created), 2)
            self.assertFalse(app.view()["fresh"])
        finally:
            first.disconnect = disconnect
            await live.close()

    async def test_automatic_reconnect_has_a_bounded_number_of_failed_attempts(self):
        app = Application(clock=ManualClock())
        clients = Clients()

        def factory(device, **options):
            client = clients(device, **options)
            if len(clients.created) > 1:

                async def fail():
                    raise ConnectionError("Controlled unavailable wheel")

                client.connect = fail
            return client

        live = LiveSession(
            app,
            scanner=Scanner(),
            client_factory=factory,
            reconnect_delay=0,
            reconnect_attempts=2,
        )
        await live.discover()
        try:
            await live.connect(ADDRESS)
            clients.created[0].emit(SOURCE_FRAME)
            clients.created[0].lose_link()
            async with asyncio.timeout(1):
                while live.status()["active"]:
                    await asyncio.sleep(0.001)
            self.assertEqual(len(clients.created), 3)
            self.assertEqual(live.status()["link"], "failed")
            self.assertIn("ConnectionError", live.status()["error"])
            self.assertFalse(app.view()["connected"])
            self.assertFalse(app.view()["fresh"])
        finally:
            await live.close()

    async def test_cancelled_connection_and_repeated_disconnect_wait_for_transport_cleanup(
        self,
    ):
        started, cleaning, released = asyncio.Event(), asyncio.Event(), asyncio.Event()
        clients = Clients()

        def factory(device, **options):
            client = clients(device, **options)

            async def connect():
                client.is_connected = True
                started.set()
                await asyncio.Event().wait()

            async def disconnect():
                cleaning.set()
                await released.wait()
                client.is_connected = False
                client.disconnected_callback(client)

            client.connect = connect
            client.disconnect = disconnect
            return client

        app = Application(clock=ManualClock())
        live = LiveSession(app, scanner=Scanner(), client_factory=factory)
        await live.discover()
        attempt = asyncio.create_task(live.connect(ADDRESS))
        await started.wait()
        attempt.cancel()
        await cleaning.wait()
        stopping = asyncio.create_task(live.disconnect())
        await asyncio.sleep(0.01)
        released.set()
        await asyncio.gather(attempt, stopping, return_exceptions=True)
        self.assertFalse(clients.created[0].is_connected)
        self.assertFalse(app.view()["connected"])
        self.assertEqual(live.status()["link"], "disconnected")
        self.assertEqual(len(clients.created), 1)
        await live.close()

    async def test_mode_change_closes_live_transport_and_old_callbacks_cannot_revive_it(
        self,
    ):
        app = Application(clock=ManualClock())
        clients = Clients()
        live = LiveSession(
            app, scanner=Scanner(), client_factory=clients, reconnect_delay=0
        )
        await live.discover()
        try:
            await live.connect(ADDRESS)
            client = clients.created[0]
            client.emit(SOURCE_FRAME)
            app.action("simulator_configure", voltage_V=135, speed_kmh=12)
            expected = app.action("simulator_start", controlled=True)["dashboard"]
            live.tick()
            async with asyncio.timeout(1):
                while client.is_connected or live.status()["link"] != "disconnected":
                    await asyncio.sleep(0.001)
            self.assertEqual(live.status()["link"], "disconnected")
            client.emit(SOURCE_FRAME)
            client.lose_link()
            self.assertEqual(app.view()["mode"], "simulator")
            self.assertEqual(app.view()["dashboard"], expected)
            self.assertEqual(len(clients.created), 1)
        finally:
            await live.close()

    async def test_live_raw_capture_replays_through_the_same_dashboard_and_session_rules(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            clock = ManualClock()
            recorder = Recorder(Path(directory) / "controlled-live.jsonl")
            app = Application(clock=clock, event_sink=recorder.record)
            clients = Clients()
            live = LiveSession(
                app, scanner=Scanner(), client_factory=clients, reconnect_delay=0
            )
            await live.discover()
            observed = []
            try:
                await live.connect(ADDRESS)
                first = clients.created[0]
                for raw in (SOURCE_FRAME[:20], SOURCE_FRAME[20:]):
                    first.emit(raw)
                    observed.append(app.view()["dashboard"])
                    clock.advance(0.02)
                clock.advance(1)
                first.emit(SOURCE_FRAME[:-1] + b"\0")
                observed.append(app.view()["dashboard"])
                first.lose_link()
                async with asyncio.timeout(1):
                    while live.status()["link"] != "subscribed":
                        await asyncio.sleep(0.001)
                first.emit(SOURCE_FRAME)
                observed.append(app.view()["dashboard"])
                clients.created[1].emit(SOURCE_FRAME)
                observed.append(app.view()["dashboard"])
            finally:
                await live.close()
                await recorder.close()
            self.assertIsNone(recorder.status()["error"])
            replay = Replay.load(recorder.path)
            playback = Application(clock=ManualClock())
            playback.action("replay_start", recording=replay)
            replayed = []
            for row in replay.rows:
                state = playback.action("replay_step")
                if row["event"] == "notification":
                    replayed.append(state["dashboard"])
            self.assertEqual(replayed, observed)
            self.assertEqual(playback.view()["diagnostics"]["valid_frames"], 2)
            self.assertEqual(playback.view()["mode"], "replay")

    async def test_missing_notification_support_and_connect_timeout_fail_visibly(self):
        for failure in ("no_notify", "timeout"):
            with self.subTest(failure=failure):
                app = Application(clock=ManualClock())
                clients = Clients()

                def factory(device, clients=clients, failure=failure, **options):
                    client = clients(device, **options)
                    if failure == "no_notify":
                        client.characteristic.properties = ["write"]
                    else:

                        async def connect():
                            client.calls.append("connect")
                            await asyncio.Event().wait()

                        client.connect = connect
                    return client

                live = LiveSession(
                    app,
                    scanner=Scanner(),
                    client_factory=factory,
                    transport_timeout=0.02,
                )
                await live.discover()
                try:
                    async with asyncio.timeout(1):
                        status = await live.connect(ADDRESS)
                    self.assertEqual(status["link"], "failed")
                    self.assertIn(
                        "FFE0/FFE1" if failure == "no_notify" else "TimeoutError",
                        status["error"],
                    )
                    self.assertFalse(app.view()["connected"])
                    self.assertFalse(app.view()["fresh"])
                    self.assertEqual(
                        clients.created[0].calls, ["connect", "disconnect"]
                    )
                finally:
                    await live.close()

    async def test_source_loss_invalidates_immediately_then_reconnects_with_fresh_session(
        self,
    ):
        app = Application(clock=ManualClock())
        clients = Clients()
        live = LiveSession(
            app, scanner=Scanner(), client_factory=clients, reconnect_delay=0
        )
        await live.discover()
        try:
            await live.connect(ADDRESS)
            first = clients.created[0]
            first.emit(SOURCE_FRAME)
            previous_session = app.view()["session"]
            first.lose_link()
            self.assertFalse(app.view()["fresh"])
            self.assertFalse(app.view()["connected"])
            self.assertGreater(app.view()["session"], previous_session)
            async with asyncio.timeout(1):
                while live.status()["link"] != "subscribed":
                    await asyncio.sleep(0.001)
            second = clients.created[1]
            self.assertFalse(first.is_connected)
            self.assertFalse(app.view()["fresh"])
            first.emit(SOURCE_FRAME)
            first.lose_link()
            self.assertTrue(app.view()["connected"])
            self.assertFalse(app.view()["fresh"])
            second.emit(SOURCE_FRAME)
            self.assertTrue(app.view()["fresh"])
            self.assertEqual(live.status()["reconnections"], 1)
            self.assertEqual(live.status()["valid_frames"], 2)
            self.assertEqual(len(clients.created), 2)
        finally:
            await live.close()

    async def test_discovery_failure_is_visible_without_starting_a_wheel_session(self):
        class UnavailableScanner:
            async def discover(self, **options):
                raise PermissionError("Controlled BlueZ denial")

        app = Application(clock=ManualClock())
        live = LiveSession(app, scanner=UnavailableScanner())
        self.assertEqual(await live.discover(), [])
        self.assertEqual(live.status()["link"], "failed")
        self.assertIn("PermissionError", live.status()["error"])
        self.assertEqual(app.view()["mode"], "idle")
        await live.close()

    async def test_selected_live_notifications_use_actual_decoder_freshness_and_capture(
        self,
    ):
        clock = ManualClock()
        events = []
        app = Application(clock=clock, event_sink=events.append)
        clients = Clients()
        live = LiveSession(app, scanner=Scanner(), client_factory=clients)
        await live.discover()
        try:
            status = await live.connect(ADDRESS)
            self.assertEqual(status["link"], "subscribed")
            self.assertEqual(app.view()["mode"], "live")
            self.assertFalse(app.view()["fresh"])
            client = clients.created[0]
            for pos in range(0, len(SOURCE_FRAME), 20):
                client.emit(SOURCE_FRAME[pos : pos + 20])
                clock.advance(0.02)
            state = app.view()
            self.assertEqual(state["dashboard"]["wheel_battery_percent"], "97")
            self.assertEqual(state["dashboard"]["average_cell_voltage"], "4.09")
            self.assertEqual(state["telemetry"]["firmware"], "006.0.03")
            self.assertTrue(state["fresh"])
            self.assertEqual(live.status()["notifications"], 5)
            self.assertEqual(live.status()["valid_frames"], 1)
            self.assertAlmostEqual(live.status()["maximum_notification_gap_s"], 0.02)
            clock.advance(1)
            client.emit(SOURCE_FRAME[:-1] + b"\0")
            self.assertFalse(app.view()["fresh"])
            self.assertGreater(live.status()["rejected_frames"], 0)
            self.assertEqual(events[-1]["event"], "notification")
            self.assertEqual(events[-1]["raw_hex"], (SOURCE_FRAME[:-1] + b"\0").hex())
            client.emit(SOURCE_FRAME)
            self.assertTrue(app.view()["fresh"])
            self.assertEqual(
                client.calls,
                [
                    "connect",
                    (
                        "subscribe",
                        CHARACTERISTIC,
                        {"bluez": {"use_start_notify": True}},
                    ),
                ],
            )
        finally:
            await live.close()
        self.assertFalse(app.view()["fresh"])
        self.assertFalse(client.is_connected)

    async def test_explicit_discovery_does_not_connect_or_change_riding_state(self):
        scanner = Scanner()
        clients = []
        app = Application(clock=ManualClock())
        live = LiveSession(
            app,
            scanner=scanner,
            client_factory=lambda *args, **kw: clients.append(args),
        )
        self.assertEqual(live.status()["devices"], [])
        self.assertEqual(scanner.calls, [])
        devices = await live.discover()
        self.assertEqual(devices[0]["address"], ADDRESS)
        self.assertEqual(devices[0]["name"], "Selected wheel")
        self.assertEqual(devices[0]["rssi"], -76)
        self.assertEqual(clients, [])
        self.assertEqual(app.view()["mode"], "idle")
        with self.assertRaises(ValueError):
            await live.connect("00:00:00:00:00:00")
        self.assertEqual(clients, [])
        await live.close()
