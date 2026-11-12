// Production main/touch/render/Storage, replaying the literal laptop input journey.
const assert=require('node:assert/strict');
const {environment,flush,frame,dispatchRecordedInput,snapshot,evidence,plain,readJson,sha256,watchSourceHashes}=require('./harness.cjs');
const riding={settings:{pedal_sensitivity:41,dynamic_assist:51,pedal_dip_compensation:61}};
async function replay(file,name){
  const laptop=readJson(file);const env=environment();let running=env.start(),now=200;env.advance(now);const states=[],renderings=[];
  for(const event of laptop.timeline){
    dispatchRecordedInput(env,event);
    env.advance(now+=200);await flush();const state=plain(running.core.view());
    assert.equal(env.bleWrites.length,0,'every editor action emits zero packets');
    const targets=env.context.require('sw-controls').targets(state);
    assert.ok(!targets.some(t=>['preset_clear','preset_clear_begin','preset_clear_done','preset_input_done'].includes(t.action)));
    if(state.screen==='preset_editor')assert.ok(targets.some(t=>t.label===(state.preset_input?'OK':'Save'))&&targets.some(t=>t.label==='Cancel'));
    if(state.preset_input&&state.preset_input.field==='pedal_dip_compensation'){
      assert.ok(targets.some(t=>t.action==='preset_include_dip'),'inclusion remains reachable with active numeric input');
      if((event.end||[])[0]===186&&(event.end||[])[1]===24){
        assert.equal(state.preset_input.text,'11');
        assert.equal(state.preset_draft.dip_included,!states.at(-1).draft.dip_included);
        assert.equal(state.config.presets[state.preset_draft.id-1].dip_included,false);
        snapshot(env,'slot-'+state.preset_draft.id+'-dip-input');
      }
    }
    if(state.validation_error&&state.preset_input&&state.preset_input.field==='name'){
      assert.match(state.validation_error,/name must contain/i);
      assert.equal(state.preset_input.text,'');
      assert.ok(env.context.graphics.ops.some(op=>op.kind==='text'&&/name must contain/i.test(op.value)));
      snapshot(env,'invalid-name-save');
    }
    states.push({input:event,screen:state.screen,page:state.preset_page,draft:state.preset_draft,keypad:state.preset_input,config:state.config,validation:state.validation_error,storage_error:state.persistence_error,storage_effects:env.storageEffects.length});
    if(state.preset_input&&(event.end||[])[1]===73&&state.preset_draft){
      const key='slot-'+state.preset_draft.id+'-'+state.preset_input.field;
      if(!renderings.includes(key)){snapshot(env,key);renderings.push(key);}
    }
    if(state.validation_error)snapshot(env,'invalid-save');if(state.persistence_error)snapshot(env,'failed-save');
  }
  assert.equal(running.core.view().screen,'preset_slots');
  for(let i=0;i<4;i++)assert.deepEqual(plain(running.core.view().config.presets[i]),{id:i+1,name:'Ab '+(i+1),configured:true,pedal_sensitivity:i===0?32:31,dynamic_assist:26,pedal_dip_compensation:11,dip_included:false});
  const saved=plain(running.core.view().config);running.stop();running=env.start();assert.deepEqual(plain(running.core.view().config),saved);assert.equal(running.core.view().preset_editor,null);assert.equal(running.core.view().preset_attempt,null);assert.equal(env.bleWrites.length,0);running.stop();
  return {trace:file,trace_sha256:sha256(file),states,renderings,storage:env.storageEffects,saved,packets:[],outcome:'passed'};
}
async function failures(){
  const results=[];
  for(const mode of ['stage','active','legacy-only','valid-but-wrong']){
    const env=environment(),f=readJson('docs/acceptance/scenarios/local-presets.json');
    if(mode==='legacy-only'){env.context.storage['sw-config-backup.json']=JSON.stringify(f.cases[0].input);env.context.storage['sw-config.json']='{partial';}
    if(mode==='valid-but-wrong')env.context.storage['sw-config.json']=JSON.stringify(f.cases[0].input);
    let running=env.start();const initial=plain(running.core.view().config);
    running.core.action('preset_begin',{slot:4});let id=running.core.view().preset_editor.id;
    running.core.action('preset_update',{editor_id:id,name:'Retry local',pedal_dip_compensation:17});
    env.storageFailure(mode==='stage'?'sw-config-stage.json':'sw-config.json',mode==='valid-but-wrong'?JSON.stringify(f.fresh):true);
    running.core.action('preset_save',{editor_id:id});assert.ok(running.core.view().persistence_error);assert.deepEqual(plain(running.core.view().config),initial);
    assert.equal(running.core.view().preset_draft.name,'Retry local');
    // Retry while running and a separate interrupted restart both retain meaning.
    const interrupted=environment();Object.assign(interrupted.context.storage,env.context.storage);const recovered=interrupted.start();assert.deepEqual(plain(recovered.core.view().config),initial);recovered.stop();
    env.storageFailure(null);running.core.action('preset_save',{editor_id:id});assert.equal(running.core.view().config.presets[3].name,'Retry local');assert.equal(running.core.view().config.presets[3].pedal_dip_compensation,17);
    results.push({mode,previous:initial,saved:plain(running.core.view().config),storage:env.storageEffects});running.stop();
  }
  const fixture=readJson('docs/acceptance/scenarios/local-editor-frames.json');
  const frames=environment(),editing=frames.start();frames.advance(200);
  editing.core.action('preset_begin',{slot:4});const identity=editing.core.view().preset_editor.id;
  editing.core.action('preset_input_begin',{editor_id:identity});const entry=editing.core.view().preset_input.id;editing.core.action('preset_input_key',{editor_id:identity,entry_id:entry,key:'Clear'});editing.core.action('preset_input_key',{editor_id:identity,entry_id:entry,key:'A'});
  editing.transport.discover();editing.transport.select('11:22:33:44:55:66 public');await flush();
  for(const raw of [fixture.frame_hex,fixture.corrupt_hex]){frames.notification(Buffer.from(raw,'hex'));assert.deepEqual(plain(editing.core.view().preset_draft),fixture.expected_draft);assert.equal(editing.core.view().preset_input.text,fixture.expected_input);}
  const old=editing.core.view().session;frames.loss();await flush();editing.core.receive(old,Buffer.from(fixture.frame_hex,'hex'));assert.deepEqual(plain(editing.core.view().preset_draft),fixture.expected_draft);assert.equal(frames.bleWrites.length,0);
  results.push({mode:'shared-raw-frame-fixture',fixture,draft:plain(editing.core.view().preset_draft),input:plain(editing.core.view().preset_input),packets:frames.bleWrites});editing.stop();
  // A save invalidates a pending native packet, preventing its unsent chunks.
  const env=environment(),running=env.start();running.transport.discover();running.transport.select('11:22:33:44:55:66 public');await flush();env.advance(200);env.notification(frame(riding));env.writeHang(true);
  running.core.action('preset_apply',{slot:2});await flush();assert.equal(env.bleWrites.length,1);
  running.core.action('preset_begin',{slot:2});let id=running.core.view().preset_editor.id;
  running.core.action('preset_input_begin',{editor_id:id});const entryId=running.core.view().preset_input.id;running.core.action('preset_input_key',{editor_id:id,entry_id:entryId,key:'Clear'});running.core.action('preset_input_key',{editor_id:id,entry_id:entryId,key:'A'});
  env.notification(frame({settings:{pedal_sensitivity:44,dynamic_assist:55,pedal_dip_compensation:66}}));env.loss();await flush();assert.equal(running.core.view().preset_input.text,'A');
  running.core.action('preset_input_accept',{editor_id:id,entry_id:entryId});running.core.action('preset_save',{editor_id:id});env.writeHang(false);env.settleWrite();await flush();assert.equal(env.bleWrites.length,1);assert.equal(running.core.view().preset_attempt.pending,false);
  results.push({mode:'pending-native-write-and-disconnect',chunks:env.bleWrites,config:plain(running.core.view().config)});running.stop();return results;
}
(async()=>{
  const trace=await replay('docs/acceptance/evidence/touch-layout/editor-laptop.json','editor');
  const faults=await failures();
  evidence.json('watch/evidence/touch-layout/editor.json',{spec:'docs/design/preset-value-editor.md',provenance:'production main/CST816/Graphics/parser/GATT/native Storage; simulated physical inputs, time, BLE and flash; no hardware operations',trace,faults,source_sha256:watchSourceHashes()});
  console.log('watch native local editor: laptop trace, Graphics, Storage faults, restart and stopped continuation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
