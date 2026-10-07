import unittest

from aiohttp.test_utils import TestClient, TestServer

from eucwatch.server import create_app


class LocalApplication(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()
        self.origin = str(self.client.make_url('/')).rstrip('/')

    async def asyncTearDown(self):
        await self.client.close()

    async def test_start_is_idle_and_controls_require_same_origin_and_credential(self):
        response = await self.client.get('/api/state')
        self.assertEqual((await response.json())['mode'], 'idle')
        response = await self.client.post('/api/action', json={'action': 'simulator_start'})
        self.assertEqual(response.status, 403)

        response = await self.client.get('/api/session', headers={'Origin': self.origin})
        session = await response.json()
        headers = {'Origin': self.origin, 'X-EucWatch-Key': session['credential']}
        response = await self.client.post('/api/action', headers=headers,
            json={'action': 'simulator_start', 'id': 'start', 'controller': session['controller'], 'epoch':0})
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['mode'], 'simulator')
        headers['Origin'] = 'http://untrusted.example'
        response = await self.client.post('/api/action', headers=headers,
            json={'action': 'disconnect', 'id': 'bad', 'controller': session['controller'], 'epoch':0})
        self.assertEqual(response.status, 403)

    async def test_only_one_controller_can_acquire_control_and_reload_reuses_it(self):
        first = await (await self.client.get('/api/session')).json()
        second = await (await self.client.get('/api/session')).json()
        self.assertIsNone(second['controller'])
        recovered = await (await self.client.get('/api/session', params={'controller': first['controller']})).json()
        self.assertEqual(recovered['controller'], first['controller'])

    async def test_abandoned_browser_press_cannot_become_recovery_hold(self):
        import asyncio
        session = await (await self.client.get('/api/session')).json()
        response = await self.client.post('/api/action',
            headers={'Origin':self.origin, 'X-EucWatch-Key':session['credential']},
            json={'controller':session['controller'], 'id':'down', 'action':'button_down','epoch':0})
        self.assertTrue((await response.json())['button']['down'])
        await asyncio.sleep(2.1)
        state = await (await self.client.get('/api/state')).json()
        self.assertFalse(state['button']['down'])
        self.assertFalse(state['recovery'])
