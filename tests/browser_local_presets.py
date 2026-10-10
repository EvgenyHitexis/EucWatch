"""Real built Canvas/backend checks for #43; physical wheel never selected."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from aiohttp import ClientSession, web
from browser_flow import Browser
from eucwatch import Application, ManualClock
from eucwatch.persistence import FileStore
from eucwatch.server import create_app

FIXTURE = json.loads(Path('docs/acceptance/scenarios/local-presets.json').read_text())

async def defaults(cdp, session, app, output):
    trace=[]
    async def pointer(start,end):
        trace.append({'start':start,'end':end})
        await cdp.pointer('#watch',start,end,session)
    async def screen(name):
        await cdp.wait(f"document.querySelector('canvas').dataset.screen==='{name}'",session)
    async def render(name):
        label=await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')",session)
        image=await cdp.evaluate("document.querySelector('canvas').toDataURL().split(',')[1]",session)
        (output/(name+'.png')).write_bytes(base64.b64decode(image))
        return label
    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",session)
    assert app.view()['config']==FIXTURE['fresh']
    await pointer((215,120),(20,120));await screen('presets')
    riding=await render('defaults-riding')
    assert all(name in riding for name in ['Jump','Forest','Road','Drag'])
    await pointer((20,120),(215,120));await screen('dashboard')
    await pointer((120,10),(120,110));await screen('settings')
    await pointer((120,196),(120,196));await screen('preset_slots')
    selection=await render('defaults-settings')
    assert all(name in selection for name in ['Jump','Forest','Road','Drag'])
    await cdp.evaluate("document.querySelector('#controlled').checked=true;document.querySelector('#start').click()",session)
    await cdp.wait("document.querySelector('#mode').textContent==='SIMULATOR'",session)
    seed=json.loads(json.dumps(FIXTURE['fresh']))
    seed['presets'][0].update(pedal_dip_compensation=83,dip_included=True)
    app.action('configuration_import_prepare',content=json.dumps(seed));app.action('configuration_import_commit')
    app.action('preset_apply',slot=1)
    app.action('advance',seconds=.2);app.action('advance',seconds=.2)
    app.action('configuration_import_prepare',content=json.dumps(FIXTURE['fresh']));app.action('configuration_import_commit')
    observed=[]
    for slot,packets in enumerate(FIXTURE['default_packets'],1):
        app.action('swipe',direction='right')
        while app.view()['screen']!='dashboard':app.action('swipe',direction='up')
        await screen('dashboard')
        await pointer((215,120),(20,120));await screen('presets')
        x=66 if slot%2 else 174;y=80 if slot<=2 else 170
        before=len(app.view()['command_events'])
        await pointer((x,y),(x,y));await screen('dashboard')
        app.action('advance',seconds=.2);app.action('advance',seconds=.2)
        state=app.view()
        actual=[row['packet_hex'] for row in state['command_events'][before:] if row['event']=='submission']
        assert actual==packets,(slot,actual,packets)
        assert state['actual_settings']['pedal_dip_compensation']==83
        assert state['confirmed_preset']['slot']==slot
        observed.append({'slot':slot,'expected_packets':packets,'observed_packets':actual,'wheel_dip':83})
    return {'issue':44,'expected':FIXTURE['fresh'],'observed':app.view()['config'],'rendered':[riding,selection],'pointer_trace':trace,'applications':observed}

async def run(flow=defaults, name='defaults-laptop'):
    output=Path('docs/acceptance/evidence/local-presets');output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='eucwatch-local-', ignore_cleanup_errors=True) as temporary:
        app=Application(clock=ManualClock(),store=FileStore(Path(temporary)/'config.json'))
        runner=web.AppRunner(create_app(app));await runner.setup()
        sock=socket.socket();sock.bind(('127.0.0.1',0));await web.SockSite(runner,sock).start()
        profile=Path(temporary)/'chrome'
        browser=subprocess.Popen(['google-chrome','--headless','--no-first-run','--no-default-browser-check','--disable-sync','--disable-background-networking','--remote-debugging-port=0',f'--user-data-dir={profile}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            async with asyncio.timeout(15):
                while not (profile/'DevToolsActivePort').exists():
                    if browser.poll() is not None:raise RuntimeError('Chrome exited')
                    await asyncio.sleep(.1)
            port,path=(profile/'DevToolsActivePort').read_text().splitlines()
            async with ClientSession() as client, client.ws_connect(f'http://127.0.0.1:{port}{path}') as ws:
                cdp=Browser(ws);target=await cdp.call('Target.createTarget',{'url':f'http://127.0.0.1:{sock.getsockname()[1]}'})
                session=(await cdp.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True}))['sessionId']
                result=await flow(cdp,session,app,output)
                result.update(provenance='Actual built Canvas / Chrome pointer events / aiohttp Application / FileStore / controlled simulator; no physical operations',source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*Path('laptop/eucwatch').glob('*.py'),*Path('frontend/src').glob('*.ts'),Path(__file__)]})
                (output/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
                print(name+': passed')
        finally:
            browser.terminate();browser.wait(timeout=10);await runner.cleanup()
if __name__=='__main__':asyncio.run(run())
