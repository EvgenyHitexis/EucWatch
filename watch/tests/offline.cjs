// Public watch application boundary, running production ES5 modules offline.
const assert = require('node:assert/strict');
const { environment, fixture, frame } = require('./harness.cjs');
function scenario() {
  let time = 0;
  const app = environment().require('sw-app').create({ clock: { now: () => time },
    battery: () => ({ voltage: 3.9, percent: 57, charging: false }) });
  return { app, at: value => { time = value; app.tick(); } };
}
const rows = fixture.rows;
const first = scenario();
const token = first.app.action('session_start').session;
first.app.action('connected', { session: token });
for (const row of rows) {
  first.at(row.receipt_elapsed_s);
  first.app.receive(token, Uint8Array.from(Buffer.from(row.raw_hex, 'hex')));
}
assert.equal(first.app.view().dashboard.speed, '0');
assert.equal(first.app.view().dashboard.pwm, '2');
assert.equal(first.app.view().dashboard.wheel_battery_percent, '97');
assert.equal(first.app.view().dashboard.average_cell_voltage, '4.09');
assert.equal(first.app.view().diagnostics.valid_frames, 3);
console.log('watch source fixture dashboard: passed');

const ridingFrame={length:87,voltage:135,speed:25,pwm:45,firmware:6010};
for (const length of [75,77,87,99]) {
  for (let split=1;split<length;split++) {
    const test=scenario();const id=test.app.action('session_start').session;
    test.app.action('connected',{session:id});const bytes=frame({...ridingFrame,length});
    test.app.receive(id,bytes.subarray(0,split));test.app.receive(id,bytes.subarray(split));
    assert.equal(test.app.view().dashboard.speed,'25');
    assert.equal(test.app.view().diagnostics.valid_frames,1);
  }
}
const malformed=scenario();const id=malformed.app.action('session_start').session;
malformed.app.action('connected',{session:id});malformed.app.receive(id,frame(ridingFrame));
malformed.at(.6);const corrupt=frame(ridingFrame);corrupt[10]^=1;
malformed.app.receive(id,Buffer.concat([corrupt,frame({...ridingFrame,firmware:7000}),Buffer.alloc(10000,42)]));
assert.equal(malformed.app.view().diagnostics.valid_frames,1);
assert.ok(malformed.app.view().diagnostics.retained_bytes<=98);
malformed.at(1.01);assert.equal(malformed.app.view().dashboard.speed,'—');
assert.equal(malformed.app.view().dashboard.wheel_battery_dimmed,true);
malformed.app.receive(id,Buffer.concat([frame({...ridingFrame,length:75}),frame({...ridingFrame,length:99})]));
assert.equal(malformed.app.view().diagnostics.valid_frames,3);
assert.equal(malformed.app.view().fresh,true);
malformed.app.action('disconnect',{session:id});
assert.equal(malformed.app.view().fresh,false);
const newer=malformed.app.action('session_start').session;
malformed.app.action('connected',{session:newer});malformed.app.receive(id,frame(ridingFrame));
assert.equal(malformed.app.view().fresh,false);
malformed.app.receive(newer,frame(ridingFrame));assert.equal(malformed.app.view().fresh,true);
for (const [voltage,expected] of [[110,'0'],[119.02,'0'],[135,'55'],[148.05,'100'],[155,'100']]) {
  malformed.app.receive(newer,frame({...ridingFrame,voltage}));assert.equal(malformed.app.view().dashboard.wheel_battery_percent,expected);
}
malformed.app.receive(newer,frame({...ridingFrame,voltage:148.14}));assert.equal(malformed.app.view().dashboard.average_cell_voltage,'4.12');
let clock=0;const painted=[];
const timed=environment().require('sw-app').create({clock:{now:()=>clock},battery:()=>({percent:50,charging:false}),present:state=>painted.push({at:clock,state})});
const timedSession=timed.action('session_start').session;timed.action('connected',{session:timedSession});
for(let sample=1;sample<=200;sample++){
  clock=sample/100;timed.receive(timedSession,frame({...ridingFrame,speed:sample/10}));timed.tick();
}
for(let i=1;i<painted.length;i++)assert.ok(painted[i].at-painted[i-1].at>=.2-1e-9);
assert.ok(timed.view().diagnostics.max_receipt_to_paint_s<=.25);
clock=3;timed.tick();assert.equal(timed.view().fresh,false);
clock=3.2;timed.tick();assert.equal(painted.at(-1).state.dashboard.speed,'—');
const navigation=scenario();navigation.at(29);
navigation.app.action('interact');navigation.at(31);assert.equal(navigation.app.view().awake,true);
navigation.at(59);assert.equal(navigation.app.view().awake,false);
navigation.app.action('button_down');assert.equal(navigation.app.view().feedback,'Wake only');
navigation.at(62);navigation.app.action('button_hold');assert.equal(navigation.app.view().button.wake_cycle,true);
navigation.app.action('button_up');assert.equal(navigation.app.view().button.wake_cycle,false);
navigation.app.action('swipe',{direction:'left'});assert.equal(navigation.app.view().screen,'presets');
assert.equal(navigation.app.view().presets.length,4);
navigation.app.action('swipe',{direction:'right'});navigation.app.action('swipe',{direction:'down',from_top:false});
assert.equal(navigation.app.view().screen,'dashboard');
navigation.app.action('swipe',{direction:'down',from_top:true});assert.equal(navigation.app.view().screen,'settings');
navigation.app.action('sleep');assert.equal(navigation.app.view().awake,false);
navigation.app.action('button_down');navigation.app.action('button_up');
const riding=navigation.app.action('session_start').session;navigation.app.action('connected',{session:riding});
navigation.app.receive(riding,frame(ridingFrame));navigation.app.action('disconnect',{session:riding});
navigation.at(120);assert.equal(navigation.app.view().awake,true);
console.log('watch parsing, freshness, battery boundaries, navigation and wake cycles: passed');
