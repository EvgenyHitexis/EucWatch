// The core repaints only when its hand-written paint signature changes (watch/app.js). Every view field the renderer
// and the touch-target module read must be in that list, or be a derived field that changes only with fields in it.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {repoPath}=require('./harness.cjs');
const readers=['watch/render.js','watch/controls.js'];
// Derived view fields: left out of the signature because they change only when a field in it does.
const derived={
  fresh:{follows:['dashboard'],because:'dashboard.connection is Connected exactly when the telemetry is fresh'},
  disconnect_available:{follows:['transport'],because:'it is the transport status active or connected, and transport is that status'},
  preset_keys:{follows:['preset_input'],because:'the keys come from the entry field, its letter page and its case'},
  preset_previous_page:{follows:['preset_page'],because:'it is the page before the current one, wrapping at 4'},
  preset_next_page:{follows:['preset_page'],because:'it is the page after the current one, wrapping at 4'},
  presets_menu:{follows:['presets','dashboard','preset_attempt','recovery','awake'],
    because:'a slot is available when configured, fresh, no attempt pending, not in recovery and awake; the control output is fixed at creation'}
};

// The signature's entries without their state. prefix: 'awake', 'vibration.output_error', ...
function signatureEntries(app){
  const match=/signature\s*=\s*JSON\.stringify\(\[([^\]]*)\]\)/.exec(app);
  assert.ok(match,'watch/app.js computes signature = JSON.stringify([...])');
  return match[1].split(',').map(entry=>entry.trim()).map(entry=>{assert.match(entry,/^state(\.\w+)+$/,'a signature entry reads the view');return entry.slice(6);});
}
// Every state.<field>(.<field>)* chain a module reads, as 'field.sub'. Only dotted reads are seen, so check() refuses
// state[...] in the readers; the view reaching another module under another name would also get past this guard.
const reads=source=>[...new Set([...source.matchAll(/\bstate((?:\.\w+)+)/g)].map(match=>match[1].slice(1)))];
// Each read neither in the signature (itself or a parent of it) nor derived, as 'state.<path> (<module>)'.
function uncovered(sources,listed,derivedFields){
  const missing=[];
  for(const [module,source] of Object.entries(sources))for(const path of reads(source)){
    const covered=listed.some(entry=>path===entry||path.startsWith(entry+'.'))||Object.hasOwn(derivedFields,path.split('.')[0]);
    if(!covered)missing.push(`state.${path} (${module})`);
  }
  return missing;
}
function check(sources,app,derivedFields){
  for(const [module,source] of Object.entries(sources))assert.ok(!/\bstate\s*\[/.test(source),`${module} reads state[...], which this guard cannot follow`);
  const listed=signatureEntries(app),missing=uncovered(sources,listed,derivedFields);
  assert.deepEqual(missing,[],'read by the renderer but neither in the paint signature (watch/app.js) nor derived: '+missing.join(', '));
  const wholeFields=new Set(listed.filter(entry=>!entry.includes('.'))),readFields=new Set(Object.values(sources).flatMap(source=>reads(source).map(path=>path.split('.')[0])));
  for(const [field,entry] of Object.entries(derivedFields)){
    assert.ok(entry.follows.length&&typeof entry.because==='string'&&entry.because,`derived ${field} names what it follows and why`);
    for(const follows of entry.follows)assert.ok(wholeFields.has(follows),`derived ${field} follows ${follows}, which is not a whole field of the signature`);
    assert.ok(readFields.has(field),`derived ${field} is no longer read; drop it from the list`);
    assert.ok(!wholeFields.has(field),`derived ${field} is already in the signature`);
  }
}

const app=fs.readFileSync(repoPath('watch/app.js'),'utf8');
const sources=Object.fromEntries(readers.map(file=>[file,fs.readFileSync(repoPath(file),'utf8')]));
// The guard itself: a new read names its field and module, and a derived entry must follow signature fields.
assert.throws(()=>check({...sources,'watch/render.js':sources['watch/render.js']+'\ntext(state.new_field.label);'},app,derived),/state\.new_field\.label \(watch\/render\.js\)/);
assert.throws(()=>check(sources,app,{...derived,fresh:{follows:['telemetry'],because:'test'}}),/follows telemetry/);
assert.throws(()=>check({...sources,'watch/controls.js':sources['watch/controls.js']+'\nstate[name];'},app,derived),/controls\.js reads state\[/);
check(sources,app,derived);
console.log('watch paint signature covers every view field the renderer reads: passed');
