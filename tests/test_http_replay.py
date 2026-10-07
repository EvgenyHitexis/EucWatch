import json
from pathlib import Path
import tempfile
import unittest
import asyncio
import threading

from aiohttp.test_utils import TestClient, TestServer
from eucwatch.server import create_app
from eucwatch.recording import Recorder


class RecordingUIBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_slow_storage_does_not_stop_behavior_without_browser_polling(self):
        with tempfile.TemporaryDirectory() as directory:
            entered, release = threading.Event(), threading.Event()
            def writer(path,lines):
                entered.set()
                release.wait(3)
                with path.open('a') as output:
                    output.writelines(lines)
            recorder = Recorder(Path(directory)/'slow.jsonl',writer=writer)
            client = TestClient(TestServer(create_app(recorder=recorder)))
            await client.start_server()
            try:
                origin = str(client.make_url('/')).rstrip('/')
                session = await (await client.get('/api/session')).json()
                await client.post('/api/action',headers={'Origin':origin,'X-EucWatch-Key':session['credential']},
                    json={'action':'simulator_start','id':'start','controller':session['controller'],'epoch':0})
                async with asyncio.timeout(2):
                    while not entered.is_set():
                        await asyncio.sleep(.01)
                await asyncio.sleep(.75)
                state = await (await client.get('/api/state')).json()
                self.assertGreaterEqual(state['diagnostics']['valid_frames'],4)
            finally:
                release.set()
                await client.close()

    async def test_raw_recording_download_and_read_only_replay_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(Path(directory) / 'session.jsonl')
            client = TestClient(TestServer(create_app(recorder=recorder)))
            await client.start_server()
            try:
                origin = str(client.make_url('/')).rstrip('/')
                session = await (await client.get('/api/session')).json()
                headers = {'Origin':origin, 'X-EucWatch-Key':session['credential']}
                async def action(name, **payload):
                    state=await (await client.get('/api/state')).json()
                    return await client.post('/api/action',headers=headers,json={
                        'controller':session['controller'], 'id':name,
                        'action':name, 'epoch':state['session'], **payload})
                await action('simulator_start', controlled=True)
                response = await client.get('/api/recording',headers=headers)
                self.assertEqual(response.status,200)
                captured = [json.loads(line) for line in (await response.text()).splitlines()]
                self.assertTrue(any(row['event']=='notification' for row in captured))
                fixture = Path('experiments/laptop-feasibility/evidence/fixture-recording.jsonl').read_text()
                response = await action('replay_start',recording=fixture)
                self.assertEqual(response.status,200)
                self.assertEqual((await response.json())['mode'],'replay')
                response = await action('simulator_emit')
                self.assertEqual(response.status,400)
            finally:
                await client.close()
