// Same serialized actions/clock/raw source drive both public Applications.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),zlib=require('node:zlib'),cp=require('node:child_process'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),repo=path.resolve(root,'..');
function load(name){const module={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(root,name.replace(/^sw-/,'')+'.js'),'utf8'),{module,exports:module.exports,require:load,Math,JSON,isFinite});return module.exports;}
const source=fs.readFileSync(path.join(repo,'experiments/laptop-feasibility/evidence/fixture-recording.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
const sourceFrame=Buffer.concat(source.slice(0,5).map(row=>Buffer.from(row.raw_hex,'hex')));
function frame(voltage=135,speed=25,pwm=45){const bytes=Buffer.from(sourceFrame);bytes.writeUInt16BE(Math.round(voltage*100),4);bytes.writeInt16BE(Math.round(speed*10),6);bytes.writeUInt16BE(Math.round(pwm*100),34);bytes.writeUInt32BE(zlib.crc32(bytes.subarray(0,bytes.length-4)),bytes.length-4);return bytes.toString('hex');}
const operations=[];
function action(at_s,action,payload={}){operations.push({at_s,type:'action',action,payload});}
function raw(at_s,voltage=135,speed=25,pwm=45){operations.push({at_s,type:'raw',hex:frame(voltage,speed,pwm)});}
function ticks(from,to,receive){for(let n=Math.round(from*20);n<=Math.round(to*20);n++){const time=n/20;operations.push({at_s:time,type:'tick'});if(receive&&n%4===0)raw(time,...receive);}}
action(0,'alert_test',{alert:'battery'});for(const alert of ['speed','pwm','lost'])action(0,'alert_test',{alert});ticks(.05,2);
action(2.1,'connect');raw(2.1);action(2.1,'swipe',{direction:'down',from_top:true});action(2.1,'alerts_begin');
for(const [alert,threshold] of [['pwm',40],['speed',20],['battery',60]])action(2.1,'alerts_update',{alert,enabled:true,threshold});action(2.1,'alerts_save');
ticks(2.15,7.1,[135,25,45]);action(7.15,'disconnect');ticks(7.2,7.5);
action(7.6,'connect');raw(7.6,140,18,37);ticks(7.65,12.6,[140,18,37]);raw(12.65);
action(12.7,'swipe',{direction:'down',from_top:true});action(12.7,'alerts_begin');action(12.7,'alerts_update',{alert:'pwm',threshold:null});action(12.7,'alerts_save');action(12.7,'alerts_cancel');
action(12.8,'alerts_begin');action(12.8,'alerts_update',{alert:'speed',threshold:100});action(12.8,'swipe',{direction:'right'});
operations.push({at_s:13,type:'restart'});
let now=0,saved=null;
const store={load:()=>saved,save:value=>{saved=JSON.parse(JSON.stringify(value));}};
const create=()=>load('sw-app').create({clock:{now:()=>now},battery:()=>({percent:50}),store});
let app=create();const watch=[];
for(const operation of operations){now=operation.at_s;let rejected=false;try{
  if(operation.type==='raw')app.receive(app.view().session,Buffer.from(operation.hex,'hex'));
  else if(operation.type==='restart')app=create();
  else if(operation.type==='action'){
    if(operation.action==='connect'){const session=app.action('session_start').session;app.action('connected',{session});}
    else if(operation.action==='disconnect')app.action('disconnect',{session:app.view().session});
    else app.action(operation.action,operation.payload);
  }else app.tick();
}catch(error){rejected=true;}
const state=app.view();watch.push({rejected,alerts:state.config.alerts,revision:state.config.revision,draft:state.alerts_draft,fresh:state.fresh,vibration:{events:state.vibration.events,event_count:state.vibration.event_count,current:state.vibration.current,queued:state.vibration.queued}});}
const python=process.env.EUCWATCH_TEST_PYTHON||path.join(repo,'experiments/laptop-feasibility/.venv/bin/python');
const result=cp.spawnSync(python,[path.join(__dirname,'laptop-alert-trace.py')],{input:JSON.stringify(operations),encoding:'utf8'});
assert.equal(result.status,0,result.stderr);const laptop=JSON.parse(result.stdout);
function normalized(value){return JSON.parse(JSON.stringify(value,(_key,value)=>typeof value==='number'?Math.round(value*1e6)/1e6:value));}
function delta(states,index){const state=normalized(states[index]),events=state.vibration.events,count=state.vibration.event_count,previous=index?states[index-1].vibration.event_count:0;
  const added=count>=previous?count-previous:count;
  state.vibration.events=added?events.slice(-added):[];delete state.vibration.event_count;return state;
}
for(let index=0;index<watch.length;index++)assert.deepEqual(delta(watch,index),delta(laptop,index),`operation ${index}: ${JSON.stringify(operations[index])}`);
const fingerprints={};for(const filename of ['laptop/eucwatch/application.py','laptop/eucwatch/alerts.py','watch/app.js','watch/alerts.js','experiments/laptop-feasibility/evidence/fixture-recording.jsonl'])fingerprints[filename]=crypto.createHash('sha256').update(fs.readFileSync(path.join(repo,filename))).digest('hex');
const pulseEvents=watch.flatMap((_state,index)=>delta(watch,index).vibration.events),expectedPulses=laptop.flatMap((_state,index)=>delta(laptop,index).vibration.events);
fs.writeFileSync(path.join(root,'evidence/alerts.json'),JSON.stringify({issue:33,provenance:'Same explicit actions, synthetic CRC-valid source-derived notifications and 50ms controlled clock enter laptop and actual watch public applications; compares newly emitted pulse events (laptop mode resets diagnostic history; watch retains bounded history); no physical outputs',fingerprints,operations,expected:normalized(laptop.at(-1)),observed:normalized(watch.at(-1)),expected_pulse_events:expectedPulses,observed_pulse_events:pulseEvents,matched_operations:watch.length,matched_pulse_events:pulseEvents.length,watch_trace_limit:32,physical_acceptance:'pending: actual motor onset/durations, memory/timing and owner pattern recognition'},null,2)+'\n');
console.log(`watch/laptop public application alert/editing traces: ${watch.length} states matched`);
