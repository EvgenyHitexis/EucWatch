// Accepted application seam: production core actions/raw parser/time/motor output.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),zlib=require('node:zlib');
const root=path.resolve(__dirname,'..');
function load(name){const module={exports:{}};const filename=path.join(root,name.replace(/^sw-/,'')+'.js');vm.runInNewContext(fs.readFileSync(filename,'utf8'),{exports:module.exports,module,require:load,Math,JSON,isFinite});return module.exports;}
const clone=value=>JSON.parse(JSON.stringify(value));
function scenario(saved=null){let time=0,configuration=saved;const output=[];
  const app=load('sw-app').create({clock:{now:()=>time},battery:()=>({voltage:3.9,percent:57,charging:false}),
    store:{load:()=>clone(configuration),save:value=>{configuration=clone(value);}},vibration_output:row=>output.push(clone(row))});
  return {app,output,at:value=>{time=value;app.tick();},setTime:value=>{time=value;},saved:()=>clone(configuration)};
}
const test=scenario();test.app.action('alert_test',{alert:'pwm'});
for(const time of [.15,.3,.45,.6,.75])test.at(time);
assert.deepEqual(test.output.map(row=>[row.alert,row.phase,row.at_s,row.duration_s]),[
  ['pwm','start',0,.15],['pwm','stop',.15,.15],['pwm','start',.3,.15],
  ['pwm','stop',.45,.15],['pwm','start',.6,.15],['pwm','stop',.75,.15]
]);
assert.equal(test.app.view().vibration.current,null);
console.log('watch PWM test vibration through public application: passed');
const editing=scenario();
assert.deepEqual(clone(editing.app.view().config.alerts),{pwm:{enabled:false,threshold:null},speed:{enabled:false,threshold:null},battery:{enabled:false,threshold:null},lost:{enabled:true}});
editing.app.action('swipe',{direction:'down',from_top:true});editing.app.action('alerts_begin');
editing.app.action('alerts_update',{alert:'pwm',enabled:true});
assert.throws(()=>editing.app.action('alerts_save'),/threshold/i);
assert.equal(editing.app.view().config.alerts.pwm.enabled,false);
editing.app.action('alerts_update',{alert:'pwm',threshold:70});editing.app.action('alerts_save');
assert.deepEqual(clone(editing.saved().alerts.pwm),{enabled:true,threshold:70});
const restarted=scenario(editing.saved());assert.deepEqual(clone(restarted.app.view().config.alerts.pwm),{enabled:true,threshold:70});
editing.app.action('alerts_begin');editing.app.action('alerts_update',{alert:'pwm',threshold:80});editing.app.action('alerts_cancel');
assert.equal(editing.app.view().config.alerts.pwm.threshold,70);
editing.app.action('alerts_begin');editing.app.action('alerts_update',{alert:'pwm',threshold:80});editing.app.action('swipe',{direction:'up'});
assert.equal(editing.app.view().alerts_draft,null);assert.equal(editing.app.view().config.alerts.pwm.threshold,70);
console.log('watch alert explicit Save/Cancel, validation, restart and back discard: passed');
const source=fs.readFileSync(path.resolve(root,'../experiments/laptop-feasibility/evidence/fixture-recording.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
const sourceFrame=Buffer.concat(source.slice(0,5).map(row=>Buffer.from(row.raw_hex,'hex')));
function frame(voltage=135,speed=25,pwm=45){const bytes=Buffer.from(sourceFrame);bytes.writeUInt16BE(Math.round(voltage*100),4);bytes.writeInt16BE(Math.round(speed*10),6);bytes.writeUInt16BE(Math.round(pwm*100),34);bytes.writeUInt32BE(zlib.crc32(bytes.subarray(0,bytes.length-4)),bytes.length-4);return bytes;}
const loss=scenario();const session=loss.app.action('session_start').session;loss.app.action('connected',{session});
loss.at(2);assert.equal(loss.output.length,0,'initial no-data has no lost-telemetry vibration');
loss.app.receive(session,frame());loss.at(3);loss.at(3.15);loss.at(5);
assert.deepEqual(loss.output.map(row=>[row.alert,row.phase,row.at_s,row.duration_s]),[['lost','start',3,.15],['lost','stop',3.15,.15]]);
loss.app.receive(session,frame());loss.at(5.1);loss.app.action('disconnect',{session});loss.at(5.25);
assert.deepEqual(loss.output.slice(2).map(row=>[row.alert,row.phase,row.at_s,row.duration_s]),[['lost','start',5.1,.15],['lost','stop',5.25,.15]]);
console.log('watch lost telemetry initial suppression, weakest pattern and fresh-data rearm: passed');
function saveAlert(target,name,threshold,enabled=true){target.app.action('swipe',{direction:'down',from_top:true});target.app.action('alerts_begin');target.app.action('alerts_update',{alert:name,enabled,...(name==='lost'?{}:{threshold})});target.app.action('alerts_save');}
const pwm=scenario();const pwmSession=pwm.app.action('session_start').session;pwm.app.action('connected',{session:pwmSession});pwm.app.receive(pwmSession,frame(135,25,70));
saveAlert(pwm,'pwm',70);assert.equal(pwm.output[0]?.alert,'pwm','Save evaluates enabled alerts immediately');
for(let step=1;step<=40;step++){const at=step*.05;pwm.at(at);if(step%4===0)pwm.app.receive(pwmSession,frame(135,25,70));}
const pwmStarts=pwm.output.filter(row=>row.phase==='start').map(row=>Math.round(row.at_s*100)/100);
assert.deepEqual(pwmStarts,[0,.3,.6,2]);
pwm.app.receive(pwmSession,frame(135,25,69));assert.ok(pwm.app.view().vibration.current,'PWM hysteresis remains active one point below threshold');
pwm.app.receive(pwmSession,frame(135,25,67));assert.equal(pwm.app.view().vibration.current,null,'PWM clears three points below threshold');
pwm.at(2.1);pwm.app.receive(pwmSession,frame(135,25,70));assert.equal(pwm.output.at(-1).phase,'start');
const coalesced=scenario();saveAlert(coalesced,'pwm',70);const cid=coalesced.app.action('session_start').session;coalesced.app.action('connected',{session:cid});
coalesced.app.receive(cid,Buffer.concat([frame(135,25,70),frame(135,25,67)]));
assert.deepEqual(coalesced.output.map(row=>row.phase),['start','stop'],'every valid frame evaluates independently of rendering');
console.log('watch PWM crossing/repeat/hysteresis, immediate Save and every-frame evaluation: passed');
const battery=scenario();saveAlert(battery,'battery',60);const bid=battery.app.action('session_start').session;battery.app.action('connected',{session:bid});battery.app.receive(bid,frame());
battery.at(.5);assert.deepEqual(battery.output.map(row=>[row.alert,row.phase,row.at_s,row.duration_s]),[['battery','start',0,.5],['battery','stop',.5,.5]]);
battery.app.receive(bid,frame());assert.equal(battery.output.length,2,'low battery is once per crossing');
for(let step=2;step<=12;step++){battery.at(step*.5);battery.app.receive(bid,frame(140));}
battery.at(6.1);battery.app.receive(bid,frame());assert.equal(battery.output.at(-1).alert,'battery');assert.equal(battery.output.at(-1).phase,'start');
const interrupted=scenario();saveAlert(interrupted,'battery',60);saveAlert(interrupted,'lost',null,false);const iid=interrupted.app.action('session_start').session;interrupted.app.action('connected',{session:iid});interrupted.app.receive(iid,frame());
interrupted.at(.5);interrupted.app.receive(iid,frame(140));interrupted.at(5.5);interrupted.app.receive(iid,frame(140));interrupted.at(5.6);interrupted.app.receive(iid,frame());
assert.equal(interrupted.output.filter(row=>row.alert==='battery'&&row.phase==='start').length,1,'stale time cannot complete continuous five-second battery rearm');
const speed=scenario();saveAlert(speed,'speed',20);const sid=speed.app.action('session_start').session;speed.app.action('connected',{session:sid});speed.app.receive(sid,frame(135,-20));
for(let step=1;step<=100;step++){speed.at(step*.05);if(step%4===0)speed.app.receive(sid,frame(135,-20));}
assert.deepEqual(speed.output.filter(row=>row.phase==='start').map(row=>Math.round(row.at_s*100)/100),[0,.3,5]);
speed.app.receive(sid,frame(135,19));assert.ok(speed.app.view().vibration.current);speed.app.receive(sid,frame(135,18));assert.equal(speed.app.view().vibration.current,null);
console.log('watch speed five-second repeat and battery crossing/continuous rearm: passed');
const competition=scenario();saveAlert(competition,'pwm',40);saveAlert(competition,'speed',20);saveAlert(competition,'battery',60);
const qid=competition.app.action('session_start').session;competition.app.action('connected',{session:qid});competition.app.receive(qid,frame());
for(let step=1;step<=35;step++){competition.at(step*.05);if(step%4===0)competition.app.receive(qid,frame());}
assert.deepEqual([...new Set(competition.output.filter(row=>row.phase==='start').map(row=>row.alert))],['pwm','speed','battery']);
let on=false;for(const row of competition.output){if(row.phase==='start'){assert.equal(on,false,'patterns do not overlap');on=true;}else{assert.equal(on,true);on=false;}}
const queued=scenario();queued.app.action('alert_test',{alert:'battery'});for(const alert of ['speed','pwm','lost'])queued.app.action('alert_test',{alert});
for(let step=1;step<=35;step++)queued.at(step*.05);
assert.deepEqual([...new Set(queued.output.filter(row=>row.phase==='start').map(row=>row.alert))],['battery','lost','pwm','speed']);
competition.at(1.8);competition.app.action('disconnect',{session:qid});
assert.equal(competition.output.at(-1).alert,'lost');assert.equal(competition.output.at(-1).duration_s,.15);
assert.equal(competition.app.view().vibration.queued.length,0);
const paused=scenario();paused.app.action('alert_test',{alert:'pwm'});paused.at(10);paused.at(10.5);
assert.deepEqual(paused.output.map(row=>row.phase),['start','stop'],'long gaps do not emit a burst or replay missed test pulses');
console.log('watch priority/nonoverlap, stale cancellation and missed-pulse suppression: passed');
const boundary=scenario();saveAlert(boundary,'pwm',40);const xid=boundary.app.action('session_start').session;boundary.app.action('connected',{session:xid});boundary.app.receive(xid,frame());
boundary.setTime(2);boundary.app.action('alert_test',{alert:'battery'});
assert.equal(boundary.output.some(row=>row.alert==='pwm'&&row.phase==='start'&&row.at_s>=2),false,'test vibration action cannot submit an overdue stale measurement repeat');
for(const [alert,threshold] of [['pwm',true],['pwm',101],['battery',-1],['speed',NaN],['speed',3276.8]]){
  const invalid=scenario();invalid.app.action('swipe',{direction:'down',from_top:true});invalid.app.action('alerts_begin');invalid.app.action('alerts_update',{alert,enabled:true,threshold});
  assert.throws(()=>invalid.app.action('alerts_save'));assert.equal(invalid.app.view().config.revision,0);assert.equal(invalid.saved(),null);
}
const ongoing=scenario();ongoing.app.action('swipe',{direction:'down',from_top:true});ongoing.app.action('alerts_begin');ongoing.at(60);assert.equal(ongoing.app.view().awake,true);
const bounded=scenario();for(let n=0;n<100;n++){bounded.app.action('alert_test',{alert:'lost'});bounded.at((n+1)*.2);}
assert.ok(bounded.app.view().vibration.events.length<=32);assert.equal(bounded.app.view().vibration.event_count,200);
console.log('watch complete validation, ongoing editor and bounded diagnostic history: passed');
