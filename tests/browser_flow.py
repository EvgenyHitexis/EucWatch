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

from eucwatch import Application, ManualClock
from eucwatch.server import create_app
from eucwatch.recording import Recorder


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

    async def pointer(self, selector, start, end, session):
        box = await self.evaluate(f"""(() => {{ const b=document.querySelector({json.dumps(selector)}).getBoundingClientRect(); return {{x:b.x,y:b.y,width:b.width,height:b.height}}; }})()""", session)
        for kind, point, pressed in [('mousePressed', start, True), ('mouseMoved', end, True), ('mouseReleased', end, False)]:
            await self.call('Input.dispatchMouseEvent', {'type': kind,
                'x': box['x'] + point[0], 'y': box['y'] + point[1],
                'button': 'left', 'buttons': 1 if pressed else 0, 'clickCount': 1}, session)


async def run():
    host_clock = ManualClock()
    recorder = Recorder(Path('.test-output/ui-recording.jsonl'))
    behavior = Application(clock=host_clock, event_sink=recorder.record)
    runner = web.AppRunner(create_app(behavior, recorder=recorder))
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
                        await cdp.pointer('#watch', (215, 120), (20, 120), session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen === 'presets'", session)
                        presets = await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session)
                        assert all(f'Preset {i}' in presets for i in range(1, 5))
                        await cdp.pointer('#watch', (20, 120), (215, 120), session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen === 'dashboard'", session)
                        await cdp.pointer('#watch', (120, 10), (120, 110), session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen === 'settings'", session)
                        await cdp.pointer('#watch', (120, 100), (120, 100), session)
                        await cdp.wait("document.querySelector('canvas').dataset.awake === 'false'", session)
                        await cdp.pointer('#watch-button', (10, 20), (10, 20), session)
                        await cdp.wait("document.querySelector('canvas').dataset.awake === 'true'", session)
                        self_button = behavior.view()['button']
                        assert self_button['down'] is False and self_button['wake_cycle'] is False
                        await cdp.pointer('#watch', (20, 120), (215, 120), session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen === 'dashboard'", session)
                        host_clock.advance(31)
                        await cdp.wait("document.querySelector('canvas').dataset.awake === 'false'", session)
                        await cdp.pointer('#watch-button', (10, 20), (10, 20), session)
                        await cdp.wait("document.querySelector('canvas').dataset.awake === 'true'", session)
                        navigation = {'issue':19, 'provenance':'actual Canvas gestures / button / aiohttp with controlled clock',
                            'expected':'fixed four slots, swipe back, Settings sleep, wake-only button, initial idle sleep',
                            'observed':'passed', 'preset_menu':presets}
                        await cdp.pointer('#watch', (120,10), (120,110), session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='settings'",session)
                        await cdp.pointer('#watch', (120,175), (120,175), session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Alert editor 1')",session)
                        await cdp.pointer('#watch',(120,88),(120,88),session)
                        await cdp.wait("document.querySelector('#alert-pwm-enabled').checked",session)
                        await cdp.pointer('#watch',(20,120),(215,120),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard' && document.querySelector('#alerts-status').textContent.includes('Saved')",session)
                        assert behavior.view()['config']['alerts']['pwm']=={'enabled':False,'threshold':None}
                        navigation['back_discards_unsaved_alert_draft']='passed'
                        await cdp.evaluate("document.querySelector('#alerts-edit').click()",session)
                        await cdp.wait("!document.querySelector('#alert-pwm-enabled').disabled",session)
                        await cdp.evaluate("document.querySelector('#alert-pwm-enabled').click(); document.querySelector('#alerts-editor').requestSubmit()",session)
                        await cdp.wait("document.querySelector('#message').textContent.includes('threshold')",session)
                        assert behavior.view()['config']['alerts']['pwm']['enabled'] is False
                        await cdp.evaluate("const i=document.querySelector('#alert-pwm-threshold'); i.value='70'; i.dispatchEvent(new Event('change',{bubbles:true}))",session)
                        await cdp.wait("!document.querySelector('#alerts-save').disabled",session)
                        await cdp.evaluate("document.querySelector('#alerts-editor').requestSubmit()",session)
                        await cdp.wait("document.querySelector('#alerts-status').textContent.includes('Saved') && document.querySelector('#alert-pwm-threshold').value==='70'",session)
                        assert behavior.view()['config']['alerts']['pwm']=={'enabled':True,'threshold':70}
                        await cdp.wait("!document.querySelector('[data-alert-test=pwm]').disabled",session)
                        await cdp.evaluate("document.querySelector('[data-alert-test=pwm]').click()",session)
                        await cdp.wait("document.querySelector('#vibration-trace').textContent.includes('PWM') || document.querySelector('#vibration-trace').textContent.includes('pwm')",session)
                        host_clock.advance(.75)
                        await cdp.wait("document.querySelector('#vibration-status').textContent.includes('idle')",session)
                        starts=[e['duration_s'] for e in behavior.view()['vibration']['events'] if e['phase']=='start' and e['test']]
                        assert starts==[.15,.15,.15],starts
                        alert_result={'issue':20,'provenance':'actual Canvas and HTML editor / aiohttp / controlled clock',
                            'expected':'back discards, missing enabled threshold refused, save authoritative threshold, PWM test three150ms pulses',
                            'observed':'passed','pulse_durations_s':starts}
                        await cdp.wait("!document.querySelector('#preset-edit').disabled",session)
                        await cdp.evaluate("document.querySelector('#preset-slot').value='2'; document.querySelector('#preset-slot').dispatchEvent(new Event('change')); document.querySelector('#preset-edit').click()",session)
                        await cdp.wait("!document.querySelector('#preset-name').disabled",session)
                        async def preset_field(selector,value):
                            await cdp.evaluate(f"(() => {{ const field=document.querySelector({json.dumps(selector)}); field.value={json.dumps(value)}; field.dispatchEvent(new Event('change',{{bubbles:true}})); }})()",session)
                            await cdp.wait("!document.querySelector('#preset-save').disabled",session)
                        await preset_field('#preset-name','Rain')
                        await preset_field('#preset-pedal-sensitivity','30')
                        await cdp.evaluate("document.querySelector('#preset-editor').requestSubmit()",session)
                        await cdp.wait("document.querySelector('#preset-validation-error').textContent.length>0",session)
                        assert not behavior.view()['config']['presets'][1]['configured']
                        await preset_field('#preset-dynamic-assist','20')
                        await cdp.evaluate("document.querySelector('#preset-editor').requestSubmit()",session)
                        await cdp.wait("document.querySelector('#preset-status').textContent.includes('Saved')",session)
                        expected_preset={'id':2,'name':'Rain','configured':True,'pedal_sensitivity':30,'dynamic_assist':20}
                        assert behavior.view()['config']['presets'][1]==expected_preset
                        await cdp.pointer('#watch',(215,120),(20,120),session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Rain')",session)
                        menu=await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')",session)
                        await cdp.wait("!document.querySelector('#preset-clear').disabled",session)
                        await cdp.evaluate("document.querySelector('#preset-clear').click()",session)
                        await cdp.wait("document.querySelector('#preset-status').textContent.includes('Unsaved')",session)
                        await cdp.wait("!document.querySelector('#preset-cancel').disabled",session)
                        await cdp.evaluate("document.querySelector('#preset-cancel').click()",session)
                        await cdp.wait("document.querySelector('#preset-status').textContent.includes('Saved')",session)
                        assert behavior.view()['config']['presets'][1]==expected_preset
                        restarted=Application(clock=ManualClock(),store=behavior.store)
                        assert restarted.view()['config']['presets'][1]==expected_preset
                        preset_result={'issue':21,'provenance':'actual HTML editor / Canvas menu / aiohttp / store restart',
                            'expected':'required validation, Save/Cancel, optional dip absent, four identities and restart retention',
                            'observed':'passed','saved':expected_preset,'menu':menu}
                        await cdp.pointer('#watch',(20,120),(215,120),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
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
                        behavior.action('advance', seconds=31)
                        after_loss = behavior.view()['elapsed_s']
                        await cdp.wait(f"Number(document.querySelector('canvas').dataset.elapsed) >= {after_loss} && document.querySelector('canvas').dataset.awake === 'true'", session)
                        navigation['keep_awake_after_loss'] = 'passed'
                        await cdp.wait("!document.querySelector('[data-action=connect]').disabled", session)
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
                        (output / 'navigation.json').write_text(json.dumps(navigation, indent=2) + '\n')
                        (output / 'alerts.json').write_text(json.dumps(alert_result, indent=2) + '\n')
                        (output / 'presets.json').write_text(json.dumps(preset_result, indent=2) + '\n')
                        before_replay = behavior.view()['diagnostics']['valid_frames']
                        document = await cdp.call('DOM.getDocument', session=session)
                        node = await cdp.call('DOM.querySelector', {'nodeId':document['root']['nodeId'], 'selector':'#replay-file'}, session)
                        await cdp.call('DOM.setFileInputFiles', {'nodeId':node['nodeId'],
                            'files':[str(Path('experiments/laptop-feasibility/evidence/fixture-recording.jsonl').resolve())]}, session)
                        await cdp.wait("!document.querySelector('#replay-load').disabled", session)
                        await cdp.evaluate("document.querySelector('#replay-load').click()", session)
                        await cdp.wait("document.querySelector('#mode').textContent.includes('REPLAY')", session)
                        for count in range(1,14):
                            await cdp.wait("!document.querySelector('#replay-step').disabled", session)
                            await cdp.evaluate("document.querySelector('#replay-step').click()", session)
                            await cdp.wait(f"document.querySelector('#replay-progress').textContent.includes('{count} / 13')", session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('battery 97 percent')", session)
                        replay_result = {'issue':24, 'provenance':'actual file import / Canvas / aiohttp / read-only replay',
                            'expected':'13 preserved notifications; three valid source frames; final voltage-derived97% and avg4.09V',
                            'observed':await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session),
                            'valid_frames':behavior.view()['diagnostics']['valid_frames']-before_replay,
                            'recording':behavior.view()['replay']}
                        assert replay_result['valid_frames'] == 3
                        assert await cdp.evaluate("document.querySelector('[data-action=simulator_emit]').disabled",session)
                        await cdp.evaluate("window.savedFileText=File.prototype.text; File.prototype.text=function(){return new Promise(resolve=>{window.finishFileRead=()=>window.savedFileText.call(this).then(resolve)})}; document.querySelector('#replay-load').click()",session)
                        await cdp.wait("typeof window.finishFileRead === 'function'",session)
                        await cdp.evaluate("document.querySelector('[data-action=simulator_start]').click()",session)
                        await cdp.wait("document.querySelector('#mode').textContent === 'SIMULATOR' && !document.querySelector('[data-action=simulator_start]').disabled",session)
                        newer_session = behavior.view()['session']
                        await cdp.evaluate("window.finishFileRead(); File.prototype.text=window.savedFileText",session)
                        await cdp.wait("!document.querySelector('#replay-load').disabled",session)
                        assert behavior.view()['mode']=='simulator' and behavior.view()['session']==newer_session
                        replay_result['delayed_file_after_new_session']='discarded'
                        (output / 'replay.json').write_text(json.dumps(replay_result,indent=2)+'\n')
                        print(json.dumps(report, indent=2))
                        print(json.dumps(replay_result, indent=2))
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
