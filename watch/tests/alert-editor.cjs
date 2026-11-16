// The alert editor module alone: no clock, battery, wheel session or store.
const assert=require('node:assert/strict');
const {alertEditor,plain,replayAlertEditorTrace}=require('./harness.cjs');
{
  // The shared trace: the laptop alert editor replays the same steps (tests/test_alert_editor.py).
  const trace=replayAlertEditorTrace('docs/acceptance/scenarios/alert-editor-keys.json');
  console.log(`watch alert editor shared key-sequence trace: ${trace.steps.length} steps matched`);
}
{
  // A missing threshold names the alert as the editor's title does; tests/test_alert_editor.py pins the same messages.
  for(const [page,alert,message] of [[0,'pwm','A threshold is required to enable High PWM'],
    [1,'speed','A threshold is required to enable High speed'],[2,'battery','A threshold is required to enable Low wheel battery']]){
    const {act,view}=alertEditor();act('alerts_page',{page});act('alerts_update',{alert,enabled:true});
    assert.throws(()=>act('alerts_save'),error=>error.message===message,alert);
    assert.equal(view().reason,'Error: '+message,alert);
  }
  console.log('watch alert editor missing-threshold message per alert: passed');
}
{
  // The core passes the reason it shares with the Preset editor: a refused Set value writes it, the next accepted
  // action clears it. Cancel leaves the editor closed.
  let held=null;const reason={get:()=>held,set:value=>{held=value||null;}};
  const {editor,act}=alertEditor(null,reason);
  act('threshold_begin',{alert:'pwm'});for(const key of '101')act('threshold_key',{key});
  assert.throws(()=>act('threshold_done'),/Threshold outside supported range/);
  assert.equal(held,'Threshold outside supported range');
  act('threshold_cancel');assert.equal(held,null);
  assert.equal(editor.editing(),true);
  assert.deepEqual(act('alerts_cancel'),{leave:true});assert.equal(plain(editor.view()).draft,null);assert.equal(editor.editing(),false);
  console.log('watch alert editor shared reason and Cancel: passed');
}
