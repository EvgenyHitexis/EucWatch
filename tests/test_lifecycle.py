"""Authoritative HTTP epochs, browser ownership and restart retention."""
from preset_fixture import save_preset

import asyncio
from pathlib import Path
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore
from eucwatch.server import create_app


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_resume_invalidates_controlled_simulator_and_replay_sources(self):
        from eucwatch.recording import Replay
        fixture=Path('experiments/laptop-feasibility/evidence/fixture-recording.jsonl').read_text()
        for mode in ('simulator','replay'):
            with self.subTest(mode=mode):
                host=ManualClock()
                app=Application(clock=host)
                if mode=='simulator':
                    app.action('simulator_start',controlled=True)
                else:
                    app.action('replay_start',recording=Replay.from_text(fixture))
                    for _ in range(13): app.action('replay_step')
                self.assertTrue(app.view()['fresh'])
                before=app.view()
                host.advance(60,suspended=True)
                app.tick()
                resumed=app.view()
                self.assertFalse(resumed['fresh'])
                self.assertGreater(resumed['session'],before['session'])
                self.assertEqual(resumed['diagnostics']['resume_events'],1)
                self.assertEqual(resumed['elapsed_s'],before['elapsed_s'])
                self.assertEqual(resumed['command_events'],[])

    async def test_evicted_response_identity_never_becomes_another_button_request(self):
        app = Application(clock=ManualClock())
        app.action('simulator_start')
        client = TestClient(TestServer(create_app(app, result_limit=1)))
        await client.start_server()
        try:
            session = await (await client.get('/api/session')).json()
            headers={'Origin':str(client.make_url('/')).rstrip('/'),'X-EucWatch-Key':session['credential']}
            async def post(name, identity):
                return await client.post('/api/action',headers=headers,json={
                    'controller':session['controller'],'id':identity,'action':name,'epoch':app.session})
            await post('button_down','press')
            await post('button_up','release')
            count=len(app.view()['command_events'])
            response=await post('button_down','press')
            self.assertEqual(response.status,409)
            self.assertEqual(len(app.view()['command_events']),count)
            self.assertFalse(app.view()['button']['down'])
        finally:
            await client.close()

    async def test_stale_epoch_cannot_press_after_mode_change_and_duplicate_retries_are_inert(self):
        app = Application(clock=ManualClock())
        client = TestClient(TestServer(create_app(app)))
        await client.start_server()
        try:
            session = await (await client.get('/api/session')).json()
            headers = {'Origin':str(client.make_url('/')).rstrip('/'), 'X-EucWatch-Key':session['credential']}
            async def post(name, identity, epoch):
                return await client.post('/api/action', headers=headers, json={
                    'controller':session['controller'], 'id':identity, 'action':name, 'epoch':epoch})
            old = app.session
            response = await post('simulator_start', 'start', old)
            self.assertEqual(response.status, 200)
            started = await response.json()
            response = await post('simulator_start', 'start', old)
            self.assertEqual(await response.json(), started)
            self.assertEqual(app.session, started['session'])
            response = await post('button_down', 'old-press', old)
            self.assertEqual(response.status, 409)
            self.assertFalse(app.view()['button']['down'])
            self.assertEqual(app.view()['command_events'], [])
        finally:
            await client.close()

    async def test_closed_controller_expires_without_stopping_behavior_and_old_owner_is_rejected(self):
        app = Application(clock=ManualClock())
        client = TestClient(TestServer(create_app(app, controller_timeout=.05)))
        await client.start_server()
        try:
            first = await (await client.get('/api/session')).json()
            second = await (await client.get('/api/session')).json()
            self.assertIsNone(second['controller'])
            app.action('simulator_start')
            app.action('button_down')
            await asyncio.sleep(.09)
            replacement = await (await client.get('/api/session')).json()
            self.assertIsNotNone(replacement['controller'])
            self.assertNotEqual(first['controller'], replacement['controller'])
            self.assertFalse(app.view()['button']['down'])
            self.assertEqual(app.mode, 'simulator')
            response = await client.get('/api/state', params={'controller':first['controller']})
            self.assertEqual(response.status, 403)
        finally:
            await client.close()

    async def test_restart_retains_configuration_discards_commands_and_resume_stops_pending_output(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = ManualClock()
            output = []
            store = FileStore(Path(directory)/'configuration.json')
            app = Application(clock=clock, store=store, command_output=output.append)
            save_preset(app, slot=1, name='Road', pedal_sensitivity=31, dynamic_assist=26)
            app.action('alerts_begin')
            app.action('alerts_update', alert='pwm', enabled=True, threshold=10)
            app.action('alerts_save')
            app.action('simulator_configure', pwm_percent=20)
            app.action('simulator_start')
            app.action('preset_apply', slot=1)
            old = app.view()
            clock.advance(60, suspended=True)
            app.tick()
            state = app.view()
            self.assertFalse(state['fresh'])
            self.assertFalse(state['preset_attempt']['pending'])
            self.assertEqual(len(output), 1)
            self.assertEqual(state['diagnostics']['resume_events'], 1)
            self.assertFalse(any(e['alert']=='pwm' and e['phase']=='start' and e['at_s']>0 for e in state['vibration']['events']))
            app.receive(old['session'], b'old bytes')
            self.assertFalse(app.view()['fresh'])
            restarted = Application(clock=ManualClock(), store=FileStore(store.path)).view()
            self.assertEqual(restarted['config'], state['config'])
            self.assertEqual(restarted['mode'], 'idle')
            self.assertIsNone(restarted['preset_attempt'])
            self.assertIsNone(restarted['confirmed_preset'])
            self.assertEqual(restarted['command_events'], [])
