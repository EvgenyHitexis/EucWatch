"""Real built UI against the aiohttp application, driven with Chrome CDP."""
import asyncio
import base64
from contextlib import suppress
import json
import hashlib
from pathlib import Path
import socket
import subprocess
import tempfile
from uuid import uuid4

from aiohttp import ClientSession, web

from eucwatch import Application, ManualClock
from eucwatch.server import create_app
from eucwatch.persistence import FileStore
from eucwatch.recording import Recorder
from eucwatch.live import LiveSession
from eucwatch.scenarios import FileScenarioStore
from test_live import Scanner, Clients, ADDRESS, SOURCE_FRAME
from test_live_control import WritingClient
from test_control import settings_frame
from browser_preset_editor import exercise
from browser_alerts import exercise as exercise_alerts


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
    run_id=uuid4().hex
    recorder = Recorder(Path(f'.test-output/ui-recording-{run_id}.jsonl'))
    behavior = Application(clock=host_clock, event_sink=recorder.record, store=FileStore(Path(f'.test-output/ui-config-{run_id}.json')))
    live_clients = Clients()
    def writing_client(*args,**options):
        client=WritingClient(*args,**options)
        live_clients.created.append(client)
        return client
    live = LiveSession(behavior,scanner=Scanner(),client_factory=writing_client,reconnect_delay=0)
    runner = web.AppRunner(create_app(behavior, recorder=recorder,live=live,scenario_store=FileScenarioStore(Path(f'.test-output/ui-scenario-{run_id}.json'))))
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
                        assert all(name in presets for name in ['Jump','Forest','Road','Drag'])
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
                        await cdp.pointer('#watch', (120, 215), (120, 20), session)
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
                        await cdp.pointer('#watch', (120,155), (120,155), session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Alert editor 1')",session)
                        await cdp.pointer('#watch',(120,88),(120,88),session)
                        await cdp.wait("document.querySelector('#alert-pwm-enabled').checked",session)
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('#alerts-status').textContent.includes('Saved')",session)
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                        assert behavior.view()['config']['alerts']['pwm']=={'enabled':False,'threshold':None}
                        navigation['back_discards_unsaved_alert_draft']='passed'
                        alert_result = await exercise_alerts(cdp, session, behavior, host_clock)
                        preset_result = await exercise(cdp, session, behavior, Path('.test-output/preset-editor'))
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='settings'",session)
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                        await cdp.evaluate("document.querySelector('#controlled').checked=true;document.querySelector('[data-action=simulator_start]').click()", session)
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
                        await cdp.pointer('#watch',(215,120),(20,120),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='presets'",session)
                        await cdp.pointer('#watch',(177,80),(177,80),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard' && document.querySelector('canvas').getAttribute('aria-label').includes('Ab 2 · Applying')",session)
                        await cdp.evaluate("document.querySelector('#advance-seconds').value='0.2'",session)
                        for index in range(2):
                            await cdp.wait("!document.querySelector('#advance').disabled",session)
                            await cdp.evaluate("document.querySelector('#advance').click()",session)
                            await cdp.wait(f"Number(document.querySelector('canvas').dataset.elapsed)>={.2*(index+1)-.00001}",session)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Ab 2 · Confirmed')",session)
                        control_result={'issue':22,'provenance':'actual Canvas one-tap / aiohttp / actual settings-frame parser / moving simulator',
                            'expected':'Ab 2 onetap immediately dashboard Applying while speed25; two matching fresh settings frames Confirmed',
                            'observed':'passed','attempt':behavior.view()['preset_attempt']}
                        def horn_count():
                            return sum(row.get('kind')=='horn' and row['event']=='submission' for row in behavior.view()['command_events'])
                        before_horn=horn_count()
                        await cdp.pointer('#watch-button',(10,20),(10,20),session)
                        await cdp.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'",session)
                        assert horn_count()==before_horn+1
                        await cdp.pointer('#watch',(120,10),(120,110),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='settings'",session)
                        await cdp.pointer('#watch',(120,100),(120,100),session)
                        await cdp.wait("document.querySelector('canvas').dataset.awake==='false'",session)
                        await cdp.pointer('#watch-button',(10,20),(10,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.awake==='true'",session)
                        assert horn_count()==before_horn+1
                        await cdp.pointer('#watch-button',(10,20),(10,20),session)
                        await cdp.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'",session)
                        assert horn_count()==before_horn+2
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                        horn_result={'issue':23,'provenance':'actual modeled sidebutton / Canvas / aiohttp / simulator command outputs',
                            'expected':'awakepressone LkAp request, wholeSleepwakecycle no horn, freshpressrequired; pending/stale pressesdiscarded',
                            'observed':'passed','physical_audible_evidence':'pending #9; sent request only'}
                        control_result['failure_scenarios']=[]
                        async def advance_control(seconds=.5):
                            elapsed=behavior.view()['elapsed_s']
                            await cdp.evaluate(f"document.querySelector('#advance-seconds').value={json.dumps(str(seconds))}",session)
                            await cdp.wait("!document.querySelector('#advance').disabled",session)
                            await cdp.evaluate("document.querySelector('#advance').click()",session)
                            await cdp.wait(f"Number(document.querySelector('canvas').dataset.elapsed)>={elapsed+seconds-.00001}",session)
                        for readback,submission,expected in [('missing','normal','Not confirmed'),('mismatch','normal','Not confirmed'),('partial','normal','Partially applied'),('normal','fail','Not confirmed'),('normal','hang','Not confirmed')]:
                            await cdp.evaluate(f"document.querySelector('#control-readback').value={json.dumps(readback)}; document.querySelector('#control-submission').value={json.dumps(submission)}",session)
                            await scenario(25,148.05,45)
                            previous_id=behavior.view()['preset_attempt']['id']
                            await cdp.pointer('#watch',(215,120),(20,120),session)
                            await cdp.wait("document.querySelector('canvas').dataset.screen==='presets'",session)
                            await cdp.pointer('#watch',(177,80),(177,80),session)
                            await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                            assert behavior.view()['preset_attempt']['id']>previous_id
                            if behavior.view()['preset_attempt']['pending']:
                                blocked_count=horn_count()
                                await cdp.pointer('#watch-button',(10,20),(10,20),session)
                                await cdp.wait("document.querySelector('#watch-feedback').textContent==='Horn unavailable: preset applying'",session)
                                assert horn_count()==blocked_count
                            for _ in range(22):
                                if not behavior.view()['preset_attempt']['pending']:break
                                await advance_control()
                            result=behavior.view()['preset_attempt']
                            assert result['status']==expected,result
                            await cdp.wait(f"document.querySelector('#preset-outcome').textContent.includes({json.dumps(expected)})",session)
                            control_result['failure_scenarios'].append({'readback':readback,'submission':submission,'observed':expected,'reason':result['reason']})
                        await cdp.evaluate("document.querySelector('#control-readback').value='normal'; document.querySelector('#control-submission').value='normal'",session)
                        await scenario(25,148.05,45)
                        assert behavior.view()['preset_attempt']['status']=='Not confirmed'
                        await cdp.pointer('#watch',(215,120),(20,120),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='presets'",session)
                        await cdp.pointer('#watch',(177,80),(177,80),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                        await advance_control(.2)
                        await advance_control(.2)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('Ab 2 · Confirmed')",session)
                        control_result['explicit_retry']='Confirmed; late readings before retry retained prior failure'
                        await cdp.evaluate("document.querySelector('#advance-seconds').value='1.1'",session)
                        await scenario(25, 119.02, 45)
                        await cdp.wait("document.querySelector('canvas').getAttribute('aria-label').includes('battery 0 percent')", session)
                        await scenario(25, 138, 45, 'paused')
                        await cdp.evaluate("document.querySelector('[data-action=advance]').click()", session)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh === 'false'", session)
                        stale = await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')", session)
                        assert 'Speed —' in stale and 'wheel battery dimmed' in stale
                        assert 'Ab 2 · Confirmed' not in stale
                        blocked_count=horn_count()
                        await cdp.pointer('#watch-button',(10,20),(10,20),session)
                        await cdp.wait("document.querySelector('#watch-feedback').textContent==='Horn unavailable: connection unavailable'",session)
                        assert horn_count()==blocked_count
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
                        (output / 'control.json').write_text(json.dumps(control_result, indent=2) + '\n')
                        (output / 'horn.json').write_text(json.dumps(horn_result, indent=2) + '\n')
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
                        await cdp.wait("!document.querySelector('#live-discover').disabled",session)
                        await cdp.evaluate("document.querySelector('#live-discover').click()",session)
                        await cdp.wait("document.querySelector('#live-device').options.length===2 && !document.querySelector('#live-device').disabled",session)
                        assert live_clients.created==[]
                        await cdp.evaluate(f"document.querySelector('#live-device').value={json.dumps(ADDRESS)}; document.querySelector('#live-device').dispatchEvent(new Event('change'))",session)
                        await cdp.wait("!document.querySelector('#live-select').disabled",session)
                        await cdp.evaluate("document.querySelector('#live-select').click()",session)
                        await cdp.wait("document.querySelector('#mode').textContent==='LIVE WHEEL' && document.querySelector('#live-status').textContent.includes('subscribed')",session)
                        assert not behavior.view()['fresh']
                        live_clients.created[0].emit(SOURCE_FRAME)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh==='true' && document.querySelector('#live-status').textContent.includes('006.0.03')",session)
                        await cdp.pointer('#watch',(215,120),(20,120),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='presets'",session)
                        await cdp.pointer('#watch',(177,80),(177,80),session)
                        await cdp.wait("document.querySelector('#preset-outcome').textContent.includes('Applying')",session)
                        async with asyncio.timeout(2):
                            while behavior.view()['preset_attempt']['status']!='confirming':
                                await asyncio.sleep(.01)
                        assert [len(data) for _,data,_ in live_clients.created[0].writes]==[15,20,11]
                        host_clock.advance(.1)
                        live_clients.created[0].emit(settings_frame(sensitivity=31,assist=26))
                        assert behavior.view()['confirmed_preset'] is None
                        host_clock.advance(.1)
                        live_clients.created[0].emit(settings_frame(sensitivity=31,assist=26))
                        await cdp.wait("document.querySelector('#preset-outcome').textContent==='Ab 2 · Confirmed'",session)
                        await cdp.pointer('#watch-button',(10,20),(10,20),session)
                        await cdp.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'",session)
                        assert [len(data) for _,data,_ in live_clients.created[0].writes]==[15,20,11,14]
                        live_control_result={'issue':26,'provenance':'actual Canvas preset/button / aiohttp / selected fake Bleak telemetry connection',
                            'expected':'serialized responseFalse15/20/11 bytes; two raw matching frames confirm; one14byteLkAp horn request; no physical operation',
                            'observed':'passed','chunks':[len(data) for _,data,_ in live_clients.created[0].writes],
                            'physical_mappings_ranges_persistence_movement_and_audible_horn':'unverified under #9/#31'}
                        (output/'live-control.json').write_text(json.dumps(live_control_result,indent=2)+'\n')
                        first=live_clients.created[0]
                        first.lose_link()
                        assert not behavior.view()['fresh']
                        await cdp.wait("document.querySelector('#live-diagnostics').textContent.includes('1 reconnections')",session)
                        assert not behavior.view()['fresh']
                        first.emit(SOURCE_FRAME)
                        assert not behavior.view()['fresh']
                        live_clients.created[1].emit(SOURCE_FRAME)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh==='true'",session)
                        await cdp.wait("!document.querySelector('[data-action=simulator_start]').disabled",session)
                        await cdp.evaluate("document.querySelector('[data-action=simulator_start]').click()",session)
                        await cdp.wait("document.querySelector('#mode').textContent==='SIMULATOR'",session)
                        assert not live_clients.created[1].is_connected
                        live_result={'issue':25,'provenance':'actual HTML discovery/select / Canvas / aiohttp / controlled Bleak-compatible transports',
                            'expected':'explicitscanonly, livefreshidentity, loss/newsession/freshrecovery, oldcallbackinert, simulatorcloseslive',
                            'observed':'passed','physical_evidence':'pending owner authorization'}
                        (output/'live.json').write_text(json.dumps(live_result,indent=2)+'\n')
                        download_dir=(output/f'downloads-{run_id}').resolve()
                        download_dir.mkdir(exist_ok=True)
                        await cdp.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(download_dir)})
                        await cdp.wait("!document.querySelector('#configuration-export').disabled",session)
                        await cdp.evaluate("document.querySelector('#configuration-export').click()",session)
                        await cdp.wait("document.querySelector('#configuration-status').textContent.includes('Exported')",session)
                        async with asyncio.timeout(5):
                            while not (download_dir/'eucwatch-configuration.json').exists():
                                await asyncio.sleep(.05)
                        exported=json.loads((download_dir/'eucwatch-configuration.json').read_text())
                        assert set(exported)=={'version','revision','presets','alerts'}
                        before_backup=behavior.view()['config']
                        before_commands=len(behavior.view()['command_events'])
                        candidate=json.loads(json.dumps(exported))
                        candidate['presets'][0]['name']='Backup slot'
                        config_file=(output/'import-configuration.json').resolve()
                        config_file.write_text(json.dumps(candidate))
                        document=await cdp.call('DOM.getDocument',session=session)
                        node=await cdp.call('DOM.querySelector',{'nodeId':document['root']['nodeId'],'selector':'#configuration-file'},session)
                        await cdp.call('DOM.setFileInputFiles',{'nodeId':node['nodeId'],'files':[str(config_file)]},session)
                        async def review_configuration():
                            await cdp.wait("!document.querySelector('#configuration-review').disabled",session)
                            await cdp.evaluate("document.querySelector('#configuration-review').click()",session)
                            await cdp.wait("document.querySelector('#configuration-preview').textContent.includes('Backup slot')",session)
                        await review_configuration()
                        assert behavior.view()['config']==before_backup
                        await cdp.wait("!document.querySelector('#configuration-cancel').disabled",session)
                        await cdp.evaluate("document.querySelector('#configuration-cancel').click()",session)
                        await cdp.wait("document.querySelector('#configuration-preview').textContent===''",session)
                        assert behavior.view()['config']==before_backup
                        await review_configuration()
                        await cdp.wait("!document.querySelector('#configuration-restore').disabled",session)
                        await cdp.evaluate("document.querySelector('#configuration-restore').click()",session)
                        await cdp.wait("document.querySelector('#configuration-status').textContent.includes('restored locally')",session)
                        assert behavior.view()['config']['presets'][0]['name']=='Backup slot'
                        assert len(behavior.view()['command_events'])==before_commands
                        assert behavior.view()['confirmed_preset'] is None
                        invalid_file=(output/'invalid-configuration.json').resolve()
                        candidate['version']=999
                        invalid_file.write_text(json.dumps(candidate))
                        await cdp.call('DOM.setFileInputFiles',{'nodeId':node['nodeId'],'files':[str(invalid_file)]},session)
                        await cdp.wait("!document.querySelector('#configuration-review').disabled",session)
                        await cdp.evaluate("document.querySelector('#configuration-review').click()",session)
                        await cdp.wait("document.querySelector('#message').textContent.includes('Unsupported')",session)
                        assert behavior.view()['config']['presets'][0]['name']=='Backup slot'
                        backup_result={'issue':27,'provenance':'actual file download/import/review/Cancel/Restore / HTML / aiohttp',
                            'expected':'saved-only export, preview noactivation, Cancelpreserves, explicitrestore, unknownversionrefused, no commands',
                            'observed':'passed','migration':'Schema 2 export; schema 1 migration is explicit; compatible updates preserve meaning; unknown versions require review'}
                        (output/'backup.json').write_text(json.dumps(backup_result,indent=2)+'\n')
                        await cdp.pointer('#watch',(120,10),(120,110),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='settings'",session)
                        assert await cdp.evaluate("!document.querySelector('[id^=transfer-],[id^=nordic-]')",session)
                        assert await cdp.evaluate("!/transfer|synchron|reconcil|conflict/i.test(document.querySelector('.panel').innerText + document.querySelector('canvas').getAttribute('aria-label'))",session)
                        before_removed_touch=behavior.view()
                        await cdp.pointer('#watch',(120,215),(120,215),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='preset_slots'",session)
                        assert behavior.view()['config']==before_removed_touch['config']
                        assert behavior.view()['session']==before_removed_touch['session']
                        assert behavior.view()['connected']==before_removed_touch['connected']
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='settings'",session)
                        (output/'local-configuration-browser.json').write_text(json.dumps({
                            'issue':40,
                            'provenance':'built Canvas and HTML panel / Chrome CDP / aiohttp / simulated wheel',
                            'expected':'no transfer, synchronization or conflict entries; former touch opens local Presets without changing configuration or wheel session; upward return and local backup/import/restore remain usable',
                            'observed':'passed; saved Backup slot and preferences preserved; backup export, review, Cancel, restore and invalid-import refusal exercised earlier in this flow',
                            'source_sha256':{source:hashlib.sha256(Path(source).read_bytes()).hexdigest() for source in ['frontend/src/main.ts','frontend/src/backup.ts','laptop/eucwatch/server.py','tests/browser_flow.py']},
                            'physical_operation':'none'
                        },indent=2)+'\n')
                        await cdp.pointer('#watch',(120,215),(120,20),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                        await cdp.wait("!document.querySelector('#scenario-save').disabled",session)
                        await cdp.evaluate("document.querySelector('#scenario-name').value='Reproducible dashboard';document.querySelector('#scenario-save').click()",session)
                        await cdp.wait("document.querySelector('#scenario-status').textContent.includes('saved locally')",session)
                        await cdp.wait("!document.querySelector('#scenario-export').disabled",session)
                        await cdp.evaluate("document.querySelector('#scenario-export').click()",session)
                        async with asyncio.timeout(5):
                            while not (download_dir/'eucwatch-scenario.json').exists(): await asyncio.sleep(.05)
                        definition=json.loads((download_dir/'eucwatch-scenario.json').read_text())
                        assert definition['seed']==0 and definition['clock']=='controlled'
                        document=await cdp.call('DOM.getDocument',session=session)
                        node=await cdp.call('DOM.querySelector',{'nodeId':document['root']['nodeId'],'selector':'#scenario-file'},session)
                        await cdp.call('DOM.setFileInputFiles',{'nodeId':node['nodeId'],'files':[str(download_dir/'eucwatch-scenario.json')]},session)
                        before_review=behavior.view()['session']
                        await cdp.wait("!document.querySelector('#scenario-review').disabled",session)
                        await cdp.evaluate("document.querySelector('#scenario-review').click()",session)
                        await cdp.wait("document.querySelector('#scenario-preview').textContent.includes('Reviewed import')",session)
                        assert behavior.view()['session']==before_review
                        await cdp.wait("!document.querySelector('#scenario-start').disabled",session)
                        await cdp.evaluate("document.querySelector('#scenario-start').click()",session)
                        await cdp.wait("document.querySelector('#scenario-status').textContent.includes('started')",session)
                        assert behavior.view()['controlled'] and behavior.view()['elapsed_s']==0
                        for index in range(3):
                            await cdp.wait("!document.querySelector('#scenario-step').disabled",session)
                            await cdp.evaluate("document.querySelector('#scenario-step').click()",session)
                            await cdp.wait(f"document.querySelector('#scenario-status').textContent.includes('{index+1}/3')",session)
                        assert behavior.view()['elapsed_s']==1.4
                        assert await cdp.evaluate("document.querySelector('#scenario-step').disabled",session)
                        scenario_result={'issue':31,'provenance':'actual saved-file backend / Chrome export/import/review/start/step; fixed inputs seed0 controlled raw parser',
                            'expected':'complete bounded definition saves/exports; review noactivation; explicit freshstart; three deterministicsteps; no commands',
                            'observed':'passed','owner_review_and_live_acceptance':'pending'}
                        (output/'scenarios.json').write_text(json.dumps(scenario_result,indent=2)+'\n')
                        await cdp.pointer('#watch',(215,120),(20,120),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='presets'",session)
                        await cdp.pointer('#watch',(177,80),(177,80),session)
                        await cdp.wait("document.querySelector('#preset-outcome').textContent.includes('Applying')",session)
                        before_resume=behavior.view()
                        host_clock.advance(60,suspended=True)
                        await cdp.wait("document.querySelector('canvas').dataset.fresh==='false' && !document.querySelector('#preset-outcome').textContent.includes('Applying')",session)
                        after_resume=behavior.view()
                        assert after_resume['session']>before_resume['session']
                        assert after_resume['elapsed_s']==before_resume['elapsed_s']
                        assert len(after_resume['command_events'])>=len(before_resume['command_events'])
                        submitted_before=[row for row in before_resume['command_events'] if row['event']=='submission']
                        submitted_after=[row for row in after_resume['command_events'] if row['event']=='submission']
                        assert submitted_after==submitted_before
                        behavior.receive(before_resume['session'],b''.join(behavior.simulator.notifications(now=after_resume['elapsed_s'])))
                        assert not behavior.view()['fresh']
                        resume_result={'issue':30,'provenance':'actual Canvas pending preset / controlled simulator clock / independent synthetic host suspend / aiohttp',
                            'expected':'host resume invalidates source and pending intent even with paused virtual time; late old frame cannot recover; no overdue command',
                            'observed':'passed','physical_suspend':'omitted by owner'}
                        (output/'resume.json').write_text(json.dumps(resume_result,indent=2)+'\n')
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
