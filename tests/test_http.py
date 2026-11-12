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

    async def test_lease_refusals_keep_their_status_codes_bodies_and_headers(self):
        response = await self.client.get('/api/session')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        session = await response.json()
        self.assertEqual(set(session), {'credential', 'controller'})
        viewer = await (await self.client.get('/api/session')).json()
        self.assertEqual(viewer, {'credential': session['credential'], 'controller': None})

        response = await self.client.get('/api/state', params={'controller': 'expired'})
        self.assertEqual(response.status, 403)
        self.assertEqual(response.content_type, 'text/plain')
        self.assertEqual(await response.text(), 'Controller expired; reacquire current state')

        headers = {'Origin': self.origin, 'X-EucWatch-Key': session['credential']}
        async def post(body):
            response = await self.client.post('/api/action', headers=headers, json=body)
            return response.status, response.content_type, await response.json()
        request = {'controller': session['controller'], 'id': 'start', 'action': 'simulator_start', 'epoch': 0}
        status, kind, started = await post(request)
        self.assertEqual((status, kind, started['mode']), (200, 'application/json', 'simulator'))
        self.assertEqual({'recording', 'live', 'scenario'} - set(started), set())
        self.assertEqual(await post(request), (200, 'application/json', started))
        self.assertEqual(await post({**request, 'id': 'stale'}), (409, 'application/json',
            {'error': 'Application session changed; refresh before acting'}))
        self.assertEqual(await post({**request, 'id': 'internal', 'action': 'horn_result'}), (400, 'application/json',
            {'error': 'Transport callbacks are internal application inputs'}))
        self.assertEqual(await post({'controller': session['controller'], 'action': 'stop'}), (400, 'application/json',
            {'error': "'id'"}))
        self.assertEqual(await post({**request, 'id': 'intruder', 'controller': 'intruder'}), (400, 'application/json',
            {'error': 'Valid controller and request identity required'}))


class EvictedResultHTTP(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_with_evicted_result_is_a_conflict(self):
        client = TestClient(TestServer(create_app(result_limit=1)))
        await client.start_server()
        try:
            session = await (await client.get('/api/session')).json()
            headers = {'Origin': str(client.make_url('/')).rstrip('/'), 'X-EucWatch-Key': session['credential']}
            async def post(identity, epoch):
                response = await client.post('/api/action', headers=headers, json={
                    'controller': session['controller'], 'id': identity, 'action': 'interact', 'epoch': epoch})
                return response.status, await response.json()
            self.assertEqual((await post('first', 0))[0], 200)
            self.assertEqual((await post('second', 0))[0], 200)
            self.assertEqual(await post('first', 0), (409,
                {'error': 'Duplicate action was already processed; its response expired'}))
        finally:
            await client.close()
