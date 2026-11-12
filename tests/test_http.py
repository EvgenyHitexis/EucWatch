import asyncio
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from eucwatch import Application, ManualClock
from eucwatch.lease import ControllerLease
from eucwatch.live import LiveSession
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


class GatedLive(LiveSession):
    """A live session whose disconnect waits for the test, holding the action lock meanwhile."""
    def __init__(self, application):
        super().__init__(application)
        self.entered, self.gate = asyncio.Event(), asyncio.Event()

    async def disconnect(self):
        self.entered.set()
        await self.gate.wait()
        await super().disconnect()


class WaitingRequestHTTP(unittest.IsolatedAsyncioTestCase):
    async def test_action_waiting_while_the_lease_expires_is_forbidden(self):
        clock, waiting = ManualClock(), []

        class ObservedLease(ControllerLease):
            async def act(self, payload):
                # Nothing awaits between here and the action lock, so once the test sees the id the request waits there.
                waiting.append(payload.get('id'))
                return await super().act(payload)

        application = Application(clock=ManualClock())
        live = GatedLive(application)
        with patch('eucwatch.server.ControllerLease', ObservedLease):
            client = TestClient(TestServer(create_app(application, live=live, clock=clock)))
        await client.start_server()
        try:
            session = await (await client.get('/api/session')).json()
            headers = {'Origin': str(client.make_url('/')).rstrip('/'), 'X-EucWatch-Key': session['credential']}
            def post(identity, action):
                return asyncio.create_task(client.post('/api/action', headers=headers, json={
                    'controller': session['controller'], 'id': identity, 'action': action, 'epoch': 0}))
            first = post('start', 'simulator_start')  # disconnects the live session first, inside the lock
            await asyncio.wait_for(live.entered.wait(), 5)
            press = post('press', 'button_down')
            # Bounded only so a regression fails instead of hanging; no real time passes for the lease.
            await asyncio.wait_for(self.until(lambda: 'press' in waiting), 5)
            clock.advance(10.5)
            replacement = await (await client.get('/api/session')).json()
            self.assertNotIn(replacement['controller'], (None, session['controller']))
            live.gate.set()
            self.assertEqual((await first).status, 200)
            response = await press
            self.assertEqual((response.status, response.content_type, await response.text()),
                (403, 'text/plain', 'Controller expired while action was waiting'))
            self.assertFalse((await (await client.get('/api/state')).json())['button']['down'])
        finally:
            live.gate.set()
            await client.close()

    @staticmethod
    async def until(condition):
        while not condition():
            await asyncio.sleep(0)


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
