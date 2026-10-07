// Exercise actual watch entry, touch, saved Storage and active-high output.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {environment}=require('./runtime.cjs');
const env=environment(),running=env.start();env.advance(200);
env.touch(0,120,10);env.touch(1,120,90);env.advance(400);
env.touch(5,120,155);env.advance(600);
assert.equal(running.core.view().screen,'alerts','Settings Alerts row opens the physical editor');
env.touch(5,195,45);env.advance(800); // Enable with no threshold: Save must reject.
env.touch(5,170,214);env.advance(1000);
assert.equal(running.core.view().config.alerts.pwm.enabled,false);
assert.match(running.core.view().validation_error,/threshold/i);
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;');
const svg=env.context.graphics.ops.map(op=>op.kind==='text'?`<text x="${op.x}" y="${op.y+op.size}" font-size="${op.size}" text-anchor="${op.align===-1?'start':op.align===1?'end':'middle'}">${escape(op.value)}</text>`:op.kind==='line'?`<line x1="${op.x1}" y1="${op.y1}" x2="${op.x2}" y2="${op.y2}" stroke="white"/>`:`<rect x="${op.x1}" y="${op.y1}" width="${op.x2-op.x1}" height="${op.y2-op.y1}" fill="${op.kind==='fill'?'white':'none'}" stroke="white"/>`).join('\n');
fs.writeFileSync(path.resolve(__dirname,'../evidence/alerts-editor.svg'),`<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240"><rect width="240" height="240" fill="black"/><g fill="white" font-family="sans-serif">${svg}</g></svg>\n`);
running.core.action('alert_test',{alert:'lost'});
assert.equal(env.context.D16.state,1,'actual hardware adapter drives the installed active level');
env.advance(1150);assert.equal(env.context.D16.state,0,'weak lost pattern ends after 150ms');
env.touch(5,120,90);env.advance(1350);assert.equal(running.core.view().screen,'threshold');
env.touch(5,40,137);env.touch(5,120,177);env.touch(5,170,220);env.advance(1550);
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
const decimal=environment(),decimalApp=decimal.start();decimal.advance(200);begin(decimalApp);decimal.touch(5,120,90);
decimal.touch(5,40,177);decimal.touch(5,120,97);decimal.touch(5,170,220);decimal.touch(5,195,45);decimal.touch(5,170,220);
assert.equal(decimalApp.core.view().config.alerts.pwm.threshold,.5);assert.equal(decimalApp.core.view().config.alerts.pwm.enabled,true);decimalApp.stop();
console.log('watch physical editor and actual active-high motor adapter: passed');
