/* Original riding behavior; no globals from the previous watch application. */
var protocol = require('sw-protocol');
exports.create = function (options) {
  var clock = options.clock, battery = options.battery;
  var parser = protocol.create(), session = 0, connected = false, established = false;
  var telemetry = null, lastValid = null, validFrames = 0, rejectedFrames = 0;
  var awake = true, screen = 'dashboard', lastInteraction = clock.now();
  var buttonDown = false, wakeCycle = false, buttonStarted = null, recovery = false;
  var watchBattery = battery(), lastBattery = clock.now(), lastPaint = -Infinity;
  var lastView = '', feedback = '', paintCount = 0, receivedAt = null;
  var paintDuration=0,maxPaintDuration=0,visibleReceipt=null,maxReceiptToPaint=0;
  var core, devices=[], recoveryCalled=false;
  function fresh() { return connected && lastValid !== null && clock.now() - lastValid < 1; }
  function resetSession() { session++; connected = false; lastValid = null; parser = protocol.create(); buttonDown = false; wakeCycle = false; buttonStarted = null; }
  function percent(voltage) {
    return voltage <= 119.02 ? 0 : voltage >= 148.05 ? 100 : Math.max(0, Math.min(100, Math.round((voltage - 119.02) / 0.2903)));
  }
  function view() {
    var live = fresh(), values = telemetry;
    return { mode: 'watch', session: session, elapsed_s: clock.now(), connected: connected,
      fresh: live, awake: awake, screen: screen, recovery: recovery,
      established_connection: established, button: { down: buttonDown, wake_cycle: wakeCycle }, feedback: feedback,
      telemetry: values, watch_battery: watchBattery,
      devices:devices,transport:options.transportStatus?options.transportStatus():null,
      diagnostics: { valid_frames: validFrames, rejected_frames: rejectedFrames,
        retained_bytes: parser.status().retained_bytes, display_frames: paintCount,
        framebuffer_bytes: 7200, last_frame_received_s: receivedAt,
        last_display_s:lastPaint,last_paint_duration_s:paintDuration,max_paint_duration_s:maxPaintDuration,
        visible_frame_received_s:visibleReceipt,max_receipt_to_paint_s:maxReceiptToPaint,
        memory: options.memory ? options.memory() : null },
      presets: [1,2,3,4].map(function (id) { return { id: id, name: 'Preset ' + id, configured: false }; }),
      dashboard: { speed: live ? String(Math.round(Math.abs(values.speed_kmh))) : '—',
        pwm: live ? String(Math.round(values.pwm_percent)) : '—',
        wheel_battery_percent: values ? String(percent(values.voltage_V)) : '—',
        average_cell_voltage: values ? (Math.round(values.voltage_V / 36 * 100+1e-9)/100).toFixed(2) : '—',
        wheel_battery_dimmed: !live, watch_battery_percent: String(watchBattery.percent),
        watch_battery_simulated: false, charging: watchBattery.charging,
        connection: live ? 'Connected' : connected ? lastValid === null ? 'Waiting for telemetry' : 'Telemetry lost' : established ? 'Disconnected' : 'Not connected' } };
  }
  core = {
    view: view,
    receive: function (token, raw) {
      if (token !== session || !connected) return;
      var previous = parser.status().rejected_frames;
      parser.feed(raw, function (values) {
        telemetry = values; lastValid = clock.now(); receivedAt = lastValid; validFrames++;
        if (options.onTelemetry) options.onTelemetry(values, lastValid);
      });
      rejectedFrames += parser.status().rejected_frames - previous;
      core.tick();
    },
    action: function (name, payload) {
      payload = payload || {};
      if (name === 'session_start') resetSession();
      else if (name === 'connected' && payload.session === session) { connected = true; established = true; awake = true; }
      else if (name === 'disconnect' && payload.session === session) resetSession();
      else if (name === 'swipe' && awake && !recovery) {
        if (payload.direction === 'left' && screen === 'dashboard') screen = 'presets';
        else if (payload.direction === 'down' && payload.from_top) screen = 'settings';
        else if (payload.direction === 'right' && screen !== 'dashboard') screen = 'dashboard';
      } else if (name === 'sleep' && awake && screen === 'settings') awake = false;
      else if (name === 'button_down' && !buttonDown) {
        buttonDown = true; buttonStarted = clock.now(); wakeCycle = !awake; awake = true;
        feedback = wakeCycle ? 'Wake only' : recovery ? 'Horn unavailable in recovery' : 'Horn control not implemented';
      } else if (name === 'button_up') { buttonDown = false; wakeCycle = false; buttonStarted = null; }
      else if (name === 'battery_refresh') { watchBattery = battery(); lastBattery = clock.now(); }
      else if(name==='open_connection'){if(awake)screen='connection';}
      else if(name==='devices'){devices=(payload.devices||[]).slice(0,4);}
      if (awake) lastInteraction = clock.now();
      core.tick();
      return view();
    },
    tick: function () {
      var now = clock.now(), state, signature;
      if (now - lastBattery >= 30) { watchBattery = battery(); lastBattery = now; }
      if (buttonDown && buttonStarted !== null && now - buttonStarted >= 30) { recovery = true; awake = true; feedback = 'Recovery mode'; if (options.recover&&!recoveryCalled) {recoveryCalled=true;options.recover();} }
      if (!established && !buttonDown && !recovery && now - lastInteraction >= 30) awake = false;
      if (options.present && now - lastPaint >= 0.2 - 0.000000001) {
        state = view();
        signature = JSON.stringify([state.awake,state.screen,state.recovery,state.dashboard,state.feedback,state.devices,state.transport]);
        if (signature !== lastView) {
          lastPaint = now; lastView = signature; paintCount++;
          options.present(state);paintDuration=Math.max(0,clock.now()-now);maxPaintDuration=Math.max(maxPaintDuration,paintDuration);
          if(state.awake&&state.fresh&&visibleReceipt!==receivedAt){visibleReceipt=receivedAt;maxReceiptToPaint=Math.max(maxReceiptToPaint,clock.now()-receivedAt);}
        }
      }
    }
  };
  core.tick();
  return core;
};
