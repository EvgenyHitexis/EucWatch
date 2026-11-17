// Execute original main + actual hardware/native-driver modules with fake pins/radio.
const assert=require('node:assert/strict');
const {environment,flush,fixture,evidence}=require('./harness.cjs');
(async()=>{
  // Every journey's paints, in order, recorded from the present(state) hook production main gives the core: main
  // creates the core through the environment's cached sw-app module, so wrapping its create sees each call. A repeated
  // identical frame is kept, so an extra paint shows up in the evidence.
  const paints={};
  function journey(name){
    const env=environment(),app=env.require('sw-app'),create=app.create,presented=paints[name]=[];
    app.create=options=>create({...options,present:state=>{presented.push({at_s:state.elapsed_s,screen:state.screen,awake:state.awake,recovery:state.recovery});options.present(state);}});
    return env;
  }
  // Harness contract: Espruino's require caches per device; clearTimeout(undefined) is refused.
  const first=environment(),second=environment();
  assert.equal(first.require('sw-app'),first.require('sw-app'),'require caches modules per environment');
  assert.notEqual(first.require('sw-app'),second.require('sw-app'),'each environment has its own module cache');
  assert.throws(()=>first.context.clearTimeout(undefined),/clearTimeout\(undefined\)/);
  const env=journey('navigation'),running=env.start();env.advance(200);
  assert.equal(env.context.D16.state,0,'installed active-high vibration must remain inactive at startup');
  assert.equal(env.context.graphics.buffer.byteLength,7200);
  assert.equal(running.core.view().dashboard.watch_battery_percent,'50');
  assert.deepEqual(env.registers[0],[0x50000700+31*4,2]);
  assert.equal([...env.watches.values()].find(w=>w.pin===env.context.D19).options.debounce,500);
  for(const [voltage,percent] of [[3.4,0],[3.5,0],[3.85,50],[4.19,100],[4.3,100]]){
    env.voltage(voltage);running.core.action('battery_refresh');assert.equal(running.core.view().watch_battery.percent,percent);
  }
  const before=env.adc();env.advance(30200);assert.ok(env.adc()>before);assert.equal(running.core.view().awake,false);
  env.button(true);env.advance(30500);assert.equal(running.core.view().feedback,'Wake only');
  env.button(false);assert.equal(running.core.view().button.wake_cycle,false);
  env.touch(0,120,10);env.touch(1,120,90);assert.equal(running.core.view().screen,'settings');
  env.touch(5,120,100);assert.equal(running.core.view().awake,false);
  assert.ok(env.context.i2cWrites.some(row=>row[1]===0xE5&&row[2]===3));
  env.button(true);env.button(false);env.advance(30900);
  env.touch(5,120,40);assert.equal(running.core.view().screen,'connection');
  env.advance(31300);env.touch(5,120,55);await flush();
  assert.equal(running.core.view().screen,'dashboard','selecting a wheel returns to the Riding dashboard');
  assert.equal(running.transport.status().link,'subscribed');assert.equal(running.core.view().fresh,false);
  const rows=fixture.rows;
  for(const row of rows.slice(0,5))env.notification(Buffer.from(row.raw_hex,'hex'));
  assert.equal(running.core.view().dashboard.wheel_battery_percent,'97');env.advance(31500);
  // Connect wheel paints Wheel selection (again at 31.1 s, with the discovered wheel), and selecting a wheel paints the
  // Riding dashboard at once. The selection comes at 31.3 s, when the 0.2 s paint window is open, so a paint from inside
  // the transport's request would show here as one more Wheel selection frame, with the dashboard 0.2 s later.
  assert.deepEqual(paints.navigation.filter(paint=>paint.at_s>=30.9&&paint.at_s<=31.3).map(paint=>[paint.at_s,paint.screen]),
    [[30.9,'connection'],[31.1,'connection'],[31.3,'dashboard']]);
  assert.equal(running.core.view().diagnostics.memory.simulated,true);
  evidence.svg('watch/evidence/local-presets/regression-dashboard.svg',env.context.graphics.ops,'regression');
  const old=running.core.view().session;env.loss();assert.equal(running.core.view().fresh,false);env.advance(32500);await flush();
  assert.ok(running.core.view().session>old);assert.equal(running.core.view().fresh,false);
  for(const row of rows.slice(0,5))env.notification(Buffer.from(row.raw_hex,'hex'));assert.equal(running.core.view().fresh,true);
  running.stop();
  env.advance(32700);await flush();assert.equal(env.context.graphics.isOn,false,'late disconnect cannot wake stopped hardware');
  assert.equal(env.watches.size,0);
  const failed=journey('disconnect_failure'),failedApp=failed.start();failedApp.transport.discover();failedApp.transport.select('11:22:33:44:55:66 public');await flush();
  failed.disconnectFailure(true);failedApp.transport.disconnect();
  assert.equal(failedApp.transport.status().link,'failed');
  assert.throws(()=>failedApp.transport.select('11:22:33:44:55:66 public'),/Disconnect/);
  failed.disconnectFailure(false);failedApp.transport.disconnect();failed.advance(0);await flush();assert.equal(failedApp.transport.status().link,'disconnected');
  const delayed=journey('delayed_disconnect'),delayedApp=delayed.start();delayedApp.transport.discover();delayedApp.transport.select('11:22:33:44:55:66 public');await flush();
  delayed.disconnectDelay(500);delayedApp.transport.disconnect();
  assert.equal(delayedApp.transport.status().busy,true);assert.equal(delayedApp.core.view().fresh,false);
  assert.throws(()=>delayedApp.transport.select('11:22:33:44:55:66 public'),/Disconnect/);
  delayed.advance(500);await flush();assert.equal(delayedApp.transport.status().link,'disconnected');assert.equal(delayedApp.transport.status().connected,false);
  const subscription=journey('subscription_failure'),subscriptionApp=subscription.start();subscription.subscriptionFailure(true);subscription.disconnectFailure(true);
  subscriptionApp.transport.discover();subscriptionApp.transport.select('11:22:33:44:55:66 public');await flush();
  assert.equal(subscriptionApp.transport.status().link,'failed');assert.equal(subscriptionApp.core.view().connected,false);
  assert.equal(subscriptionApp.transport.status().connected,true,'failed cleanup retains transport ownership');
  assert.throws(()=>subscriptionApp.transport.select('11:22:33:44:55:66 public'),/Disconnect/);
  const scanning=journey('discovery_timeout'),scanningApp=scanning.start();scanning.scanHang(true);scanningApp.transport.discover();scanning.advance(6000);
  assert.equal(scanningApp.transport.status().link,'failed');assert.match(scanningApp.transport.status().error,/Discovery timed out/);
  const retrying=journey('reconnect_retry'),retryApp=retrying.start();retryApp.transport.discover();retryApp.transport.select('11:22:33:44:55:66 public');await flush();
  for(const row of rows.slice(0,5))retrying.notification(Buffer.from(row.raw_hex,'hex'));
  const retrySession=retryApp.core.view().session;retrying.connectFailureCount(1);retrying.loss();retrying.advance(1000);await flush();
  assert.equal(retryApp.transport.status().active,true,'a failed reconnect retains the bounded recovery intent');
  assert.equal(retryApp.transport.status().link,'reconnecting');
  retrying.advance(3000);await flush();assert.equal(retryApp.transport.status().link,'subscribed');
  assert.equal(retrying.connectCalls(),3);assert.ok(retryApp.core.view().session>retrySession);
  assert.equal(retryApp.core.view().fresh,false,'successful reconnect requires new telemetry');
  for(const row of rows.slice(0,5))retrying.notification(Buffer.from(row.raw_hex,'hex'));assert.equal(retryApp.core.view().fresh,true);
  const limited=journey('reconnect_limit'),limitedApp=limited.start();limitedApp.transport.discover();limitedApp.transport.select('11:22:33:44:55:66 public');await flush();
  limited.connectFailureCount(10);limited.loss();
  for(const elapsed of [1000,3000,7000]){limited.advance(elapsed);await flush();}
  assert.equal(limited.connectCalls(),4);assert.equal(limitedApp.transport.status().active,false);
  assert.equal(limitedApp.transport.status().link,'failed');limited.advance(20000);await flush();assert.equal(limited.connectCalls(),4);
  const initial=journey('initial_connect_failure'),initialApp=initial.start();initial.connectFailureCount(1);initialApp.transport.discover();initialApp.transport.select('11:22:33:44:55:66 public');await flush();
  assert.equal(initialApp.transport.status().link,'failed');assert.equal(initialApp.transport.status().active,false);
  initial.advance(20000);await flush();assert.equal(initial.connectCalls(),1);
  const replaced=journey('replaced_session'),replacedApp=replaced.start();replacedApp.transport.discover();replacedApp.transport.select('11:22:33:44:55:66 public');await flush();
  replacedApp.core.action('session_start');replaced.notification(Buffer.from(rows[0].raw_hex,'hex'));replaced.advance(50);await flush();
  assert.equal(replacedApp.transport.status().active,false);assert.equal(replacedApp.transport.status().connected,false);
  assert.equal(replacedApp.core.view().diagnostics.valid_frames,0);
  const prolonged=journey('recovery_hold'),prolongedApp=prolonged.start();prolongedApp.transport.discover();prolongedApp.transport.select('11:22:33:44:55:66 public');await flush();
  prolonged.button(true);prolonged.advance(30100);await flush();
  assert.equal(prolongedApp.core.view().recovery,true);assert.equal(prolongedApp.transport.status().active,false);
  assert.equal(prolonged.context.storage['sw-recovery'],'hold');assert.equal(prolonged.context.resets,1);
  const held=environment();held.context.BTN1.state=1;held.boot();
  assert.equal(held.context.imports.includes('sw-main'),false);assert.ok(held.context.global.ShermanRecovery);
  const broken=environment();broken.context.storage['sw-active.json']=JSON.stringify({main:'sw-missing'});broken.boot();
  assert.ok(broken.context.global.ShermanRecovery.reason.includes('startup failed'));
  assert.deepEqual(broken.context.watchdog,[30,false]);
  evidence.json('watch/evidence/local-presets/regression-offline.json',{issue:32,provenance:'Node VM executes original ES5 application/hardware; fake radio/pins/clock; SVG replays Graphics operations, host fonts',fixture:'experiments/laptop-feasibility/evidence/fixture-recording.jsonl',observed:'240x240 1-bpp buffer7200; sourcebattery97/avg4.09; battery sampling/pinrelease; raw816 nav/wake; D16 startup0 inactive; failed reconnect retries up to3 and later recovery requires newtelemetry; independent recovery beforeimports',hardware_acceptance:'pending: no deployment, device memory, radio, fonts, timing or physical controls measured',paints});
  console.log('actual watch entry/hardware, battery, touch/button, fake direct BLE and recovery: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
