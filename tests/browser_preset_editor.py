"""Reusable #46 native-sized local input journey; all expectations are literal."""
import asyncio
from pathlib import Path
from eucwatch import Application
from unittest.mock import patch
from support import main, record_flow, served_laptop, type_percentage, write_evidence

async def exercise(page, app, output):
    output.mkdir(parents=True,exist_ok=True)
    timeline=[];renderings=[];observed=[]
    wait=page.label
    async def pointer(start,end):
        timeline.append({'input':'tap' if start==end else 'swipe','start':start,'end':end})
        await page.pointer(start,end)
        await asyncio.sleep(.12)
    async def tap(x,y):await pointer((x,y),(x,y))
    async def page_index(index):
        while app.view()['preset_page']!=index:await tap(220,20)
        await wait(['Name:','Pedal sensitivity:','Dynamic assist:','Pedal dip compensation:'][index])
    async def snap(name):
        await asyncio.sleep(.12)
        await page.snapshot(output/(name+'.png'))
        renderings.append({'file':name+'.png','label':await page.description()})
    async def number(text):
        if app.view()['preset_input'] is None:await tap(120,80)
        await type_percentage(tap,text)
        await wait('Input '+(text or 'empty'))
    await page.wait("document.querySelector('#backend-status')?.textContent==='Application ready'")
    if app.view()['mode']!='idle':app.action('stop')
    await pointer((120,10),(120,110));await wait('Settings.')
    await tap(120,196);await wait('Settings Presets.')
    for slot in range(1,5):
        before=app.view()['config']
        await tap(80,55+(slot-1)*44);await wait(f'Preset editor slot {slot}. Name:')
        await tap(120,80);await tap(120,174) # Character clear, not preset deletion.
        await tap(49,73);await tap(32,174);await tap(92,60) # A then lowercase b.
        await tap(76,174) # Space.
        await tap(208,174);await tap(208,174) # Digits page.
        # 0,1,2,3 are indices 2..5 on the last character page.
        i=slot+2;await tap(36+i%4*56,60+i//4*38)
        await tap(49,73);await tap(164,174) # Add/remove y.
        name=f'Ab {slot}';await wait('Input '+name)
        # OK accepts the name, then whole-preset Save persists it.
        await snap(f'slot-{slot}-name');await tap(176,226);await wait('Whole-preset Save');await tap(176,226);await wait('Settings Presets.')
        assert app.view()['config']['presets'][slot-1]['name']==name
        await tap(80,55+(slot-1)*44);await page_index(3)
        assert app.view()['preset_draft']['dip_included'] is False
        await tap(120,162);await tap(120,162) # Inclusion does not erase stored value.
        await number('11')
        # Inclusion remains reachable after input opens, in this same transaction.
        for included in (True,False):
            await tap(186,24);await wait('Dip '+('included' if included else 'omitted')+'.')
            assert app.view()['preset_draft']['dip_included'] is included
            assert app.view()['preset_input']['text']=='11'
            assert app.view()['config']['presets'][slot-1]['dip_included'] is False
        await snap(f'slot-{slot}-dip-input')
        await tap(176,226);await page_index(1);await number('31');await tap(176,226);await page_index(2);await number('26')
        await snap(f'slot-{slot}-numeric');await tap(176,226);await tap(176,226);await wait('Settings Presets.')
        expected={'id':slot,'name':name,'configured':True,'pedal_sensitivity':31,'dynamic_assist':26,'pedal_dip_compensation':11,'dip_included':False}
        assert app.view()['config']['presets'][slot-1]==expected
        assert app.view()['config']['alerts']==before['alerts']
        assert app.view()['config']['presets'][:slot-1]+app.view()['config']['presets'][slot:]==before['presets'][:slot-1]+before['presets'][slot:]
        await tap(80,55+(slot-1)*44);await page_index(1);await number('99');await tap(176,226);await page_index(2);await number('98');await tap(64,226);await tap(64,226);await wait('Settings Presets.')
        assert app.view()['config']['presets'][slot-1]==expected
        observed.append({'slot':slot,'expected':expected,'observed':app.view()['config']['presets'][slot-1]})
    saved=app.view()['config']
    # Invalid OK keeps this field's entry open without changing its draft.
    await tap(80,55);await tap(120,80);await tap(120,174)
    await tap(176,226);await wait('name must contain');await snap('invalid-name-save')
    assert app.view()['preset_draft']['name']=='Ab 1'
    assert app.view()['preset_input']['field']=='name'
    assert app.view()['preset_input']['text']==''
    assert app.view()['config']==saved
    await tap(64,226);await tap(64,226);await wait('Settings Presets.')
    await tap(80,55);await page_index(1);await number('')
    await tap(176,226);await wait('Pedal sensitivity: enter');await snap('invalid-save')
    assert app.view()['config']==saved
    await number('32');await tap(176,226)
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
    result={'spec':'docs/design/preset-value-editor.md','timeline':timeline,'observed':observed,'renderings':renderings,'saved':app.view()['config'],'packets':[],'expected':'four offline slots; name/numeric OK; whole-preset Save; retained accepted values; Cancel; validation; failed FileStore save and retry; no commands','outcome':'passed','hardware_acceptance':'pending'}
    return result

async def editor_laptop():
    """The touch-layout acceptance record of the journey."""
    await record_flow(exercise,'editor-laptop','touch-layout')

async def presets():
    """The same journey on the served laptop, recorded in .test-output/presets.json (#46)."""
    async with served_laptop() as laptop:
        result=await exercise(laptop.page,laptop.app,laptop.output/'preset-editor')
    write_evidence(Path('.test-output/presets.json'),result)
    print('presets: passed')

if __name__=='__main__':
    main(editor_laptop,presets)
