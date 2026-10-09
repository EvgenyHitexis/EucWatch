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
  const test=scenario();test.receive();open(test);
  assert.equal(test.app.view().screen,'preset_editor');
  assert.equal(test.app.view().preset_editor.status,'waiting');
  assert.equal(test.app.view().preset_draft,null,'cached values cannot seed opening');
  assert.equal(test.writes.length,0,'opening emits no setting command');
  test.at(.1);test.receive(frame(42,52,62));
  assert.equal(test.app.view().preset_draft.pedal_sensitivity,42,'external wheel settings seed the editor');
  assert.equal(test.app.view().preset_draft.dynamic_assist,52);
  assert.equal(test.app.view().preset_draft.pedal_dip_compensation,undefined);
  console.log('watch editor waits for fresh external settings: passed');
  const before=JSON.stringify(test.app.view().config.presets.slice(1));
  test.app.action('preset_update',{pedal_sensitivity:31});
  assert.equal(test.writes.length,1);
  assert.equal(test.writes[0].packet_hex,'4c6441700f01028080801ff753d033');
  assert.equal(test.app.view().preset_attempt.kind,'editor');
  assert.equal(test.app.view().config.presets[0].pedal_sensitivity,31);
  assert.equal(JSON.stringify(test.app.view().config.presets.slice(1)),before);
  assert.throws(()=>test.app.action('preset_update',{dynamic_assist:20}),/Wait/);
  test.result(test.writes[0]);test.at(.2);test.receive(frame(31,52,62));
  assert.equal(test.app.view().preset_attempt.pending,true);
  test.at(.3);test.receive(frame(31,52,62));
  assert.equal(test.app.view().preset_attempt.status,'Confirmed');
  assert.equal(test.app.view().preset_editor.current_confirmation,true);
  assert.equal(test.app.view().confirmed_preset,null,'field confirmation never labels the whole preset');
  test.at(.4);test.receive(frame(32,52,62));
  assert.equal(test.app.view().preset_editor.current_confirmation,false);
  assert.equal(test.app.view().preset_attempt.status,'Confirmed','terminal evidence remains historical');
  console.log('watch editor submits one field and distinguishes fresh confirmation: passed');
  test.app.action('preset_update',{name:'Rain'});
  test.app.action('preset_include_dip',{included:true});
  assert.equal(test.app.view().config.presets[0].pedal_dip_compensation,62);
  test.app.action('preset_include_dip',{included:false});
  assert.equal(test.app.view().config.presets[0].pedal_dip_compensation,undefined);
  assert.equal(test.writes.length,1,'name and optional metadata are local');
  const good=JSON.stringify(test.app.view().config);
  test.fail(true);test.app.action('preset_update',{pedal_sensitivity:33});
  assert.equal(JSON.stringify(test.app.view().config),good);
  assert.equal(test.app.view().preset_draft.pedal_sensitivity,33);
  assert.match(test.app.view().persistence_error,/not undone/);
  test.result(test.writes[1]);test.at(.5);test.receive(frame(33,52,62));test.at(.6);test.receive(frame(33,52,62));
  assert.equal(test.app.view().preset_attempt.status,'Confirmed','wheel confirmation independent of local save');
  test.fail(false);test.app.action('preset_save');
  assert.equal(test.app.view().config.presets[0].pedal_sensitivity,33);
  assert.equal(test.writes.length,2,'retry saves locally without reissuing');
  test.app.action('preset_update',{dynamic_assist:34});const command=test.writes[2];
  test.app.action('preset_cancel');
  assert.equal(test.app.view().screen,'preset_slots');
  assert.equal(test.app.commandEligible(command),false);
  test.result(command);assert.equal(test.writes.length,3,'late completion after leaving cannot replay');
  const restarted=test.create();assert.equal(restarted.view().config.presets[0].dynamic_assist,34);
  assert.equal(restarted.view().preset_editor,null);assert.equal(restarted.view().confirmed_preset,null);
  assert.equal(restarted.view().command_events.length,0);
  test.app.action('preset_clear',{slot:1});
  assert.equal(test.app.view().config.presets[0].name,'Rain');
  assert.equal(test.app.view().config.presets[0].configured,false);
  assert.equal(test.writes.length,3);
  console.log('watch local metadata, save failure/retry, cancel and restart: passed');
  for(const invalid of ['corrupt','speed','partial','prefix','old-session','disconnected','timeout']){
    const waiting=scenario();waiting.receive();const bytes=frame(44,54,64);
    if(invalid==='prefix')waiting.receive(bytes.subarray(0,30));
    open(waiting);waiting.at(.1);
    if(invalid==='corrupt'){bytes[50]^=1;waiting.receive(bytes);}
    if(invalid==='speed'){bytes[46]=0;bytes.writeUInt32BE(zlib.crc32(bytes.subarray(0,-4)),bytes.length-4);waiting.receive(bytes);}
    if(invalid==='partial')waiting.receive(frame(44,128,64));
    if(invalid==='prefix')waiting.receive(bytes.subarray(30));
    if(invalid==='old-session')waiting.app.receive(waiting.session-1,bytes);
    if(invalid==='disconnected')waiting.app.action('disconnect',{session:waiting.session});
    assert.equal(waiting.app.view().preset_draft,null,invalid+' cannot expose editable saved values');
    waiting.at(5);assert.equal(waiting.app.view().preset_editor.status,'unavailable');
    assert.equal(waiting.writes.length,0);
  }
  console.log('watch invalid/cached/old-session opening has bounded unavailable result: passed');
  for(const outcome of ['rejected','submission-timeout','confirmation-timeout','mismatch','partial-readback','disconnect','stale','prefix-readback']){
    const operation=scenario();open(operation);operation.receive();operation.app.action('preset_update',{dynamic_assist:20});
    const row=operation.writes[0];
    if(outcome==='rejected')operation.result(row,false);
    else if(outcome!=='submission-timeout')operation.result(row);
    if(outcome==='disconnect')operation.app.action('disconnect',{session:operation.session});
    else if(outcome==='stale')operation.at(1);
    else if(outcome==='prefix-readback'){
      operation.at(.1);operation.receive(frame(41,20,61));
      const bytes=frame(41,20,61);operation.receive(bytes.subarray(0,30));
      operation.app.action('preset_cancel');open(operation);operation.receive(bytes.subarray(30));
      assert.equal(operation.app.view().preset_draft,null);
    }else if(outcome!=='rejected'){
      for(let tenth=1;tenth<=101;tenth++){
        operation.at(tenth/10);
        operation.receive(outcome==='partial-readback'?frame(41,128,61):frame(41,51,61));
      }
    }
    if(outcome!=='prefix-readback'){
      assert.equal(operation.app.view().preset_attempt.pending,false,outcome+' is bounded');
      assert.equal(operation.app.view().preset_editor.current_confirmation,false);
      assert.equal(operation.app.view().confirmed_preset,null);
    }
    assert.equal(operation.writes.length,1,outcome+' never retries');
    const replacement=operation.app.action('session_start').session;operation.app.action('connected',{session:replacement});operation.app.receive(operation.session,frame(41,20,61));operation.result(row);
    assert.equal(operation.writes.length,1);assert.equal(operation.app.view().preset_draft,null,'new session requires explicit reopen');
  }
  console.log('watch bounded rejected/hung/missing/mismatching/partial/stale/disconnected results: passed');
}
