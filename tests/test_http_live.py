"""Live UI/backend boundary with controlled transport, no Bluetooth operations."""
import unittest
import asyncio
from aiohttp.test_utils import TestClient, TestServer
from eucwatch import Application, ManualClock
from eucwatch.live import LiveSession
from eucwatch.server import create_app
from support import Scanner, Clients, ADDRESS, SOURCE_FRAME


class LiveHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_duplicate_selection_has_one_transport_effect(self):
        app = Application(clock=ManualClock())
        clients = Clients()
        entered,release=asyncio.Event(),asyncio.Event()
        def factory(device,**options):
            client=clients(device,**options)
            original=client.start_notify
            async def subscribe(*args,**kwargs):
                entered.set()
                await release.wait()
                await original(*args,**kwargs)
            client.start_notify=subscribe
            return client
        live=LiveSession(app,scanner=Scanner(),client_factory=factory)
        client=TestClient(TestServer(create_app(app,live=live)))
        await client.start_server()
        requests=[]
        try:
            session=await (await client.get('/api/session')).json()
            headers={'Origin':str(client.make_url('/')).rstrip('/'),'X-EucWatch-Key':session['credential']}
            common={'controller':session['controller'],'epoch':app.session}
            await client.post('/api/action',headers=headers,json={**common,'id':'discover','action':'live_discover'})
            payload={**common,'id':'same-selection','action':'live_select','address':ADDRESS}
            requests.append(asyncio.create_task(client.post('/api/action',headers=headers,json=payload)))
            await asyncio.wait_for(entered.wait(),1)
            requests.append(asyncio.create_task(client.post('/api/action',headers=headers,json=payload)))
            # Real time, not lease time: lets the second request reach the intent lock over the socket.
            await asyncio.sleep(.03)
            self.assertEqual(len(clients.created),1)
            release.set()
            responses=await asyncio.gather(*requests)
            self.assertTrue(all(response.status==200 for response in responses))
            states=[await response.json() for response in responses]
            self.assertEqual(states[0],states[1])
            self.assertEqual(len(clients.created),1)
        finally:
            release.set()
            await asyncio.gather(*requests,return_exceptions=True)
            await client.close()

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
                    'controller':session['controller'],'id':str(count),'action':name,'epoch':app.session,**payload})
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
