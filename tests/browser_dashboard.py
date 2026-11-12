"""Riding dashboard battery boundaries, staleness, CRC rejection and recovery (#18)."""
from support import (advance, horn_requests, main, save_ab_2, select_second_preset,
                     send_readings, served_laptop, start_simulator, write_evidence)


async def run():
    async with served_laptop() as laptop:
        page, behavior = laptop.page, laptop.app
        save_ab_2(behavior)
        await start_simulator(page)
        await send_readings(page, 25, 148.05, 45)
        await page.wait("document.querySelector('#watch').getAttribute('aria-label').includes('100 percent') && document.querySelector('#watch').getAttribute('aria-label').includes('Speed 25')")
        boundary_high = await page.description()
        # A Confirmed riding preset, so the stale check below can see it hidden.
        await select_second_preset(page)
        await page.label('Ab 2 · Applying')
        await advance(page, behavior, .2)
        await advance(page, behavior, .2)
        await page.label('Ab 2 · Confirmed')
        await page.evaluate("document.querySelector('#advance-seconds').value='1.1'")
        await send_readings(page, 25, 119.02, 45)
        await page.label('battery 0 percent')
        await send_readings(page, 25, 138, 45, 'paused')
        await page.evaluate("document.querySelector('[data-action=advance]').click()")
        await page.wait("document.querySelector('#watch').dataset.fresh === 'false'")
        stale = await page.description()
        assert 'Speed —' in stale and 'wheel battery dimmed' in stale
        assert 'Ab 2 · Confirmed' not in stale
        blocked_count=horn_requests(behavior)
        await page.press_button()
        await page.wait("document.querySelector('#watch-feedback').textContent==='Horn unavailable: connection unavailable'")
        assert horn_requests(behavior)==blocked_count
        await send_readings(page, 99, 138, 99, 'corrupt')
        await page.wait("document.querySelector('#watch').dataset.fresh === 'false'")
        await send_readings(page, 25, 138, 45)
        await page.wait("document.querySelector('#watch').dataset.fresh === 'true'")
        await page.evaluate("document.querySelector('[data-action=disconnect]').click()")
        await page.label('Disconnected')
        disconnected = await page.description()
        await page.click('[data-action=connect]')
        await page.click('[data-action=simulator_emit]')
        await page.wait("document.querySelector('#watch').dataset.fresh === 'true'")
        report = {'issue': 18, 'provenance': 'actual built UI / deterministic simulator',
            'browser': (await page.browser.call('Browser.getVersion'))['product'],
            'expected': 'idle launch; battery boundaries; stale dashes/dimming; CRC rejection; disconnect; fresh recovery',
            'high_boundary': boundary_high, 'stale': stale, 'disconnected': disconnected,
            'observed': await page.description()}
        await page.screenshot(laptop.output / 'dashboard.png')
    write_evidence(laptop.output / 'browser.json', report)
    print('dashboard: passed')


if __name__ == '__main__':
    main(run)
