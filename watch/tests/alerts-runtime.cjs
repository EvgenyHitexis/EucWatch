// Exercise actual watch entry, touch, saved Storage and active-high output.
const assert=require('node:assert/strict');
const {environment,evidence}=require('./harness.cjs');
const env=environment(),running=env.start();env.advance(200);
env.touch(0,120,10);env.touch(1,120,120);env.advance(400);
env.touch(5,120,155);env.advance(600);
assert.equal(running.core.view().screen,'alerts','Settings Alerts row opens the physical editor');
env.touch(5,195,72);env.advance(800); // Enable with no threshold: Save must reject.
env.touch(5,170,214);env.advance(1000);
assert.equal(running.core.view().config.alerts.pwm.enabled,false);
assert.match(running.core.view().validation_error,/threshold/i);
evidence.svg('watch/evidence/local-presets/regression-alerts-editor.svg',env.context.graphics.ops,'regression');
running.core.action('alert_test',{alert:'lost'});
assert.equal(env.context.D16.state,1,'actual hardware adapter drives the installed active level');
env.advance(1150);assert.equal(env.context.D16.state,0,'weak lost pattern ends after 150ms');
env.touch(5,120,120);env.advance(1350);assert.equal(running.core.view().screen,'threshold');
env.touch(5,46,138);env.touch(5,120,177);env.touch(5,170,220);env.advance(1550);
assert.equal(running.core.view().alerts_draft.pwm.threshold,70);
env.touch(5,170,220);env.advance(1750);assert.equal(running.core.view().config.alerts.pwm.threshold,70);
assert.ok(env.context.storage['sw-config.json'],'actual main persists explicit Save in Storage');
running.stop();const restarted=env.start();env.advance(1950);
assert.equal(restarted.core.view().config.alerts.pwm.threshold,70);assert.equal(restarted.core.view().config.alerts.pwm.enabled,true);
function begin(app){app.core.action('swipe',{direction:'down',from_top:true});app.core.action('alerts_begin');}
begin(restarted);restarted.core.action('alerts_update',{alert:'pwm',threshold:71});env.storageFailure('sw-config-stage.json');restarted.core.action('alerts_save');
assert.equal(restarted.core.view().config.alerts.pwm.threshold,70);assert.equal(restarted.core.view().alerts_draft.pwm.threshold,71);assert.match(restarted.core.view().persistence_error,/save failed/i);
env.storageFailure('sw-config.json',true);restarted.core.action('alerts_save');assert.equal(restarted.core.view().config.alerts.pwm.threshold,70);
restarted.stop();env.storageFailure(null);const recovered=env.start();assert.equal(recovered.core.view().config.alerts.pwm.threshold,70);assert.match(recovered.core.view().persistence_error,/Recovered previous good/);
for(const [alert,starts,stops] of [['lost',[.2],[.35]],['pwm',[.2,.5,.8],[.35,.65,.95]],['speed',[.2,.5],[.35,.65]],['battery',[.2],[.7]]]){
  const motor=environment(),app=motor.start();motor.advance(200);app.core.action('alert_test',{alert});motor.advance(1200);
  const events=Array.from(app.core.view().vibration.output.events);
  assert.deepEqual(events.filter(row=>row.phase==='start').map(row=>Math.round(row.at_s*100)/100),starts);
  assert.deepEqual(events.filter(row=>row.phase==='stop').map(row=>Math.round(row.at_s*100)/100),stops);
  assert.equal(motor.context.D16.state,0);app.stop();app.core.action('alert_test',{alert:'lost'});assert.equal(motor.context.D16.state,0,'stopped entry cannot restart motor output');
}
const frozen=environment(),frozenApp=frozen.start({clock:{now:()=>0}});frozen.advance(200);frozenApp.core.action('alert_test',{alert:'pwm'});frozen.advance(1000);
assert.equal(frozen.context.D16.state,0,'independent motor deadline stops output when behavior clock does not progress');
assert.equal(frozenApp.core.view().vibration.output.events.at(-1).source,'deadline');frozenApp.stop();
const first=environment(),firstApp=first.start();begin(firstApp);firstApp.core.action('alerts_update',{alert:'pwm',enabled:true,threshold:70});first.storageFailure('sw-config.json',true);firstApp.core.action('alerts_save');
assert.ok(first.context.storage['sw-config-backup.json'],'first interrupted activation has a validated previous default copy');
firstApp.stop();first.storageFailure(null);const firstRecovered=first.start();assert.equal(firstRecovered.core.view().config.alerts.pwm.enabled,false);assert.match(firstRecovered.core.view().persistence_error,/Recovered previous good/);
recovered.stop();delete env.context.storage['sw-config.json'];const absent=env.start();assert.equal(absent.core.view().config.alerts.pwm.threshold,70);assert.match(absent.core.view().persistence_error,/Recovered previous good/);
const decimal=environment(),decimalApp=decimal.start();decimal.advance(200);begin(decimalApp);decimal.touch(5,120,120);
decimal.touch(5,40,177);decimal.touch(5,120,103);decimal.touch(5,170,220);decimal.touch(5,195,72);decimal.touch(5,170,220);
assert.equal(decimalApp.core.view().config.alerts.pwm.threshold,.5);assert.equal(decimalApp.core.view().config.alerts.pwm.enabled,true);decimalApp.stop();
// A refused Save keeps the alert's title above its explanation, all above the Enabled control (y 52); the laptop
// Canvas draws the same lines (frontend/src/main.ts).
for(const [page,lines] of [[0,['High PWM','A threshold is required','to enable High PWM']],[1,['High speed','A threshold is required','to enable High speed']],
  [2,['Low wheel battery','A threshold is required','to enable Low wheel','battery']]]){
  const screen=environment(),app=screen.start();screen.advance(200);begin(app);
  for(let next=0;next<page;next++)screen.touch(5,208,22);
  screen.touch(5,195,72);screen.touch(5,170,214);screen.advance(400);
  assert.match(app.core.view().validation_error,/threshold is required/);
  const heading=screen.context.graphics.ops.filter(op=>op.kind==='text'&&op.x===120&&op.y<52);
  assert.deepEqual(heading.map(op=>op.value),lines,`alert page ${page}`);
  heading.forEach((op,index)=>{assert.ok(op.y+op.size<=52&&op.width<=128,`${op.value} fits between the arrows`);if(index)assert.ok(op.y>=heading[index-1].y+heading[index-1].size,`${op.value} below the line before`);});
  app.stop();
}
console.log('watch physical editor and actual active-high motor adapter: passed');
