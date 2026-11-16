// The core decides what every touch and gesture means, Wheel selection included, against a small fake transport.
const assert=require('node:assert/strict');
const {environment,plain}=require('./harness.cjs');

// A fake transport: records requests, refuses with the reason it is given, reports the status it is given.
function fakeTransport(){
  const calls=[],refusals={},status={active:false,connected:false,busy:false};
  const ask=(name,...args)=>{calls.push([name,...args]);if(refusals[name])throw new Error(refusals[name]);};
  return {calls,refusals,status,adapter:{discover:()=>ask('discover'),select:id=>ask('select',id),disconnect:()=>ask('disconnect'),status:()=>({...status})}};
}
function scenario(transport){
  const env=environment();let now=0;
  const app=env.require('sw-app').create({clock:{now:()=>now},battery:()=>({percent:50,charging:false}),transport:transport&&transport.adapter});
  const target=label=>{const found=env.require('sw-controls').targets(app.view()).find(t=>t.label===label);assert.ok(found,'no target '+label+' on '+app.view().screen);return found;};
  // Touch the centre of the target with this label, as the hardware reports a tap.
  const tap=label=>{const r=target(label).rect;app.gesture('interact');return app.touch((r[0]+r[2])/2,(r[1]+r[3])/2);};
  const settings=()=>app.gesture('swipe',{direction:'down',from_top:true});
  const texts=()=>{const g=env.context.Graphics.createArrayBuffer(240,240,1);env.require('sw-render').draw(g,plain(app.view()));return g.ops.filter(op=>op.kind==='text').map(op=>op.value);};
  return {env,app,tap,settings,texts,at:value=>{now=value;app.tick();}};
}
const devices=[{id:'11:22:33:44:55:66 public',name:'Sherman L'},{id:'aa:bb:cc:dd:ee:ff public',name:'Spare'}];

{ // Connect, select and disconnect, all through touches.
  const transport=fakeTransport(),{app,tap,settings}=scenario(transport);
  settings();assert.equal(app.view().screen,'settings');assert.equal(app.view().disconnect_available,false);
  tap('Connect wheel');
  assert.deepEqual(transport.calls,[['discover']]);assert.equal(app.view().screen,'connection','accepted discovery opens Wheel selection');
  app.action('devices',{devices});assert.deepEqual(plain(app.view().devices),devices);
  tap('Spare');
  assert.deepEqual(transport.calls.at(-1),['select','aa:bb:cc:dd:ee:ff public']);
  assert.equal(app.view().screen,'dashboard','an accepted selection returns to the Riding dashboard');
  transport.status.active=true;settings();assert.equal(app.view().disconnect_available,true);
  tap('Disconnect wheel');
  assert.deepEqual(transport.calls.at(-1),['disconnect']);assert.equal(app.view().screen,'settings','disconnecting stays on Settings');
  transport.status.active=false;transport.status.connected=true;assert.equal(app.view().disconnect_available,true,'a live link without intent is still disconnected');
  transport.status.connected=false;assert.equal(app.view().disconnect_available,false);
}
{ // Link events change connection state, never the screen; connected still wakes the watch.
  const transport=fakeTransport(),{app,tap,settings,at}=scenario(transport);
  settings();tap('Connect wheel');at(31);assert.equal(app.view().awake,false,'an idle watch that never connected sleeps');
  const session=app.action('session_start').session;app.action('connected',{session});
  assert.equal(app.view().awake,true,'a connected wheel wakes the watch');
  app.action('devices',{devices});app.action('disconnect',{session});
  app.action('connected',{session:app.action('session_start').session});
  assert.equal(app.view().screen,'connection','link events leave Wheel selection open');
}
{ // A refused discovery stays on Settings and shows its reason; leaving the screen clears it.
  const transport=fakeTransport(),{app,tap,settings,texts}=scenario(transport);
  transport.refusals.discover='Disconnect the wheel before discovery';
  settings();tap('Connect wheel');
  assert.equal(app.view().screen,'settings');assert.equal(app.view().connection_error,'Disconnect the wheel before discovery');
  assert.ok(texts().includes('Disconnect the wheel before discovery'),'Settings shows the refusal');
  app.gesture('swipe',{direction:'up'});assert.equal(app.view().connection_error,'');
  settings();assert.ok(!texts().includes('Disconnect the wheel before discovery'));
  delete transport.refusals.discover;tap('Connect wheel');assert.equal(app.view().screen,'connection');assert.equal(app.view().connection_error,'');
}
{ // A refused selection stays on Wheel selection and shows its reason; swipe up still goes back.
  const transport=fakeTransport(),{app,tap,settings,texts}=scenario(transport);
  settings();tap('Connect wheel');app.action('devices',{devices});
  transport.refusals.select='Select a device from explicit discovery';
  tap('Sherman L');
  assert.equal(app.view().screen,'connection');assert.equal(app.view().connection_error,'Select a device from explicit discovery');
  assert.ok(texts().includes('Select a device from explicit discovery'),'Wheel selection shows the refusal');
  app.gesture('swipe',{direction:'up'});assert.equal(app.view().screen,'dashboard');assert.equal(app.view().connection_error,'');
}
{ // Without a transport, and in recovery mode, connecting is refused.
  const {app,tap,settings}=scenario(null);
  settings();assert.equal(app.view().transport,null);tap('Connect wheel');
  assert.equal(app.view().screen,'settings');assert.equal(app.view().connection_error,'Wheel transport not ready');
  app.action('device_select',{id:devices[0].id});
  assert.equal(app.view().screen,'settings');assert.equal(app.view().connection_error,'Wheel transport not ready','a selection is a refusal too, not an exception');
}
{ // Recovery mode refuses connection requests outright.
  const transport=fakeTransport(),{app,at}=scenario(transport);
  app.gesture('button_down');at(30);assert.equal(app.view().recovery,true);
  assert.throws(()=>app.action('transport_toggle'),/recovery mode/);
  assert.throws(()=>app.action('device_select',{id:devices[0].id}),/recovery mode/);
  assert.deepEqual(transport.calls,[]);
}
{ // Unknown action names are rejected; interact and button_hold are accepted no-ops.
  const {app,at}=scenario(fakeTransport());
  for(const name of ['open_connection','wheel_selected','nonsense','transfer_begin','preset_input_done'])
    assert.throws(()=>app.action(name),new RegExp('Unknown action: '+name));
  at(29);app.gesture('interact');app.gesture('button_hold');at(31);
  assert.equal(app.view().awake,true,'interact counts as an interaction');
}
{ // Touches and swipes carry the current editor and entry ids; core.action without them is still refused.
  const {app,tap}=scenario(fakeTransport());
  app.gesture('swipe',{direction:'down',from_top:true});tap('Presets');app.touch(120,54);
  assert.equal(app.view().screen,'preset_editor');
  assert.throws(()=>app.action('swipe',{direction:'left'}),/Preset editor changed/);
  app.gesture('swipe',{direction:'left'});assert.equal(app.view().preset_page,1,'a hardware swipe turns the page');
  app.touch(120,100);assert.ok(app.view().preset_input,'a touch opens the value entry');
  app.gesture('swipe',{direction:'up'});assert.equal(app.view().preset_input,null,'swipe up closes the entry');
  app.gesture('swipe',{direction:'up'});assert.equal(app.view().screen,'preset_slots','swipe up leaves the editor');
  assert.equal(app.touch(1,1),null,'a touch outside every target does nothing');
}
console.log('watch core touch and gesture meaning, Wheel selection, refusals, link events and unknown names: passed');
