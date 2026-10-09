/* Production entry point and input adapters, with fake hardware only. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {environment}=require('./runtime.cjs');
const env=environment(),serialHandlers={},services=[];
env.context.Bluetooth={on:(name,handler)=>serialHandlers[name]=handler,setConsole:value=>{env.context.consoleEnabled=value;}};
env.context.NRF.setServices=(value,options)=>services.push(options);
const saved=env.context.require('sw-configuration').defaults();
saved.revision=23;
saved.presets[0]={id:1,name:'Watch local',configured:true,pedal_sensitivity:60,dynamic_assist:50,pedal_dip_compensation:25};
saved.alerts.pwm={enabled:true,threshold:80};
env.context.storage['sw-config.json']=JSON.stringify(saved);
env.context.storage['sw-config-stage.json']='{"partial historical stage"';
const running=env.start();
env.advance(200);
assert.equal(JSON.stringify(running.core.view().config),JSON.stringify(saved),'existing watch schema-1 content needs no re-entry');
env.touch(0,120,10);env.touch(1,120,90);
assert.equal(running.core.view().screen,'settings');
env.touch(5,120,202);
assert.equal(running.core.view().screen,'settings','former transfer touch must leave Settings usable');
for(const name of ['transfer_begin','transfer_preview','transfer_choose','transfer_send','transfer_reconcile','transfer_cancel','transfer_return','transfer_activate','transfer_exit','transfer_scenario','transfer_watch_edit','nordic_select']){
  const before=running.core.view();
  assert.throws(()=>running.core.action(name,{config:before.config}),/Unknown action/);
  assert.equal(JSON.stringify(running.core.view().config),JSON.stringify(before.config));
  assert.equal(running.core.view().session,before.session);
}
assert.ok(!env.context.imports.includes('sw-transfer'),'watch configuration exchange endpoint is absent');
assert.throws(()=>env.context.require('sw-transfer'),/ENOENT/);
assert.equal(serialHandlers.data,undefined,'old JSONL requests have no application listener');
assert.equal(services.length,0,'riding app has no configuration UART service');
assert.ok(!env.context.graphics.ops.some(row=>row.kind==='text'&&/transfer|synchron|reconcil|conflict/i.test(row.value)));
env.touch(5,120,155);
assert.equal(running.core.view().screen,'alerts');
running.core.action('alerts_update',{alert:'pwm',threshold:82});
running.core.action('alerts_save');
assert.equal(running.core.view().config.alerts.pwm.threshold,82);
const updated=JSON.stringify(running.core.view().config);
running.stop();
const restarted=env.start();
assert.equal(JSON.stringify(restarted.core.view().config),updated);
assert.equal(JSON.stringify(restarted.core.view().config.presets),JSON.stringify(saved.presets));
restarted.core.action('swipe',{direction:'down',from_top:true});
restarted.core.action('alerts_begin');
restarted.core.action('alerts_update',{alert:'pwm',threshold:83});
env.storageFailure('sw-config.json',true);
restarted.core.action('alerts_save');
assert.match(restarted.core.view().persistence_error,/save failed/i);
assert.equal(JSON.stringify(restarted.core.view().config),updated);
restarted.stop();env.storageFailure(null);
const recovered=env.start();
assert.equal(JSON.stringify(recovered.core.view().config),updated);
assert.match(recovered.core.view().persistence_error,/Recovered previous good/);
recovered.stop();env.context.BTN1.state=1;env.boot();
assert.equal(env.context.consoleEnabled,true,'independent recovery retains BLE console');
assert.equal(services.at(-1).uart,true,'independent recovery retains UART communication');
const root=path.resolve(__dirname,'../..');
const sources=['watch/main.js','watch/app.js','watch/controls.js','watch/render.js','watch/store.js','watch/boot.js','watch/tests/local-configuration.cjs','watch/tests/runtime.cjs'];
fs.writeFileSync(path.join(root,'watch/evidence/local-configuration.json'),JSON.stringify({
  issue:40,
  provenance:'Node VM executes production watch main/app/hardware/Storage/boot; fake pins/radio/native drivers/clock; preexisting schema-1 watch configuration',
  expected:'no transfer in Settings or stale actions/UART endpoint; independent local presets and alert edits persist across restart and recover interrupted active save; independent recovery console remains available',
  observed:{settings_and_former_touch:'passed',stale_actions:'rejected',configuration_endpoint:'absent',existing_revision:23,retained_slot:'Watch local',saved_pwm_threshold:82,restart_and_recovery:'passed',independent_recovery_uart:'available'},
  source_sha256:Object.fromEntries(sources.map(source=>[source,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,source))).digest('hex')])),
  physical_operation:'none; physical flash atomicity, radio and update deployment acceptance remain separate'
},null,2)+'\n');
console.log('watch local configuration, withdrawn entry points, restart/save recovery and independent recovery UART: passed');
