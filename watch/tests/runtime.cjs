// Execute original main + actual hardware/native-driver modules with fake pins/radio.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
function environment(){
  let now=0,next=1,voltage=3.85,adc=0,disconnectFails=false,disconnectDelay=0,subscribeFails=false,scanHangs=false,connectFailures=0,connectCalls=0,failedStorageKey=null,partialStorage=false;
  const pending=new Map(),watches=new Map(),pins={},writes=[],registers=[],commands=[];
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
      setColor(value){this.color=value;return this;},setRotation(){return this;},
      setFont(name,size){this.font=size;return this;},setFontAlign(value){this.align=value;return this;},
      setPixel(x,y,value){const n=y*240+x;const bytes=new Uint8Array(this.buffer);if(value)bytes[n>>3]|=1<<(n&7);else bytes[n>>3]&=~(1<<(n&7));return this;},
      drawString(value,x,y){this.ops.push({kind:'text',value,x,y,size:this.font,align:this.align});return this;},
      drawRect(x1,y1,x2,y2){this.ops.push({kind:'rect',x1,y1,x2,y2});return this;},
      fillRect(x1,y1,x2,y2){this.ops.push({kind:'fill',x1,y1,x2,y2});return this;},
      drawLine(x1,y1,x2,y2){this.ops.push({kind:'line',x1,y1,x2,y2});return this;}};
    context.graphics=g;return g;
  }};
  const storage={};context.storage=storage;
  const modules={};context.imports=[];
  context.require=name=>{
    context.imports.push(name);
    if(name==='Storage')return{read:key=>storage[key],readJSON:key=>storage[key]?JSON.parse(storage[key]):undefined,write:(key,value)=>{if(key===failedStorageKey){if(partialStorage)storage[key]='{"partial"';return false;}storage[key]=value;},erase:key=>delete storage[key]};
    if(modules[name])return modules[name];
    const module={exports:{}};const sandbox={...context,module,exports:module.exports};
    vm.runInNewContext(fs.readFileSync(path.join(root,name.replace(/^sw-/,'')+'.js'),'utf8'),sandbox);
    modules[name]=module.exports;return module.exports;
  };
  const timers={setTimeout:context.setTimeout,clearTimeout:context.clearTimeout};
  const callbacks={};let notification;
  context.NRF={setServices:()=>{},setAdvertising:()=>{},findDevices:(callback)=>{if(!scanHangs)callback([{id:'11:22:33:44:55:66 public',name:'Sherman L'}]);},
    connect:()=>{connectCalls++;if(connectFailures>0){connectFailures--;return Promise.reject(Error('wheel unavailable'));}return Promise.resolve({device:{connected:true,on:(name,callback)=>callbacks[name]=callback},
      disconnect(){if(disconnectFails)throw Error('radio cleanup failure');const device=this.device;return new Promise(resolve=>{context.setTimeout(()=>{device.connected=false;resolve();},disconnectDelay);});},getPrimaryService:uuid=>{assert.equal(uuid,'ffe0');return Promise.resolve({getCharacteristic:uuid=>{
        assert.equal(uuid,'ffe1');return Promise.resolve({on:(name,callback)=>{assert.equal(name,'characteristicvaluechanged');notification=callback;},startNotifications:()=>subscribeFails?Promise.reject(Error('notification subscription failed')):Promise.resolve()});
      }});}});}};
  return {context,timers,watches,registers,commands,
    start:(options={})=>context.require('sw-main').start({clock:{now:context.getTime},radio:context.NRF,timers,...options}),
    voltage:value=>{voltage=value;},adc:()=>adc,
    disconnectFailure:value=>{disconnectFails=value;},
    disconnectDelay:value=>{disconnectDelay=value;},subscriptionFailure:value=>{subscribeFails=value;},scanHang:value=>{scanHangs=value;},
    connectFailureCount:value=>{connectFailures=value;},connectCalls:()=>connectCalls,
    storageFailure:(key,partial=false)=>{failedStorageKey=key;partialStorage=partial;},
    advance:time=>{while(true){const entry=[...pending].sort((a,b)=>a[1].at-b[1].at)[0];if(!entry||entry[1].at>time)break;now=entry[1].at;if(entry[1].period)entry[1].at+=entry[1].period;else pending.delete(entry[0]);entry[1].fn();}now=time;},
    button:down=>[...watches.values()].find(w=>w.pin===context.BTN1).callback({state:down}),
    touch:(gesture,x,y,fingers=1)=>{context.touchBytes=Uint8Array.from([0,gesture,fingers,x>>8,x&255,y>>8,y&255]);[...watches.values()].find(w=>w.pin===pins.D28).callback();},
    notification:bytes=>notification({target:{value:new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength)}}),
    loss:()=>callbacks.gattserverdisconnected(),
    boot:()=>vm.runInNewContext(fs.readFileSync(path.join(root,'boot.js'),'utf8'),context)
  };
}
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
exports.environment=environment;exports.flush=flush;
if(require.main===module)(async()=>{
  const env=environment(),running=env.start();env.advance(200);
  assert.equal(env.context.D16.state,0,'installed active-high vibration must remain inactive at startup');
  assert.equal(env.context.graphics.buffer.byteLength,7200);
  assert.equal(running.core.view().dashboard.watch_battery_percent,'50');
  assert.deepEqual(env.registers[0],[0x50000700+31*4,2]);
  assert.equal([...env.watches.values()].find(w=>w.pin===env.context.D19).options.debounce,500);
  for(const [voltage,percent] of [[3.4,0],[3.5,0],[3.85,50],[4.19,100],[4.3,100]]){
    env.voltage(voltage);running.core.action('battery_refresh');assert.equal(running.core.view().watch_battery.percent,percent);
  }
  const before=env.adc();env.advance(30200);assert.ok(env.adc()>before);assert.equal(running.core.view().awake,false);
  env.button(true);env.advance(30500);assert.equal(running.core.view().feedback,'Wake only');
  env.button(false);assert.equal(running.core.view().button.wake_cycle,false);
  env.touch(0,120,10);env.touch(1,120,90);assert.equal(running.core.view().screen,'settings');
  env.touch(5,120,100);assert.equal(running.core.view().awake,false);
  assert.ok(env.context.i2cWrites.some(row=>row[1]===0xE5&&row[2]===3));
  env.button(true);env.button(false);env.advance(30900);
  env.touch(5,120,40);assert.equal(running.core.view().screen,'connection');
  env.advance(31200);env.touch(5,120,55);await flush();
  assert.equal(running.transport.status().link,'subscribed');assert.equal(running.core.view().fresh,false);
  const rows=fs.readFileSync(path.resolve(root,'../experiments/laptop-feasibility/evidence/fixture-recording.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  for(const row of rows.slice(0,5))env.notification(Buffer.from(row.raw_hex,'hex'));
  assert.equal(running.core.view().dashboard.wheel_battery_percent,'97');env.advance(31500);
  assert.equal(running.core.view().diagnostics.memory.simulated,true);
  const out=path.join(root,'evidence');fs.mkdirSync(out,{recursive:true});
  function escape(value){return String(value).replaceAll('&','&amp;').replaceAll('<','&lt;');}
  const svg=env.context.graphics.ops.map(op=>op.kind==='text'?`<text x="${op.x}" y="${op.y+op.size}" font-size="${op.size}" text-anchor="${op.align===-1?'start':op.align===1?'end':'middle'}">${escape(op.value)}</text>`:op.kind==='line'?`<line x1="${op.x1}" y1="${op.y1}" x2="${op.x2}" y2="${op.y2}" stroke="white"/>`:`<rect x="${op.x1}" y="${op.y1}" width="${op.x2-op.x1}" height="${op.y2-op.y1}" fill="${op.kind==='fill'?'white':'none'}" stroke="white"/>`).join('\n');
  fs.writeFileSync(path.join(out,'dashboard.svg'),`<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240"><rect width="240" height="240" fill="black"/><g fill="white" font-family="sans-serif">${svg}</g></svg>\n`);
  const old=running.core.view().session;env.loss();assert.equal(running.core.view().fresh,false);env.advance(32500);await flush();
  assert.ok(running.core.view().session>old);assert.equal(running.core.view().fresh,false);
  for(const row of rows.slice(0,5))env.notification(Buffer.from(row.raw_hex,'hex'));assert.equal(running.core.view().fresh,true);
  running.stop();
  env.advance(32700);await flush();assert.equal(env.context.graphics.isOn,false,'late disconnect cannot wake stopped hardware');
  assert.equal(env.watches.size,0);
  const failed=environment(),failedApp=failed.start();failedApp.transport.discover();failedApp.transport.select('11:22:33:44:55:66 public');await flush();
  failed.disconnectFailure(true);failedApp.transport.disconnect();
  assert.equal(failedApp.transport.status().link,'failed');
  assert.throws(()=>failedApp.transport.select('11:22:33:44:55:66 public'),/Disconnect/);
  failed.disconnectFailure(false);failedApp.transport.disconnect();failed.advance(0);await flush();assert.equal(failedApp.transport.status().link,'disconnected');
  const delayed=environment(),delayedApp=delayed.start();delayedApp.transport.discover();delayedApp.transport.select('11:22:33:44:55:66 public');await flush();
  delayed.disconnectDelay(500);delayedApp.transport.disconnect();
  assert.equal(delayedApp.transport.status().busy,true);assert.equal(delayedApp.core.view().fresh,false);
  assert.throws(()=>delayedApp.transport.select('11:22:33:44:55:66 public'),/Disconnect/);
  delayed.advance(500);await flush();assert.equal(delayedApp.transport.status().link,'disconnected');assert.equal(delayedApp.transport.status().connected,false);
  const subscription=environment(),subscriptionApp=subscription.start();subscription.subscriptionFailure(true);subscription.disconnectFailure(true);
  subscriptionApp.transport.discover();subscriptionApp.transport.select('11:22:33:44:55:66 public');await flush();
  assert.equal(subscriptionApp.transport.status().link,'failed');assert.equal(subscriptionApp.core.view().connected,false);
  assert.equal(subscriptionApp.transport.status().connected,true,'failed cleanup retains transport ownership');
  assert.throws(()=>subscriptionApp.transport.select('11:22:33:44:55:66 public'),/Disconnect/);
  const scanning=environment(),scanningApp=scanning.start();scanning.scanHang(true);scanningApp.transport.discover();scanning.advance(6000);
  assert.equal(scanningApp.transport.status().link,'failed');assert.match(scanningApp.transport.status().error,/Discovery timed out/);
  const retrying=environment(),retryApp=retrying.start();retryApp.transport.discover();retryApp.transport.select('11:22:33:44:55:66 public');await flush();
  for(const row of rows.slice(0,5))retrying.notification(Buffer.from(row.raw_hex,'hex'));
  const retrySession=retryApp.core.view().session;retrying.connectFailureCount(1);retrying.loss();retrying.advance(1000);await flush();
  assert.equal(retryApp.transport.status().active,true,'a failed reconnect retains the bounded recovery intent');
  assert.equal(retryApp.transport.status().link,'reconnecting');
  retrying.advance(3000);await flush();assert.equal(retryApp.transport.status().link,'subscribed');
  assert.equal(retrying.connectCalls(),3);assert.ok(retryApp.core.view().session>retrySession);
  assert.equal(retryApp.core.view().fresh,false,'successful reconnect requires new telemetry');
  for(const row of rows.slice(0,5))retrying.notification(Buffer.from(row.raw_hex,'hex'));assert.equal(retryApp.core.view().fresh,true);
  const limited=environment(),limitedApp=limited.start();limitedApp.transport.discover();limitedApp.transport.select('11:22:33:44:55:66 public');await flush();
  limited.connectFailureCount(10);limited.loss();
  for(const elapsed of [1000,3000,7000]){limited.advance(elapsed);await flush();}
  assert.equal(limited.connectCalls(),4);assert.equal(limitedApp.transport.status().active,false);
  assert.equal(limitedApp.transport.status().link,'failed');limited.advance(20000);await flush();assert.equal(limited.connectCalls(),4);
  const initial=environment(),initialApp=initial.start();initial.connectFailureCount(1);initialApp.transport.discover();initialApp.transport.select('11:22:33:44:55:66 public');await flush();
  assert.equal(initialApp.transport.status().link,'failed');assert.equal(initialApp.transport.status().active,false);
  initial.advance(20000);await flush();assert.equal(initial.connectCalls(),1);
  const replaced=environment(),replacedApp=replaced.start();replacedApp.transport.discover();replacedApp.transport.select('11:22:33:44:55:66 public');await flush();
  replacedApp.core.action('session_start');replaced.notification(Buffer.from(rows[0].raw_hex,'hex'));replaced.advance(50);await flush();
  assert.equal(replacedApp.transport.status().active,false);assert.equal(replacedApp.transport.status().connected,false);
  assert.equal(replacedApp.core.view().diagnostics.valid_frames,0);
  const prolonged=environment(),prolongedApp=prolonged.start();prolongedApp.transport.discover();prolongedApp.transport.select('11:22:33:44:55:66 public');await flush();
  prolonged.button(true);prolonged.advance(30100);await flush();
  assert.equal(prolongedApp.core.view().recovery,true);assert.equal(prolongedApp.transport.status().active,false);
  assert.equal(prolonged.context.storage['sw-recovery'],'hold');assert.equal(prolonged.context.resets,1);
  const held=environment();held.context.BTN1.state=1;held.boot();
  assert.equal(held.context.imports.includes('sw-main'),false);assert.ok(held.context.global.ShermanRecovery);
  const broken=environment();broken.context.storage['sw-active.json']=JSON.stringify({main:'sw-missing'});broken.boot();
  assert.ok(broken.context.global.ShermanRecovery.reason.includes('startup failed'));
  assert.deepEqual(broken.context.watchdog,[30,false]);
  fs.writeFileSync(path.join(out,'offline.json'),JSON.stringify({issue:32,provenance:'Node VM executes original ES5 application/hardware; fake radio/pins/clock; SVG replays Graphics operations, host fonts',fixture:'experiments/laptop-feasibility/evidence/fixture-recording.jsonl',observed:'240x240 1-bpp buffer7200; sourcebattery97/avg4.09; battery sampling/pinrelease; raw816 nav/wake; D16 startup0 inactive; failed reconnect retries up to3 and later recovery requires newtelemetry; independent recovery beforeimports',hardware_acceptance:'pending: no deployment, device memory, radio, fonts, timing or physical controls measured'},null,2)+'\n');
  console.log('actual watch entry/hardware, battery, touch/button, fake direct BLE and recovery: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
