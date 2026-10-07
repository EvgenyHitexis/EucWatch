/* Original riding behavior; no globals from the previous watch application. */
var protocol = require('sw-protocol');
var configuration=require('sw-configuration');
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
  var config=configuration.defaults(),draft=null,persistenceError=null,validationError=null,alertPage=0,thresholdInput=null;
  if(options.store){try{var saved=options.store.load();if(saved!==null&&saved!==undefined)config=configuration.validate(saved);persistenceError=options.store.warning||null;}catch(error){persistenceError='Saved configuration requires review: '+String(error);}}
  var alerts=require('sw-alerts').create({output:options.vibration_output,settings:config.alerts});
  function fresh() { return connected && lastValid !== null && clock.now() - lastValid < 1; }
  function resetSession() { session++; connected = false; lastValid = null; parser = protocol.create(); buttonDown = false; wakeCycle = false; buttonStarted = null; }
  function percent(voltage) {
    return voltage <= 119.02 ? 0 : voltage >= 148.05 ? 100 : Math.max(0, Math.min(100, Math.round((voltage - 119.02) / 0.2903)));
  }
  function updateAlerts(){alerts.evaluate(clock.now(),{fresh:fresh(),pwm:telemetry?telemetry.pwm_percent:null,speed:telemetry?Math.abs(telemetry.speed_kmh):null,battery:telemetry?percent(telemetry.voltage_V):null});}
  function view() {
    var live = fresh(), values = telemetry,vibration=alerts.view();
    vibration.output=options.vibration_status?options.vibration_status():null;
    return { mode: 'watch', session: session, elapsed_s: clock.now(), connected: connected,
      fresh: live, awake: awake, screen: screen, recovery: recovery,
      established_connection: established, button: { down: buttonDown, wake_cycle: wakeCycle }, feedback: feedback,
      telemetry: values, watch_battery: watchBattery,
      vibration:vibration,
      config:configuration.copy(config),alerts_draft:draft?configuration.copy(draft):null,alert_page:alertPage,persistence_error:persistenceError,validation_error:validationError,
      threshold_input:thresholdInput?configuration.copy(thresholdInput):null,
      devices:devices,transport:options.transportStatus?options.transportStatus():null,
      diagnostics: { valid_frames: validFrames, rejected_frames: rejectedFrames,
        retained_bytes: parser.status().retained_bytes, display_frames: paintCount,
        framebuffer_bytes: 7200, last_frame_received_s: receivedAt,
        last_display_s:lastPaint,last_paint_duration_s:paintDuration,max_paint_duration_s:maxPaintDuration,
        visible_frame_received_s:visibleReceipt,max_receipt_to_paint_s:maxReceiptToPaint,
        memory: options.memory ? options.memory() : null },
      presets:configuration.copy(config.presets),
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
    ownership:function(){return {session:session,recovery:recovery};},
    receive: function (token, raw) {
      if (token !== session || !connected) return;
      updateAlerts();
      var previous = parser.status().rejected_frames;
      parser.feed(raw, function (values) {
        telemetry = values; lastValid = clock.now(); receivedAt = lastValid; validFrames++;
        updateAlerts();
        if (options.onTelemetry) options.onTelemetry(values, lastValid);
      });
      rejectedFrames += parser.status().rejected_frames - previous;
      core.tick();
    },
    action: function (name, payload) {
      payload = payload || {};
      core.tick();
      if (name === 'session_start') resetSession();
      else if (name === 'connected' && payload.session === session) { connected = true; established = true; awake = true; }
      else if (name === 'disconnect' && payload.session === session) resetSession();
      else if (name === 'swipe' && awake && !recovery) {
        if (payload.direction === 'left' && screen === 'dashboard') screen = 'presets';
        else if (payload.direction === 'down' && payload.from_top) screen = 'settings';
        else if (payload.direction === 'right' && screen !== 'dashboard') {screen = 'dashboard';draft=null;thresholdInput=null;validationError=null;}
      } else if (name === 'sleep' && awake && screen === 'settings') awake = false;
      else if (name === 'button_down' && !buttonDown) {
        buttonDown = true; buttonStarted = clock.now(); wakeCycle = !awake; awake = true;
        feedback = wakeCycle ? 'Wake only' : recovery ? 'Horn unavailable in recovery' : 'Horn control not implemented';
      } else if (name === 'button_up') { buttonDown = false; wakeCycle = false; buttonStarted = null; }
      else if (name === 'battery_refresh') { watchBattery = battery(); lastBattery = clock.now(); }
      else if(name==='open_connection'){if(awake)screen='connection';}
      else if(name==='devices'){devices=(payload.devices||[]).slice(0,4);}
      else if(name==='alert_test')alerts.test(payload.alert,clock.now());
      else if(name==='alerts_begin'){
        if(!awake||screen!=='settings')throw new Error('Open alert editing inside Settings');
        draft=configuration.copy(config.alerts);alertPage=0;screen='alerts';validationError=null;
      }else if(name==='alerts_update'){
        if(!draft||!Object.prototype.hasOwnProperty.call(draft,payload.alert))throw new Error('Open a valid alert draft before editing');
        var allowed=payload.alert==='lost'?['alert','enabled']:['alert','enabled','threshold'];
        if(Object.keys(payload).some(function(key){return allowed.indexOf(key)<0;})||Object.keys(payload).length<2)throw new Error('Invalid alert draft field');
        if(Object.prototype.hasOwnProperty.call(payload,'enabled'))draft[payload.alert].enabled=payload.enabled;
        if(Object.prototype.hasOwnProperty.call(payload,'threshold'))draft[payload.alert].threshold=payload.threshold;
        validationError=null;
      }else if(name==='alerts_save'){
        if(!draft)throw new Error('No alert draft is open');
        var proposed=configuration.copy(config);
        try{proposed.alerts=configuration.validateAlerts(draft);proposed.revision++;proposed=configuration.validate(proposed);}
        catch(error){validationError=String(error);core.tick();throw error;}
        try{if(options.store)options.store.save(proposed);}
        catch(error){persistenceError='Configuration save failed: '+String(error);core.tick();return view();}
        config=proposed;draft=null;screen='settings';validationError=null;persistenceError=null;alerts.configure(config.alerts,clock.now());
      }else if(name==='alerts_cancel'){draft=null;thresholdInput=null;screen='settings';validationError=null;}
      else if(name==='alerts_page'){
        if(!draft||typeof payload.page!=='number'||Math.floor(payload.page)!==payload.page||payload.page<0||payload.page>3)throw new Error('Invalid alert page');
        alertPage=payload.page;validationError=null;
      }else if(name==='alerts_adjust'){
        if(!draft||['pwm','speed','battery'].indexOf(payload.alert)<0||(payload.delta!==1&&payload.delta!==-1))throw new Error('Invalid threshold adjustment');
        var value=draft[payload.alert].threshold;
        draft[payload.alert].threshold=value===null?0:Math.max(0,Math.min(payload.alert==='speed'?3276.7:100,value+payload.delta));validationError=null;
      }else if(name==='threshold_begin'){
        if(!draft||['pwm','speed','battery'].indexOf(payload.alert)<0)throw new Error('Select a measurement alert threshold');
        thresholdInput={alert:payload.alert,text:draft[payload.alert].threshold===null?'':String(draft[payload.alert].threshold)};screen='threshold';validationError=null;
      }else if(name==='threshold_key'){
        if(!thresholdInput)throw new Error('No threshold input is open');
        if(payload.key==='backspace')thresholdInput.text=thresholdInput.text.slice(0,-1);
        else if(typeof payload.key==='string'&&/^[0-9.]$/.test(payload.key)&&thresholdInput.text.length<10){if(payload.key!=='.'||thresholdInput.text.indexOf('.')<0)thresholdInput.text+=payload.key;}
        else throw new Error('Invalid threshold key');
        validationError=null;
      }else if(name==='threshold_done'){
        if(!thresholdInput||!draft)throw new Error('No threshold input is open');
        var number=thresholdInput.text===''?null:Number(thresholdInput.text),limit=thresholdInput.alert==='speed'?3276.7:100;
        if(number!==null&&(!isFinite(number)||number<0||number>limit)){validationError='Threshold outside supported range';core.tick();throw new Error(validationError);}
        draft[thresholdInput.alert].threshold=number;thresholdInput=null;screen='alerts';validationError=null;
      }else if(name==='threshold_cancel'){thresholdInput=null;screen='alerts';validationError=null;}
      if (awake) lastInteraction = clock.now();
      core.tick();
      return view();
    },
    tick: function () {
      var now = clock.now(), state, signature;
      updateAlerts();
      if (now - lastBattery >= 30) { watchBattery = battery(); lastBattery = now; }
      if (buttonDown && buttonStarted !== null && now - buttonStarted >= 30) { recovery = true; awake = true; feedback = 'Recovery mode'; if (options.recover&&!recoveryCalled) {recoveryCalled=true;options.recover();} }
      if (!established && !buttonDown && !recovery && !draft && now - lastInteraction >= 30) awake = false;
      if (options.present && now - lastPaint >= 0.2 - 0.000000001) {
        state = view();
        signature = JSON.stringify([state.awake,state.screen,state.recovery,state.dashboard,state.feedback,state.devices,state.transport,state.alerts_draft,state.alert_page,state.threshold_input,state.validation_error,state.persistence_error]);
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
