"""Offline fake BLE feeding the actual watch JS endpoint and Storage adapter."""
import asyncio
import base64
import json
from pathlib import Path

from test_nordic import FakeClient, FakeScanner


class WatchWire:
    def __init__(self):
        self.process = None
        self.lock = asyncio.Lock()
        self.clients = []
        self.requests = []
        self.drop_commit = False

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            'node', str(Path(__file__).resolve().parents[1] / 'watch/tests/protocol-bridge.cjs'),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        return self

    async def call(self, **row):
        async with self.lock:
            self.process.stdin.write((json.dumps(row)+'\n').encode())
            await self.process.stdin.drain()
            response=json.loads(await asyncio.wait_for(self.process.stdout.readline(), 5))
            if 'error' in response:
                raise OSError(response['error'])
            return response

    async def exchange(self, message):
        self.requests.append(json.loads(message))
        response=await self.call(message=base64.b64encode(message).decode())
        return base64.b64decode(response['response'])

    def client(self, *args, **kwargs):
        wire=self

        class Client(FakeClient):
            async def write_gatt_char(self, characteristic, data, *, response):
                self.writes.append((bytes(data),response))
                self.buffer+=bytes(data)
                if self.buffer.endswith(b'\n'):
                    message,self.buffer=self.buffer,b''
                    raw=await wire.exchange(message)
                    if wire.drop_commit and json.loads(message)['op']=='commit':
                        wire.drop_commit=False
                        return
                    for offset in range(0,len(raw),20):
                        self.receiver(characteristic,raw[offset:offset+20])
        client=Client(*args,**kwargs)
        self.clients.append(client)
        return client

    async def close(self):
        if self.process is not None:
            self.process.stdin.close()
            await self.process.wait()


Scanner = FakeScanner
