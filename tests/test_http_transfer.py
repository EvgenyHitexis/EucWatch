"""Transfer entry closes the selected wheel only after stopped validation."""
import unittest

from aiohttp.test_utils import TestClient, TestServer

from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.server import create_app
from eucwatch.simulator import Simulator
from test_live import Scanner, Clients, ADDRESS


class TransferHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_moving_refusal_preserves_link_stopped_entry_closes_and_return_reselects(self):
        app = Application(clock=ManualClock())
        clients = Clients()
        live = LiveSession(app, scanner=Scanner(), client_factory=clients)
        client = TestClient(TestServer(create_app(app, live=live)))
        await client.start_server()
        try:
            session = await (await client.get('/api/session')).json()
            headers = {'Origin': str(client.make_url('/')).rstrip('/'), 'X-EucWatch-Key': session['credential']}
            count = 0
            async def action(name, expected=200, **payload):
                nonlocal count
                count += 1
                response = await client.post('/api/action', headers=headers, json={
                    'controller': session['controller'], 'id': str(count), 'action': name, 'epoch':app.session, **payload})
                self.assertEqual(response.status, expected, await response.text())
                return await response.json()
            await action('live_discover')
            await action('live_select', address=ADDRESS)
            wheel = clients.created[0]
            simulator = Simulator()
            simulator.configure({'speed_kmh': 5})
            for raw in simulator.notifications():
                wheel.emit(raw)
            await action('swipe', direction='down')
            await action('transfer_begin', expected=400)
            self.assertTrue(wheel.is_connected)
            self.assertTrue(app.view()['fresh'])
            simulator.configure({'speed_kmh': 0})
            for raw in simulator.notifications():
                wheel.emit(raw)
            state = await action('transfer_begin')
            self.assertFalse(wheel.is_connected)
            self.assertEqual(state['mode'], 'transfer')
            self.assertFalse(state['fresh'])
            await action('transfer_cancel')
            state = await action('transfer_return')
            self.assertEqual(state['mode'], 'live')
            self.assertFalse(state['fresh'])
            self.assertEqual(len(clients.created), 2)
            wheel.emit(b''.join(simulator.notifications()))
            self.assertFalse(app.view()['fresh'])
            clients.created[1].emit(b''.join(simulator.notifications()))
            self.assertTrue(app.view()['fresh'])
            self.assertEqual(app.view()['command_events'], [])
        finally:
            await client.close()
