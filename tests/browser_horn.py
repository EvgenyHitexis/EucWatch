"""Horn requests from the modeled watch button on the built UI (#23)."""
from support import (horn_requests, main, send_readings, served_laptop, start_simulator,
                     write_evidence)


async def run():
    async with served_laptop() as laptop:
        page, behavior = laptop.page, laptop.app
        await start_simulator(page)
        await send_readings(page, 25, 148.05, 45)
        await page.label('Speed 25')
        before_horn=horn_requests(behavior)
        await page.press_button()
        await page.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'")
        assert horn_requests(behavior)==before_horn+1
        await page.pointer((120,10),(120,110))
        await page.screen('settings')
        await page.tap(120,100)
        await page.wait("document.querySelector('#watch').dataset.awake==='false'")
        await page.press_button()
        await page.wait("document.querySelector('#watch').dataset.awake==='true'")
        assert horn_requests(behavior)==before_horn+1
        await page.press_button()
        await page.wait("document.querySelector('#watch-feedback').textContent==='Horn request sent'")
        assert horn_requests(behavior)==before_horn+2
        await page.pointer((120,215),(120,20))
        await page.screen('dashboard')
        horn_result={'issue':23,'provenance':'actual modeled sidebutton / Canvas / aiohttp / simulator command outputs',
            'expected':'awakepressone LkAp request, wholeSleepwakecycle no horn, freshpressrequired; pending/stale pressesdiscarded',
            'observed':'passed','physical_audible_evidence':'pending #9; sent request only'}
    write_evidence(laptop.output / 'horn.json', horn_result)
    print('horn: passed')


if __name__ == '__main__':
    main(run)
