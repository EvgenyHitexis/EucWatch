"""Watch navigation, sleep and wake on the built Canvas against the aiohttp application (#19)."""
from support import main, served_laptop, start_simulator, write_evidence


async def run():
    async with served_laptop() as laptop:
        page, behavior, host_clock = laptop.page, laptop.app, laptop.clock
        await page.label('Not connected')
        await page.pointer((215, 120), (20, 120))
        await page.screen('presets')
        presets = await page.description()
        assert all(name in presets for name in ['Jump','Forest','Road','Drag'])
        await page.pointer((20, 120), (215, 120))
        await page.screen('dashboard')
        await page.pointer((120, 10), (120, 110))
        await page.screen('settings')
        await page.tap(120, 100)
        await page.wait("document.querySelector('#watch').dataset.awake === 'false'")
        await page.press_button()
        await page.wait("document.querySelector('#watch').dataset.awake === 'true'")
        self_button = behavior.view()['button']
        assert self_button['down'] is False and self_button['wake_cycle'] is False
        await page.pointer((120, 215), (120, 20))
        await page.screen('dashboard')
        host_clock.advance(31)
        await page.wait("document.querySelector('#watch').dataset.awake === 'false'")
        await page.press_button()
        await page.wait("document.querySelector('#watch').dataset.awake === 'true'")
        navigation = {'issue':19, 'provenance':'actual Canvas gestures / button / aiohttp with controlled clock',
            'expected':'fixed four slots, swipe back, Settings sleep, wake-only button, initial idle sleep',
            'observed':'passed', 'preset_menu':presets}
        await page.pointer((120,10), (120,110))
        await page.screen('settings')
        await page.tap(120,155)
        await page.label('Alert editor 1')
        await page.tap(120,88)
        await page.wait("document.querySelector('#alert-pwm-enabled').checked")
        await page.pointer((120,215),(120,20))
        await page.wait("document.querySelector('#alerts-status').textContent.includes('Saved')")
        await page.pointer((120,215),(120,20))
        await page.screen('dashboard')
        assert behavior.view()['config']['alerts']['pwm']=={'enabled':False,'threshold':None}
        navigation['back_discards_unsaved_alert_draft']='passed'
        # The watch stays awake after the wheel connection is lost.
        await start_simulator(page)
        await page.evaluate("document.querySelector('[data-action=disconnect]').click()")
        await page.label('Disconnected')
        behavior.action('advance', seconds=31)
        after_loss = behavior.view()['elapsed_s']
        await page.wait(f"Number(document.querySelector('#watch').dataset.elapsed) >= {after_loss} && document.querySelector('#watch').dataset.awake === 'true'")
        navigation['keep_awake_after_loss'] = 'passed'
    write_evidence(laptop.output / 'navigation.json', navigation)
    print('navigation: passed')


if __name__ == '__main__':
    main(run)
