// Test support for the watch suites: one fake Espruino 2v14 device. Not a suite; check.sh never runs it.
//
//   const harness=require('./harness.cjs');
//   const env=harness.environment();        // one fake device: pins, NRF, Storage, Graphics, timers, clock
//   const app=env.require('sw-app').create({clock:{now:env.context.getTime},battery:()=>({percent:50})});
//   env.require('sw-main')                   // cached per environment, as Espruino's require is
//   env.start()                              // production main with the fake radio and timers
//   env.advance(ms)                          // run due timers in order, then set the clock to ms
//   env.setTime(ms)                          // set the clock only; the next advance runs what is due
//   env.touch(gesture,x,y) env.button(down) env.notification(bytes) env.loss()
//   await harness.flush()                    // settle pending promise chains
//   harness.frame({voltage,speed,pwm,firmware,length,settings})  // CRC-valid frame from the fixture
//   harness.fixture.rows                     // parsed fixture-recording.jsonl
//   harness.evidence.json(path,value)        // writes only when EUCWATCH_WRITE_EVIDENCE=1
//   harness.laptopTrace('touch-layout/x.json')  // where the laptop browser flows' trace is, for parity replays
//   harness.alertEditor(alerts,reason)       // the alert editor module alone: {config,editor,act,view}
//   harness.drawnText(env,state)             // the renderer's text for state, on a fresh Graphics buffer of env
//   harness.fakeTransport()                  // a core transport adapter: {adapter,calls,refusals,status,link}
//   harness.replayAlertEditorTrace(path)     // replay a shared alert editor key-sequence trace, asserting every step
//
// Paths given to the harness are relative to the repository root, never to the current directory.
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),zlib=require('node:zlib');
const watch=path.resolve(__dirname,'..'),repo=path.resolve(watch,'..');
const repoPath=(...parts)=>path.join(repo,...parts);
const readJson=relative=>JSON.parse(fs.readFileSync(repoPath(relative)));
const plain=value=>JSON.parse(JSON.stringify(value));

// One fake device. Each environment has its own module cache, Storage, pins, radio, timers and clock.
function environment(){
  let now=0,next=1,voltage=3.85,adc=0,disconnectFails=false,disconnectDelay=0,subscribeFails=false,scanHangs=false,connectFailures=0,connectCalls=0,failedStorageKey=null,partialStorage=false;
  const pending=new Map(),watches=new Map(),pins={},writes=[],registers=[],commands=[],bleWrites=[],storageEffects=[];
  let writeFailure=-1,writeHangs=false,settleWrite=null,server=null,characteristic=null;
  const context={module:{exports:{}},Uint8Array,Uint16Array,ArrayBuffer,Promise,Math,JSON,isFinite,
    print:()=>{},reset:()=>{context.resets++;},resets:0,global:{},
    getTime:()=>now/1000,process:{env:{VERSION:'2v14'},memory:()=>({free:4096,usage:100,simulated:true})},
    atob:encoded=>Buffer.from(encoded,'base64').toString('binary'),
    analogRead:()=>{adc++;return voltage/7.1;},digitalRead:pin=>pin.state,
    poke32:(address,value)=>registers.push([address,value]),
    digitalWrite:(pin,value)=>writes.push([pin,value]),digitalPulse:(...args)=>writes.push(args),
    setWatch:(callback,pin,options)=>{const id=next++;watches.set(id,{callback,pin,options});return id;},
    clearWatch:id=>watches.delete(id),
    setTimeout:(fn,delay)=>{const id=next++;pending.set(id,{fn,at:now+delay,period:0});return id;},
    clearTimeout:id=>{assert.notEqual(id,undefined,'clearTimeout(undefined) clears all Espruino timers');pending.delete(id);},
    setInterval:(fn,delay)=>{const id=next++;pending.set(id,{fn,at:now+delay,period:delay});return id;},
    clearInterval:id=>pending.delete(id)
  };
  for(let id=0;id<32;id++)pins['D'+id]=context['D'+id]={state:0,write(value){this.state=value;},read(){return this.state;},set(){this.state=1;},reset(){this.state=0;},valueOf(){return id;}};
  context.BTN1={...pins.D0};
  context.E={nativeCall:offset=>(...args)=>{commands.push([offset,...args]);return 0;},getAddressOf:()=>100,
    toString:arr=>String.fromCharCode(...arr),toArrayBuffer:value=>Uint8Array.from(value,c=>c.charCodeAt(0)),
    enableWatchdog:(...args)=>{context.watchdog=args;},kickWatchdog:()=>{context.kicks=(context.kicks||0)+1;}};
  context.i2cWrites=[];context.touchBytes=new Uint8Array(7);
  context.I2C=function(){this.setup=options=>{context.i2cOptions=options;};this.writeTo=(...args)=>context.i2cWrites.push(args);this.readFrom=()=>context.touchBytes;};
  context.Graphics={createArrayBuffer:(width,height,bpp)=>{
    assert.deepEqual([width,height,bpp],[240,240,1]);
    const g={buffer:new ArrayBuffer(7200),ops:[],font:12,color:1,align:0,
      getWidth:()=>240,getHeight:()=>240,getModified:()=>({x1:0,y1:0,x2:239,y2:239}),
      clear(){new Uint8Array(this.buffer).fill(0);this.ops=[];return this;},
      flip(){return this;},
      setColor(value){this.color=value;return this;},setRotation(){return this;},
      setFont(name,size){this.font=size;return this;},setFontAlign(value){this.align=value;return this;},
      // Synthetic variable-width glyph metrics at the native Graphics boundary.
      stringWidth(value){return Array.from(String(value)).reduce((width,character)=>width+(character==='W'?1:character==='i'?.25:.55)*this.font,0);},
      setPixel(x,y,value){const n=y*240+x;const bytes=new Uint8Array(this.buffer);if(value)bytes[n>>3]|=1<<(n&7);else bytes[n>>3]&=~(1<<(n&7));return this;},
      drawString(value,x,y){this.ops.push({kind:'text',value,x,y,size:this.font,align:this.align,width:this.stringWidth(value)});return this;},
      drawRect(x1,y1,x2,y2){this.ops.push({kind:'rect',x1,y1,x2,y2});return this;},
      fillRect(x1,y1,x2,y2){this.ops.push({kind:'fill',x1,y1,x2,y2});return this;},
      drawLine(x1,y1,x2,y2){this.ops.push({kind:'line',x1,y1,x2,y2});return this;}};
    context.graphics=g;return g;
  }};
  const storage={};context.storage=storage;
  const modules={};context.imports=[];
  // Espruino's require: native Storage, then a cached module from Storage or watch/<name>.js.
  // The sandbox is built when a module is first required, so context overrides made before then apply.
  context.require=name=>{
    context.imports.push(name);
    if(name==='Storage')return{
      read:key=>storage[key],readJSON:key=>storage[key]?JSON.parse(storage[key]):undefined,
      write:(key,value)=>{
        storageEffects.push({key,value,failed:key===failedStorageKey});
        if(key===failedStorageKey){
          if(partialStorage)storage[key]=typeof partialStorage==='string'?partialStorage:'{"partial"';
          return typeof partialStorage==='string'?undefined:false;
        }
        storage[key]=value;
      },
      erase:key=>{storageEffects.push({key,erased:true});return delete storage[key];}
    };
    if(modules[name])return modules[name];
    const module={exports:{}};const sandbox={...context,module,exports:module.exports};
    const stored=Object.prototype.hasOwnProperty.call(storage,name);
    const filename=stored?name:path.join(watch,name.replace(/^sw-/,'')+'.js');
    const content=stored?storage[name]:fs.readFileSync(filename,'utf8');
    vm.runInNewContext(content,sandbox,{filename});
    modules[name]=module.exports;return module.exports;
  };
  const timers={setTimeout:context.setTimeout,clearTimeout:context.clearTimeout};
  const callbacks={};let notification;
  context.NRF={setServices:()=>{},setAdvertising:()=>{},findDevices:(callback)=>{if(!scanHangs)callback([{id:'11:22:33:44:55:66 public',name:'Sherman L'}]);},
    connect:()=>{connectCalls++;if(connectFailures>0){connectFailures--;return Promise.reject(Error('wheel unavailable'));}server={device:{connected:true,on:(name,callback)=>callbacks[name]=callback},
      disconnect(){if(disconnectFails)throw Error('radio cleanup failure');const device=this.device;return new Promise(resolve=>{context.setTimeout(()=>{device.connected=false;resolve();},disconnectDelay);});},getPrimaryService:uuid=>{assert.equal(uuid,'ffe0');return Promise.resolve({getCharacteristic:uuid=>{
        assert.equal(uuid,'ffe1');characteristic={properties:{notify:true,writeWithoutResponse:true},writeValue:bytes=>{bleWrites.push(Buffer.from(bytes).toString('hex'));if(bleWrites.length===writeFailure)return Promise.reject(Error('Controlled partial write failure'));return writeHangs?new Promise(resolve=>{settleWrite=resolve;}):Promise.resolve();},on:(name,callback)=>{assert.equal(name,'characteristicvaluechanged');notification=callback;},startNotifications:()=>subscribeFails?Promise.reject(Error('notification subscription failed')):Promise.resolve()};return Promise.resolve(characteristic);
      }});}};return Promise.resolve(server);}};
  return {context,timers,watches,registers,commands,bleWrites,storageEffects,
    require:context.require,
    server:()=>server,characteristic:()=>characteristic,
    writeFailure:count=>{writeFailure=count;},writeHang:value=>{writeHangs=value;},settleWrite:()=>{if(settleWrite)settleWrite();},
    start:(options={})=>context.require('sw-main').start({clock:{now:context.getTime},radio:context.NRF,timers,...options}),
    voltage:value=>{voltage=value;},adc:()=>adc,
    disconnectFailure:value=>{disconnectFails=value;},
    disconnectDelay:value=>{disconnectDelay=value;},subscriptionFailure:value=>{subscribeFails=value;},scanHang:value=>{scanHangs=value;},
    connectFailureCount:value=>{connectFailures=value;},connectCalls:()=>connectCalls,
    storageFailure:(key,partial=false)=>{failedStorageKey=key;partialStorage=partial;},
    // Move the clock without running timers, so a step's inputs arrive before timers due at that instant.
    setTime:time=>{now=time;},
    advance:time=>{while(true){const entry=[...pending].sort((a,b)=>a[1].at-b[1].at)[0];if(!entry||entry[1].at>time)break;now=entry[1].at;if(entry[1].period)entry[1].at+=entry[1].period;else pending.delete(entry[0]);entry[1].fn();}now=time;},
    button:down=>[...watches.values()].find(w=>w.pin===context.BTN1).callback({state:down}),
    touch:(gesture,x,y,fingers=1)=>{context.touchBytes=Uint8Array.from([0,gesture,fingers,x>>8,x&255,y>>8,y&255]);[...watches.values()].find(w=>w.pin===pins.D28).callback();},
    notification:bytes=>notification({target:{value:new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength)}}),
    loss:()=>callbacks.gattserverdisconnected(),
    boot:name=>vm.runInNewContext(name?storage[name]:fs.readFileSync(path.join(watch,'boot.js'),'utf8'),context)
  };
}
const flush=async(rounds=12)=>{for(let i=0;i<rounds;i++)await Promise.resolve();};

// A recorded laptop pointer event, replayed through the CST816 touch interrupt.
function dispatchRecordedInput(env,event){
  if(event.input==='storage_failure')env.storageFailure(event.mode==='refuse'?'sw-config-stage.json':null);
  else if(event.input==='tap')env.touch(5,...event.end);
  else if(event.input==='swipe'){
    const [x,y]=event.start,[ex,ey]=event.end;
    env.touch(0,x,y);env.touch(Math.abs(ex-x)>Math.abs(ey-y)?ex>x?4:3:ey>y?1:2,ex,ey);
  }else throw Error('Unknown trace input '+event.input);
}

// Sanitized Sherman L recording; its first five notifications form one 87-byte frame.
const fixturePath='experiments/laptop-feasibility/evidence/fixture-recording.jsonl';
const rows=fs.readFileSync(repoPath(fixturePath),'utf8').trim().split('\n').map(JSON.parse);
const source=Buffer.concat(rows.slice(0,5).map(row=>Buffer.from(row.raw_hex,'hex')));
const fixture={path:fixturePath,rows,source};
const settingBytes=[['pedal_sensitivity',50],['dynamic_assist',66],['pedal_dip_compensation',68]];
// The fixture frame with only the given fields rewritten, then a fresh CRC32.
// length pads or truncates the body; settings selects subtype 8 (null reports 0x80, unsupported).
function frame(fields={}){
  const length=fields.length===undefined?source.length:fields.length,bytes=Buffer.alloc(length);
  source.copy(bytes,0,0,Math.min(length-4,source.length-4));bytes[3]=length-4;
  if(fields.voltage!==undefined)bytes.writeUInt16BE(Math.round(fields.voltage*100),4);
  if(fields.speed!==undefined)bytes.writeInt16BE(Math.round(fields.speed*10),6);
  if(fields.firmware!==undefined)bytes.writeUInt16BE(fields.firmware,28);
  if(fields.pwm!==undefined)bytes.writeUInt16BE(Math.round(fields.pwm*100),34);
  if(fields.settings){bytes[46]=8;for(const [name,index] of settingBytes){const value=fields.settings[name];assert.ok(value!==undefined,'frame settings need '+name);bytes[index]=value===null?128:value;}}
  bytes.writeUInt32BE(zlib.crc32(bytes.subarray(0,length-4)),length-4);return bytes;
}

// Graphics operations as SVG. Two historical evidence formats are kept byte for byte:
// 'regression' (watch/evidence/local-presets) has a viewBox and escapes & and <;
// 'touch-layout' (watch/evidence/touch-layout) has no viewBox and also escapes >.
function svg(ops,style){
  assert.ok(style==='regression'||style==='touch-layout','unknown SVG style '+style);
  const escape=style==='touch-layout'?value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'):value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;');
  const body=ops.map(op=>op.kind==='text'?`<text x="${op.x}" y="${op.y+op.size}" font-size="${op.size}" text-anchor="${op.align===-1?'start':op.align===1?'end':'middle'}">${escape(op.value)}</text>`:op.kind==='line'?`<line x1="${op.x1}" y1="${op.y1}" x2="${op.x2}" y2="${op.y2}" stroke="white"/>`:`<rect x="${op.x1}" y="${op.y1}" width="${op.x2-op.x1}" height="${op.y2-op.y1}" fill="${op.kind==='fill'?'white':'none'}" stroke="white"/>`).join('\n');
  const open=style==='touch-layout'?'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">':'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">';
  return `${open}<rect width="240" height="240" fill="black"/><g fill="white" font-family="sans-serif">${body}</g></svg>\n`;
}

// Tracked evidence is rewritten only on request, so a plain run leaves git status unchanged.
const evidence={
  enabled:()=>process.env.EUCWATCH_WRITE_EVIDENCE==='1',
  text(relative,content){if(!evidence.enabled())return;const file=repoPath(relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,content);},
  json(relative,value){evidence.text(relative,JSON.stringify(value,null,2)+'\n');},
  svg(relative,ops,style){evidence.text(relative,svg(ops,style));}
};
// Where a laptop browser flow's trace docs/acceptance/evidence/<relative> is. It mirrors
// tests/support.py:evidence_directory(): an EUCWATCH_BROWSER_CHECKS=1 run without
// EUCWATCH_WRITE_EVIDENCE=1 has just written it to .test-output/evidence/ (check.sh runs the
// flows before the suites), so a parity suite replays the laptop's current behavior. Any other
// run, such as a plain check.sh or a suite run on its own, replays the tracked trace;
// `EUCWATCH_BROWSER_CHECKS=1 node watch/tests/<suite>.cjs` replays what the last flow run wrote.
function laptopTrace(relative){
  const fresh=process.env.EUCWATCH_BROWSER_CHECKS==='1'&&!evidence.enabled();
  return (fresh?'.test-output/evidence/':'docs/acceptance/evidence/')+relative;
}
// The device's current screen as touch-layout evidence; returns the plain Graphics operations.
function snapshot(env,name){const ops=plain(env.context.graphics.ops);evidence.svg('watch/evidence/touch-layout/'+name+'.svg',ops,'touch-layout');return ops;}

// The alert editor module alone, with no clock, battery, wheel session or store, holding a draft of alerts (the defaults
// when none). reason is the optional {get,set} the core would share. act(name,payload) returns the plain outcome.
function alertEditor(alerts,reason){
  const env=environment(),config=env.require('sw-configuration').defaults(),editor=env.require('sw-alert-editor').create(reason);
  if(alerts)config.alerts=plain(alerts);editor.open(config.alerts);
  const act=(name,payload={})=>plain(editor.action(name,plain(payload),config));
  return {config,editor,act,view:()=>plain(editor.view())};
}
// The renderer's text, drawn on a fresh Graphics buffer of the scenario's device.
function drawnText(env,state){const g=env.context.Graphics.createArrayBuffer(240,240,1);env.require('sw-render').draw(g,plain(state));return g.ops.filter(op=>op.kind==='text').map(op=>op.value);}
// The core's transport adapter without a radio. It records every request in calls, refuses a request whose name has a
// reason in refusals (throwing it, as the real transport does), and reports status. An accepted discover or select
// changes status as the real one does; after link(app) it also reports to that core from inside the request (devices
// on discovery, session_start on selection), as the real transport does.
function fakeTransport(){
  const calls=[],refusals={},status={link:'idle',active:false,connected:false,busy:false};let app=null;
  const ask=(name,...args)=>{calls.push([name,...args]);if(refusals[name])throw new Error(refusals[name]);};
  return {calls,refusals,status,link:value=>{app=value;},adapter:{
    discover:()=>{ask('discover');status.link='discovering';if(app)app.action('devices',{devices:[]});},
    select:id=>{ask('select',id);status.link='connecting';status.active=true;if(app)app.action('session_start');},
    disconnect:()=>ask('disconnect'),status:()=>({...status})}};
}
// A watch error or reason as the laptop words it: without Espruino's leading "Error: ".
const message=value=>value&&String(value).replace(/^Error: /,'');
// Replay a shared alert editor trace (tests/test_alert_editor.py replays the same file through the laptop editor):
// after every step the page, entry, draft, refusal and reason must be the expected ones, and Save's replacement too.
// Save only returns the replacement, so the configuration the editor was given stays at revision 0. Returns the trace.
function replayAlertEditorTrace(relative){
  const trace=readJson(relative),{config,act,view}=alertEditor(trace.alerts);
  trace.steps.forEach((step,index)=>{
    let refused=null,result=null;
    try{result=act(step.action,step.payload);}catch(error){refused=message(error.message);}
    const state=view(),observed={page:state.page,entry:state.entry,draft:state.draft,refused,reason:message(state.reason)};
    if(result&&result.save)observed.saved={revision:result.save.revision,alerts:result.save.alerts};
    assert.deepEqual(observed,step.expect,`step ${index}: ${JSON.stringify(step)}`);
  });
  assert.equal(config.revision,0,'Save returns a replacement and leaves the saved configuration alone');
  return trace;
}

const sha256=relative=>crypto.createHash('sha256').update(fs.readFileSync(repoPath(relative))).digest('hex');
const sourceHashes=files=>Object.fromEntries(files.map(file=>[file,sha256(file)]));
// Every production module, in directory order, as the evidence files have always listed them.
const watchSourceHashes=()=>sourceHashes(fs.readdirSync(watch).filter(name=>name.endsWith('.js')).map(name=>'watch/'+name));
// The laptop interpreter for the differential suites.
const python=()=>process.env.EUCWATCH_TEST_PYTHON||repoPath('experiments/laptop-feasibility/.venv/bin/python');

module.exports={environment,flush,dispatchRecordedInput,fixture,frame,svg,evidence,laptopTrace,snapshot,alertEditor,drawnText,fakeTransport,message,replayAlertEditorTrace,plain,repo,repoPath,readJson,sha256,sourceHashes,watchSourceHashes,python};
