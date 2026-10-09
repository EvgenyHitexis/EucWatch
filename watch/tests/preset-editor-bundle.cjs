// Complete bundle build/staging/activation rehearsal and versioned runtime.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),child=require('node:child_process');
const {environment,flush}=require('./runtime.cjs');
const {frame}=require('./preset-editor.cjs');
const repo=path.resolve(__dirname,'../..'),source=path.join(repo,'watch');
const digest=crypto.createHash('sha256');for(const name of fs.readdirSync(source).filter(name=>name.endsWith('.js')).sort())digest.update(name).update(fs.readFileSync(path.join(source,name)));
const version=digest.digest('hex').slice(0,8),directory=path.join(repo,'.test-output/watch-preset-editor',version);
fs.mkdirSync(path.dirname(directory),{recursive:true});
const python=process.env.EUCWATCH_TEST_PYTHON||path.join(repo,'experiments/laptop-feasibility/.venv/bin/python');
function command(args){return JSON.parse(child.execFileSync(python,[path.join(repo,'scripts/watch-bundle.py'),...args],{cwd:repo,encoding:'utf8'}));}
if(!fs.existsSync(directory))command(['build','--version',version,'--output',directory]);
command(['verify',directory]);const rehearsal=command(['rehearse',directory]);
assert.equal(rehearsal.outcome.status,'verified');assert.equal(rehearsal.writes.at(-1),'sw-active.json');
const manifest=JSON.parse(fs.readFileSync(path.join(directory,'manifest.json'),'utf8'));
assert.ok(manifest.files.some(row=>row.name==='sw-'+version+'-preset-editor'));
function install(env){for(const row of manifest.files)env.context.storage[row.name]=fs.readFileSync(path.join(directory,row.name+'.bin'),'utf8');env.context.storage['sw-active.json']=JSON.stringify({schema:1,version,main:manifest.main});}
(async()=>{
  const env=environment();install(env);env.boot(manifest.recovery);const running=env.context.global.ShermanWatch;
  assert.ok(running,'versioned main starts from the independent recovery pointer');env.advance(200);
  running.transport.discover();running.transport.select('11:22:33:44:55:66 public');await flush();
  env.touch(0,120,10);env.touch(1,120,110);env.touch(5,120,196);env.touch(5,80,187);env.notification(frame(44,54,64));
  assert.equal(running.core.view().preset_draft.id,4);
  running.core.action('preset_update',{name:'Versioned'});running.core.action('preset_update',{pedal_sensitivity:30});await flush();
  env.advance(300);env.notification(frame(30,54,64));env.advance(400);env.notification(frame(30,54,64));
  assert.equal(running.core.view().preset_editor.current_confirmation,true);
  const config=JSON.parse(JSON.stringify(running.core.view().config));running.stop();env.advance(400);await flush();
  const newer=environment();install(newer);newer.context.storage['sw-config.json']=JSON.stringify(config);newer.boot(manifest.recovery);
  const updated=newer.context.global.ShermanWatch;assert.deepEqual(JSON.parse(JSON.stringify(updated.core.view().config)),config);
  assert.equal(updated.core.view().preset_attempt,null);assert.equal(updated.core.view().confirmed_preset,null);assert.equal(newer.bleWrites.length,0);
  assert.ok(env.context.imports.filter(name=>name.startsWith('sw-')).every(name=>name.startsWith('sw-'+version+'-')),'all compiled module references stay in this bundle');
  updated.stop();
  const held=environment();install(held);held.context.BTN1.state=1;held.boot(manifest.recovery);assert.ok(held.context.global.ShermanRecovery);
  assert.equal(held.context.imports.filter(name=>name.startsWith('sw-')).length,0,'held-button recovery bypasses all application imports');
  const failed=environment();install(failed);delete failed.context.storage[manifest.main];failed.boot(manifest.recovery);
  assert.ok(failed.context.global.ShermanRecovery);assert.ok(failed.context.storage['sw-starting'],'failed startup retains independent recovery guard');
  fs.writeFileSync(path.join(source,'evidence/preset-editor/bundle.json'),JSON.stringify({issue:42,manifest,rehearsal,versioned_runtime:'editor packet/readback and existing local configuration survive compatible application startup; no command or confirmation replay',native_imports:env.context.imports.filter(name=>name.startsWith('sw-')),recovery:'held button bypasses imports; absent main retains recovery guard',artifact:path.relative(repo,directory),hardware:'all hardware, flash capacity and authorization are simulated; display/input/vibration, memory fit, live controls and deployment pending'},null,2)+'\n');
  console.log('complete versioned watch bundle, synthetic staging/activation and independent recovery: passed ('+version+')');
})().catch(error=>{console.error(error);process.exitCode=1;});
