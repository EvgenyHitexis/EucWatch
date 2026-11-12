// Public application actions/raw notifications; no physical wheel or watch.
const assert=require('node:assert/strict');
const {environment,frame}=require('./harness.cjs');
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
