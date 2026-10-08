const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {environment,flush}=require('./runtime.cjs');
const {crc32}=require('./transfer.cjs');
const root=path.resolve(__dirname,'..');
function settingsFrame(assist=25,speed=0){const rows=fs.readFileSync(path.resolve(root,'../experiments/laptop-feasibility/evidence/fixture-recording.jsonl'),'utf8').trim().split('\n').map(JSON.parse);const bytes=Buffer.concat(rows.slice(0,5).map(row=>Buffer.from(row.raw_hex,'hex')));bytes.writeInt16BE(speed*10,6);bytes[46]=8;bytes[50]=30;bytes[66]=assist;bytes[68]=10;bytes.writeUInt32BE(crc32(bytes.subarray(0,-4).toString('latin1')),bytes.length-4);return bytes;}
function coreScenario(){
  const {environment}=require('./transfer.cjs'),env=environment(),store=env.store(),config=env.config.defaults(),writes=[],drawn=[];
  config.presets[0]={id:1,name:'Road',configured:true,pedal_sensitivity:31,dynamic_assist:26};store.save(config);
  const graphics={};for(const name of ['setColor','setFont','setFontAlign','drawRect','fillRect','drawLine','setPixel','flip'])graphics[name]=()=>graphics;
  graphics.clear=()=>{drawn.length=0;return graphics;};graphics.drawString=text=>{drawn.push(String(text));return graphics;};
  let now=0;const app=env.context.require('sw-app').create({store,clock:{now:()=>now},battery:()=>({percent:50,charging:false}),command_output:row=>writes.push(row),present:state=>env.context.require('sw-render').draw(graphics,state)});
  const session=app.action('session_start').session;app.action('connected',{session});app.receive(session,settingsFrame());
  return{app,writes,drawn,time:time=>{now=time;},at:time=>{now=time;app.tick();},receive:assist=>app.receive(app.view().session,settingsFrame(assist)),result:(row,success)=>app.action('command_result',{attempt:row.attempt,index:row.index,session:row.session,success,error:success?'':'controlled rejection'})};
}
function runtime(){
  const env=environment(),context=env.context,radio=context.NRF,serialEvents=new Map(),radioEvents=new Map(),writes=[],operations=[];
  let peripheral=false,refuse=false,disconnectBlocked=false,consoleDevice='Bluetooth',now=0;
  context.E.CRC32=crc32;context.E.getConsole=()=>consoleDevice;context.E.setConsole=device=>{consoleDevice=device;};
  context.btoa=text=>Buffer.from(text,'latin1').toString('base64');context.atob=text=>Buffer.from(text,'base64').toString('latin1');
  const originalRequire=context.require;context.require=name=>name==='crypto'?{SHA256:text=>Uint8Array.from(crypto.createHash('sha256').update(Buffer.from(text,'latin1')).digest()).buffer}:originalRequire(name);
  context.LoopbackA={setConsole:force=>{assert.equal(force,true);consoleDevice='LoopbackA';operations.push('console LoopbackA');}};
  context.Bluetooth={on:(name,callback)=>serialEvents.set(name,callback),removeListener:(name,callback)=>{if(serialEvents.get(name)===callback)serialEvents.delete(name);},
    setConsole:()=>{consoleDevice='Bluetooth';},write:text=>{assert.ok(text.length<=20);if(refuse)return false;writes.push(text);operations.push('write '+text);}};
  radio.on=(name,callback)=>radioEvents.set(name,callback);radio.removeListener=(name,callback)=>{if(radioEvents.get(name)===callback)radioEvents.delete(name);};
  radio.getSecurityStatus=()=>({connected:peripheral});
  radio.sleep=()=>{operations.push('peripheral sleep');if(peripheral&&!disconnectBlocked){peripheral=false;radioEvents.get('disconnect')?.();}};
  radio.wake=()=>operations.push('peripheral wake');radio.setServices=()=>{assert.equal(peripheral,false);operations.push('NUS services');};
  radio.setAdvertising=(_data,options)=>operations.push('advertise '+options.name);
  return{env,context,operations,writes,now:()=>now,console:()=>consoleDevice,refuse:value=>refuse=value,blockDisconnect:value=>disconnectBlocked=value,
    advance:milliseconds=>{now+=milliseconds;env.advance(now);},
    connect:()=>{peripheral=true;radioEvents.get('connect')?.();},disconnect:()=>{peripheral=false;radioEvents.get('disconnect')?.();},
    data:text=>{assert.equal(consoleDevice,'LoopbackA','protocol bytes cannot reach the REPL');serialEvents.get('data')(text);},
    drain:()=>{for(let count=0;count<80;count++)env.advance(now+=50);},
    exchange:row=>{const offset=writes.length,text=JSON.stringify({protocol:1,...row})+'\n';for(let index=0;index<text.length;index+=7){assert.equal(consoleDevice,'LoopbackA');serialEvents.get('data')(text.slice(index,index+7));}for(let count=0;count<40;count++)env.advance(now+=50);return JSON.parse(writes.slice(offset).join(''));}
  };
}
exports.runtime=runtime;
if(process.argv.includes('--bridge')){
  const {environment}=require('./transfer.cjs'),env=environment(),endpoint=env.endpoint(env.store());let retained='';
  process.stdin.on('data',bytes=>{retained+=bytes.toString('latin1');let index;while((index=retained.indexOf('\n'))>=0){const row=retained.slice(0,index+1);retained=retained.slice(index+1);process.stdout.write(Buffer.from(endpoint.exchange(row),'latin1'));}});
}else if(require.main===module)(async()=>{
  const observations=[];
  function observe(name,expected,observed){assert.deepEqual(observed,expected);observations.push({name,expected,observed});}
  const test=runtime(),running=test.env.start();test.advance(200);
  test.env.touch(0,120,10);test.env.touch(1,120,90);test.env.touch(5,120,202);test.advance(100);
  assert.equal(running.core.view().mode,'transfer','actual Settings transfer tap ends the wheel session');
  assert.equal(running.transfer.status().phase,'ready');assert.equal(test.console(),'LoopbackA');test.connect();
  observe('Explicit Settings entry switches the console and ends riding',{mode:'transfer',phase:'ready',console:'LoopbackA',fresh:false},{mode:running.core.view().mode,phase:running.transfer.status().phase,console:test.console(),fresh:running.core.view().fresh});
  const read=test.exchange({op:'read'});assert.equal(read.ok,true);assert.equal(read.revision,0);
  test.data('{"protocol":1,"op":"read"}\n{"protocol":1,"op":"read_chunk","index":0}\n');test.drain();
  assert.equal(running.transfer.status().retained_line_bytes,0);
  const finish=test.exchange({op:'finish'});assert.equal(finish.returned,true);
  assert.equal(running.core.view().mode,'watch');assert.equal(running.core.view().fresh,false);assert.equal(test.env.connectCalls(),0);
  assert.equal(test.console(),'Bluetooth');assert.equal(running.transfer.status().active,false);
  observe('Acknowledged finish returns without historic telemetry',{returned:true,mode:'watch',fresh:false,active:false},{returned:finish.returned,mode:running.core.view().mode,fresh:running.core.view().fresh,active:running.transfer.status().active});
  assert.ok(test.operations.indexOf('NUS services')>test.operations.indexOf('peripheral sleep'));
  running.stop();await flush();
  const delayed=runtime(),delayedApp=delayed.env.start();delayedApp.transport.discover();delayedApp.transport.select('11:22:33:44:55:66 public');await flush();
  delayed.env.notification(settingsFrame());const oldSession=delayedApp.core.view().session;delayed.env.disconnectDelay(500);
  delayedApp.core.action('swipe',{direction:'down',from_top:true});delayedApp.transfer.begin();delayed.advance(200);
  assert.equal(delayedApp.core.view().mode,'transfer');assert.equal(delayedApp.core.view().fresh,false);
  assert.equal(delayed.operations.includes('NUS services'),false,'peripheral transfer service waits for confirmed central cleanup');
  observe('Delayed wheel cleanup blocks peripheral advertising',false,delayed.operations.includes('NUS services'));
  delayed.env.notification(settingsFrame());assert.equal(delayedApp.core.view().fresh,false,'late old-session telemetry cannot reenable wheel controls');
  delayed.advance(400);await flush();delayed.advance(50);assert.equal(delayedApp.transfer.status().phase,'ready');
  delayed.connect();delayed.blockDisconnect(true);assert.equal(delayed.exchange({op:'finish'}).returned,true);
  assert.equal(delayedApp.core.view().mode,'transfer','a sent ACK cannot bypass an active peripheral connection');assert.equal(delayed.env.connectCalls(),1);
  observe('Finish waits for confirmed laptop disconnection',{mode:'transfer',wheel_connections:1},{mode:delayedApp.core.view().mode,wheel_connections:delayed.env.connectCalls()});
  delayed.advance(4000);assert.match(delayedApp.transfer.status().error,/disconnect not confirmed/);assert.equal(delayed.env.connectCalls(),1);
  delayed.blockDisconnect(false);delayedApp.transfer.returnToRiding();await flush();assert.equal(delayedApp.core.view().mode,'watch');assert.equal(delayed.env.connectCalls(),2);
  assert.ok(delayedApp.core.view().session>oldSession);assert.equal(delayedApp.core.view().fresh,false,'return/reconnect never restores historical telemetry');delayedApp.stop();
  const refused=runtime(),refusedApp=refused.env.start();refusedApp.core.action('swipe',{direction:'down',from_top:true});refusedApp.transfer.begin();refused.advance(50);refused.connect();refused.refuse(true);
  refused.data('{"protocol":1,"op":"finish"}\n');refused.advance(3500);
  assert.equal(refusedApp.core.view().mode,'transfer','refused finish acknowledgement cannot cause automatic return');assert.match(refusedApp.transfer.status().error,/output refused/);
  observe('Refused output preserves explicit reconciliation/Return',{mode:'transfer',returning:false},{mode:refusedApp.core.view().mode,returning:refusedApp.transfer.status().returning});
  refused.refuse(false);refused.disconnect();refused.connect();assert.equal(refused.exchange({op:'read'}).revision,0,'reconnection can explicitly resolve saved content');refusedApp.transfer.returnToRiding();refusedApp.stop();
  const bounded=runtime(),boundedApp=bounded.env.start();boundedApp.core.action('swipe',{direction:'down',from_top:true});boundedApp.transfer.begin();bounded.advance(50);bounded.connect();
  const offset=bounded.writes.length;bounded.data('x'.repeat(700)+'\n');bounded.drain();assert.equal(JSON.parse(bounded.writes.slice(offset).join('')).ok,false);assert.equal(boundedApp.transfer.status().retained_line_bytes,0);
  assert.equal(bounded.exchange({op:'read'}).revision,0,'oversized lines do not poison the next complete request');
  const info=bounded.exchange({op:'read'});assert.equal(bounded.exchange({op:'stage',size:20,expected_revision:0,expected_digest:info.digest,digest:'0'.repeat(64)}).ok,true);
  bounded.advance(31000);assert.equal(boundedApp.transfer.status().staging,false);assert.equal(boundedApp.core.view().awake,true,'active transfer remains outside the initial-idle sleep rule');
  observe('Expired staging preserves awake transfer mode',{staging:false,awake:true},{staging:boundedApp.transfer.status().staging,awake:boundedApp.core.view().awake});
  bounded.env.button(true);bounded.advance(30100);assert.equal(bounded.context.resets,1);assert.equal(boundedApp.transfer.status().active,false,'independent recovery closes the transfer endpoint');
  bounded.env.boot();assert.equal(bounded.console(),'Bluetooth','independent recovery restores its console after a transfer reset');
  observe('Long hold closes transfer and restores independent recovery console',{active:false,resets:1,console:'Bluetooth'},{active:boundedApp.transfer.status().active,resets:bounded.context.resets,console:bounded.console()});
  const pending=coreScenario();pending.app.action('preset_apply',{slot:1});assert.equal(pending.app.view().preset_attempt.pending,true);
  pending.app.action('swipe',{direction:'down',from_top:true});pending.app.action('transfer_begin');assert.equal(pending.app.view().preset_attempt.pending,false);assert.equal(pending.app.view().confirmed_preset,null);
  pending.result(pending.writes[0],true);pending.app.action('button_down');assert.equal(pending.writes.length,1,'transfer invalidates pending preset callbacks and cannot submit horn');
  assert.match(pending.app.view().horn_feedback.message,/configuration transfer/);
  observe('Pending preset invalidation and horn block during transfer',{pending:false,confirmed:null,commands:1},{pending:pending.app.view().preset_attempt.pending,confirmed:pending.app.view().confirmed_preset,commands:pending.writes.length});
  const painting=coreScenario();painting.app.action('preset_apply',{slot:1});painting.result(painting.writes[0],true);painting.result(painting.writes[1],false);painting.app.action('swipe',{direction:'left'});
  painting.time(.7);painting.receive(26);const paints=painting.app.view().diagnostics.display_frames;
  painting.time(.95);painting.receive(27);assert.ok(painting.app.view().diagnostics.display_frames>paints,'fresh actual settings changes repaint terminal preset results at the scheduled cadence');
  assert.ok(painting.drawn.some(text=>text.includes('now 27')),'production renderer updates the displayed current settings');
  observe('Fresh current values repaint terminal results',true,painting.drawn.some(text=>text.includes('now 27')));
  for(const screen of ['settings','alerts','threshold','connection']){
    const horn=coreScenario();horn.app.action('swipe',{direction:'down',from_top:true});
    if(screen==='alerts'||screen==='threshold')horn.app.action('alerts_begin');
    if(screen==='threshold')horn.app.action('threshold_begin',{alert:'pwm'});
    if(screen==='connection')horn.app.action('open_connection');
    horn.app.action('button_down');const request=horn.writes[0];horn.app.action('horn_result',{request:request.request,session:request.session,success:true});horn.at(.25);
    assert.equal(horn.app.view().screen,screen);assert.ok(horn.drawn.includes('Horn request sent'),`${screen} displays brief horn request feedback`);
    observe('Horn feedback on '+screen,true,horn.drawn.includes('Horn request sent'));
  }
  const source_fingerprints={};for(const file of ['app.js','boot.js','configuration.js','controls.js','main.js','render.js','store.js','transfer.js','tests/transfer.cjs','tests/transfer-wire.cjs'])source_fingerprints['watch/'+file]=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex');
  fs.writeFileSync(path.join(root,'evidence/transfer.json'),JSON.stringify({issue:35,provenance:'Production original ES5 watch App/main/Storage/UART adapters executed in Node VM; controlled pins/clock/radio; 2v14 JSON high-byte escaping modeled in endpoint tests; sanitized WheelLog fixture supplies CRC-valid protocol shape',fixture:'experiments/laptop-feasibility/evidence/fixture-recording.jsonl',source_fingerprints,observations,hardware_acceptance:'Pending installed-runtime API/memory checks, real BLE role transitions, flash interruptions and physical controls; no deployment or hardware operations'},null,2)+'\n');
  console.log('actual watch entry, raw Nordic UART fragments and acknowledged return: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
