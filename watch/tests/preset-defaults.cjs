// Shared literal contracts through production main, native touch/Graphics/Storage/GATT.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {environment,flush}=require('./runtime.cjs');
const {frame}=require('./preset-editor.cjs');
const fixture=JSON.parse(fs.readFileSync('docs/acceptance/scenarios/local-presets.json'));
const plain=value=>JSON.parse(JSON.stringify(value));
const results=[];
(async()=>{
  for(const test of [{name:'fresh',expected:fixture.fresh},...fixture.cases]){
    const env=environment();if(test.input)env.context.storage['sw-config.json']=JSON.stringify(test.input);
    let running=env.start();assert.deepEqual(plain(running.core.view().config),test.expected);
    running.core.action('swipe',{direction:'left'});env.advance(200);
    assert.ok(test.expected.presets.every(slot=>env.context.graphics.ops.some(op=>op.kind==='text'&&op.value===slot.name)));
    const rendering=plain(env.context.graphics.ops);
    running.stop();running=env.start();assert.deepEqual(plain(running.core.view().config),test.expected);
    running.core.action('swipe',{direction:'down',from_top:true});running.core.action('alerts_begin');running.core.action('alerts_update',{alert:'pwm',threshold:74});running.core.action('alerts_save');
    const saved=plain(running.core.view().config);assert.equal(saved.alerts.pwm.threshold,74);assert.deepEqual(saved.presets,test.expected.presets);
    running.stop();running=env.start();assert.deepEqual(plain(running.core.view().config),saved);assert.equal(running.core.view().preset_attempt,null);assert.equal(env.bleWrites.length,0);
    results.push({name:test.name,expected:test.expected,observed:saved,rendering,storage:env.storageEffects});running.stop();
  }
  for(const mode of ['stage','active','legacy-backup','unknown','oversized','corrupt']){
    const env=environment();let expected=fixture.fresh;
    if(mode==='legacy-backup'){env.context.storage['sw-config-backup.json']=JSON.stringify(fixture.cases[0].input);env.context.storage['sw-config.json']='{partial';expected=fixture.cases[0].expected;}
    if(['unknown','oversized','corrupt'].includes(mode))env.context.storage['sw-config.json']=mode==='unknown'?'{"version":999}':mode==='oversized'?' '.repeat(4097):'{partial';
    let running=env.start();assert.deepEqual(plain(running.core.view().config),expected);
    if(['unknown','oversized','corrupt'].includes(mode)){assert.match(running.core.view().persistence_error,/review/);assert.equal(env.storageEffects.length,0);}
    else {
      running.core.action('swipe',{direction:'down',from_top:true});running.core.action('alerts_begin');running.core.action('alerts_update',{alert:'pwm',threshold:76});
      env.storageFailure(mode==='stage'?'sw-config-stage.json':'sw-config.json',true);running.core.action('alerts_save');
      assert.ok(running.core.view().persistence_error);assert.deepEqual(plain(running.core.view().config),expected);
      running.stop();env.storageFailure(null);running=env.start();assert.deepEqual(plain(running.core.view().config),expected);
    }
    results.push({mode,observed:plain(running.core.view().config),warning:running.core.view().persistence_error,storage:env.storageEffects});running.stop();
  }
  for(const [slot,dip,packet] of [[1,0,'4c64417021010280808080808080808080808080808080808080808000f0fc0bd4'],[2,11,'4c6441702101028080808080808080808080808080808080808080800b672ed25c']]){
    const env=environment();env.context.storage['sw-config.json']=JSON.stringify(fixture.cases[0].input);const running=env.start();
    running.transport.discover();running.transport.select('11:22:33:44:55:66 public');await flush();env.advance(200);env.notification(frame(44,55,83));env.touch(2,120,20);env.touch(3,20,120);env.touch(5,slot===1?66:174,80);await flush();
    assert.deepEqual(env.bleWrites.slice(-2),[packet.slice(0,40),packet.slice(40)]);
    assert.equal(running.core.view().preset_attempt.fields.pedal_dip_compensation.requested,dip);
    results.push({included_dip:dip,expected_packet:packet,observed_chunks:env.bleWrites});running.stop();
  }
  {
    const env=environment();env.context.JSON={parse:JSON.parse,stringify:value=>JSON.stringify(value,(key,value)=>key==='threshold'&&value===70.125?70.1:value)};
    const running=env.start(),before=plain(running.core.view().config);running.core.action('swipe',{direction:'down',from_top:true});running.core.action('alerts_begin');running.core.action('alerts_update',{alert:'pwm',threshold:70.125});running.core.action('alerts_save');
    assert.match(running.core.view().persistence_error,/precision/);assert.deepEqual(plain(running.core.view().config),before);assert.equal(env.context.storage['sw-config.json'],undefined);
    results.push({mode:'native-json-precision-refusal',warning:running.core.view().persistence_error,storage:env.storageEffects});running.stop();
  }
  const env=environment(),running=env.start();running.transport.discover();running.transport.select('11:22:33:44:55:66 public');await flush();
  let now=200;env.advance(now);env.notification(frame(44,55,83));env.touch(2,120,20);
  env.touch(0,120,10);env.touch(1,120,110);env.touch(5,120,196);env.advance(now+=200);
  assert.equal(running.core.view().screen,'preset_slots');assert.ok(fixture.fresh.presets.every(slot=>env.context.graphics.ops.some(op=>op.kind==='text'&&String(op.value).includes(slot.name))));
  for(let i=0;i<4;i++){
    while(running.core.view().screen!=='dashboard')env.touch(running.core.view().screen==='presets'?4:2,120,20);
    env.notification(frame(44,55,83));env.touch(3,20,120);
    const before=env.bleWrites.length;env.touch(5,i%2?174:66,i<2?80:170);await flush();
    const chunks=fixture.default_packets[i].flatMap(packet=>[packet.slice(0,40),packet.slice(40)].filter(Boolean));
    assert.deepEqual(env.bleWrites.slice(before),chunks);
    const p=fixture.fresh.presets[i];env.advance(now+=100);env.notification(frame(p.pedal_sensitivity,p.dynamic_assist,83));env.advance(now+=100);env.notification(frame(p.pedal_sensitivity,p.dynamic_assist,83));
    assert.equal(running.core.view().confirmed_preset.slot,i+1);
    results.push({slot:i+1,expected_packets:fixture.default_packets[i],observed_chunks:env.bleWrites.slice(before),dip:running.core.view().actual_settings.pedal_dip_compensation});
  }
  running.stop();
  const out='watch/evidence/local-presets';fs.mkdirSync(out,{recursive:true});
  fs.writeFileSync(out+'/defaults.json',JSON.stringify({issue:45,provenance:'production main, native Storage, CST816, Graphics, parser and GATT; simulated pins, flash, clock and BLE; no hardware operations',results,source_sha256:Object.fromEntries(fs.readdirSync('watch').filter(n=>n.endsWith('.js')).map(n=>['watch/'+n,crypto.createHash('sha256').update(fs.readFileSync('watch/'+n)).digest('hex')]))},null,2)+'\n');
  console.log('watch defaults/migration/recovery/native lists/application: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
