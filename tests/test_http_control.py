"""Live writes are reached through normal authenticated UI intents only."""
import asyncio
import json
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
                    'controller':session['controller'], 'id':identity or str(count), 'action':action_name, 'epoch':app.session, **payload})
                self.assertEqual(response.status, expected, await response.text())
                return await response.json()
            config = app.view()['config']
            config['presets'][0].update(name='Road', configured=True, pedal_sensitivity=31, dynamic_assist=26)
            await action('configuration_import_prepare', content=json.dumps(config))
            await action('configuration_import_commit')
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

    async def test_duplicate_editor_completion_is_not_replayed_after_reload_or_reconnect(self):
        clock = ManualClock()
        app = Application(clock=clock)
        app.action('connect')
        app.receive(app.session, settings_frame())
        http = TestClient(TestServer(create_app(app, result_limit=2)))
        await http.start_server()
        try:
            session = await (await http.get('/api/session')).json()
            headers = {'Origin': str(http.make_url('/')).rstrip('/'), 'X-EucWatch-Key': session['credential']}
            async def post(name, identity, epoch=None, **values):
                return await http.post('/api/action', headers=headers, json={
                    'controller': session['controller'], 'id': identity, 'action': name,
                    'epoch': app.session if epoch is None else epoch, **values})
            response = await post('preset_begin', 'open', slot=2, source='watch')
            self.assertEqual(response.status, 200)
            clock.advance(.1); app.receive(app.session, settings_frame())
            old = app.session
            for _ in range(2):
                response = await post('preset_update', 'complete-once', dynamic_assist=26, source='watch')
                self.assertEqual(response.status, 200)
            count = len([r for r in app.view()['command_events'] if r['event'] == 'submission'])
            self.assertEqual(count, 1)
            await http.get('/api/session', params={'controller': session['controller']})
            await http.get('/api/state', params={'controller': session['controller']})
            await post('disconnect', 'disconnect')
            await post('connect', 'connect')
            app.receive(app.session, settings_frame())
            response = await post('preset_update', 'complete-once', epoch=old, dynamic_assist=26)
            self.assertEqual(response.status, 409)
            response = await post('preset_update', 'late-new-identity', epoch=old, dynamic_assist=26)
            self.assertEqual(response.status, 409)
            self.assertEqual(len([r for r in app.view()['command_events'] if r['event'] == 'submission']), count)
        finally:
            await http.close()
