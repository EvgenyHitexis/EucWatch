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
            json={'action': 'simulator_start', 'id': 'start', 'controller': session['controller']})
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['mode'], 'simulator')
        headers['Origin'] = 'http://untrusted.example'
        response = await self.client.post('/api/action', headers=headers,
            json={'action': 'disconnect', 'id': 'bad', 'controller': session['controller']})
        self.assertEqual(response.status, 403)
