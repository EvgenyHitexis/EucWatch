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
  var core, devices=[], recoveryCalled=false, wheelLinkError='';
  /* options.transport: {discover(), select(id), disconnect(), status()}. discover and select throw the reason when the
     transport refuses, before reporting anything; a refused request leaves the screen as it was. */
  var transport=options.transport||null;
  var config=configuration.defaults(),persistenceError=null,validationError=null,validationReason={get:function(){return validationError;},set:function(value){validationError=value||null;}};
  var presetEditor=require('sw-preset-editor'),editor=presetEditor.create(validationReason),alertEditorModule=require('sw-alert-editor'),alertEditor=alertEditorModule.create(validationReason);
  if(options.store){try{var saved=options.store.load();if(saved!==null&&saved!==undefined)config=configuration.validate(saved);persistenceError=options.store.warning||null;}catch(error){persistenceError='Saved configuration requires review: '+String(error);}}
  var alerts=require('sw-alerts').create({output:options.vibration_output,settings:config.alerts});
  var commandEvents=[],controlFeedback='',control=require('sw-preset-control').create({send:submit});
  var horn=require('sw-horn').create({send:submit});
  function submit(row){
    commandEvents.push(configuration.copy(row));if(commandEvents.length>64)commandEvents.shift();
    try{if(!options.command_output)throw new Error('Live control transport unavailable');options.command_output(configuration.copy(row));}
    catch(error){var result={attempt:row.attempt,request:row.request,session:row.session,index:row.index,success:false,error:String(error)};if(row.kind==='horn')horn.result(result,clock.now());else control.result(result,clock.now());}
  }
  function updateControl(){
    control.tick(clock.now(),{fresh:fresh(),session:session,revision:config.revision,recovery:recovery});
    var result=control.view(),attempt=result.attempt,key=attempt?attempt.id+':'+attempt.status+':'+!!result.confirmed:'';
    if(attempt&&key!==controlFeedback){controlFeedback=key;feedback=attempt.name+' · '+(attempt.pending?'Applying':attempt.status==='Confirmed'&&!result.confirmed?'Unconfirmed':attempt.status);}
    var previous=horn.view();horn.tick(clock.now(),session);
    if(previous&&!horn.view()&&feedback===previous.message)feedback='';
    if(horn.view())feedback=horn.view().message;
  }
  function requestHorn(){
    var reason=recovery?'recovery mode':control.pending()?'preset applying':!awake||!fresh()?'connection unavailable':!options.command_output?'control transport unavailable':null;
    if(reason)horn.show('Horn unavailable: '+reason,clock.now(),session);else horn.request(clock.now(),session);
    feedback=horn.view().message;
  }
  function fresh() { return connected && lastValid !== null && clock.now() - lastValid < 1; }
  function resetSession() { session++; connected = false; lastValid = null; parser = protocol.create(); }
  function store(proposed){
    try{if(options.store)options.store.save(proposed);}
    catch(error){persistenceError=configuration.saveFailed+String(error);return false;}
    config=proposed;persistenceError=null;return true;
  }
  function saveEditor(proposed){if(!store(proposed))return false;control.invalidate(clock.now(),'Saved configuration changed');return true;}
  function alertScreen(){return alertEditor.editing()?alertEditor.entryOpen()?'threshold':'alerts':'settings';}
  function leaveEditor(){editor.close();}
  function transportStatus(){return transport?transport.status():null;}
  // The Connect/Disconnect target's meaning: a wanted or live wheel link is disconnected, otherwise discovery starts.
  function disconnectAvailable(){var status=transportStatus();return !!(status&&(status.active||status.connected));}
  function askTransport(request){
    wheelLinkError='';
    try{if(!transport)throw new Error('Wheel transport not ready');request();return true;}
    catch(error){wheelLinkError=error&&error.message?error.message:String(error);return false;}
  }
  // The core's own input carries the current editor and entry ids, which the Preset editor checks.
  function withEditorIds(name,payload){
    var copy={},state=editor.view(),key;payload=payload||{};
    for(key in payload)copy[key]=payload[key];
    if((name==='swipe'||name.indexOf('preset_')===0)&&state.request){copy.editor_id=state.request.id;if(state.input)copy.entry_id=state.input.id;}
    return copy;
  }
  function percent(voltage) {
    return voltage <= 119.02 ? 0 : voltage >= 148.05 ? 100 : Math.max(0, Math.min(100, Math.round((voltage - 119.02) / 0.2903)));
  }
  function updateAlerts(){alerts.evaluate(clock.now(),{fresh:fresh(),pwm:telemetry?telemetry.pwm_percent:null,speed:telemetry?Math.abs(telemetry.speed_kmh):null,battery:telemetry?percent(telemetry.voltage_V):null});}
  function view() {
    var live = fresh(), values = telemetry,vibration=alerts.view(),controlState=control.view(),editing=editor.view(),alertView=alertEditor.view();
    vibration.output=options.vibration_status?options.vibration_status():null;
    return { mode: 'watch',session: session, elapsed_s: clock.now(), connected: connected,
      fresh: live, awake: awake, screen: screen, recovery: recovery,
      established_connection: established, button: { down: buttonDown, wake_cycle: wakeCycle }, feedback: feedback,
      telemetry: values, watch_battery: watchBattery,
      vibration:vibration,
      preset_attempt:controlState.attempt,confirmed_preset:controlState.confirmed&&controlState.confirmed.kind==='preset'?controlState.confirmed:null,actual_settings:controlState.actual,
      horn_feedback:horn.view(),command_events:configuration.copy(commandEvents),
      config:configuration.copy(config),alerts_draft:alertView.draft,alert_page:alertView.page,persistence_error:persistenceError,validation_error:validationError,
      threshold_entry:alertView.entry,
      preset_editor:editing.request,preset_draft:editing.draft,preset_page:editing.page,preset_input:editing.input,
      preset_keys:editing.keys,preset_previous_page:editing.previous_page,preset_next_page:editing.next_page,
      devices:devices,transport:transportStatus(),disconnect_available:disconnectAvailable(),wheel_link_error:wheelLinkError,
      diagnostics: { valid_frames: validFrames, rejected_frames: rejectedFrames,
        retained_bytes: parser.status().retained_bytes, display_frames: paintCount,
        framebuffer_bytes: 7200, last_frame_received_s: receivedAt,
        last_display_s:lastPaint,last_paint_duration_s:paintDuration,max_paint_duration_s:maxPaintDuration,
        visible_frame_received_s:visibleReceipt,max_receipt_to_paint_s:maxReceiptToPaint,
        memory: options.memory ? options.memory() : null },
      presets:configuration.copy(config.presets),
      presets_menu:config.presets.map(function(preset){return {id:preset.id,available:!!(preset.configured&&live&&!control.pending()&&!recovery&&awake&&options.command_output)};}),
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
    commandEligible:function(row){
      if(!row||typeof row!=='object')return false;
      updateControl();
      if(!fresh()||recovery||row.session!==session)return false;
      if(row.kind==='horn')return awake&&!control.pending()&&horn.eligible(row.request,session)&&row.packet_hex===require('sw-horn').packet;
      if(row.kind!=='preset')return false;
      var attempt=control.view().attempt;if(!attempt||!attempt.pending||attempt.status!=='submitting'||row.attempt!==attempt.id||row.index!==attempt.awaiting)return false;
      var name=Object.keys(attempt.fields)[row.index];return row.field===name&&row.value===attempt.fields[name].requested&&row.packet_hex===require('sw-preset-control').hex(require('sw-preset-control').command(name,row.value));
    },
    receive: function (token, raw) {
      if (token !== session || !connected) return;
      updateControl();
      updateAlerts();
      var previous = parser.status().rejected_frames;
      parser.feed(raw, function (values,frame) {
        telemetry = values; lastValid = clock.now(); receivedAt = lastValid; validFrames++;
        var settings=protocol.settings(frame);if(settings){control.observe(settings,clock.now(),session);}
        updateAlerts();
        if (options.onTelemetry) options.onTelemetry(values, lastValid);
      });
      rejectedFrames += parser.status().rejected_frames - previous;
      core.tick();
    },
    // A touch at (x, y): the target under it, if any, acts with the current editor and entry ids.
    touch:function(x,y){
      var target=require('sw-controls').hit(view(),x,y);
      return target?core.action(target.action,withEditorIds(target.action,target.payload)):null;
    },
    // A hardware input (swipe, button, battery or interact); a swipe carries the current editor and entry ids.
    gesture:function(name,payload){return core.action(name,name==='swipe'?withEditorIds(name,payload):payload);},
    action: function (name, payload) {
      payload = payload || {};
      core.tick();
      var before=screen;
      // Link events from the transport: they change connection state, never the screen.
      if (name === 'session_start') resetSession();
      else if (name === 'connected') { if (payload.session === session) { connected = true; established = true; awake = true; } }
      else if (name === 'disconnect') { if (payload.session === session) resetSession(); }
      else if(name==='devices'){devices=(payload.devices||[]).slice(0,4);}
      else if (name === 'swipe') { if (awake && !recovery) {
        if(screen==='preset_editor'){if(editor.swipe(payload)){leaveEditor();screen='preset_slots';}}
        else if(payload.direction==='left'&&screen==='dashboard')screen='presets';
        else if(payload.direction==='down'&&payload.from_top&&screen==='dashboard')screen='settings';
        else if(payload.direction==='up'){
          if(screen==='preset_slots')screen='settings';
          else if(screen==='threshold'){alertEditor.action('threshold_cancel');screen=alertScreen();}
          else if(screen==='alerts'){alertEditor.close();screen=alertScreen();}
          else if(screen==='settings'||screen==='connection')screen='dashboard';
        }else if(payload.direction==='right'&&screen==='presets')screen='dashboard';
      } } else if (name === 'sleep') { if (awake && screen === 'settings') awake = false; }
      else if (name === 'button_down') { if (!buttonDown) {
        buttonDown = true; buttonStarted = clock.now(); wakeCycle = !awake; awake = true;
        if(wakeCycle)feedback='Wake only';else requestHorn();
      } } else if (name === 'button_up') { buttonDown = false; wakeCycle = false; buttonStarted = null; }
      else if (name === 'button_hold' || name === 'interact') {}
      else if (name === 'battery_refresh') { watchBattery = battery(); lastBattery = clock.now(); }
      else if(name==='transport_toggle'||name==='device_select'){
        if(recovery)throw new Error('Wheel connection unavailable in recovery mode');
        // The screen changes before the request, so a paint from inside it (the transport reports back synchronously)
        // already shows the new screen; a refusal, thrown before the transport reports anything, restores it.
        if(name==='transport_toggle'&&disconnectAvailable())askTransport(function(){transport.disconnect();});
        else if(name==='transport_toggle'){if(awake)screen='connection';if(!askTransport(function(){transport.discover();}))screen=before;}
        else{if(screen==='connection')screen='dashboard';if(!askTransport(function(){transport.select(payload.id);}))screen=before;}
      }
      else if(name==='preset_slots'){
        if(!awake||recovery)throw new Error('Preset editing unavailable');
        leaveEditor();alertEditor.close();screen='preset_slots';
      }else if(name==='preset_begin'){
        if(!awake||recovery)throw new Error('Preset editing unavailable');
        editor.open(config,payload.slot);screen='preset_editor';
      }else if(presetEditor.actions.indexOf(name)>=0){
        var edited=editor.action(name,payload,awake&&!recovery,config);
        if(edited&&edited.invalid)return view();
        if(edited&&(edited.leave||saveEditor(edited.save))){leaveEditor();screen='preset_slots';}
      }
      else if(name==='preset_apply'){
        if(control.pending()){feedback='Preset already applying';return view();}
        if(typeof payload.slot!=='number'||Math.floor(payload.slot)!==payload.slot||payload.slot<1||payload.slot>4)throw new Error('A fixed preset slot is required');
        var preset=config.presets[payload.slot-1];
        if(!preset.configured)throw new Error('Preset slot is unconfigured');
        if(!awake||!fresh()||recovery||!options.command_output)throw new Error('Preset unavailable: healthy fresh connection and control transport required');
        screen='dashboard';parser=protocol.create();control.start(preset,config.revision,session,clock.now());
      }else if(name==='command_result'){
        if(typeof payload.success!=='boolean'||typeof payload.attempt!=='number'||typeof payload.session!=='number'||typeof payload.index!=='number')throw new Error('Explicit command result required');
        var prior=control.view().attempt;control.result(payload,clock.now());var after=control.view().attempt;
        if(prior&&after&&prior.status==='submitting'&&after.status==='confirming')parser=protocol.create();
      }else if(name==='horn_result'){
        if(typeof payload.success!=='boolean'||typeof payload.request!=='number'||typeof payload.session!=='number')throw new Error('Explicit horn transport result required');
        horn.result(payload,clock.now());
      }else if(name==='configuration_reload'){
        if(!options.store)throw new Error('Saved configuration adapter unavailable');
        var loaded=configuration.validate(options.store.load()||configuration.defaults());
        if(!configuration.equal(loaded,config))control.invalidate(clock.now(),'Saved configuration changed');
        leaveEditor();alertEditor.close();config=loaded;screen='dashboard';alerts.configure(config.alerts,clock.now());persistenceError=options.store.warning||null;
      }
      else if(name==='alert_test')alerts.test(payload.alert,clock.now());
      else if(name==='alerts_begin'){
        if(!awake||screen!=='settings')throw new Error('Open alert editing inside Settings');
        alertEditor.open(config.alerts);screen=alertScreen();
      }else if(alertEditorModule.actions.indexOf(name)>=0){
        var outcome;try{outcome=alertEditor.action(name,payload,config);}catch(error){core.tick();throw error;}
        if(outcome&&outcome.save){
          if(!store(outcome.save)){core.tick();return view();}
          alertEditor.close();alerts.configure(config.alerts,clock.now());
        }
        screen=alertScreen();
      }
      else throw new Error('Unknown action: '+name);
      // A refusal reason belongs to the screen it was shown on.
      if(screen!==before)wheelLinkError='';
      if (awake) lastInteraction = clock.now();
      core.tick();
      return view();
    },
    tick: function () {
      var now = clock.now(), state, signature;
      updateControl();
      updateAlerts();
      if (now - lastBattery >= 30) { watchBattery = battery(); lastBattery = now; }
      if (buttonDown && buttonStarted !== null && now - buttonStarted >= 30) { recovery = true; awake = true; feedback = 'Recovery mode'; if (options.recover&&!recoveryCalled) {recoveryCalled=true;options.recover();} }
      if (!established && !buttonDown && !recovery && !alertEditor.editing() && !editor.view().request && now - lastInteraction >= 30) awake = false;
      if (options.present && now - lastPaint >= 0.2 - 0.000000001) {
        state = view();
        signature = JSON.stringify([state.awake,state.screen,state.recovery,state.dashboard,state.feedback,state.devices,state.transport,state.wheel_link_error,state.alerts_draft,state.alert_page,state.threshold_entry,state.validation_error,state.persistence_error,state.presets,state.preset_attempt,state.confirmed_preset,state.actual_settings,state.horn_feedback,state.preset_editor,state.preset_draft,state.preset_page,state.preset_input]);
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
