"""Real Chrome lifecycle failures against the built UI and authoritative host."""
from preset_fixture import save_preset

import asyncio
import json
from pathlib import Path
import tempfile

from eucwatch import Application
from eucwatch.persistence import FileStore
from eucwatch.recording import Recorder
from support import Server, chrome, main, write_evidence


async def run():
    with tempfile.TemporaryDirectory(prefix='eucwatch-lifecycle-', ignore_cleanup_errors=True) as directory:
        root=Path(directory)
        app=Application(store=FileStore(root/'configuration.json'))
        save_preset(app, slot=1, name='Retained',pedal_sensitivity=31,dynamic_assist=26)
        recorder=Recorder(root/'capture.jsonl')
        app.event_sink=recorder.record
        server=await Server(app,recorder=recorder,controller_timeout=.7).start()
        try:
            async with chrome() as browser:
                owner=await browser.open(server.url)
                await owner.wait("document.querySelector('#backend-status')?.textContent==='Application ready'")
                await owner.evaluate("document.querySelector('#controlled').checked=false;document.querySelector('#start').click()")
                await owner.wait("document.querySelector('#mode').textContent==='SIMULATOR'")
                # Reload abandons a local editor operation, including active text.
                await owner.pointer((120,10),(120,110))
                await owner.screen('settings')
                await owner.tap(120,196)
                await owner.screen('preset_slots')
                await owner.tap(80,55)
                await owner.screen('preset_editor')
                await owner.tap(120,80)
                await owner.label('keypad')
                saved_before_reload=app.view()['config']
                count=len(app.view()['command_events'])
                await owner.call('Page.reload')
                await owner.wait("document.querySelector('#backend-status')?.textContent==='Application ready' && document.querySelector('#mode').textContent==='SIMULATOR'")
                assert len(app.view()['command_events'])==count
                assert app.view()['preset_editor'] is None
                assert app.view()['config']==saved_before_reload
                await owner.evaluate("window.originalFetch=window.fetch;window.fetch=(url,...args)=>window.originalFetch(url,...args).then(response=>String(url).includes('/api/state')&&!window.capturedOldState ? (window.capturedOldState=true,new Promise(resolve=>window.finishOldState=()=>resolve(response))) : response)")
                await owner.wait("typeof window.finishOldState==='function'")
                await owner.evaluate("document.querySelector('#stop').click()")
                await owner.wait("document.querySelector('#mode').textContent==='IDLE · NO WHEEL'")
                await owner.evaluate("window.finishOldState();window.fetch=window.originalFetch")
                await asyncio.sleep(.3)
                assert await owner.evaluate("document.querySelector('#mode').textContent==='IDLE · NO WHEEL'")
                await owner.wait("!document.querySelector('#start').disabled")
                await owner.evaluate("document.querySelector('#controlled').checked=false;document.querySelector('#start').click()")
                await owner.wait("document.querySelector('#mode').textContent==='SIMULATOR'")
                other=await browser.open(server.url)
                await other.wait("document.querySelector('#backend-status')?.textContent.includes('Viewing only')")
                assert await other.evaluate("document.querySelector('#start').disabled")
                await other.call('Emulation.setFocusEmulationEnabled',{'enabled':True})
                before=app.view()['diagnostics']['valid_frames']
                await owner.call('Page.setWebLifecycleState',{'state':'frozen'})
                await asyncio.sleep(1)
                await other.wait("document.querySelector('#backend-status').textContent==='Application ready'")
                assert app.view()['diagnostics']['valid_frames']>before
                assert recorder.status()['written']>0
                await owner.call('Page.setWebLifecycleState',{'state':'active'})
                await owner.call('Emulation.setFocusEmulationEnabled',{'enabled':True})
                await owner.wait("document.querySelector('#backend-status').textContent.includes('Viewing only')")
                assert await owner.evaluate("document.querySelector('#watch-button').disabled")
                await other.close()
                await owner.wait("document.querySelector('#backend-status').textContent==='Application ready'")
                # Press/reload is a released cycle, never a resubmitted request.
                box=await owner.evaluate("(() => {const b=document.querySelector('#watch-button').getBoundingClientRect();return {x:b.x+10,y:b.y+20}})()")
                await owner.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':box['x'],'y':box['y'],'button':'left','buttons':1,'clickCount':1})
                await owner.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'")
                pressed_count=len(app.view()['command_events'])
                await owner.call('Page.reload')
                await owner.wait("document.querySelector('#backend-status')?.textContent==='Application ready'")
                async with asyncio.timeout(3):
                    while app.view()['button']['down']: await asyncio.sleep(.01)
                assert len(app.view()['command_events'])==pressed_count
                before=app.view()['diagnostics']['valid_frames']
                await owner.close()
                await asyncio.sleep(.5)
                assert app.view()['diagnostics']['valid_frames']>before
                owner=await browser.open(server.url)
                await owner.wait("document.querySelector('#backend-status')?.textContent==='Application ready'")
                await server.stop()
                await owner.wait("document.querySelector('#backend-status').textContent.includes('unavailable')")
                assert await owner.evaluate("document.querySelector('#watch-button').disabled && document.querySelector('#start').disabled")
                restarted=Application(store=FileStore(root/'configuration.json'))
                server=await Server(restarted,controller_timeout=.7).start(server.port)
                await owner.wait("document.querySelector('#backend-status').textContent==='Application ready' && document.querySelector('#mode').textContent==='IDLE · NO WHEEL'")
                assert restarted.view()['config']['presets'][0]['name']=='Retained'
                assert restarted.view()['preset_attempt'] is None and restarted.view()['command_events']==[]
                evidence={'issue':30,'provenance':'actual built Chrome UI / aiohttp / background recorder / local durable store; accelerated0.7s test lease (production10s)',
                    'expected':'reload noresubmit; delayedoldpoll discarded; competition readonly; freeze backendcontinues; lease takeover oldownerreadonly; closure backendcontinues; backendloss controlsdisabled; offline relaunchsavedonly',
                    'observed':'passed','physical_suspend':'explicitly omitted by owner; synthetic resume covered in test_lifecycle.py'}
                write_evidence('.test-output/lifecycle.json',evidence)
                print(json.dumps(evidence,indent=2))
        finally:
            await server.stop()


if __name__=='__main__':
    main(run)
