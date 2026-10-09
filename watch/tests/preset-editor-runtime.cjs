// Actual main, CST816 touch, Graphics, BLE writer and native Storage adapter.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {environment,flush}=require('./runtime.cjs');
const {frame}=require('./preset-editor.cjs');
const repo=path.resolve(__dirname,'../..'),out=path.resolve(__dirname,'../evidence/preset-editor');
const evidence={issue:42,provenance:'Production main, hardware CST816 interrupts, Graphics operations, direct GATT chunk writer, native Storage adapter under Node VM; fake pins, timers, ADC, BLE promises and flash. No hardware operations.',hardware_acceptance:{display:'pending',input:'pending',vibration:'pending',memory_fit:'pending',live_controls:'pending',deployment:'not performed'}};
function snapshot(env,name){
  fs.mkdirSync(out,{recursive:true});
  const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const operations=env.context.graphics.ops;
  const svg=operations.map(op=>op.kind==='text'?`<text x="${op.x}" y="${op.y+op.size}" font-size="${op.size}" text-anchor="${op.align===-1?'start':op.align===1?'end':'middle'}">${escape(op.value)}</text>`:op.kind==='line'?`<line x1="${op.x1}" y1="${op.y1}" x2="${op.x2}" y2="${op.y2}" stroke="white"/>`:`<rect x="${op.x1}" y="${op.y1}" width="${op.x2-op.x1}" height="${op.y2-op.y1}" fill="${op.kind==='fill'?'white':'none'}" stroke="white"/>`).join('\n');
  fs.writeFileSync(path.join(out,name+'.svg'),`<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240"><rect width="240" height="240" fill="black"/><g fill="white" font-family="sans-serif">${svg}</g></svg>\n`);
  return JSON.parse(JSON.stringify(operations));
}
async function connected(){const env=environment(),running=env.start();running.transport.discover();running.transport.select('11:22:33:44:55:66 public');await flush();return {env,running};}
async function laptopTrace(){
  const file=path.join(repo,'docs/acceptance/evidence/preset-editor/preset-editor-browser.json'),laptop=JSON.parse(fs.readFileSync(file,'utf8'));
  const {env,running}=await connected();let now=200,failed=false,rendered=[],previousConfig='',selected=null,otherSlots=null;const states=[],observed=[];env.advance(now);
  for(const [index,event] of laptop.timeline.entries()){
    if(event.input==='simulator_configure')continue; // The fake wheel emits only recorded raw responses.
    if(event.input==='tap'){
      const state=running.core.view();
      if(state.preset_input&&state.preset_input.field==='pedal_sensitivity'&&state.preset_input.text==='31'&&event.y===226){env.storageFailure('sw-config-stage.json');failed=true;}
      if(failed&&state.persistence_error&&event.x===131&&event.y===221)env.storageFailure(null);
      env.touch(5,event.x,event.y);
    }else if(event.input==='swipe'){
      env.touch(0,...event.start);env.touch(event.end[0]>event.start[0]?4:event.end[0]<event.start[0]?3:1,...event.end);
    }else if(event.input==='notification'){
      now+=event.advance_s*1000;env.advance(now);env.notification(Buffer.from(event.raw_hex,'hex'));
    }else if(event.input==='advance'){now+=event.seconds*1000;env.advance(now);}
    else throw Error('Unknown laptop event '+event.input);
    await flush();
    const state=running.core.view();
    if(state.preset_editor&&state.preset_editor.slot!==selected){selected=state.preset_editor.slot;otherSlots=JSON.stringify(state.config.presets.filter(slot=>slot.id!==selected));}
    if(state.preset_editor)assert.equal(JSON.stringify(state.config.presets.filter(slot=>slot.id!==selected)),otherSlots,'editing slot '+selected+' preserves the other three');
    // Draw on the normal 5 Hz timer without introducing fake elapsed time per tap.
    const view=JSON.parse(JSON.stringify(state)),configText=JSON.stringify(view.config);
    const record={event:index,screen:view.screen,editor:view.preset_editor?{slot:view.preset_editor.slot,status:view.preset_editor.status,current_confirmation:view.preset_editor.current_confirmation}:null,draft:view.preset_draft,input:view.preset_input,attempt:view.preset_attempt?{slot:view.preset_attempt.slot,status:view.preset_attempt.status,pending:view.preset_attempt.pending,fields:view.preset_attempt.fields,reason:view.preset_attempt.reason}:null,persistence_error:view.persistence_error,commands:view.command_events.length};
    if(configText!==previousConfig){record.config=view.config;previousConfig=configText;}states.push(record);
    if(state.preset_editor&&state.preset_editor.current_confirmation&&state.preset_attempt.fields[['name','pedal_sensitivity','dynamic_assist','pedal_dip_compensation'][state.preset_page]]&&!state.preset_input&&state.preset_clear_slot===null){
      const name='slot-'+state.preset_draft.id+'-field-'+state.preset_page;
      if(!rendered.includes(name)){
        // The public renderer receives the real current runtime view; hardware
        // display is checked separately by the timer-driven tracer above.
        env.context.require('sw-render').draw(env.context.graphics,state);
        const ops=snapshot(env,name);assert.ok(ops.some(op=>op.kind==='text'&&/confirmed/.test(op.value)));rendered.push(name);
      }
    }
    if(state.screen==='preset_editor'&&state.preset_editor.status==='unavailable'){env.context.require('sw-render').draw(env.context.graphics,state);snapshot(env,'unavailable-readback');}
    if(state.persistence_error&&state.preset_attempt.status==='Confirmed'){env.context.require('sw-render').draw(env.context.graphics,state);snapshot(env,'save-failure-after-wheel-change');assert.equal(state.config.presets[0].pedal_sensitivity,30);assert.equal(state.preset_draft.pedal_sensitivity,31);}
    if(event.input==='tap'&&event.x===120&&event.y===126&&state.preset_page===3&&state.preset_draft.pedal_dip_compensation===undefined){
      const expected=laptop.observed[state.preset_draft.id-1].saved;
      assert.deepEqual(JSON.parse(JSON.stringify(state.config.presets[state.preset_draft.id-1])),expected);
      observed.push({slot:state.preset_draft.id,expected_laptop:expected,observed_watch:JSON.parse(JSON.stringify(state.config.presets[state.preset_draft.id-1]))});
    }
  }
  assert.equal(observed.length,4);assert.equal(rendered.length,12);
  assert.equal(env.bleWrites.length,21,'four slots × three field packets (assist/dip split at 20 bytes), plus failed-save sensitivity');
  const packets=['4c6441700f01028080801e8054e0a5','4c6441701f010280808080808080808080808080808080808080145d845628','4c6441702101028080808080808080808080808080808080808080800b672ed25c'];
  const chunks=packets.flatMap(packet=>[packet.slice(0,40),packet.slice(40)].filter(Boolean));
  assert.deepEqual(env.bleWrites,[...chunks,...chunks,...chunks,...chunks,'4c6441700f01028080801ff753d033'],'packets match laptop evidenced commands, including native chunk boundaries');
  const saved=JSON.parse(JSON.stringify(running.core.view().config));running.stop();env.advance(now);await flush();
  const restarted=env.start();assert.deepEqual(JSON.parse(JSON.stringify(restarted.core.view().config)),saved);
  assert.equal(restarted.core.view().preset_attempt,null);assert.equal(restarted.core.view().preset_editor,null);assert.equal(restarted.core.view().confirmed_preset,null);
  assert.equal(env.bleWrites.length,21);restarted.stop();
  evidence.laptop_trace={path:path.relative(repo,file),sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),input_events:laptop.timeline,observed_slots:observed,states,renderings:rendered,native_ble_chunks:env.bleWrites,native_storage_effects:env.storageEffects.map(row=>({key:row.key,bytes:row.value.length,failed:row.failed,sha256:crypto.createHash('sha256').update(row.value).digest('hex')})),restart:'definitions retained; no editor, command replay or confirmation restored',matched:'all four slots, name/keypad/cancel, three writes and fresh confirmation, dip omission, clear cancel/commit, recreate, unavailable readback, save failure and local retry'};
  console.log('all 249 reusable laptop action/frame events through actual watch runtime: passed');
}
async function failures(){
  const results=[];
  for(const mode of ['reject-second-chunk','hang-cancel','hang-disconnect','hung-timeout','confirmation-timeout','mismatch','storage-stage','storage-active']){
    const {env,running}=await connected();env.advance(200);
    env.touch(0,120,10);env.touch(1,120,110);env.touch(5,120,196);env.touch(5,80,55);env.notification(frame());
    if(mode==='reject-second-chunk')env.writeFailure(2);
    if(mode.startsWith('hang')||mode==='hung-timeout')env.writeHang(true);
    if(mode==='storage-stage')env.storageFailure('sw-config-stage.json');
    if(mode==='storage-active')env.storageFailure('sw-config.json',true);
    running.core.action('preset_update',{dynamic_assist:20});await flush();
    const saved=JSON.parse(JSON.stringify(running.core.view().config));
    if(mode==='hang-cancel')env.touch(5,44,221);
    if(mode==='hang-disconnect')env.loss();
    for(let ms=300;ms<=10500;ms+=100){
      env.advance(ms);await flush();
      if(mode!=='hang-disconnect')env.notification(frame(41,mode==='mismatch'?51:mode==='confirmation-timeout'?128:20,61));
    }
    const state=JSON.parse(JSON.stringify(running.core.view()));
    assert.equal(state.preset_attempt.pending,false);
    if(mode.startsWith('storage')){
      assert.equal(state.preset_attempt.status,'Confirmed');assert.ok(state.persistence_error);assert.equal(saved.presets[0].configured,false);
      env.context.require('sw-render').draw(env.context.graphics,state);snapshot(env,mode);
      running.stop();env.advance(10500);await flush();env.storageFailure(null);const recovered=env.start();
      assert.equal(recovered.core.view().config.presets[0].configured,false);
      assert.equal(recovered.core.view().preset_attempt,null);
      results.push({mode,expected:'wheel confirmed despite failed local save; restart restores previous good slots; no replay',observed:'passed',attempt:state.preset_attempt,storage_warning:recovered.core.view().persistence_error});recovered.stop();
    }else{
      assert.equal(state.preset_attempt.status,'Not confirmed',mode);
      const count=env.bleWrites.length;env.writeHang(false);env.settleWrite();await flush();assert.equal(env.bleWrites.length,count,'late native completion cannot send the tail');
      if(mode==='hang-disconnect'){env.advance(11500);await flush();assert.equal(env.bleWrites.length,count,'reconnect cannot replay the write');}
      results.push({mode,expected:'bounded unconfirmed result; no unsent tail or reconnect replay',observed:'passed',attempt:state.preset_attempt,chunks:env.bleWrites});running.stop();
    }
  }
  evidence.native_failures=results;console.log('watch native partial/hung writes, cancel/disconnect, timeout and interrupted Storage recovery: passed');
}
(async()=>{
  const {env,running}=await connected();env.advance(200);
  env.touch(0,120,10);env.touch(1,120,110);
  env.touch(5,120,196);
  assert.equal(running.core.view().screen,'preset_slots','Settings → Presets through physical input');
  env.touch(5,80,55);assert.equal(running.core.view().preset_draft,null);
  env.notification(frame());env.advance(400);
  assert.equal(running.core.view().preset_draft.pedal_sensitivity,41);
  env.touch(5,120,80);
  assert.ok(running.core.view().preset_input,'rendered name value opens keypad');
  env.touch(5,148,196);env.touch(5,49,73);env.touch(5,176,226);
  assert.equal(running.core.view().config.presets[0].name,'A');
  assert.equal(env.bleWrites.length,0,'native name save emits no wheel packet');
  env.touch(5,220,20);env.touch(5,120,80);env.touch(5,189,73);env.touch(5,49,73);env.touch(5,176,226);await flush();
  assert.deepEqual(env.bleWrites,['4c6441700f01028080801ff753d033']);
  assert.equal(running.core.view().preset_attempt.status,'confirming');
  env.advance(500);env.notification(frame(31));env.advance(600);env.notification(frame(31));env.advance(800);
  assert.equal(running.core.view().preset_editor.current_confirmation,true);
  assert.ok(env.context.graphics.ops.some(op=>op.kind==='text'&&/confirmed/.test(op.value)),'actual Graphics renders fresh confirmation');
  assert.equal(JSON.parse(env.context.storage['sw-config.json']).presets[0].pedal_sensitivity,31);
  running.core.action('preset_cancel');running.core.action('swipe',{direction:'right'});running.core.action('swipe',{direction:'right'});env.advance(1000);
  assert.ok(env.context.graphics.ops.some(op=>op.kind==='text'&&/Pedal sensitivity.*Confirmed/.test(op.value)),'dashboard identifies the confirmed field after leaving, without a whole-preset label');
  env.advance(1800);
  assert.ok(env.context.graphics.ops.some(op=>op.kind==='text'&&/Pedal sensitivity.*Unconfirmed/.test(op.value)),'stale dashboard drops current field confirmation');
  running.stop();console.log('watch native preset editor input/render/Storage/writer: passed');
  await laptopTrace();
  await failures();
  evidence.source_sha256={};for(const name of fs.readdirSync(path.join(repo,'watch')).filter(name=>name.endsWith('.js')))evidence.source_sha256['watch/'+name]=crypto.createHash('sha256').update(fs.readFileSync(path.join(repo,'watch',name))).digest('hex');
  fs.writeFileSync(path.join(out,'runtime.json'),JSON.stringify(evidence,null,2)+'\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
