// Public application actions/raw notifications; no physical wheel or watch.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),zlib=require('node:zlib');
const root=path.resolve(__dirname,'..');
function load(name){const module={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(root,name.replace(/^sw-/,'')+'.js'),'utf8'),{module,exports:module.exports,require:load,Uint8Array,Uint16Array,ArrayBuffer,Math,JSON,isFinite});return module.exports;}
const rows=fs.readFileSync(path.resolve(root,'../experiments/laptop-feasibility/evidence/fixture-recording.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
const source=Buffer.concat(rows.slice(0,5).map(row=>Buffer.from(row.raw_hex,'hex')));
function frame(sensitivity=41,assist=51,dip=61){const bytes=Buffer.from(source);bytes[46]=8;bytes[50]=sensitivity;bytes[66]=assist;bytes[68]=dip;bytes.writeUInt32BE(zlib.crc32(bytes.subarray(0,-4)),bytes.length-4);return bytes;}
function scenario(){
  let now=0,saved=load('sw-configuration').defaults(),fail=false;const writes=[];
  const store={load:()=>JSON.parse(JSON.stringify(saved)),save:value=>{if(fail)throw Error('Controlled storage full');saved=JSON.parse(JSON.stringify(value));}};
  function create(){return load('sw-app').create({clock:{now:()=>now},battery:()=>({percent:50,charging:false}),store,command_output:row=>writes.push(JSON.parse(JSON.stringify(row)))});}
  const app=create(),session=app.action('session_start').session;app.action('connected',{session});
  return {app,writes,session,create,fail:value=>{fail=value;},at:value=>{now=value;app.tick();},receive:bytes=>app.receive(app.view().session,bytes||frame()),
    result:(row,success=true)=>app.action('command_result',{attempt:row.attempt,session:row.session,index:row.index,success,error:'Controlled transport rejection'})};
}
function open(test,slot=1){test.app.action('swipe',{direction:'down',from_top:true});test.app.action('preset_slots');test.app.action('preset_begin',{slot});}
exports.frame=frame;exports.scenario=scenario;exports.open=open;
if(require.main===module){
  const test=scenario();open(test,4);
  assert.equal(test.app.view().preset_draft.dynamic_assist,70);
  const id=test.app.view().preset_editor.id;
  test.app.action('preset_update',{editor_id:id,name:'Local',dynamic_assist:26,pedal_dip_compensation:17});
  test.receive(frame(44,55,66));assert.equal(test.app.view().preset_draft.dynamic_assist,26);
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
}
