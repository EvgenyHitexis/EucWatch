"""Reproducible scenario save, export, reviewed import, start and steps (#31)."""
import asyncio
import json

from support import main, send_readings, served_laptop, start_simulator, write_evidence


async def run():
    async with served_laptop() as laptop:
        page, behavior, output = laptop.page, laptop.app, laptop.output
        await start_simulator(page)
        await send_readings(page, 25, 138, 45)
        download_dir=(output/f'downloads-{laptop.run_id}').resolve()
        download_dir.mkdir(exist_ok=True)
        await page.browser.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(download_dir)})
        await page.wait("!document.querySelector('#scenario-save').disabled")
        await page.evaluate("document.querySelector('#scenario-name').value='Reproducible dashboard';document.querySelector('#scenario-save').click()")
        await page.wait("document.querySelector('#scenario-status').textContent.includes('saved locally')")
        await page.click('#scenario-export')
        async with asyncio.timeout(5):
            while not (download_dir/'eucwatch-scenario.json').exists(): await asyncio.sleep(.05)
        definition=json.loads((download_dir/'eucwatch-scenario.json').read_text())
        assert definition['seed']==0 and definition['clock']=='controlled'
        await page.choose_files('#scenario-file', download_dir/'eucwatch-scenario.json')
        before_review=behavior.view()['session']
        await page.click('#scenario-review')
        await page.wait("document.querySelector('#scenario-preview').textContent.includes('Reviewed import')")
        assert behavior.view()['session']==before_review
        await page.click('#scenario-start')
        await page.wait("document.querySelector('#scenario-status').textContent.includes('started')")
        assert behavior.view()['controlled'] and behavior.view()['elapsed_s']==0
        for index in range(3):
            await page.click('#scenario-step')
            await page.wait(f"document.querySelector('#scenario-status').textContent.includes('{index+1}/3')")
        assert behavior.view()['elapsed_s']==1.4
        assert await page.evaluate("document.querySelector('#scenario-step').disabled")
        scenario_result={'issue':31,'provenance':'actual saved-file backend / Chrome export/import/review/start/step; fixed inputs seed0 controlled raw parser',
            'expected':'complete bounded definition saves/exports; review noactivation; explicit freshstart; three deterministicsteps; no commands',
            'observed':'passed','owner_review_and_live_acceptance':'pending'}
    write_evidence(output/'scenarios.json', scenario_result)
    print('scenarios: passed')


if __name__ == '__main__':
    main(run)
