"""Reusable #46 native-sized local input journey; all expectations are literal."""
import asyncio
import base64
import json
from eucwatch import Application
from unittest.mock import patch

async def exercise(cdp, session, app, output):
    output.mkdir(parents=True,exist_ok=True)
    timeline=[];renderings=[];observed=[]
    async def wait(text):
        await cdp.wait(f"document.querySelector('canvas').getAttribute('aria-label').includes({json.dumps(text)})",session)
    async def pointer(start,end):
        timeline.append({'input':'tap' if start==end else 'swipe','start':start,'end':end})
        await cdp.pointer('#watch',start,end,session)
        await asyncio.sleep(.12)
    async def tap(x,y):await pointer((x,y),(x,y))
    async def page(index):
        while app.view()['preset_page']!=index:await tap(220,20)
        await wait(['Name:','Pedal sensitivity:','Dynamic assist:','Pedal dip compensation:'][index])
    async def snap(name):
        await asyncio.sleep(.12)
        image=await cdp.evaluate("document.querySelector('canvas').toDataURL().split(',')[1]",session)
        (output/(name+'.png')).write_bytes(base64.b64decode(image))
        renderings.append({'file':name+'.png','label':await cdp.evaluate("document.querySelector('canvas').getAttribute('aria-label')",session)})
    async def number(text):
        if app.view()['preset_input'] is None:await tap(120,80)
        await tap(49,166)
        for digit in text:
            i=10 if digit=='0' else '123456789'.index(digit)
            await tap(49+i%3*70,73+i//3*31)
        await wait('Input '+(text or 'empty'))
    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",session)
    if app.view()['mode']!='idle':app.action('stop')
    await pointer((120,10),(120,110));await wait('Settings.')
    await tap(120,196);await wait('Settings Presets.')
    for slot in range(1,5):
        before=app.view()['config']
        await tap(80,55+(slot-1)*44);await wait(f'Preset editor slot {slot}. Name:')
        await tap(120,80);await tap(125,196) # Character clear, not preset deletion.
        await tap(49,73);await tap(30,196);await tap(119,73) # A then lowercase b.
        await tap(80,196) # Space.
        await tap(205,196);await tap(205,196) # Digits page.
        # 0,1,2,3 are indices 2..5 on the last character page.
        i=slot+2;await tap(49+i%3*70,73+i//3*31)
        await tap(49,73);await tap(166,196) # Add/remove y.
        name=f'Ab {slot}';await wait('Input '+name)
        # Save directly from active name input; reopening proves operation completion.
        await snap(f'slot-{slot}-name');await tap(176,226);await wait('Settings Presets.')
        assert app.view()['config']['presets'][slot-1]['name']==name
        await tap(80,55+(slot-1)*44);await page(3)
        assert app.view()['preset_draft']['dip_included'] is False
        await tap(120,126);await tap(120,126) # Inclusion does not erase stored value.
        await number('11')
        # Inclusion remains reachable after input opens, in this same transaction.
        await page(0);await page(3)
        for included in (True,False):
            await tap(120,196);await wait('Dip '+('included' if included else 'omitted')+'.')
            assert app.view()['preset_draft']['dip_included'] is included
            assert app.view()['preset_input']['text']=='11'
            assert app.view()['config']['presets'][slot-1]['dip_included'] is False
        await snap(f'slot-{slot}-dip-input')
        await page(1);await number('31');await page(2);await number('26')
        await snap(f'slot-{slot}-numeric');await tap(176,226);await wait('Settings Presets.')
        expected={'id':slot,'name':name,'configured':True,'pedal_sensitivity':31,'dynamic_assist':26,'pedal_dip_compensation':11,'dip_included':False}
        assert app.view()['config']['presets'][slot-1]==expected
        assert app.view()['config']['alerts']==before['alerts']
        assert app.view()['config']['presets'][:slot-1]+app.view()['config']['presets'][slot:]==before['presets'][:slot-1]+before['presets'][slot:]
        await tap(80,55+(slot-1)*44);await page(1);await number('99');await page(2);await number('98');await tap(64,226);await wait('Settings Presets.')
        assert app.view()['config']['presets'][slot-1]==expected
        observed.append({'slot':slot,'expected':expected,'observed':app.view()['config']['presets'][slot-1]})
    saved=app.view()['config']
    # Report the invalid field even when Save is tapped on another field's keypad.
    await tap(80,55);await tap(120,80);await tap(125,196);await page(1)
    await tap(176,226);await wait('name must contain');await snap('invalid-name-save')
    assert app.view()['preset_draft']['name']==''
    assert app.view()['preset_input']['field']=='pedal_sensitivity'
    assert app.view()['config']==saved
    await page(0);await wait('Input empty');await tap(64,226);await wait('Settings Presets.')
    await tap(80,55);await page(1);await number('');await page(2);await page(1)
    await tap(176,226);await wait('Pedal sensitivity: enter');await snap('invalid-save')
    assert app.view()['config']==saved
    await number('32')
    # A controlled file boundary fault around real FileStore, then local retry.
    timeline.append({'input':'storage_failure','mode':'refuse'})
    with patch('os.replace',side_effect=OSError('Controlled disk full')):
        await tap(176,226);await wait('Controlled disk full');await snap('failed-save')
    assert app.view()['config']==saved
    timeline.append({'input':'storage_failure','mode':'none'})
    await tap(176,226);await wait('Settings Presets.')
    assert app.view()['config']['presets'][0]['pedal_sensitivity']==32
    assert app.view()['command_events']==[]
    assert app.view()['preset_attempt'] is None
    assert Application(store=app.store).view()['config']==app.view()['config']
    result={'issue':46,'timeline':timeline,'observed':observed,'renderings':renderings,'saved':app.view()['config'],'packets':[],'expected':'four offline slots; active name/numeric Save; retained multi-field text; Cancel; validation; failed FileStore save and retry; no commands','outcome':'passed','hardware_acceptance':'pending'}
    return result

if __name__=='__main__':
    from browser_local_presets import run
    asyncio.run(run(exercise,'editor-laptop'))
