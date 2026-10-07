"""Live UI/backend boundary with controlled transport, no Bluetooth operations."""
import unittest
from aiohttp.test_utils import TestClient, TestServer
from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.server import create_app
from test_live import Scanner, Clients, ADDRESS, SOURCE_FRAME


class LiveHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_live_selection_and_mode_switch_close_owned_transport(self):
        app = Application(clock=ManualClock())
        clients = Clients()
        live = LiveSession(app, scanner=Scanner(), client_factory=clients)
        client = TestClient(TestServer(create_app(app, live=live)))
        await client.start_server()
        try:
            origin = str(client.make_url('/')).rstrip('/')
            session = await (await client.get('/api/session')).json()
            count = 0
            async def action(name, **payload):
                nonlocal count
                count += 1
                response = await client.post('/api/action', headers={
                    'Origin':origin,'X-EucWatch-Key':session['credential']},json={
                    'controller':session['controller'],'id':str(count),'action':name,**payload})
                self.assertEqual(response.status,200,await response.text())
                return await response.json()
            state = await (await client.get('/api/state')).json()
            self.assertEqual(state['mode'],'idle')
            self.assertEqual(clients.created,[])
            state = await action('live_discover')
            self.assertEqual(state['live']['devices'][0]['address'],ADDRESS)
            state = await action('live_select',address=ADDRESS)
            self.assertEqual(state['mode'],'live')
            self.assertFalse(state['fresh'])
            clients.created[0].emit(SOURCE_FRAME)
            state = await (await client.get('/api/state')).json()
            self.assertTrue(state['fresh'])
            self.assertEqual(state['live']['firmware'],'006.0.03')
            previous = clients.created[0]
            state = await action('simulator_start',controlled=True)
            self.assertFalse(previous.is_connected)
            self.assertEqual(state['mode'],'simulator')
            previous.emit(SOURCE_FRAME)
            self.assertEqual(app.view()['mode'],'simulator')
        finally:
            await client.close()
        self.assertTrue(live.status()['closed'])
