const assert=require('node:assert/strict');
const {environment,flush,dispatchRecordedInput,snapshot,evidence,laptopTrace,plain,readJson,watchSourceHashes}=require('./harness.cjs');
const laptop=readJson(laptopTrace('touch-layout/navigation-laptop.json'));
(async()=>{
 const env=environment();let running=env.start(),now=200;env.advance(now);const states=[];
 for(const [index,event] of laptop.timeline.entries()){
  dispatchRecordedInput(env,event);
  env.advance(now+=200);await flush();const state=plain(running.core.view());
  if(event.expected){assert.equal(state.screen,event.expected.screen,'event '+index);if(event.expected.page!==undefined)assert.equal(state.preset_page,event.expected.page,'event '+index);if(event.expected.input!==undefined)assert.equal(state.preset_input.text,event.expected.input,'event '+index);}
  assert.equal(env.bleWrites.length,0);
  states.push({input:event,screen:state.screen,page:state.preset_page,keypad:state.preset_input,draft:state.preset_draft,saved:state.config,storage_effects:env.storageEffects.length,graphics:plain(env.context.graphics.ops)});
 }
 const expected=readJson('docs/acceptance/scenarios/local-presets.json').fresh;expected.revision=1;expected.presets[0].name='A';expected.presets[0].pedal_sensitivity=31;
 assert.deepEqual(plain(running.core.view().config),expected);
 snapshot(env,'navigation-dashboard');const saved=plain(running.core.view().config);running.stop();running=env.start();assert.deepEqual(plain(running.core.view().config),saved);assert.equal(running.core.view().preset_editor,null);
 // Shared Settings hierarchy retains independent alert Cancel/back behavior.
 env.advance(now+=200);env.touch(0,120,10);env.touch(1,120,110);env.touch(5,120,155);assert.equal(running.core.view().screen,'alerts');env.touch(2,120,20);assert.equal(running.core.view().screen,'settings');env.touch(2,120,20);assert.equal(running.core.view().screen,'dashboard');
 running.stop();
 evidence.json('watch/evidence/touch-layout/navigation.json',{spec:'docs/design/preset-value-editor.md',provenance:'exact laptop pointer trace through production CST816 interrupts/main/controls/Graphics/native Storage; simulated inputs, clock, BLE, flash; no device operations',states,saved,storage:env.storageEffects,packets:[],outcome:'passed',source_sha256:watchSourceHashes()});
 console.log('watch exact laptop swipe trace, input, rendering, Storage and alert hierarchy: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
