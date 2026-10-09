"""Real Chrome lifecycle failures against the built UI and authoritative host."""
from preset_fixture import save_preset

import asyncio
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from contextlib import suppress

from aiohttp import ClientSession, web

from browser_flow import Browser
from eucwatch import Application
from eucwatch.persistence import FileStore
from eucwatch.recording import Recorder
from eucwatch.server import create_app


async def run():
    with tempfile.TemporaryDirectory(prefix='eucwatch-lifecycle-') as directory:
        root=Path(directory)
        app=Application(store=FileStore(root/'configuration.json'))
        save_preset(app, slot=1, name='Retained',pedal_sensitivity=31,dynamic_assist=26)
        recorder=Recorder(root/'capture.jsonl')
        app.event_sink=recorder.record
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        runner=web.AppRunner(create_app(app,recorder=recorder,controller_timeout=.7))
        await runner.setup();await web.TCPSite(runner,'127.0.0.1',port).start()
        url=f'http://127.0.0.1:{port}'
        browser=subprocess.Popen(['google-chrome','--headless','--no-first-run','--no-default-browser-check',
            '--disable-sync','--disable-background-networking','--remote-debugging-port=0',
            f'--user-data-dir={root / "profile"}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            portfile=root/'profile'/'DevToolsActivePort'
            async with asyncio.timeout(15):
                while not portfile.exists(): await asyncio.sleep(.05)
            chrome_port,path=portfile.read_text().splitlines()
            async with ClientSession() as client:
                async with client.ws_connect(f'http://127.0.0.1:{chrome_port}{path}') as ws:
                    cdp=Browser(ws)
                    async def tab():
                        target=await cdp.call('Target.createTarget',{'url':url})
                        attached=await cdp.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True})
                        return target['targetId'],attached['sessionId']
                    target,owner=await tab()
                    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",owner)
                    await cdp.evaluate("document.querySelector('#controlled').checked=false;document.querySelector('#start').click()",owner)
                    await cdp.wait("document.querySelector('#mode').textContent==='SIMULATOR'",owner)
                    count=len(app.view()['command_events'])
                    await cdp.call('Page.reload',session=owner)
                    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready' && document.querySelector('#mode').textContent==='SIMULATOR'",owner)
                    assert len(app.view()['command_events'])==count
                    await cdp.evaluate("window.originalFetch=window.fetch;window.fetch=(url,...args)=>window.originalFetch(url,...args).then(response=>String(url).includes('/api/state')&&!window.capturedOldState ? (window.capturedOldState=true,new Promise(resolve=>window.finishOldState=()=>resolve(response))) : response)",owner)
                    await cdp.wait("typeof window.finishOldState==='function'",owner)
                    await cdp.evaluate("document.querySelector('#stop').click()",owner)
                    await cdp.wait("document.querySelector('#mode').textContent==='IDLE · NO WHEEL'",owner)
                    await cdp.evaluate("window.finishOldState();window.fetch=window.originalFetch",owner)
                    await asyncio.sleep(.3)
                    assert await cdp.evaluate("document.querySelector('#mode').textContent==='IDLE · NO WHEEL'",owner)
                    await cdp.wait("!document.querySelector('#start').disabled",owner)
                    await cdp.evaluate("document.querySelector('#controlled').checked=false;document.querySelector('#start').click()",owner)
                    await cdp.wait("document.querySelector('#mode').textContent==='SIMULATOR'",owner)
                    other_target,other=await tab()
                    await cdp.wait("document.querySelector('#backend-status')?.textContent.includes('Viewing only')",other)
                    assert await cdp.evaluate("document.querySelector('#start').disabled",other)
                    await cdp.call('Emulation.setFocusEmulationEnabled',{'enabled':True},other)
                    before=app.view()['diagnostics']['valid_frames']
                    await cdp.call('Page.setWebLifecycleState',{'state':'frozen'},owner)
                    await asyncio.sleep(1)
                    await cdp.wait("document.querySelector('#backend-status').textContent==='Application ready'",other)
                    assert app.view()['diagnostics']['valid_frames']>before
                    assert recorder.status()['written']>0
                    await cdp.call('Page.setWebLifecycleState',{'state':'active'},owner)
                    await cdp.call('Emulation.setFocusEmulationEnabled',{'enabled':True},owner)
                    await cdp.wait("document.querySelector('#backend-status').textContent.includes('Viewing only')",owner)
                    assert await cdp.evaluate("document.querySelector('#watch-button').disabled",owner)
                    await cdp.call('Target.closeTarget',{'targetId':other_target})
                    await cdp.wait("document.querySelector('#backend-status').textContent==='Application ready'",owner)
                    # Press/reload is a released cycle, never a resubmitted request.
                    box=await cdp.evaluate("(() => {const b=document.querySelector('#watch-button').getBoundingClientRect();return {x:b.x+10,y:b.y+20}})()",owner)
                    await cdp.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':box['x'],'y':box['y'],'button':'left','buttons':1,'clickCount':1},owner)
                    await cdp.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'",owner)
                    pressed_count=len(app.view()['command_events'])
                    await cdp.call('Page.reload',session=owner)
                    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",owner)
                    async with asyncio.timeout(3):
                        while app.view()['button']['down']: await asyncio.sleep(.01)
                    assert len(app.view()['command_events'])==pressed_count
                    before=app.view()['diagnostics']['valid_frames']
                    await cdp.call('Target.closeTarget',{'targetId':target})
                    await asyncio.sleep(.5)
                    assert app.view()['diagnostics']['valid_frames']>before
                    target,owner=await tab()
                    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",owner)
                    await runner.cleanup()
                    await cdp.wait("document.querySelector('#backend-status').textContent.includes('unavailable')",owner)
                    assert await cdp.evaluate("document.querySelector('#watch-button').disabled && document.querySelector('#start').disabled",owner)
                    restarted=Application(store=FileStore(root/'configuration.json'))
                    runner=web.AppRunner(create_app(restarted,controller_timeout=.7))
                    await runner.setup();await web.TCPSite(runner,'127.0.0.1',port).start()
                    await cdp.wait("document.querySelector('#backend-status').textContent==='Application ready' && document.querySelector('#mode').textContent==='IDLE · NO WHEEL'",owner)
                    assert restarted.view()['config']['presets'][0]['name']=='Retained'
                    assert restarted.view()['preset_attempt'] is None and restarted.view()['command_events']==[]
                    evidence={'issue':30,'provenance':'actual built Chrome UI / aiohttp / background recorder / local durable store; accelerated0.7s test lease (production10s)',
                        'expected':'reload noresubmit; delayedoldpoll discarded; competition readonly; freeze backendcontinues; lease takeover oldownerreadonly; closure backendcontinues; backendloss controlsdisabled; offline relaunchsavedonly',
                        'observed':'passed','physical_suspend':'explicitly omitted by owner; synthetic resume covered in test_lifecycle.py'}
                    Path('.test-output/lifecycle.json').write_text(json.dumps(evidence,indent=2)+'\n')
                    print(json.dumps(evidence,indent=2))
        finally:
            browser.terminate()
            try: await asyncio.to_thread(browser.wait,timeout=5)
            except subprocess.TimeoutExpired:
                browser.kill();await asyncio.to_thread(browser.wait)
            await runner.cleanup()


if __name__=='__main__':
    asyncio.run(run())
