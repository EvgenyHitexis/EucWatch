"""Real built UI against the aiohttp application, driven with Chrome CDP."""
import asyncio
import base64
from contextlib import suppress
import json
from pathlib import Path
import socket
import subprocess
import tempfile

from aiohttp import ClientSession, web

from eucwatch.server import create_app


class Browser:
    def __init__(self, ws):
        self.ws, self.sequence = ws, 0

    async def call(self, method, params=None, session=None):
        self.sequence += 1
        message = {'id': self.sequence, 'method': method, 'params': params or {}}
        if session:
            message['sessionId'] = session
        await self.ws.send_json(message)
        async with asyncio.timeout(15):
            while True:
                response = await self.ws.receive_json()
                if response.get('id') == self.sequence:
                    if 'error' in response:
                        raise RuntimeError(response['error'])
                    return response.get('result', {})

    async def evaluate(self, expression, session):
        response = await self.call('Runtime.evaluate', {'expression': expression,
            'returnByValue': True, 'awaitPromise': True}, session)
        if 'exceptionDetails' in response:
            raise RuntimeError(response['exceptionDetails'])
        return response['result'].get('value')

    async def wait(self, expression, session):
        async with asyncio.timeout(15):
            while not await self.evaluate(expression, session):
                await asyncio.sleep(.05)


async def run():
    runner = web.AppRunner(create_app())
    await runner.setup()
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    await web.SockSite(runner, sock).start()
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    try:
        with tempfile.TemporaryDirectory(prefix='eucwatch-ui-', ignore_cleanup_errors=True) as profile:
            browser = subprocess.Popen(['google-chrome', '--headless', '--no-first-run',
                '--no-default-browser-check', '--disable-sync', '--disable-background-networking',
                '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                port_file = Path(profile) / 'DevToolsActivePort'
                async with asyncio.timeout(15):
                    while not port_file.exists():
                        if browser.poll() is not None:
                            raise RuntimeError('Chrome exited before readiness')
                        await asyncio.sleep(.1)
                port, path = port_file.read_text().splitlines()
                async with ClientSession() as client:
                    async with client.ws_connect(f'http://127.0.0.1:{port}{path}') as ws:
                        cdp = Browser(ws)
                        target = await cdp.call('Target.createTarget', {'url': url})
                        attached = await cdp.call('Target.attachToTarget',
                            {'targetId': target['targetId'], 'flatten': True})
                        session = attached['sessionId']
                        await cdp.wait("document.querySelector('canvas') && document.querySelector('canvas').getAttribute('aria-label').includes('Not connected')", session)
                        await cdp.evaluate("document.querySelector('[data-action=simulator_start]').click()", session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Connected')", session)
                        async def scenario(speed, voltage, pwm, traffic='normal'):
                            await cdp.evaluate(f"""document.querySelector('#speed').value={json.dumps(str(speed))};
                                document.querySelector('#voltage').value={json.dumps(str(voltage))};
                                document.querySelector('#pwm').value={json.dumps(str(pwm))};
                                document.querySelector('#traffic').value={json.dumps(traffic)};
                                document.querySelector('#scenario').requestSubmit();""", session)
                            await cdp.wait("!document.querySelector('[data-action=simulator_configure]').disabled", session)
                        await scenario(25, 148.05, 45)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('100 percent') && document.querySelector('canvas').getAttribute('aria-label').includes('Speed 25')", session)
                        boundary_high = await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session)
                        await scenario(25, 119.02, 45)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('battery 0 percent')", session)
                        await scenario(25, 138, 45, 'paused')
                        await cdp.evaluate("document.querySelector('[data-action=advance]').click()", session)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh === 'false'", session)
                        stale = await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session)
                        assert 'Speed —' in stale and 'wheel battery dimmed' in stale
                        await scenario(99, 138, 99, 'corrupt')
                        await cdp.wait("document.querySelector('canvas').dataset.fresh === 'false'", session)
                        await scenario(25, 138, 45)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh === 'true'", session)
                        await cdp.evaluate("document.querySelector('[data-action=disconnect]').click()", session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Disconnected')", session)
                        disconnected = await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session)
                        await cdp.evaluate("document.querySelector('[data-action=connect]').click()", session)
                        await cdp.wait("!document.querySelector('[data-action=simulator_emit]').disabled", session)
                        await cdp.evaluate("document.querySelector('[data-action=simulator_emit]').click()", session)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh === 'true'", session)
                        report = {'issue': 18, 'provenance': 'actual built UI / deterministic simulator',
                            'browser': (await cdp.call('Browser.getVersion'))['product'],
                            'expected': 'idle launch; battery boundaries; stale dashes/dimming; CRC rejection; disconnect; fresh recovery',
                            'high_boundary': boundary_high, 'stale': stale, 'disconnected': disconnected,
                            'observed': await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session)}
                        output = Path('.test-output')
                        output.mkdir(exist_ok=True)
                        screenshot = await cdp.call('Page.captureScreenshot', {'format': 'png'}, session)
                        (output / 'dashboard.png').write_bytes(base64.b64decode(screenshot['data']))
                        (output / 'browser.json').write_text(json.dumps(report, indent=2) + '\n')
                        print(json.dumps(report, indent=2))
            finally:
                browser.terminate()
                try:
                    await asyncio.to_thread(browser.wait, timeout=5)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    await asyncio.to_thread(browser.wait)
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(run())
