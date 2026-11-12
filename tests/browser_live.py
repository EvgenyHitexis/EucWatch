"""Live wheel discovery, selection, Riding preset writes and reconnection over fake Bleak (#25, #26)."""
import asyncio
import json

from support import (ADDRESS, SOURCE_FRAME, main, save_ab_2, select_second_preset,
                     served_laptop, settings_frame, start_simulator, write_evidence)


async def run():
    async with served_laptop() as laptop:
        page, behavior, host_clock, live_clients = laptop.page, laptop.app, laptop.clock, laptop.clients
        save_ab_2(behavior)
        await start_simulator(page)
        await page.click('#live-discover')
        await page.wait("document.querySelector('#live-device').options.length===2 && !document.querySelector('#live-device').disabled")
        assert live_clients.created==[]
        await page.evaluate(f"document.querySelector('#live-device').value={json.dumps(ADDRESS)}; document.querySelector('#live-device').dispatchEvent(new Event('change'))")
        await page.click('#live-select')
        await page.wait("document.querySelector('#mode').textContent==='LIVE WHEEL' && document.querySelector('#live-status').textContent.includes('subscribed')")
        assert not behavior.view()['fresh']
        live_clients.created[0].emit(SOURCE_FRAME)
        await page.wait("document.querySelector('#watch').dataset.fresh==='true' && document.querySelector('#live-status').textContent.includes('006.0.03')")
        await select_second_preset(page)
        await page.wait("document.querySelector('#preset-outcome').textContent.includes('Applying')")
        async with asyncio.timeout(2):
            while behavior.view()['preset_attempt']['status']!='confirming':
                await asyncio.sleep(.01)
        assert [len(data) for _,data,_ in live_clients.created[0].writes]==[15,20,11]
        host_clock.advance(.1)
        live_clients.created[0].emit(settings_frame(sensitivity=31,assist=26))
        assert behavior.view()['confirmed_preset'] is None
        host_clock.advance(.1)
        live_clients.created[0].emit(settings_frame(sensitivity=31,assist=26))
        await page.wait("document.querySelector('#preset-outcome').textContent==='Ab 2 · Confirmed'")
        await page.press_button()
        await page.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'")
        assert [len(data) for _,data,_ in live_clients.created[0].writes]==[15,20,11,14]
        live_control_result={'issue':26,'provenance':'actual Canvas preset/button / aiohttp / selected fake Bleak telemetry connection',
            'expected':'serialized responseFalse15/20/11 bytes; two raw matching frames confirm; one14byteLkAp horn request; no physical operation',
            'observed':'passed','chunks':[len(data) for _,data,_ in live_clients.created[0].writes],
            'physical_mappings_ranges_persistence_movement_and_audible_horn':'unverified under #9/#31'}
        write_evidence(laptop.output/'live-control.json', live_control_result)
        first=live_clients.created[0]
        first.lose_link()
        assert not behavior.view()['fresh']
        await page.wait("document.querySelector('#live-diagnostics').textContent.includes('1 reconnections')")
        assert not behavior.view()['fresh']
        first.emit(SOURCE_FRAME)
        assert not behavior.view()['fresh']
        live_clients.created[1].emit(SOURCE_FRAME)
        await page.wait("document.querySelector('#watch').dataset.fresh==='true'")
        await page.click('[data-action=simulator_start]')
        await page.wait("document.querySelector('#mode').textContent==='SIMULATOR'")
        assert not live_clients.created[1].is_connected
        live_result={'issue':25,'provenance':'actual HTML discovery/select / Canvas / aiohttp / controlled Bleak-compatible transports',
            'expected':'explicitscanonly, livefreshidentity, loss/newsession/freshrecovery, oldcallbackinert, simulatorcloseslive',
            'observed':'passed','physical_evidence':'pending owner authorization'}
    write_evidence(laptop.output/'live.json', live_result)
    print('live: passed')


if __name__ == '__main__':
    main(run)
