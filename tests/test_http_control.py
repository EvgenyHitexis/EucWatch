"""Live writes are reached through normal authenticated UI intents only."""
import asyncio
import unittest

from aiohttp.test_utils import TestClient, TestServer

from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.server import create_app
from test_control import settings_frame
from test_live import Scanner, ADDRESS, SOURCE_FRAME
from test_live_control import WritingClient


class ControlHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_preset_and_duplicate_horn_use_selected_client_and_internal_results_are_refused(self):
        clock = ManualClock()
        app = Application(clock=clock)
        clients = []
        def factory(*args, **options):
            client = WritingClient(*args, **options)
            clients.append(client)
            return client
        live = LiveSession(app, scanner=Scanner(), client_factory=factory)
        http = TestClient(TestServer(create_app(app, live=live)))
        await http.start_server()
        try:
            session = await (await http.get('/api/session')).json()
            headers = {'Origin':str(http.make_url('/')).rstrip('/'), 'X-EucWatch-Key':session['credential']}
            count = 0
            async def action(action_name, expected=200, identity=None, **payload):
                nonlocal count
                count += 1
                response = await http.post('/api/action', headers=headers, json={
                    'controller':session['controller'], 'id':identity or str(count), 'action':action_name, **payload})
                self.assertEqual(response.status, expected, await response.text())
                return await response.json()
            await action('preset_begin', slot=1)
            await action('preset_update', name='Road', pedal_sensitivity=31, dynamic_assist=26)
            await action('preset_save')
            await action('live_discover')
            await action('live_select', address=ADDRESS)
            wheel = clients[0]
            wheel.emit(SOURCE_FRAME)
            await action('preset_apply', slot=1, identity='preset-once')
            await action('preset_apply', slot=1, identity='preset-once')
            async with asyncio.timeout(1):
                while app.view()['preset_attempt']['status'] != 'confirming':
                    await asyncio.sleep(.001)
            self.assertEqual([len(data) for _, data, _ in wheel.writes], [15,20,11])
            await action('command_result', expected=400, attempt=1, session=app.session, index=0, success=True)
            clock.advance(.1); wheel.emit(settings_frame())
            self.assertIsNone(app.view()['confirmed_preset'])
            clock.advance(.1); wheel.emit(settings_frame())
            self.assertEqual(app.view()['confirmed_preset']['name'], 'Road')
            await action('button_down', identity='horn-once')
            await action('button_down', identity='horn-once')
            await action('button_up')
            async with asyncio.timeout(1):
                while len(wheel.writes) != 4:
                    await asyncio.sleep(.001)
            self.assertEqual(wheel.writes[-1][1].hex(), '4c6b41700e0080808001ca87e66f')
            self.assertFalse(wheel.writes[-1][2])
            await action('simulator_start', controlled=True)
            await action('preset_apply', slot=1)
            self.assertEqual(len(wheel.writes), 4)
            self.assertFalse(wheel.is_connected)
        finally:
            await http.close()
