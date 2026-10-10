// Value-entry completion through production touch, Graphics and native Storage.
const assert=require('node:assert/strict');
const fs=require('node:fs'),crypto=require('node:crypto');
const {environment}=require('./runtime.cjs');
const {dispatchRecordedInput}=require('./preset-editor-runtime.cjs');
const plain=value=>JSON.parse(JSON.stringify(value));
const env=environment(),running=env.start();
let now=200;env.advance(now);
function tap(x,y){env.touch(5,x,y);env.advance(now+=200);return running.core.view();}
env.touch(0,120,10);env.touch(1,120,110);tap(120,196);tap(80,143);
const initial=plain(running.core.view().config),writes=env.storageEffects.length;
tap(120,80);tap(125,196);tap(49,73);
let state=tap(176,226);
assert.equal(state.screen,'preset_editor');
assert.equal(state.preset_input,null);
assert.equal(state.preset_draft.name,'A');
assert.deepEqual(plain(state.config),initial);
assert.equal(env.storageEffects.length,writes,'OK never writes Storage');
assert.ok(env.context.graphics.ops.some(op=>op.kind==='text'&&op.value==='Save'));
tap(220,20);tap(120,80);tap(49,166);tap(49,104);tap(119,166); // 40.
state=tap(64,226);
assert.equal(state.preset_draft.pedal_sensitivity,30);
assert.equal(state.preset_draft.name,'A');
assert.equal(state.preset_input,null);
tap(120,80);tap(49,166);tap(49,73);tap(119,166);tap(49,73); // 101.
state=tap(176,226);
assert.equal(state.preset_input.text,'101');
assert.match(state.preset_editor.reason,/whole percentage/);
assert.ok(env.context.graphics.ops.some(op=>op.kind==='text'&&op.value==='101'),'invalid text remains visible beside its reason');
// A captured touch target from a completed entry cannot act on its successor.
const stale={editor_id:state.preset_editor.id,entry_id:state.preset_input.id};
tap(64,226);tap(120,80);
const later=plain(running.core.view());
for(const [action,payload] of [['preset_input_accept',{}],['preset_input_cancel',{}],['preset_input_key',{key:'Clear'}],['preset_input_page',{delta:1}],['swipe',{direction:'up'}],['preset_page',{page:2}],['preset_save',{}],['preset_cancel',{}]]){
  assert.throws(()=>running.core.action(action,{...stale,...payload}),/changed/);
  assert.deepEqual(plain(running.core.view().preset_input),later.preset_input);
  assert.deepEqual(plain(running.core.view().preset_draft),later.preset_draft);
}
tap(64,226);
assert.throws(()=>running.core.action('swipe',{...stale,direction:'up'}),/changed/);
tap(64,226);tap(80,187);tap(120,80);
assert.throws(()=>running.core.action('preset_input_accept',stale),/changed/);
assert.equal(env.bleWrites.length,0);
running.stop();
// Replay the actual laptop pointer trace through CST816/main/Graphics/Storage.
const tracePath='docs/acceptance/evidence/preset-values/value-editor-laptop.json';
const trace=JSON.parse(fs.readFileSync(tracePath));
const native=environment();let app=native.start(),time=200;native.advance(time);
const renderings=[];
for(const [index,event] of trace.timeline.entries()){
  const before=app.core.view(),storage=native.storageEffects.length;
  dispatchRecordedInput(native,event);
  native.advance(time+=200);
  const state=plain(app.core.view());
  if(event.expected)for(const [key,value] of Object.entries(event.expected))assert.deepEqual(state[key],value,'event '+index+' '+key);
  if(before.preset_input)assert.equal(native.storageEffects.length,storage,'entry action never writes Storage');
  assert.equal(native.bleWrites.length,0);
  if(state.preset_input){
    const text=native.context.graphics.ops.filter(op=>op.kind==='text').map(op=>op.value);
    assert.ok(text.includes('OK')&&text.includes('Cancel')&&!text.includes('Save'));
    if(state.preset_editor.reason){
      assert.ok(text.includes(state.preset_input.text||'-'));
      renderings.push({event:index,graphics:plain(native.context.graphics.ops)});
    }
  }
}
const saved=plain(app.core.view().config);
assert.equal(saved.presets[2].name,'Commute');assert.equal(saved.presets[2].pedal_sensitivity,41);
assert.equal(saved.revision,2);
app.stop();app=native.start();assert.deepEqual(plain(app.core.view().config),saved);app.stop();
fs.mkdirSync('watch/evidence/preset-values',{recursive:true});
fs.writeFileSync('watch/evidence/preset-values/value-editor.json',JSON.stringify({
  spec:trace.spec,provenance:'Actual laptop pointer trace through native CST816/main/Graphics/Storage; simulated hardware, clock, flash and BLE',
  trace:tracePath,trace_sha256:crypto.createHash('sha256').update(fs.readFileSync(tracePath)).digest('hex'),
  events:trace.timeline.length,renderings,saved,storage:native.storageEffects,packets:[],stale_actions:'rejected',outcome:'passed'
},null,2)+'\n');
console.log('watch value completion, validation, stale actions, laptop parity and Storage retry/restart: passed');
