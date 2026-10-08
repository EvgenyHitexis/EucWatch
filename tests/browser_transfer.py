"""Built Canvas/HTML → aiohttp → fake BLE → original watch endpoint/Storage."""
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import tempfile

from aiohttp import ClientSession, web

from browser_flow import Browser
from eucwatch import Application, ManualClock
from eucwatch.async_transfer import AsyncConfigurationTransfer
from eucwatch.live import LiveSession
from eucwatch.nordic import NusTransport
from eucwatch.persistence import FileStore
from eucwatch.server import create_app
from watch_wire import Scanner, WatchWire


async def run():
    with tempfile.TemporaryDirectory(prefix='eucwatch-transfer-') as directory:
        root=Path(directory)
        behavior=Application(clock=ManualClock(),store=FileStore(root/'configuration.json'))
        behavior.action('preset_begin',slot=1)
        behavior.action('preset_update',name='Wire Rain',pedal_sensitivity=31,dynamic_assist=26)
        behavior.action('preset_save')
        wire=await WatchWire().start()
        live=LiveSession(behavior)
        nus=NusTransport(behavior,live,scanner=Scanner,client_factory=wire.client,timeout=.5)
        def factory(address,protocol):
            return AsyncConfigurationTransfer(behavior.store,FileStore(root/'shared.json'),protocol,
                endpoint_label='Actual watch JS / fake BLE',journal_store=FileStore(root/'journal.json'))
        runner=web.AppRunner(create_app(behavior,live=live,nus=nus,nus_transfer_factory=factory))
        await runner.setup()
        sock=socket.socket();sock.bind(('127.0.0.1',0))
        await web.SockSite(runner,sock).start()
        url=f'http://127.0.0.1:{sock.getsockname()[1]}'
        browser=None
        try:
            with tempfile.TemporaryDirectory(prefix='eucwatch-transfer-ui-',ignore_cleanup_errors=True) as profile:
                browser=subprocess.Popen(['google-chrome','--headless','--no-first-run','--no-default-browser-check',
                    '--disable-sync','--disable-background-networking','--remote-debugging-port=0',f'--user-data-dir={profile}','about:blank'],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                port_file=Path(profile)/'DevToolsActivePort'
                async with asyncio.timeout(15):
                    while not port_file.exists(): await asyncio.sleep(.05)
                port,path=port_file.read_text().splitlines()
                async with ClientSession() as client, client.ws_connect(f'http://127.0.0.1:{port}{path}') as ws:
                    cdp=Browser(ws)
                    target=await cdp.call('Target.createTarget',{'url':url})
                    attached=await cdp.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True})
                    session=attached['sessionId']
                    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",session)
                    assert wire.clients==[],'launch must not discover/connect a watch'
                    async def enter():
                        await cdp.pointer('#watch',(120,10),(120,110),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='settings'",session)
                        await cdp.pointer('#watch',(120,202),(120,202),session)
                        await cdp.wait("document.querySelector('canvas').dataset.screen==='transfer'",session)
                        await cdp.evaluate("document.querySelector('#nordic-discover').click()",session)
                        await cdp.wait("document.querySelector('#nordic-device').options.length===1 && !document.querySelector('#nordic-select').disabled",session)
                        await cdp.evaluate("document.querySelector('#nordic-select').click()",session)
                        await cdp.wait("document.querySelector('#transfer-status').textContent.includes('Actual watch JS') && !document.querySelector('#transfer-send').disabled",session)
                    await enter()
                    assert await cdp.evaluate("document.querySelector('#start').disabled && document.querySelector('#transfer-watch-editor button').disabled",session)
                    await cdp.evaluate("document.querySelector('#transfer-send').click()",session)
                    await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard' && document.querySelector('#mode').textContent==='IDLE · NO WHEEL'",session)
                    first=behavior.config
                    assert first==(await wire.call())['saved']
                    assert first['presets'][0]['name']=='Wire Rain'
                    assert all(not item.is_connected for item in wire.clients)
                    assert behavior.view()['command_events']==[]
                    # Edit saved content through the actual HTML alert editor.
                    await cdp.evaluate("document.querySelector('#alerts-edit').click()",session)
                    await cdp.wait("!document.querySelector('#alert-pwm-enabled').disabled",session)
                    await cdp.evaluate("document.querySelector('#alert-pwm-enabled').click();const i=document.querySelector('#alert-pwm-threshold');i.value='70';i.dispatchEvent(new Event('change',{bubbles:true}))",session)
                    await cdp.wait("!document.querySelector('#alerts-save').disabled",session)
                    await cdp.evaluate("document.querySelector('#alerts-editor').requestSubmit()",session)
                    await cdp.wait("document.querySelector('#alerts-status').textContent.includes('Saved') && document.querySelector('#alert-pwm-threshold').value==='70'",session)
                    wire.drop_commit=True
                    await enter()
                    before=sum(row['op']=='commit' for row in wire.requests)
                    await cdp.evaluate("document.querySelector('#transfer-send').click()",session)
                    await cdp.wait("document.querySelector('#transfer-status').textContent.includes('unknown') && document.querySelector('#transfer-send').disabled",session)
                    assert behavior.transfer.active
                    assert sum(row['op']=='commit' for row in wire.requests)==before+1
                    # Actual watch Storage and laptop recovery journal survive restart.
                    await wire.call(restart=True)
                    await cdp.wait("!document.querySelector('#nordic-select').disabled",session)
                    await cdp.evaluate("document.querySelector('#nordic-select').click()",session)
                    await cdp.wait("document.querySelector('#nordic-status').textContent.includes('subscribed') && !document.querySelector('#transfer-reconcile').disabled",session)
                    await cdp.evaluate("document.querySelector('#transfer-reconcile').click()",session)
                    await cdp.wait("document.querySelector('canvas').dataset.screen==='dashboard'",session)
                    assert sum(row['op']=='commit' for row in wire.requests)==before+1,'readback must not resubmit activation'
                    assert behavior.config==(await wire.call())['saved']
                    assert behavior.config['alerts']['pwm']=={'enabled':True,'threshold':70}
                    assert behavior.view()['confirmed_preset'] is None and behavior.view()['fresh'] is False
                    assert behavior.view()['command_events']==[]
                    restarted=Application(store=FileStore(root/'configuration.json'))
                    assert restarted.config==behavior.config
                    evidence={'issues':[35,31],'provenance':'actual Chrome built Canvas/HTML + aiohttp + Python Nordic adapter + fake BLE + original watch JS/Storage adapter; no physical BLE',
                        'expected':'explicit stopped mode/discovery/selection; reviewed saved copies; role cleanup before return; lost commit ack stays unknown; explicit reconnect/readback after watch restart; no resubmit/commands/confirmation; laptop restart saved copy',
                        'observed':'passed','saved_revision':behavior.config['revision'],'ble_clients':len(wire.clients),'commit_requests':sum(row['op']=='commit' for row in wire.requests),
                        'physical_acceptance':'pending actual BLE, installed Storage, interruption/recovery and owner review'}
                    Path('.test-output').mkdir(exist_ok=True)
                    Path('.test-output/watch-transfer-browser.json').write_text(json.dumps(evidence,indent=2)+'\n')
                    print(json.dumps(evidence,indent=2))
        finally:
            if browser is not None:
                browser.terminate()
                try: await asyncio.to_thread(browser.wait,timeout=5)
                except subprocess.TimeoutExpired: browser.kill();await asyncio.to_thread(browser.wait)
            await runner.cleanup()
            await wire.close()


if __name__=='__main__':
    asyncio.run(run())
