// Public application actions/raw notifications; no physical wheel or watch.
const assert=require('node:assert/strict');
const {environment,frame,plain}=require('./harness.cjs');
const riding={settings:{pedal_sensitivity:41,dynamic_assist:51,pedal_dip_compensation:61}};
function scenario(){
  const env=environment();
  let now=0,saved=env.require('sw-configuration').defaults(),fail=false;const writes=[];
  const store={load:()=>JSON.parse(JSON.stringify(saved)),save:value=>{if(fail)throw Error('Controlled storage full');saved=JSON.parse(JSON.stringify(value));}};
  function create(){return env.require('sw-app').create({clock:{now:()=>now},battery:()=>({percent:50,charging:false}),store,command_output:row=>writes.push(JSON.parse(JSON.stringify(row)))});}
  const app=create(),session=app.action('session_start').session;app.action('connected',{session});
  return {app,writes,session,create,fail:value=>{fail=value;},at:value=>{now=value;app.tick();},receive:bytes=>app.receive(app.view().session,bytes||frame(riding)),
    result:(row,success=true)=>app.action('command_result',{attempt:row.attempt,session:row.session,index:row.index,success,error:'Controlled transport rejection'})};
}
function open(test,slot=1){test.app.action('swipe',{direction:'down',from_top:true});test.app.action('preset_slots');test.app.action('preset_begin',{slot});}
const test=scenario();open(test,4);
assert.equal(test.app.view().preset_draft.dynamic_assist,70);
const id=test.app.view().preset_editor.id;
test.app.action('preset_update',{editor_id:id,name:'Local',dynamic_assist:26,pedal_dip_compensation:17});
test.receive(frame({settings:{pedal_sensitivity:44,dynamic_assist:55,pedal_dip_compensation:66}}));assert.equal(test.app.view().preset_draft.dynamic_assist,26);
assert.equal(test.app.view().config.presets[3].name,'Drag');
test.fail(true);test.app.action('preset_save',{editor_id:id});assert.match(test.app.view().persistence_error,/storage full/);
assert.equal(test.app.view().config.presets[3].name,'Drag');test.fail(false);
test.app.action('preset_save',{editor_id:id});assert.equal(test.app.view().screen,'preset_slots');assert.equal(test.app.view().preset_editor,null);
assert.equal(test.app.view().config.presets[3].name,'Local');assert.equal(test.app.view().config.presets[3].pedal_dip_compensation,17);assert.equal(test.app.view().config.presets[3].dip_included,false);
open(test,1);assert.throws(()=>test.app.action('preset_save',{editor_id:id}),/changed/);
const newId=test.app.view().preset_editor.id;test.app.action('configuration_reload');assert.throws(()=>test.app.action('preset_save',{editor_id:newId}),/changed/);
for(const name of ['preset_clear','preset_clear_begin','preset_clear_done','preset_input_done'])assert.throws(()=>test.app.action(name),/Unknown/);
assert.equal(test.writes.length,0);assert.equal(test.create().view().config.presets[3].name,'Local');
console.log('watch local drafts, retry, stale completion/reload and retired actions: passed');
{
  // The Preset editor and the alert editor share one validation error: the last one set or cleared shows in both views.
  const shared=scenario();open(shared,1);
  const editorId={editor_id:shared.app.view().preset_editor.id},entryId=()=>({...editorId,entry_id:shared.app.view().preset_input.id});
  const reasons=()=>{const state=shared.app.view();return [state.validation_error,state.preset_editor.reason];};
  const percentage='Error: Pedal sensitivity: enter a whole percentage 0-100',threshold='Threshold outside supported range';
  shared.app.action('preset_update',{...editorId,pedal_sensitivity:101});shared.app.action('preset_save',editorId);
  assert.deepEqual(reasons(),[percentage,percentage]);
  // Leave the Preset editor open behind other screens and use the alert editor.
  shared.app.action('open_connection');shared.app.action('swipe',{direction:'up'});shared.app.action('swipe',{direction:'down',from_top:true});
  shared.app.action('alerts_begin');
  assert.equal(shared.app.view().preset_editor.id,editorId.editor_id);
  assert.deepEqual(reasons(),[null,''],'an alert action clears the Preset editor reason');
  shared.app.action('threshold_begin',{alert:'pwm'});for(const key of '111')shared.app.action('threshold_key',{key});
  assert.throws(()=>shared.app.action('threshold_done'),/Threshold outside supported range/);
  assert.deepEqual(reasons(),[threshold,threshold],'an alert error is the Preset editor reason too');
  shared.app.action('preset_page',{...editorId,page:1});
  assert.deepEqual(reasons(),[null,''],'a Preset editor action clears the alert error');
  shared.app.action('preset_input_begin',editorId);shared.app.action('preset_input_key',{...entryId(),key:'Clear'});shared.app.action('preset_input_accept',entryId());
  assert.deepEqual(reasons(),[percentage,percentage]);
  shared.app.action('threshold_cancel');
  assert.deepEqual(reasons(),[null,''],'an alert action clears the Preset editor error');
  shared.app.action('preset_slots');
  assert.deepEqual([shared.app.view().validation_error,shared.app.view().preset_editor],[null,null]);
  console.log('watch shared validation error across the Preset and alert editors: passed');
}
// The Preset editor module alone: no clock, battery, wheel session or store.
function editing(slot=1){
  const env=environment(),saved=env.require('sw-configuration').defaults(),editor=env.require('sw-preset-editor').create();editor.open(saved,slot);
  const ids=()=>({editor_id:editor.view().request.id,entry_id:editor.view().input?.id});
  const act=(name,payload={},editable=true)=>plain(editor.action(name,{...ids(),...payload},editable,saved));
  const type=text=>{for(const key of text)act('preset_input_key',{key});};
  return {env,saved,editor,ids,act,type,keys:()=>plain(editor.view().keys),view:()=>plain(editor.view())};
}
{
  const {saved,act,type,view}=editing(1);
  act('preset_input_begin');
  assert.deepEqual(view().input,{id:1,field:'name',text:'Jump',letters:0,lowercase:false});
  act('preset_input_key',{key:'Clear'});type('AB');
  act('preset_input_accept');
  assert.equal(view().input,null);assert.equal(view().draft.name,'AB');
  assert.equal(saved.presets[0].name,'Jump','an accepted entry changes only the Preset draft');
}
{
  // Finish the current preset value entry before changing or saving the Preset draft.
  const {act,view}=editing(2);
  act('preset_input_begin');
  assert.throws(()=>act('preset_update',{dynamic_assist:5}),/Finish the current preset value entry first/);
  assert.deepEqual(act('preset_save'),{invalid:true});
  assert.equal(view().request.reason,'Error: Finish the current preset value entry first');
  assert.equal(view().draft.dynamic_assist,0);assert.equal(view().input.field,'name');
  act('preset_input_cancel');
  assert.equal(view().input,null);assert.equal(view().draft.name,'Forest');
}
{
  // Key rules: a name takes 24 characters from three 12-key pages, a percentage 3 digits.
  const {act,type,keys,view}=editing(1);
  assert.deepEqual(keys(),[],'no key set without an open entry');
  act('preset_input_begin');assert.deepEqual(keys(),'ABCDEFGHIJKL'.split(''));act('preset_input_key',{key:'Clear'});
  act('preset_input_page',{delta:1});act('preset_input_key',{key:'a/A'});
  assert.deepEqual(keys(),['m','n','o','p','q','r','s','t','u','v','w','x']);
  type('mno p');act('preset_input_key',{key:'<'});
  assert.equal(view().input.text,'mno ');
  act('preset_input_page',{delta:-1});act('preset_input_page',{delta:-1});
  assert.equal(view().input.letters,2);
  assert.throws(()=>act('preset_input_key',{key:'A'}),/Invalid preset input key/,'a key outside the shown set is refused');
  type('0123456789012345678901234');
  assert.equal(view().input.text,'mno 01234567890123456789');
  assert.throws(()=>act('preset_input_page',{delta:2}),/Invalid name keypad page/);
  act('preset_input_accept');act('preset_page',{page:1});act('preset_input_begin');
  assert.deepEqual(view().input,{id:2,field:'pedal_sensitivity',text:'0',letters:0,lowercase:false});
  assert.deepEqual(keys(),['1','2','3','4','5','6','7','8','9','Clear','0','<']);
  type('1234');assert.equal(view().input.text,'012');
  assert.throws(()=>act('preset_input_key',{key:' '}),/Invalid preset input key/,'a percentage has no space');
  assert.throws(()=>act('preset_input_page',{delta:1}),/Invalid name keypad page/);
  act('preset_input_key',{key:'Clear'});type('101');act('preset_input_accept');
  assert.equal(view().input.text,'101','an invalid entry stays open beside its reason');
  assert.equal(view().request.reason,'Error: Pedal sensitivity: enter a whole percentage 0-100');
  act('preset_input_key',{key:'<'});
  assert.equal(view().request.reason,'','the next editor action clears the reason');
  act('preset_input_accept');
  assert.equal(view().draft.pedal_sensitivity,10);assert.equal(view().draft.name,'mno 01234567890123456789');
}
{
  // Editor and entry ids: a captured id cannot act on a later editor or entry; identity is checked before availability.
  const {editor,saved,act,ids,view}=editing(1);
  act('preset_input_begin');const first=ids();act('preset_input_cancel');act('preset_input_begin');
  assert.equal(view().input.id,2);
  for(const name of ['preset_input_key','preset_input_accept','preset_save','preset_update'])
    assert.throws(()=>editor.action(name,{...first,key:'Clear',name:'X'},true,saved),/Preset value entry changed/);
  assert.throws(()=>editor.swipe({...first,direction:'up'}),/Preset value entry changed/);
  for(const name of ['preset_input_key','preset_input_page','preset_input_accept','preset_input_cancel'])
    assert.throws(()=>editor.action(name,{editor_id:first.editor_id,key:'Clear',delta:1},true,saved),/Preset value entry changed/,name+' needs the entry id');
  assert.throws(()=>editor.action('preset_input_cancel',{...ids(),editor_id:first.editor_id+1},false,saved),/Preset editor changed/);
  assert.throws(()=>act('preset_input_cancel',{},false),/Preset editing unavailable/);
  assert.equal(view().input.id,2);
  editor.open(saved,1);
  assert.equal(view().request.id,2);assert.equal(view().input,null);assert.equal(view().page,0);
  assert.throws(()=>editor.action('preset_page',{...first,entry_id:undefined,page:1},true,saved),/Preset editor changed/);
  editor.close();
  assert.deepEqual(view(),{request:null,draft:null,page:0,input:null,keys:[],previous_page:3,next_page:1});
  assert.throws(()=>editor.swipe({editor_id:2,direction:'left'}),/Preset editor changed/);
}
{
  // In-editor swipes: left/right turn the field page unless an entry is open; up closes the entry, then the editor.
  const {editor,act,ids,view}=editing(3);
  const swipe=direction=>editor.swipe({editor_id:ids().editor_id,entry_id:ids().entry_id,direction});
  assert.deepEqual([view().previous_page,view().next_page],[3,1]);
  assert.equal(plain(swipe('right')),null);assert.equal(view().page,3);
  assert.deepEqual([view().previous_page,view().next_page],[2,0],'the page controls wrap as the swipes do');
  swipe('left');swipe('left');assert.equal(view().page,1);
  swipe('down');assert.equal(view().page,1);
  // An empty percentage is refused, so its entry stays open beside a reason.
  const refuse=()=>{act('preset_input_begin');act('preset_input_key',{key:'Clear'});act('preset_input_accept');assert.match(view().request.reason,/whole percentage/);};
  refuse();swipe('left');swipe('right');
  assert.equal(view().page,1,'the page holds while a value entry is open');
  assert.match(view().request.reason,/whole percentage/,'a refused page swipe keeps the reason');
  act('preset_page',{page:2});assert.equal(view().page,1);
  assert.equal(plain(swipe('up')),null);
  assert.equal(view().input,null);assert.equal(view().request.id,1);
  refuse();swipe('up');assert.equal(view().request.reason,'','closing the entry clears its reason');
  act('preset_update',{pedal_sensitivity:101});act('preset_save');assert.match(view().request.reason,/whole percentage/);
  swipe('right');
  assert.equal(view().page,0);assert.equal(view().request.reason,'','turning the page clears the reason');
  assert.deepEqual(plain(swipe('up')),{leave:true});
  assert.throws(()=>act('preset_page',{page:4}),/Invalid preset page/);
  assert.throws(()=>act('preset_page',{page:1.5}),/Invalid preset page/);
}
{
  // Save proposes the whole replacement configuration and leaves persistence to the caller; Cancel only asks to leave.
  const {saved,act,view}=editing(4);
  act('preset_update',{name:'Local',dynamic_assist:26,source:'touch'});
  assert.throws(()=>act('preset_update',{horn:true}),/Invalid preset draft field/);
  assert.throws(()=>act('preset_include_dip',{included:'yes'}),/Choose explicit dip inclusion/);
  act('preset_page',{page:3});act('preset_input_begin');
  act('preset_include_dip',{included:true});
  assert.equal(view().draft.dip_included,true,'dip inclusion changes while the dip entry is open');
  act('preset_input_cancel');
  const outcome=act('preset_save');
  assert.deepEqual(Object.keys(outcome),['save']);
  assert.equal(outcome.save.revision,1);
  assert.deepEqual(outcome.save.presets[3],{id:4,name:'Local',configured:true,pedal_sensitivity:20,dynamic_assist:26,pedal_dip_compensation:5,dip_included:true});
  assert.deepEqual(outcome.save.presets.slice(0,3),plain(saved.presets.slice(0,3)));
  assert.equal(saved.revision,0);assert.equal(saved.presets[3].name,'Drag');
  assert.equal(view().request.id,1,'Save leaves closing to the caller');
  act('preset_update',{pedal_sensitivity:101});
  assert.deepEqual(act('preset_save'),{invalid:true});
  assert.equal(view().request.reason,'Error: Pedal sensitivity: enter a whole percentage 0-100');
  assert.deepEqual(act('preset_cancel'),{leave:true});
  assert.equal(view().request.reason,'');
  // Actions that do not act on an entry need no entry id.
  act('preset_page',{page:1});act('preset_input_begin');
  assert.equal(view().input.field,'pedal_sensitivity');
}
{
  // ADR 0002: the editor loads no wheel command module and takes no writer.
  const env=environment();env.require('sw-preset-editor').create();
  assert.deepEqual(env.context.imports,['sw-preset-editor','sw-configuration']);
}
console.log('watch Preset editor module: value entry, finish-entry rule, key rules, ids, swipes, Save outcome and no wheel writer: passed');
