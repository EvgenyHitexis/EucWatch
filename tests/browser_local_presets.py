"""Real built Canvas/backend checks for #43; physical wheel never selected."""
import json
from pathlib import Path

from support import main, record_flow

FIXTURE = json.loads(Path('docs/acceptance/scenarios/local-presets.json').read_text())

async def defaults(page, app, output):
    trace=[]
    async def pointer(start,end):
        trace.append({'start':start,'end':end})
        await page.pointer(start,end)
    screen=page.screen
    async def render(name,shows):
        return await page.snapshot(output/(name+'.png'),shows=shows)
    await page.wait("document.querySelector('#backend-status')?.textContent==='Application ready'")
    assert app.view()['config']==FIXTURE['fresh']
    await pointer((215,120),(20,120));await screen('presets')
    riding=await render('defaults-riding','presets')
    assert all(name in riding for name in ['Jump','Forest','Road','Drag'])
    await pointer((20,120),(215,120));await screen('dashboard')
    await pointer((120,10),(120,110));await screen('settings')
    await pointer((120,196),(120,196));await screen('preset_slots')
    selection=await render('defaults-settings','preset_slots')
    assert all(name in selection for name in ['Jump','Forest','Road','Drag'])
    await page.evaluate("document.querySelector('#controlled').checked=true;document.querySelector('#start').click()")
    await page.wait("document.querySelector('#mode').textContent==='SIMULATOR'")
    seed=json.loads(json.dumps(FIXTURE['fresh']))
    seed['presets'][0].update(pedal_dip_compensation=83,dip_included=True)
    app.action('configuration_import_prepare',content=json.dumps(seed));app.action('configuration_import_commit')
    app.action('preset_apply',slot=1)
    app.action('advance',seconds=.2);app.action('advance',seconds=.2)
    app.action('configuration_import_prepare',content=json.dumps(FIXTURE['fresh']));app.action('configuration_import_commit')
    observed=[]
    for slot,packets in enumerate(FIXTURE['default_packets'],1):
        app.action('swipe',direction='right')
        while app.view()['screen']!='dashboard':app.action('swipe',direction='up')
        await screen('dashboard')
        await pointer((215,120),(20,120));await screen('presets')
        x=66 if slot%2 else 174;y=80 if slot<=2 else 170
        before=len(app.view()['command_events'])
        await pointer((x,y),(x,y));await screen('dashboard')
        app.action('advance',seconds=.2);app.action('advance',seconds=.2)
        state=app.view()
        actual=[row['packet_hex'] for row in state['command_events'][before:] if row['event']=='submission']
        assert actual==packets,(slot,actual,packets)
        assert state['actual_settings']['pedal_dip_compensation']==83
        assert state['confirmed_preset']['slot']==slot
        observed.append({'slot':slot,'expected_packets':packets,'observed_packets':actual,'wheel_dip':83})
    return {'issue':44,'expected':FIXTURE['fresh'],'observed':app.view()['config'],'rendered':[riding,selection],'pointer_trace':trace,'applications':observed}

async def run():
    await record_flow(defaults,'defaults-laptop','local-presets')

if __name__=='__main__':main(run)
