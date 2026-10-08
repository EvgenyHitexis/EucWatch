const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
function crc32(text){let value=0xffffffff;for(const byte of Buffer.from(text,'latin1')){value^=byte;for(let bit=0;bit<8;bit++)value=(value>>>1)^((value&1)?0xedb88320:0);}return (~value)>>>0;}
function environment(options={}){
  const saved={},modules={};let failed=null,partial=false;
  const storage={read:key=>saved[key],write:(key,value)=>{if(key===failed){if(partial)saved[key]='{"partial"';return false;}saved[key]=value;return true;},erase:key=>delete saved[key]};
  const context={JSON:{parse:JSON.parse,stringify:(value,replacer,space)=>JSON.stringify(value,options.roundNearIntegers?(_key,item)=>typeof item==='number'&&item>=0&&item!==Math.floor(item)&&Math.floor(item+1e-7)===Math.floor(item)+1?Math.ceil(item):item:replacer,space).replace(/[\x7f-\xff]/g,char=>'\\u00'+char.charCodeAt(0).toString(16).padStart(2,'0'))},E:{CRC32:crc32},btoa:text=>Buffer.from(text,'latin1').toString('base64'),atob:text=>Buffer.from(text,'base64').toString('latin1')};
  context.require=name=>{
    if(name==='Storage')return storage;
    if(name==='crypto')return{SHA256:text=>{const bytes=crypto.createHash('sha256').update(Buffer.from(text,'latin1')).digest();return Uint8Array.from(bytes).buffer;}};
    if(modules[name])return modules[name];
    const module={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(root,name.replace(/^sw-/,'')+'.js'),'utf8'),{...context,module,exports:module.exports});
    modules[name]=module.exports;return module.exports;
  };
  const config=context.require('sw-configuration');
  return {context,saved,storage,config,store:()=>context.require('sw-store').create({storage}),
    endpoint:store=>context.require('sw-transfer').endpoint({store}),
    fail:(key,value=false)=>{failed=key;partial=value;}};
}
function request(endpoint,op,fields={}){return JSON.parse(endpoint.exchange(JSON.stringify({protocol:1,op,...fields})+'\n'));}
function stage(endpoint,value){
  const info=request(endpoint,'read'),data=JSON.stringify(value);
  assert.equal(request(endpoint,'stage',{size:data.length,expected_revision:info.revision,expected_digest:info.digest,digest:crypto.createHash('sha256').update(Buffer.from(data,'latin1')).digest('hex')}).ok,true);
  for(let index=0;index<Math.ceil(data.length/64);index++){const piece=data.slice(index*64,(index+1)*64);assert.equal(request(endpoint,'chunk',{index,data:Buffer.from(piece,'latin1').toString('base64'),crc32:crc32(piece)}).ok,true);}
}
exports.environment=environment;exports.request=request;exports.crc32=crc32;exports.stage=stage;
if(require.main===module){
  const env=environment(),store=env.store(),endpoint=env.endpoint(store);
  const info=request(endpoint,'read');assert.equal(info.ok,true);assert.equal(info.revision,0);
  let bytes='';for(let index=0;index<Math.ceil(info.size/64);index++){const row=request(endpoint,'read_chunk',{index});assert.equal(row.index,index);const text=Buffer.from(row.data,'base64').toString('latin1');assert.equal(crc32(text),row.crc32);bytes+=text;}
  assert.equal(bytes.length,info.size);assert.equal(crypto.createHash('sha256').update(Buffer.from(bytes,'latin1')).digest('hex'),info.digest);
  assert.deepEqual(JSON.parse(bytes),JSON.parse(JSON.stringify(env.config.defaults())));
  const next=env.config.defaults();next.revision=1;next.alerts.speed={enabled:true,threshold:0.5};
  stage(endpoint,next);assert.equal(store.load(),null,'received chunks do not activate saved content');
  assert.equal(request(endpoint,'validate').validated,true);assert.equal(store.load(),null,'validation does not activate saved content');
  assert.equal(request(endpoint,'commit').revision,1);assert.equal(env.store().load().alerts.speed.threshold,0.5,'actual Storage adapter retains complete content across restart');
  assert.equal(JSON.parse(endpoint.exchange('{"protocol":1,"op":"abort","op":"read"}\n')).ok,false,'duplicate protocol keys are rejected');
  const duplicate=JSON.stringify({...next,revision:2}).replace('"version":1','"version":9,"version":1');
  const current=request(endpoint,'read');
  assert.equal(request(endpoint,'stage',{size:duplicate.length,expected_revision:current.revision,expected_digest:current.digest,digest:crypto.createHash('sha256').update(duplicate).digest('hex')}).ok,true);
  for(let index=0;index<Math.ceil(duplicate.length/64);index++){const part=duplicate.slice(index*64,(index+1)*64);assert.equal(request(endpoint,'chunk',{index,data:Buffer.from(part).toString('base64'),crc32:crc32(part)}).ok,true);}
  assert.equal(request(endpoint,'validate').ok,false,'duplicate complete-configuration keys are rejected');
  assert.equal(request(endpoint,'abort').aborted,true);assert.equal(request(endpoint,'commit').ok,false);
  assert.equal(env.store().load().revision,1,'cancellation retains the saved independent copy');
  const stale=env.config.defaults();stale.revision=2;stage(endpoint,stale);assert.equal(request(endpoint,'validate').ok,true);
  const intervening=env.config.defaults();intervening.revision=1;intervening.alerts.lost.enabled=false;store.save(intervening);
  assert.equal(request(endpoint,'commit').ok,false,'same-revision changed content invalidates the reviewed stage');
  assert.equal(env.store().load().alerts.lost.enabled,false);
  for(const [key,partial] of [['sw-config-stage.json',true],['sw-config-backup.json',false],['sw-config.json',true]]){
    const fault=environment(),saved=fault.store(),wire=fault.endpoint(saved),candidate=fault.config.defaults();candidate.revision=1;
    stage(wire,candidate);fault.fail(key,partial);
    const validated=request(wire,'validate');const committed=validated.ok?request(wire,'commit'):validated;
    assert.equal(committed.ok,false,`${key} failure is observable`);fault.fail(null);
    assert.equal(request(fault.endpoint(fault.store()),'read').revision,0,`${key} first-write interruption recovers validated default`);
  }
  const stable=environment(),stableStore=stable.store(),stableWire=stable.endpoint(stableStore);stableStore.save(next);
  const interrupted={...JSON.parse(JSON.stringify(next)),revision:2};stage(stableWire,interrupted);assert.equal(request(stableWire,'validate').ok,true);
  stable.fail('sw-config.json',true);assert.equal(request(stableWire,'commit').ok,false);stable.fail(null);
  assert.equal(request(stable.endpoint(stable.store()),'read').revision,1,'restart after partial activation recovers the previous complete copy');
  const recovered=environment(),recoveredStore=recovered.store(),recoveredWire=recovered.endpoint(recoveredStore);
  recoveredStore.save(next);recoveredStore.save(interrupted);
  recovered.saved['sw-config.json']='{"partial"';
  assert.equal(request(recoveredWire,'read').revision,1,'the sole good backup is the recovered saved content');
  const replacement={...JSON.parse(JSON.stringify(next)),revision:3};
  stage(recoveredWire,replacement);assert.equal(request(recoveredWire,'validate').ok,true);
  recovered.fail('sw-config-backup.json',true);
  assert.equal(request(recoveredWire,'commit').ok,true,'activation after recovery preserves the sole good backup instead of rewriting it');
  recovered.fail(null);
  assert.equal(request(recovered.endpoint(recovered.store()),'read').revision,3,'a recovered configuration can be replaced and read after restart');
  recovered.saved['sw-config.json']='{"partial"';
  assert.equal(request(recoveredWire,'read').revision,1);
  stage(recoveredWire,replacement);assert.equal(request(recoveredWire,'validate').ok,true);
  recovered.fail('sw-config.json',true);assert.equal(request(recoveredWire,'commit').ok,false);
  recovered.fail(null);
  assert.equal(request(recovered.endpoint(recovered.store()),'read').revision,1,'a second interrupted activation after recovery still retains the sole validated backup');
  const lost=environment(),lostStore=lost.store(),lostWire=lost.endpoint(lostStore);stage(lostWire,next);assert.equal(request(lostWire,'validate').ok,true);
  request(lostWire,'commit');assert.equal(request(lost.endpoint(lost.store()),'read').revision,1,'lost acknowledgement is resolved by explicit active readback');
  assert.equal(request(lostWire,'commit').ok,false,'activation cannot be retried without an explicit new reviewed stage');
  assert.equal(request(lostWire,'finish').returned,true);
  assert.equal(request(lostWire,'stage',{size:4097,expected_revision:1,expected_digest:'0'.repeat(64),digest:'0'.repeat(64)}).ok,false);
  const savedInfo=request(lostWire,'read');assert.equal(request(lostWire,'stage',{size:4,expected_revision:1,expected_digest:savedInfo.digest,digest:'0'.repeat(64)}).ok,true);
  assert.equal(request(lostWire,'chunk',{index:1,data:'e30=',crc32:crc32('{}')}).ok,false);
  assert.equal(request(lostWire,'chunk',{index:0,data:'e30=',crc32:0}).ok,false);
  assert.equal(request(lostWire,'validate').ok,false);
  assert.equal(request(lostWire,'read').revision,1);
  const unicode=env.config.defaults();unicode.revision=3;unicode.presets[0].name=Buffer.from('é'.repeat(24),'utf8').toString('latin1');
  stage(endpoint,unicode);assert.equal(request(endpoint,'validate').ok,true,'24 readable UTF-8 characters remain accepted on the 8-bit Espruino string boundary');
  assert.equal(request(endpoint,'commit').ok,true);
  const utfInfo=request(endpoint,'read');let utf='';for(let index=0;index<Math.ceil(utfInfo.size/64);index++)utf+=Buffer.from(request(endpoint,'read_chunk',{index}).data,'base64').toString('latin1');
  assert.equal(JSON.parse(Buffer.from(utf,'latin1').toString('utf8')).presets[0].name,'é'.repeat(24));
  const precision=environment({roundNearIntegers:true}),preciseStore=precision.store(),precise=precision.config.defaults();precise.revision=1;precise.alerts.speed={enabled:true,threshold:19.99999999};
  assert.equal(precision.config.validate(precise).alerts.speed.threshold,19.99999999,'copy/validation cannot change alert meaning through native JSON rounding');
  assert.throws(()=>preciseStore.save(precise),/precision|meaning|roundtrip/i,'unsupported native serialization retains the previous saved content with an explicit error');
  assert.equal(preciseStore.load(),null);
  console.log('watch configuration read snapshot through actual byte protocol: passed');
}
