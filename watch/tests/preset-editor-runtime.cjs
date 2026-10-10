// Production main/touch/render/Storage, replaying the literal laptop input journey.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {environment,flush}=require('./runtime.cjs');
const {frame}=require('./preset-editor.cjs');
const plain=value=>JSON.parse(JSON.stringify(value));
const out='watch/evidence/local-presets';
function snapshot(env,name){
  fs.mkdirSync(out,{recursive:true});
  const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const ops=plain(env.context.graphics.ops);
  const svg=ops.map(op=>op.kind==='text'?`<text x="${op.x}" y="${op.y+op.size}" font-size="${op.size}" text-anchor="${op.align===-1?'start':op.align===1?'end':'middle'}">${escape(op.value)}</text>`:op.kind==='line'?`<line x1="${op.x1}" y1="${op.y1}" x2="${op.x2}" y2="${op.y2}" stroke="white"/>`:`<rect x="${op.x1}" y="${op.y1}" width="${op.x2-op.x1}" height="${op.y2-op.y1}" fill="${op.kind==='fill'?'white':'none'}" stroke="white"/>`).join('\n');
  fs.writeFileSync(out+'/'+name+'.svg',`<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><rect width="240" height="240" fill="black"/><g fill="white" font-family="sans-serif">${svg}</g></svg>\n`);return ops;
}
exports.snapshot=snapshot;
async function replay(file,name){
  const laptop=JSON.parse(fs.readFileSync(file));const env=environment();let running=env.start(),now=200;env.advance(now);const states=[],renderings=[];
  for(const event of laptop.timeline){
    if(event.input==='storage_failure')env.storageFailure(event.mode==='refuse'?'sw-config-stage.json':null);
    else if(event.input==='tap')env.touch(5,...event.end);
    else if(event.input==='swipe'){
      const [x,y]=event.start,[ex,ey]=event.end;
      env.touch(0,x,y);env.touch(Math.abs(ex-x)>Math.abs(ey-y)?ex>x?4:3:ey>y?1:2,ex,ey);
    }else throw Error('Unknown trace input '+event.input);
    env.advance(now+=200);await flush();const state=plain(running.core.view());
    assert.equal(env.bleWrites.length,0,'every editor action emits zero packets');
    const targets=env.context.require('sw-controls').targets(state);
    assert.ok(!targets.some(t=>['preset_clear','preset_clear_begin','preset_clear_done','preset_input_done','preset_input_cancel'].includes(t.action)));
    if(state.screen==='preset_editor')assert.ok(targets.some(t=>t.label==='Save')&&targets.some(t=>t.label==='Cancel'));
    if(state.preset_input&&state.preset_input.field==='pedal_dip_compensation'){
      assert.ok(targets.some(t=>t.action==='preset_include_dip'),'inclusion remains reachable with active numeric input');
      if((event.end||[])[1]===196){
        assert.equal(state.preset_input.text,'11');
        assert.equal(state.preset_draft.dip_included,!states.at(-1).draft.dip_included);
        assert.equal(state.config.presets[state.preset_draft.id-1].dip_included,false);
        snapshot(env,'slot-'+state.preset_draft.id+'-dip-input');
      }
    }
    if(state.validation_error&&state.preset_draft.name===''){
      assert.match(state.validation_error,/name must contain/i);
      assert.equal(state.preset_input.field,'pedal_sensitivity');
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
  return {trace:file,trace_sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),states,renderings,storage:env.storageEffects,saved,packets:[],outcome:'passed'};
}
exports.replay=replay;
async function failures(){
  const results=[];
  for(const mode of ['stage','active','legacy-only','valid-but-wrong']){
    const env=environment(),f=JSON.parse(fs.readFileSync('docs/acceptance/scenarios/local-presets.json'));
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
  const fixture=JSON.parse(fs.readFileSync('docs/acceptance/scenarios/local-editor-frames.json'));
  const frames=environment(),editing=frames.start();frames.advance(200);
  editing.core.action('preset_begin',{slot:4});const identity=editing.core.view().preset_editor.id;
  editing.core.action('preset_input_begin',{editor_id:identity});editing.core.action('preset_input_key',{editor_id:identity,key:'Clear'});editing.core.action('preset_input_key',{editor_id:identity,key:'A'});
  editing.transport.discover();editing.transport.select('11:22:33:44:55:66 public');await flush();
  for(const raw of [fixture.frame_hex,fixture.corrupt_hex]){frames.notification(Buffer.from(raw,'hex'));assert.deepEqual(plain(editing.core.view().preset_draft),fixture.expected_draft);assert.equal(editing.core.view().preset_input.text,fixture.expected_input);}
  const old=editing.core.view().session;frames.loss();await flush();editing.core.receive(old,Buffer.from(fixture.frame_hex,'hex'));assert.deepEqual(plain(editing.core.view().preset_draft),fixture.expected_draft);assert.equal(frames.bleWrites.length,0);
  results.push({mode:'shared-raw-frame-fixture',fixture,draft:plain(editing.core.view().preset_draft),input:plain(editing.core.view().preset_input),packets:frames.bleWrites});editing.stop();
  // A save invalidates a pending native packet, preventing its unsent chunks.
  const env=environment(),running=env.start();running.transport.discover();running.transport.select('11:22:33:44:55:66 public');await flush();env.advance(200);env.notification(frame());env.writeHang(true);
  running.core.action('preset_apply',{slot:2});await flush();assert.equal(env.bleWrites.length,1);
  running.core.action('preset_begin',{slot:2});let id=running.core.view().preset_editor.id;
  running.core.action('preset_input_begin',{editor_id:id});running.core.action('preset_input_key',{editor_id:id,key:'Clear'});running.core.action('preset_input_key',{editor_id:id,key:'A'});
  env.notification(frame(44,55,66));env.loss();await flush();assert.equal(running.core.view().preset_input.text,'A');
  running.core.action('preset_save',{editor_id:id});env.writeHang(false);env.settleWrite();await flush();assert.equal(env.bleWrites.length,1);assert.equal(running.core.view().preset_attempt.pending,false);
  results.push({mode:'pending-native-write-and-disconnect',chunks:env.bleWrites,config:plain(running.core.view().config)});running.stop();return results;
}
if(require.main===module)(async()=>{
  const trace=await replay('docs/acceptance/evidence/local-presets/editor-laptop.json','editor');
  const faults=await failures();
  fs.writeFileSync(out+'/editor.json',JSON.stringify({issue:47,provenance:'production main/CST816/Graphics/parser/GATT/native Storage; simulated physical inputs, time, BLE and flash; no hardware operations',trace,faults,source_sha256:Object.fromEntries(fs.readdirSync('watch').filter(n=>n.endsWith('.js')).map(n=>['watch/'+n,crypto.createHash('sha256').update(fs.readFileSync('watch/'+n)).digest('hex')]))},null,2)+'\n');
  console.log('watch native local editor: laptop trace, Graphics, Storage faults, restart and stopped continuation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
