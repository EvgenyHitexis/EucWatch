"""Actual application commands through the real session and a fake BLE boundary."""
from preset_fixture import save_preset


import asyncio
import unittest
from bleak.exc import BleakError

from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.live_control import LiveControl
from test_control import settings_frame
from test_live import ADDRESS, CHARACTERISTIC, SOURCE_FRAME, Client, Scanner


class WritingClient(Client):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.characteristic.properties = ["notify", "write-without-response"]
        self.characteristic.max_write_without_response_size = 20
        self.writes = []
        self.behavior = None

    async def write_gatt_char(self, characteristic, data, *, response):
        self.writes.append((characteristic.uuid, bytes(data), response))
        if self.behavior:
            await self.behavior(bytes(data))


class LiveControlTests(unittest.IsolatedAsyncioTestCase):
    async def prepared(self, **options):
        self.clock = ManualClock()
        self.app = Application(clock=self.clock, command_output=lambda row: self.control.submit(row))
        save_preset(self.app, slot=1, name="Road", pedal_sensitivity=31, dynamic_assist=26)
        self.clients = []
        def factory(*args, **kwargs):
            client = WritingClient(*args, **kwargs)
            self.clients.append(client)
            return client
        self.live = LiveSession(self.app, scanner=Scanner(), client_factory=factory, reconnect_attempts=0)
        self.control = LiveControl(self.live, self.app, **options)
        await self.live.discover()
        await self.live.connect(ADDRESS)
        self.client = self.clients[-1]
        self.client.emit(SOURCE_FRAME)

    async def asyncTearDown(self):
        if hasattr(self, "control"):
            await self.control.close()
        if hasattr(self, "live"):
            await self.live.close()

    async def until(self, predicate):
        async with asyncio.timeout(1):
            while not predicate():
                await asyncio.sleep(0)

    async def test_serial_live_writes_omit_dip_and_require_two_fresh_actual_readbacks(self):
        await self.prepared()
        state = self.app.action("preset_apply", slot=1)
        self.assertEqual(state["preset_attempt"]["status"], "submitting")
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")
        self.assertEqual(self.client.writes, [
            (CHARACTERISTIC, bytes.fromhex("4c6441700f01028080801ff753d033"), False),
            (CHARACTERISTIC, bytes.fromhex("4c6441701f010280808080808080808080808080"), False),
            (CHARACTERISTIC, bytes.fromhex("8080808080801aba3c7b2f"), False),
        ])
        self.assertIsNone(self.app.view()["confirmed_preset"])
        self.clock.advance(0.1)
        self.client.emit(settings_frame())
        self.assertIsNone(self.app.view()["confirmed_preset"])
        self.clock.advance(0.1)
        self.client.emit(settings_frame())
        self.assertEqual(self.app.view()["preset_attempt"]["status"], "Confirmed")
        self.assertEqual(len(self.clients), 1)

    async def test_partial_failure_stops_remaining_chunks_and_optional_settings(self):
        await self.prepared()
        save_preset(self.app, slot=1, pedal_dip_compensation=11)
        started, release = asyncio.Event(), asyncio.Event()
        async def fail_second(_packet):
            if len(self.client.writes) == 2:
                started.set()
                await release.wait()
                raise OSError("Controlled setting write failed")
        self.client.behavior = fail_second
        self.app.action("preset_apply", slot=1)
        await started.wait()
        for _ in range(2):
            self.clock.advance(0.1)
            self.client.emit(settings_frame(assist=25))
        release.set()
        await self.until(lambda: not self.app.view()["preset_attempt"]["pending"])
        state = self.app.view()
        self.assertEqual(state["preset_attempt"]["status"], "Partially applied")
        self.assertIn("Controlled setting write failed", state["preset_attempt"]["reason"])
        self.assertEqual(len(self.client.writes), 2)
        self.assertEqual(state["preset_attempt"]["fields"]["pedal_sensitivity"]["state"], "confirmed")
        self.assertEqual(state["preset_attempt"]["fields"]["dynamic_assist"]["state"], "unknown")
        self.clock.advance(0.1)
        self.client.emit(settings_frame(dip=11))
        self.assertEqual(self.app.view()["preset_attempt"]["status"], "Partially applied")
        self.assertEqual(len(self.client.writes), 2)

    async def test_discovered_characteristic_must_explicitly_support_evidenced_chunks(self):
        await self.prepared()
        characteristic = self.client.characteristic
        for changes in ({"properties": ["notify", "write"]}, {"max_write_without_response_size": 19}, {"max_write_without_response_size": None}, {"service_uuid": "unrelated"}):
            with self.subTest(changes=changes):
                characteristic.properties = ["notify", "write-without-response"]
                characteristic.max_write_without_response_size = 20
                characteristic.service_uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
                for key, value in changes.items():
                    setattr(characteristic, key, value)
                state = self.app.action("preset_apply", slot=1)
                self.assertFalse(state["preset_attempt"]["pending"])
                self.assertEqual(state["preset_attempt"]["status"], "Not confirmed")
                self.assertIn("write-without-response", state["preset_attempt"]["reason"])
                self.assertEqual(self.client.writes, [])

    async def test_transport_timeout_finishes_attempt_and_never_retries(self):
        await self.prepared(write_timeout=0.01)
        async def stalled(_packet):
            await asyncio.Event().wait()
        self.client.behavior = stalled
        self.app.action("preset_apply", slot=1)
        await self.until(lambda: not self.app.view()["preset_attempt"]["pending"])
        state = self.app.view()
        self.assertIn("TimeoutError", state["preset_attempt"]["reason"])
        self.assertEqual(len(self.client.writes), 1)
        self.assertIsNone(state["confirmed_preset"])
        self.clock.advance(0.2)
        self.client.emit(SOURCE_FRAME)
        self.assertEqual(len(self.client.writes), 1)

    async def test_stale_queued_intent_is_discarded_and_a_new_explicit_attempt_can_submit(self):
        await self.prepared()
        self.app.action("preset_apply", slot=1)
        self.clock.advance(1)
        self.control.tick()
        await asyncio.sleep(0)
        self.assertFalse(self.app.view()["preset_attempt"]["pending"])
        self.assertEqual(self.client.writes, [])
        self.client.emit(SOURCE_FRAME)
        state = self.app.action("preset_apply", slot=1)
        self.assertTrue(state["preset_attempt"]["pending"])
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")
        self.assertEqual(len(self.client.writes), 3)

    async def test_close_discards_an_unstarted_intent_and_releases_pending_state(self):
        await self.prepared()
        self.app.action("preset_apply", slot=1)
        await self.control.close()
        self.assertEqual(self.client.writes, [])
        self.assertFalse(self.app.view()["preset_attempt"]["pending"])
        self.assertIn("closed", self.app.view()["preset_attempt"]["reason"].lower())

    async def test_staleness_during_a_write_cancels_it_and_does_not_send_remaining_settings(self):
        await self.prepared()
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def stalled(_packet):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.client.behavior = stalled
        self.app.action("preset_apply", slot=1)
        await started.wait()
        self.clock.advance(1)
        self.control.tick()
        await cancelled.wait()
        state = self.app.view()
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertIn("stale", state["preset_attempt"]["reason"])
        self.clock.advance(0.1)
        self.client.emit(settings_frame())
        self.assertIsNone(self.app.view()["confirmed_preset"])
        self.assertEqual(len(self.client.writes), 1)

    async def test_optional_dip_uses_its_exact_serial_chunks_and_confirmation_includes_it(self):
        await self.prepared()
        save_preset(self.app, slot=1, pedal_dip_compensation=11)
        self.app.action("preset_apply", slot=1)
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")
        self.assertEqual([len(data) for _uuid, data, _response in self.client.writes], [15, 20, 11, 20, 13])
        self.assertEqual((self.client.writes[3][1] + self.client.writes[4][1]).hex(), "4c6441702101028080808080808080808080808080808080808080800b672ed25c")
        for _ in range(2):
            self.clock.advance(0.1)
            self.client.emit(settings_frame(dip=10))
        self.assertIsNone(self.app.view()["confirmed_preset"])
        for _ in range(2):
            self.clock.advance(0.1)
            self.client.emit(settings_frame(dip=11))
        self.assertEqual(self.app.view()["preset_attempt"]["status"], "Confirmed")

    async def test_horn_uses_single_variant_and_busy_or_duplicate_presses_never_queue(self):
        await self.prepared()
        started, release = asyncio.Event(), asyncio.Event()
        async def stalled(_packet):
            started.set()
            await release.wait()
        self.client.behavior = stalled
        self.app.action("button_down")
        await started.wait()
        self.app.action("button_down")
        self.app.action("button_hold")
        self.app.action("button_up")
        state = self.app.action("button_down")
        self.assertIn("busy", state["horn_feedback"]["message"])
        self.assertEqual(self.client.writes, [(CHARACTERISTIC, bytes.fromhex("4c6b41700e0080808001ca87e66f"), False)])
        release.set()
        await self.until(lambda: len([row for row in self.app.view()["command_events"] if row["event"] == "result"]) == 2)
        self.assertEqual(len(self.client.writes), 1)
        self.app.action("button_up")
        self.app.action("button_down")
        await self.until(lambda: self.app.view()["horn_feedback"]["message"] == "Horn request sent")
        self.assertEqual(len(self.client.writes), 2)
        self.assertEqual(self.client.writes[1][1].hex(), "4c6b41700e0080808001ca87e66f")

    async def test_request_during_cancel_handoff_is_rejected_instead_of_stranding_an_intent(self):
        await self.prepared()
        self.app.action("preset_apply", slot=1)
        self.clock.advance(1)
        self.control.tick()
        self.client.emit(SOURCE_FRAME)
        state = self.app.action("preset_apply", slot=1)
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertIn("stopping", state["preset_attempt"]["reason"])
        await asyncio.sleep(0)
        self.assertEqual(self.client.writes, [])
        state = self.app.action("preset_apply", slot=1)
        self.assertTrue(state["preset_attempt"]["pending"])
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")

    async def test_characteristic_lookup_failure_is_visible_and_does_not_escape_application_action(self):
        await self.prepared()
        def unavailable(_uuid):
            raise BleakError("Controlled services unavailable")
        self.client.services.get_characteristic = unavailable
        state = self.app.action("preset_apply", slot=1)
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertIn("Controlled services unavailable", state["preset_attempt"]["reason"])
        self.assertEqual(self.client.writes, [])

    async def test_disconnect_cancels_old_client_write_and_late_readback_cannot_confirm(self):
        await self.prepared()
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def stalled(_packet):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.client.behavior = stalled
        state = self.app.action("preset_apply", slot=1)
        await started.wait()
        self.client.lose_link()
        self.control.tick()
        await cancelled.wait()
        self.client.emit(settings_frame())
        self.assertFalse(self.app.view()["preset_attempt"]["pending"])
        self.assertGreater(self.app.view()["session"], state["session"])
        self.assertIsNone(self.app.view()["confirmed_preset"])
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(len(self.clients), 1)

    async def test_overall_submission_deadline_precedes_confirmation_even_with_fresh_telemetry(self):
        await self.prepared()
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def stalled(_packet):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.client.behavior = stalled
        self.app.action("preset_apply", slot=1)
        await started.wait()
        for _ in range(10):
            self.clock.advance(0.5)
            self.client.emit(SOURCE_FRAME)
            self.control.tick()
        await cancelled.wait()
        state = self.app.view()
        self.assertTrue(state["fresh"])
        self.assertEqual(state["preset_attempt"]["reason"], "Submission timeout")
        self.assertIsNone(state["preset_attempt"]["submitted_s"])
        self.assertEqual(len(self.client.writes), 1)

    async def test_horn_is_blocked_through_live_confirmation_and_late_settings_keep_terminal_failure(self):
        await self.prepared()
        self.app.action("preset_apply", slot=1)
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")
        state = self.app.action("button_down")
        self.assertEqual(state["horn_feedback"]["message"], "Horn unavailable: preset applying")
        self.assertEqual(len(self.client.writes), 3)
        self.clock.advance(0.1)
        self.client.emit(settings_frame())
        self.clock.advance(1)
        state = self.app.view()
        self.assertFalse(state["preset_attempt"]["pending"])
        self.assertEqual(state["preset_attempt"]["status"], "Not confirmed")
        self.client.emit(settings_frame())
        self.app.action("button_up")
        self.assertEqual(len(self.client.writes), 3)
        self.assertIsNone(self.app.view()["confirmed_preset"])
        self.app.action("button_down")
        await self.until(lambda: self.app.view()["horn_feedback"]["message"] == "Horn request sent")
        self.assertEqual(len(self.client.writes), 4)

    async def test_direct_duplicate_or_altered_packet_cannot_bypass_exact_application_intent(self):
        await self.prepared()
        state = self.app.action("preset_apply", slot=1)
        row = next(row for row in state["command_events"] if row["event"] == "submission")
        with self.assertRaises(ValueError):
            self.control.submit({**row, "packet_hex": "4c6b41700e0080808001ca87e66f"})
        with self.assertRaises(ValueError):
            self.control.submit(row)
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")
        with self.assertRaises(ValueError):
            self.control.submit(row)
        self.assertEqual(len(self.client.writes), 3)

    async def test_watch_editor_uses_selected_client_and_fresh_external_settings(self):
        await self.prepared()
        self.client.emit(settings_frame(sensitivity=44, assist=55, dip=66))
        self.app.action("preset_begin", slot=4, source="watch")
        self.assertIsNone(self.app.view()["preset_draft"])
        self.assertEqual(self.client.writes, [])
        self.clock.advance(.1)
        self.client.emit(settings_frame(sensitivity=45, assist=56, dip=67))
        self.assertEqual(self.app.view()["preset_draft"]["dynamic_assist"], 56)
        self.app.action("preset_update", dynamic_assist=26, source="watch")
        await self.until(lambda: self.app.view()["preset_attempt"]["status"] == "confirming")
        self.assertEqual(b''.join(packet for _, packet, _ in self.client.writes).hex(),
                         "4c6441701f0102808080808080808080808080808080808080801aba3c7b2f")
        self.clock.advance(.1); self.client.emit(settings_frame(sensitivity=45, assist=27, dip=67))
        self.assertEqual(self.app.view()["preset_attempt"]["fields"]["dynamic_assist"]["state"], "mismatched")
        for _ in range(2):
            self.clock.advance(.1); self.client.emit(settings_frame(sensitivity=45, assist=26, dip=67))
        self.assertEqual(self.app.view()["preset_attempt"]["status"], "Confirmed")
        self.assertIsNone(self.app.view()["confirmed_preset"])
        self.assertEqual(self.app.view()["config"]["presets"][3]["dynamic_assist"], 26)

    async def test_editor_disconnect_during_chunk_stops_unsent_tail_and_cannot_resume(self):
        await self.prepared()
        self.app.action("preset_begin", slot=1, source="watch")
        self.clock.advance(.1); self.client.emit(settings_frame())
        entered, release = asyncio.Event(), asyncio.Event()
        async def interrupted(_packet):
            entered.set()
            await release.wait()
        self.client.behavior = interrupted
        self.app.action("preset_update", dynamic_assist=26, source="watch")
        await entered.wait()
        old = self.app.session
        self.app.action("live_disconnected", session=old)
        self.control.tick()
        release.set()
        await self.until(lambda: not self.app.view()["preset_attempt"]["pending"])
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(self.app.view()["preset_editor"]["status"], "unavailable")
        await self.live.connect(ADDRESS)
        replacement = self.clients[-1]
        replacement.emit(SOURCE_FRAME)
        self.clock.advance(.1); replacement.emit(settings_frame())
        self.app.receive(old, settings_frame())
        self.assertIsNone(self.app.view()["preset_draft"])
        self.assertEqual(replacement.writes, [])
        self.assertEqual(len(self.client.writes), 1)
