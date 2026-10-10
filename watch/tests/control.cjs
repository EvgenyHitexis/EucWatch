// Actual watch App input/raw-parser/output seam. All radio/time/storage controlled.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),zlib=require('node:zlib');
const root=path.resolve(__dirname,'..');
const child=require('node:child_process');
const evidence={issue:34,provenance:'Original production ES5 watch modules in Node VM; controlled clock/store/NRF, synthetic settings and movement derived from the sanitized WheelLog fixture; no physical operations',fixture:'experiments/laptop-feasibility/evidence/fixture-recording.jsonl',hardware_acceptance:'Pending owner-authorized actual-device controls, BLE writes, audible horn and recovery coexistence; #9/#31 remain open'};
function load(name){const module={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(root,name.replace(/^sw-/,'')+'.js'),'utf8'),{module,exports:module.exports,require:load,Uint8Array,Uint16Array,ArrayBuffer,Math,JSON,isFinite});return module.exports;}
function draw(state){const drawn=[],graphics={};for(const name of ['setColor','setFont','setFontAlign','drawRect','fillRect','drawLine','setPixel','clear','flip'])graphics[name]=()=>graphics;graphics.drawString=(text,x,y)=>{drawn.push({text,x,y});return graphics;};load('sw-render').draw(graphics,state);return drawn;}
const fixture=fs.readFileSync(path.resolve(root,'../experiments/laptop-feasibility/evidence/fixture-recording.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
const source=Buffer.concat(fixture.slice(0,5).map(row=>Buffer.from(row.raw_hex,'hex')));
function frame(settings={pedal_sensitivity:31,dynamic_assist:26,pedal_dip_compensation:10},speed=25){
 const bytes=Buffer.from(source);bytes.writeInt16BE(Math.round(speed*10),6);bytes[46]=8;
 for(const [name,index]of [['pedal_sensitivity',50],['dynamic_assist',66],['pedal_dip_compensation',68]])bytes[index]=settings[name]===null?128:settings[name];
 bytes.writeUInt32BE(zlib.crc32(bytes.subarray(0,-4)),bytes.length-4);return bytes;
}
function scenario(extra={}){
 let time=0;const writes=[];let config=load('sw-configuration').defaults();
 config.presets[0]={id:1,name:'Road',configured:true,pedal_sensitivity:31,dynamic_assist:26,pedal_dip_compensation:0,dip_included:false};
 const store={load:()=>JSON.parse(JSON.stringify(config)),save:value=>{config=JSON.parse(JSON.stringify(value));}};
 const app=load('sw-app').create({clock:{now:()=>time},battery:()=>({percent:50,charging:false}),store,command_output:row=>writes.push(JSON.parse(JSON.stringify(row))),...extra});
 const token=app.action('session_start').session;app.action('connected',{session:token});app.receive(token,frame({pedal_sensitivity:30,dynamic_assist:25,pedal_dip_compensation:10}));
 return{app,writes,store,at:value=>{time=value;app.tick();},receive:settings=>app.receive(app.view().session,frame(settings)),result:(row,success=true,error='')=>app.action('command_result',{attempt:row.attempt,session:row.session,index:row.index,success,error})};
}
function testMoving(){const moving=scenario();moving.app.action('swipe',{direction:'left'});
assert.equal(moving.app.view().presets.length,4);
const controls=load('sw-controls');assert.equal(controls.targets(moving.app.view()).length,4);
assert.equal(controls.hit(moving.app.view(),175,79).action,'preset_apply','configured default is available');
const tap=controls.hit(moving.app.view(),61,79);assert.equal(tap.action,'preset_apply');
let state=moving.app.action(tap.action,tap.payload);
assert.equal(state.screen,'dashboard');assert.equal(state.preset_attempt.pending,true);assert.match(state.feedback,/Road.*Applying/);
const drawn=draw(state);
assert.ok(drawn.some(row=>/Road.*Applying/.test(row.text)),'actual renderer presents immediate Applying');
assert.equal(moving.writes.length,1);assert.equal(moving.writes[0].packet_hex,'4c6441700f01028080801ff753d033');
moving.app.action('preset_apply',{slot:1});assert.equal(moving.writes.length,1,'extra taps never queue');
moving.result(moving.writes[0]);assert.equal(moving.writes.length,2);assert.equal(moving.writes[1].packet_hex.length,62);
moving.result(moving.writes[1]);assert.equal(moving.app.view().preset_attempt.status,'confirming');
assert.equal(moving.writes.length,2,'omitted dip produces no write');
moving.at(.1);moving.receive();assert.equal(moving.app.view().confirmed_preset,null);
moving.at(.2);moving.receive();assert.equal(moving.app.view().confirmed_preset.name,'Road');
assert.equal(moving.app.view().preset_attempt.status,'Confirmed');
assert.deepEqual(Array.from(moving.app.view().preset_attempt.readbacks||[]),[.1,.2],'retain temporal readback provenance');
console.log('watch one-tap moving preset, serial omitted-dip submission and two-frame confirmation: passed');
}
function testHorn(){
 const test=scenario();test.app.action('swipe',{direction:'down',from_top:true});test.app.action('sleep');
 test.app.action('button_down');test.app.action('button_down');test.at(.1);test.app.action('button_hold');test.app.action('button_up');
 assert.equal(test.writes.length,0,'whole sleeping button cycle consumed');
 let state=test.app.action('button_down');assert.equal(test.writes.length,1);assert.equal(test.writes[0].packet_hex,'4c6b41700e0080808001ca87e66f');
 assert.equal(state.horn_feedback.message,'Horn request submitting');
 test.app.action('horn_result',{request:test.writes[0].request,session:test.writes[0].session,success:true});
 assert.equal(test.app.view().horn_feedback.message,'Horn request sent');
 for(let i=0;i<5;i++){test.app.action('button_down');test.app.action('button_hold');}
 test.app.action('button_up');assert.equal(test.writes.length,1);
 test.at(1.2);state=test.app.action('button_down');assert.match(state.horn_feedback.message,/connection unavailable/);
 test.receive();test.app.action('button_hold');test.app.action('button_up');assert.equal(test.writes.length,1,'blocked input is never replayed');
 const held=scenario();held.app.action('swipe',{direction:'down',from_top:true});held.app.action('sleep');held.app.action('button_down');
 held.app.action('disconnect',{session:held.app.view().session});const replacement=held.app.action('session_start').session;held.app.action('connected',{session:replacement});held.receive();
 held.app.action('button_down');held.app.action('button_hold');assert.equal(held.writes.length,0,'session changes cannot release a consumed physical cycle');
 held.app.action('button_up');held.app.action('button_down');assert.equal(held.writes.length,1,'a fresh physical cycle may request once');
 console.log('watch sleeping wake-only cycle, fresh single horn request and discarded stale holds: passed');
}
function testFailureTraces(){
 const test=scenario();test.app.action('preset_apply',{slot:1});
 test.at(.1);test.receive();test.at(.2);test.receive();assert.equal(test.app.view().confirmed_preset,null,'pre-write data cannot confirm');
 test.result(test.writes[0]);
 test.at(.3);test.receive();test.at(.4);test.receive();
 test.result(test.writes[1],false,'Controlled write rejection');
 let state=test.app.view();assert.equal(state.preset_attempt.status,'Partially applied');
 assert.equal(state.preset_attempt.fields.pedal_sensitivity.state,'confirmed');
 assert.equal(state.preset_attempt.fields.dynamic_assist.state,'unknown');assert.equal(test.writes.length,2);
 test.app.action('swipe',{direction:'left'});const partial=draw(test.app.view());assert.ok(partial.some(row=>/Sensitivity.*31\/31.*confirmed/.test(row.text)));assert.ok(partial.some(row=>/Assist.*26\/26.*unknown/.test(row.text)));
 test.at(.5);test.receive();test.at(.6);test.receive();assert.equal(test.app.view().preset_attempt.status,'Partially applied');assert.equal(test.app.view().confirmed_preset,null);
 test.app.action('preset_apply',{slot:1});assert.equal(test.writes.length,3,'fresh explicit retry only');
 const noMerge=scenario();noMerge.app.action('preset_apply',{slot:1});noMerge.result(noMerge.writes[0]);noMerge.result(noMerge.writes[1]);
 for(let i=1;i<=4;i++){noMerge.at(i/10);noMerge.receive(i%2?{pedal_sensitivity:31,dynamic_assist:27,pedal_dip_compensation:10}:{pedal_sensitivity:32,dynamic_assist:26,pedal_dip_compensation:10});}
 assert.equal(noMerge.app.view().confirmed_preset,null,'independent matching fields do not merge into matching frames');
 noMerge.at(.5);noMerge.receive();noMerge.at(.6);noMerge.receive();assert.ok(noMerge.app.view().confirmed_preset);
 noMerge.at(.7);noMerge.receive({pedal_sensitivity:31,dynamic_assist:27,pedal_dip_compensation:10});assert.equal(noMerge.app.view().confirmed_preset,null);
 const timeout=scenario();timeout.app.action('preset_apply',{slot:1});
 for(let i=1;i<=50;i++){timeout.at(i/10);timeout.receive();}
 assert.equal(timeout.app.view().preset_attempt.pending,false);assert.match(timeout.app.view().preset_attempt.reason,/Submission timeout/);
 timeout.result(timeout.writes[0]);assert.equal(timeout.writes.length,1,'late receipt cannot submit remaining fields');
 const confirmation=scenario();confirmation.app.action('preset_apply',{slot:1});confirmation.result(confirmation.writes[0]);confirmation.result(confirmation.writes[1]);
 for(let i=1;i<=100;i++){confirmation.at(i/10);confirmation.receive({pedal_sensitivity:31,dynamic_assist:27,pedal_dip_compensation:10});}
 assert.equal(confirmation.app.view().preset_attempt.pending,false);assert.match(confirmation.app.view().preset_attempt.reason,/Confirmation timeout/);
 const stale=scenario();stale.app.action('preset_apply',{slot:1});stale.at(1.01);stale.receive();assert.equal(stale.app.view().preset_attempt.pending,false,'late fresh frame cannot revive stale attempt');
 const changed=scenario();changed.app.action('preset_apply',{slot:1});changed.result(changed.writes[0]);changed.result(changed.writes[1]);changed.at(.1);changed.receive();changed.at(.2);changed.receive();
 const config=changed.app.view().config;config.revision++;config.presets[0].name='Changed';changed.store.save(config);changed.app.action('configuration_reload');assert.equal(changed.app.view().confirmed_preset,null);assert.equal(changed.writes.length,2);
 const dip=scenario();const dipConfig=dip.app.view().config;dipConfig.presets[0].pedal_dip_compensation=11;dipConfig.presets[0].dip_included=true;dip.store.save(dipConfig);dip.app.action('configuration_reload');dip.app.action('preset_apply',{slot:1});dip.result(dip.writes[0]);dip.result(dip.writes[1]);dip.result(dip.writes[2]);
 assert.equal(dip.writes[2].packet_hex,'4c6441702101028080808080808080808080808080808080808080800b672ed25c');
 dip.at(.1);dip.receive();dip.at(.2);dip.receive();assert.equal(dip.app.view().confirmed_preset,null,'included dip must match in both complete frames');
 dip.at(.3);dip.receive({pedal_sensitivity:31,dynamic_assist:26,pedal_dip_compensation:11});dip.at(.4);dip.receive({pedal_sensitivity:31,dynamic_assist:26,pedal_dip_compensation:11});assert.ok(dip.app.view().confirmed_preset);
 const old=scenario();old.app.action('preset_apply',{slot:1});const oldRow=old.writes[0];old.app.action('disconnect',{session:oldRow.session});old.result(oldRow);assert.equal(old.writes.length,1);assert.equal(old.app.view().preset_attempt.pending,false);
 const recovering=scenario();recovering.app.action('preset_apply',{slot:1});recovering.app.action('button_down');assert.match(recovering.app.view().horn_feedback.message,/preset applying/);recovering.result(recovering.writes[0]);recovering.result(recovering.writes[1]);recovering.app.action('button_up');recovering.app.action('button_down');assert.match(recovering.app.view().horn_feedback.message,/preset applying/);
 recovering.at(30);recovering.app.action('button_up');recovering.receive();recovering.app.action('button_down');assert.equal(recovering.app.view().recovery,true);assert.match(recovering.app.view().horn_feedback.message,/recovery mode/);assert.equal(recovering.writes.length,2);
 console.log('watch cached/mixed/late rejection, partial/terminal results, deadlines, fresh retry and definition invalidation: passed');
}
function testLaptopParity(){
 const traces=[
  [{at:0,action:'preset_apply',slot:1},{at:.1,result:0},{at:.2,result:1},{at:.3,raw:frame().toString('hex')},{at:.4,raw:frame().toString('hex')}],
  [{at:0,action:'preset_apply',slot:1},{at:.1,result:0},{at:.2,raw:frame().toString('hex')},{at:.3,raw:frame().toString('hex')},{at:.4,result:1,success:false},{at:.5,raw:frame().toString('hex')}],
  [{at:0,action:'preset_apply',slot:1},{at:1.1,raw:frame().toString('hex')},{at:1.2,result:0}],
 ];
 function normalized(state){const a=state.preset_attempt;return{speed:state.dashboard.speed,status:a?a.status:null,pending:a?a.pending:false,fields:a?a.fields:null,confirmed:state.confirmed_preset?state.confirmed_preset.name:null};}
 const observed=traces.map(steps=>{const test=scenario();return steps.map(step=>{test.at(step.at);if(step.raw)test.app.receive(test.app.view().session,Buffer.from(step.raw,'hex'));else if(step.result!==undefined)test.result(test.writes[step.result],step.success!==false,'Controlled rejection');else test.app.action(step.action,{slot:step.slot});return normalized(test.app.view());});});
 const script=String.raw`
import json,sys,zlib
from eucwatch import Application,ManualClock
from eucwatch.configuration import default_configuration
from eucwatch.persistence import MemoryStore
data=json.load(sys.stdin);observed=[]
for steps in data['traces']:
 clock=ManualClock();writes=[];config=default_configuration();config['presets'][0]={'id':1,'name':'Road','configured':True,'pedal_sensitivity':31,'dynamic_assist':26,'pedal_dip_compensation':0,'dip_included':False}
 app=Application(clock=clock,store=MemoryStore(config),command_output=writes.append);app.action('connect');app.receive(app.session,bytes.fromhex(data['initial']))
 output=[]
 for step in steps:
  clock.advance(step['at']-clock.read()[0]);app.tick()
  if 'raw' in step:app.receive(app.session,bytes.fromhex(step['raw']))
  elif 'result' in step:
   row=writes[step['result']];app.action('command_result',attempt=row['attempt'],session=row['session'],index=row['index'],success=step.get('success',True),error='Controlled rejection')
  else:app.action(step['action'],slot=step['slot'])
  state=app.view();a=state['preset_attempt'];output.append({'speed':state['dashboard']['speed'],'status':a['status'] if a else None,'pending':a['pending'] if a else False,'fields':a['fields'] if a else None,'confirmed':state['confirmed_preset']['name'] if state['confirmed_preset'] else None})
 observed.append(output)
print(json.dumps(observed))
`;
 const python=path.resolve(root,'../experiments/laptop-feasibility/.venv/bin/python');
 const result=child.execFileSync(python,['-c',script],{cwd:path.resolve(root,'..'),env:{...process.env,PYTHONPATH:path.resolve(root,'../laptop')},input:JSON.stringify({traces,initial:frame({pedal_sensitivity:30,dynamic_assist:25,pedal_dip_compensation:10}).toString('hex')}),encoding:'utf8'});
 const expected=JSON.parse(result);assert.deepEqual(observed,expected);evidence.parity={traces,expected_laptop:expected,observed_watch:observed};console.log('watch/laptop identical actual raw/action traces: success, partial rejection and stale/late callbacks passed');
}
async function testWriter(){
 let now=0,id=0,rejectAt=-1,hang=false,notify,disconnected,resolveWrite;
 const tasks=new Map(),written=[];let adapter;
 const clock={now:()=>now},timers={setTimeout:(fn,delay)=>{const token=++id;tasks.set(token,{fn,due:now+delay/1000});return token;},clearTimeout:token=>tasks.delete(token)};
 const characteristic={properties:{notify:true,writeWithoutResponse:true},on:(name,callback)=>{notify=callback;},startNotifications:()=>Promise.resolve(),writeValue:bytes=>{
   written.push(Buffer.from(bytes));if(written.length===rejectAt)return Promise.reject(Error('Controlled partial write failure'));
   return hang?new Promise(resolve=>resolveWrite=resolve):Promise.resolve();
 }};
 const server={connected:true,device:{connected:true,on:(name,callback)=>disconnected=callback},getPrimaryService:()=>Promise.resolve({getCharacteristic:()=>Promise.resolve(characteristic)}),disconnect:()=>{server.connected=false;server.device.connected=false;return Promise.resolve();}};
 const radio={findDevices:callback=>callback([{id:'synthetic wheel',name:'Sherman L'}]),connect:()=>Promise.resolve(server)};
 const test=scenario({clock,command_output:row=>adapter.submit(row)});adapter=load('sw-transport').create({app:test.app,radio,timers});
 const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
 adapter.discover();adapter.select('synthetic wheel');await flush();
 function emit(settings){const bytes=frame(settings);notify({target:{value:new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength)}});}
 emit();test.app.action('preset_apply',{slot:1});await flush();
 assert.deepEqual(written.map(bytes=>bytes.length),[15,20,11]);assert.equal(test.app.view().preset_attempt.status,'confirming');
 now=.1;emit();now=.2;emit();assert.equal(test.app.view().confirmed_preset.name,'Road');
 test.app.action('button_down');await flush();test.app.action('button_up');assert.equal(written.at(-1).toString('hex'),'4c6b41700e0080808001ca87e66f');assert.equal(test.app.view().horn_feedback.message,'Horn request sent');
 characteristic.properties.writeWithoutResponse=false;test.app.action('button_down');await flush();test.app.action('button_up');assert.match(test.app.view().horn_feedback.message,/write-without-response/);assert.equal(written.length,4);
 characteristic.properties.writeWithoutResponse=true;const config=test.app.view().config;config.presets[0].pedal_dip_compensation=11;config.presets[0].dip_included=true;test.store.save(config);test.app.action('configuration_reload');rejectAt=7;test.app.action('preset_apply',{slot:1});await flush();
 assert.equal(written.length,7);assert.equal(test.app.view().preset_attempt.pending,false);assert.match(test.app.view().preset_attempt.reason,/Controlled partial write failure/);assert.ok(!written.some(bytes=>bytes[4]===33),'native chunk rejection prevents the unsent dip command');
 hang=true;test.app.action('preset_apply',{slot:1});await flush();assert.equal(written.length,8);
 for(let step=3;step<=32;step++){now=step/10;emit();test.app.tick();adapter.tick();for(const [token,task]of [...tasks])if(task.due<=now){tasks.delete(token);task.fn();}await flush();}
 assert.match(test.app.view().preset_attempt.reason,/submission timeout/);
 const timeoutResult=test.app.view().preset_attempt;
 assert.equal(test.app.view().preset_attempt.pending,false);test.app.action('preset_apply',{slot:1});await flush();assert.equal(written.length,8,'native hung writer retains ownership; new request cannot queue');
 hang=false;resolveWrite();await flush();assert.equal(written.length,8,'late completion never sends remaining packet chunks/settings');
 server.connected=false;server.device.connected=false;disconnected();await flush();assert.equal(test.app.view().fresh,false);
 evidence.writer={chunk_hex:written.map(bytes=>bytes.toString('hex')),timeout_result:timeoutResult,expected:'serialized <=20-byte writes, unsent dip stopped on rejection; fresh-telemetry timeout; no queued retry or remaining late chunks',observed:'assertions passed',native_writer_released_after_settlement:true};
 if(!process.env.EUCWATCH_CONTROL_CASE)fs.writeFileSync(path.join(root,'evidence/local-presets/regression-control.json'),JSON.stringify(evidence,null,2)+'\n');
 console.log('watch same-session 2v14 property-selected 20-byte writer, horn request, bounded hang and late rejection: passed');
}
if(process.env.EUCWATCH_CONTROL_CASE==='horn')testHorn();else if(process.env.EUCWATCH_CONTROL_CASE==='writer')testWriter().catch(error=>{console.error(error);process.exitCode=1;});else{testMoving();testHorn();testFailureTraces();testLaptopParity();testWriter().catch(error=>{console.error(error);process.exitCode=1;});}
