// The alert editor module alone: no clock, battery, wheel session or store.
const assert=require('node:assert/strict');
const {environment,plain,readJson}=require('./harness.cjs');
function editing(alerts){
  const env=environment(),config=env.require('sw-configuration').defaults(),editor=env.require('sw-alert-editor').create();
  if(alerts)config.alerts=plain(alerts);editor.open(config.alerts);
  const act=(name,payload={})=>plain(editor.action(name,plain(payload),config));
  return {config,editor,act,view:()=>plain(editor.view())};
}
const message=value=>value&&String(value).replace(/^Error: /,'');
{
  // The shared trace: the laptop alert editor reads the same file (tests/test_alert_editor.py).
  const trace=readJson('docs/acceptance/scenarios/alert-editor-keys.json');
  const {config,act,view}=editing(trace.alerts);
  trace.steps.forEach((step,index)=>{
    let refused=null,result=null;
    try{result=act(step.action,step.payload);}catch(error){refused=message(error.message);}
    const state=view(),observed={page:state.page,entry:state.entry,draft:state.draft,refused,reason:message(state.reason)};
    if(result&&result.save)observed.saved={revision:result.save.revision,alerts:result.save.alerts};
    assert.deepEqual(observed,step.expect,`step ${index}: ${JSON.stringify(step)}`);
  });
  assert.equal(config.revision,0,'Save returns a replacement and leaves the saved configuration alone');
  console.log(`watch alert editor shared key-sequence trace: ${trace.steps.length} steps matched`);
}
{
  // Watch rules the laptop does not share, kept from the core: Set value refuses an out-of-range or digitless entry and
  // says so in the reason the core shares with the Preset editor; Cancel needs no open entry.
  let shared=null;const reason={get:()=>shared,set:value=>{shared=value||null;}};
  const env=environment(),config=env.require('sw-configuration').defaults(),editor=env.require('sw-alert-editor').create(reason);
  editor.open(config.alerts);
  for(const [alert,text] of [['pwm','101'],['speed','3276.8'],['battery','.']]){
    editor.action('threshold_begin',{alert},config);for(const key of text)editor.action('threshold_key',{key},config);
    assert.throws(()=>editor.action('threshold_done',{},config),/Threshold outside supported range/);
    assert.equal(shared,'Threshold outside supported range');assert.equal(plain(editor.view()).draft[alert].threshold,null);
    editor.action('threshold_cancel',{},config);assert.equal(shared,null);
  }
  assert.equal(editor.action('threshold_cancel',{},config),null);
  assert.equal(editor.editing(),true);
  assert.deepEqual(plain(editor.action('alerts_cancel',{},config)),{leave:true});assert.equal(editor.view().draft,null);assert.equal(editor.editing(),false);
  console.log('watch alert editor Set value range, shared reason and Cancel: passed');
}
