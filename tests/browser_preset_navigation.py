"""Literal gesture expectations through real pointer events and production backend."""
import asyncio
import base64
from unittest.mock import patch
from eucwatch import Application

async def exercise(cdp,session,app,output):
    timeline=[];states=[];now=0
    async def event(start,end,screen,page=None,text=None):
        row={'input':'tap' if start==end else 'swipe','start':start,'end':end,'expected':{'screen':screen}}
        if page is not None:row['expected']['page']=page
        if text is not None:row['expected']['input']=text
        timeline.append(row)
        await cdp.pointer('#watch',start,end,session)
        await asyncio.sleep(.13)
        state=app.view()
        assert state['screen']==screen,(row,state['screen'])
        if page is not None:assert state['preset_page']==page,(row,state['preset_page'])
        if text is not None:assert state['preset_input']['text']==text,(row,state['preset_input'])
        assert state['command_events']==[]
        states.append({'screen':state['screen'],'page':state['preset_page'],'input':state['preset_input'],'draft':state['preset_draft'],'saved':state['config']})
    async def tap(x,y,screen,page=None,text=None):await event((x,y),(x,y),screen,page,text)
    async def swipe(direction,screen,page=None,text=None):
        positions={'down':((120,10),(120,110)),'up':((120,220),(120,40)),'left':((215,220),(20,220)),'right':((20,220),(215,220))}
        await event(*positions[direction],screen,page,text)
    await cdp.wait("document.querySelector('#backend-status')?.textContent==='Application ready'",session)
    initial=app.view()['config']
    for slot in range(1,5):
        await swipe('down','settings');await swipe('right','settings')
        await tap(120,196,'preset_slots');await swipe('right','preset_slots')
        await tap(200,55+(slot-1)*44,'preset_editor',0) # former Clear area opens slot now.
        for direction,page in [('right',3),('left',0),('left',1),('left',2),('left',3),('left',0),('right',3),('right',2),('right',1),('right',0)]:await swipe(direction,'preset_editor',page)
        await tap(120,80,'preset_editor',0,initial['presets'][slot-1]['name']);await tap(125,196,'preset_editor',0,'');await tap(49,73,'preset_editor',0,'A')
        await swipe('right','preset_editor',0,'A');await swipe('left','preset_editor',0,'A')
        await swipe('up','preset_editor',0);assert app.view()['preset_input'] is None
        await swipe('left','preset_editor',1);await tap(120,80,'preset_editor',1,str(initial['presets'][slot-1]['pedal_sensitivity']))
        await tap(49,166,'preset_editor',1,'');await swipe('left','preset_editor',1,'');await swipe('right','preset_editor',1,'')
        await tap(176,226,'preset_editor',1,'');assert 'Pedal sensitivity' in app.view()['preset_editor']['reason']
        await swipe('up','preset_editor',1);assert app.view()['preset_input'] is None
        await swipe('up','preset_slots');await swipe('up','settings');await swipe('up','dashboard')
        assert app.view()['config']==initial
    # OK closes each entry; Save after gestures persists both accepted values.
    await swipe('down','settings');await tap(120,196,'preset_slots');await tap(80,55,'preset_editor',0)
    await tap(120,80,'preset_editor',0,'Jump');await tap(125,196,'preset_editor',0,'');await tap(49,73,'preset_editor',0,'A')
    await tap(176,226,'preset_editor',0);await swipe('left','preset_editor',1);await tap(120,80,'preset_editor',1,'0');await tap(49,166,'preset_editor',1,'');await tap(189,73,'preset_editor',1,'3');await tap(49,73,'preset_editor',1,'31')
    await tap(176,226,'preset_editor',1);await tap(176,226,'preset_slots');assert app.view()['config']['presets'][0]['name']=='A';assert app.view()['config']['presets'][0]['pedal_sensitivity']==31
    saved=app.view()['config']
    # Up exits storage-failure and active name input without retrying implicitly.
    await tap(80,55,'preset_editor',0);await tap(120,80,'preset_editor',0,'A');await tap(119,73,'preset_editor',0,'AB')
    await tap(176,226,'preset_editor',0)
    timeline.append({'input':'storage_failure','mode':'refuse'})
    with patch('os.replace',side_effect=OSError('Controlled disk full')):await tap(176,226,'preset_editor',0)
    assert app.view()['persistence_error']
    timeline.append({'input':'storage_failure','mode':'none'})
    await swipe('up','preset_slots');assert app.view()['config']==saved
    await swipe('up','settings');await swipe('up','dashboard')
    assert Application(store=app.store).view()['config']==saved
    image=await cdp.evaluate("document.querySelector('canvas').toDataURL().split(',')[1]",session)
    (output/'navigation-dashboard.png').write_bytes(base64.b64decode(image))
    return {'spec':'docs/design/preset-value-editor.md','timeline':timeline,'states':states,'saved':saved,'packets':[],'outcome':'passed','expected':'up hierarchy, both wraps, every slot, active keypads, empty text, validation, failed save, gesture crossing old targets, local Save and restart'}

if __name__=='__main__':
    from browser_local_presets import run
    asyncio.run(run(exercise,'navigation-laptop','preset-values'))
