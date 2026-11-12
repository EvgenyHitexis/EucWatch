"""Riding preset one-tap apply and its failure outcomes on the built UI (#22)."""
import json

from support import (advance, horn_requests, main, save_ab_2, select_second_preset,
                     send_readings, served_laptop, start_simulator, write_evidence)


async def run():
    async with served_laptop() as laptop:
        page, behavior = laptop.page, laptop.app
        save_ab_2(behavior)
        await start_simulator(page)
        await send_readings(page, 25, 148.05, 45)
        await page.label('Speed 25')
        await select_second_preset(page)
        await page.wait("document.querySelector('#watch').dataset.screen==='dashboard' && document.querySelector('#watch').getAttribute('aria-label').includes('Ab 2 · Applying')")
        await page.evaluate("document.querySelector('#advance-seconds').value='0.2'")
        for index in range(2):
            await page.wait("!document.querySelector('#advance').disabled")
            await page.evaluate("document.querySelector('#advance').click()")
            await page.wait(f"Number(document.querySelector('#watch').dataset.elapsed)>={.2*(index+1)-.00001}")
        await page.label('Ab 2 · Confirmed')
        control_result={'issue':22,'provenance':'actual Canvas one-tap / aiohttp / actual settings-frame parser / moving simulator',
            'expected':'Ab 2 onetap immediately dashboard Applying while speed25; two matching fresh settings frames Confirmed',
            'observed':'passed','attempt':behavior.view()['preset_attempt']}
        control_result['failure_scenarios']=[]
        for readback,submission,expected in [('missing','normal','Not confirmed'),('mismatch','normal','Not confirmed'),('partial','normal','Partially applied'),('normal','fail','Not confirmed'),('normal','hang','Not confirmed')]:
            await page.evaluate(f"document.querySelector('#control-readback').value={json.dumps(readback)}; document.querySelector('#control-submission').value={json.dumps(submission)}")
            await send_readings(page, 25, 148.05, 45)
            previous_id=behavior.view()['preset_attempt']['id']
            await select_second_preset(page)
            await page.screen('dashboard')
            assert behavior.view()['preset_attempt']['id']>previous_id
            if behavior.view()['preset_attempt']['pending']:
                blocked_count=horn_requests(behavior)
                await page.press_button()
                await page.wait("document.querySelector('#watch-feedback').textContent==='Horn unavailable: preset applying'")
                assert horn_requests(behavior)==blocked_count
            for _ in range(22):
                if not behavior.view()['preset_attempt']['pending']:break
                await advance(page, behavior, .5)
            result=behavior.view()['preset_attempt']
            assert result['status']==expected,result
            await page.wait(f"document.querySelector('#preset-outcome').textContent.includes({json.dumps(expected)})")
            control_result['failure_scenarios'].append({'readback':readback,'submission':submission,'observed':expected,'reason':result['reason']})
        await page.evaluate("document.querySelector('#control-readback').value='normal'; document.querySelector('#control-submission').value='normal'")
        await send_readings(page, 25, 148.05, 45)
        assert behavior.view()['preset_attempt']['status']=='Not confirmed'
        await select_second_preset(page)
        await page.screen('dashboard')
        await advance(page, behavior, .2)
        await advance(page, behavior, .2)
        await page.label('Ab 2 · Confirmed')
        control_result['explicit_retry']='Confirmed; late readings before retry retained prior failure'
    write_evidence(laptop.output / 'control.json', control_result)
    print('control: passed')


if __name__ == '__main__':
    main(run)
