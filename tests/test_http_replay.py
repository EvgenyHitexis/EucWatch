import json
from pathlib import Path
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer
from eucwatch.server import create_app
from eucwatch.recording import Recorder


class RecordingUIBoundary(unittest.IsolatedAsyncioTestCase):
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
                    return await client.post('/api/action',headers=headers,json={
                        'controller':session['controller'], 'id':name,
                        'action':name, **payload})
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
