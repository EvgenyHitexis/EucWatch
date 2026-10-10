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
  var editor=require('sw-preset-editor').create(),presetPage=0,presetInput=null,clearSlot=null;
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
    if(attempt&&key!==controlFeedback){controlFeedback=key;feedback=require('sw-preset-editor').attemptName(attempt)+' · '+(attempt.pending?'Applying':attempt.status==='Confirmed'&&!result.confirmed?'Unconfirmed':attempt.status);}
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
  function saveEditor(proposed){
    try{if(options.store)options.store.save(proposed);}
    catch(error){persistenceError='Configuration save failed: '+String(error);return false;}
    config=proposed;control.invalidate(clock.now(),'Saved configuration changed');persistenceError=null;return true;
  }
  function leaveEditor(){
    editor.close();presetInput=null;clearSlot=null;validationError=null;
  }
  function percent(voltage) {
    return voltage <= 119.02 ? 0 : voltage >= 148.05 ? 100 : Math.max(0, Math.min(100, Math.round((voltage - 119.02) / 0.2903)));
  }
  function updateAlerts(){alerts.evaluate(clock.now(),{fresh:fresh(),pwm:telemetry?telemetry.pwm_percent:null,speed:telemetry?Math.abs(telemetry.speed_kmh):null,battery:telemetry?percent(telemetry.voltage_V):null});}
  function view() {
    var live = fresh(), values = telemetry,vibration=alerts.view(),controlState=control.view(),editing=editor.view();
    vibration.output=options.vibration_status?options.vibration_status():null;
    if(editing.request)editing.request.reason=validationError||'';
    return { mode: 'watch',session: session, elapsed_s: clock.now(), connected: connected,
      fresh: live, awake: awake, screen: screen, recovery: recovery,
      established_connection: established, button: { down: buttonDown, wake_cycle: wakeCycle }, feedback: feedback,
      telemetry: values, watch_battery: watchBattery,
      vibration:vibration,
      preset_attempt:controlState.attempt,confirmed_preset:controlState.confirmed&&controlState.confirmed.kind==='preset'?controlState.confirmed:null,actual_settings:controlState.actual,
      confirmed_setting:controlState.confirmed&&controlState.confirmed.kind==='editor'?controlState.confirmed:null,
      horn_feedback:horn.view(),command_events:configuration.copy(commandEvents),
      config:configuration.copy(config),alerts_draft:draft?configuration.copy(draft):null,alert_page:alertPage,persistence_error:persistenceError,validation_error:validationError,
      threshold_input:thresholdInput?configuration.copy(thresholdInput):null,
      preset_editor:editing.request,preset_draft:editing.draft,preset_page:presetPage,preset_input:configuration.copy(presetInput),preset_clear_slot:clearSlot,
      devices:devices,transport:options.transportStatus?options.transportStatus():null,
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
    action: function (name, payload) {
      if(typeof name==='string'&&(/^(transfer_|nordic_)/.test(name)||['preset_clear','preset_clear_begin','preset_clear_cancel','preset_clear_done','preset_input_done','preset_input_cancel'].indexOf(name)>=0))throw new Error('Unknown action: '+name);
      payload = payload || {};
      core.tick();
      if (name === 'session_start') resetSession();
      else if (name === 'connected' && payload.session === session) { connected = true; established = true; awake = true; }
      else if (name === 'disconnect' && payload.session === session) resetSession();
      else if (name === 'swipe' && awake && !recovery) {
        if(screen==='preset_editor'){
          editor.require(payload.editor_id);
          if(payload.direction==='left'||payload.direction==='right')core.action('preset_page',{editor_id:payload.editor_id,page:(presetPage+(payload.direction==='left'?1:3))%4});
          else if(payload.direction==='up'){leaveEditor();screen='preset_slots';}
        }else if(payload.direction==='left'&&screen==='dashboard')screen='presets';
        else if(payload.direction==='down'&&payload.from_top&&screen==='dashboard')screen='settings';
        else if(payload.direction==='up'){
          if(screen==='preset_slots')screen='settings';
          else if(screen==='threshold'){thresholdInput=null;screen='alerts';validationError=null;}
          else if(screen==='alerts'){draft=null;screen='settings';validationError=null;}
          else if(screen==='settings'||screen==='connection')screen='dashboard';
        }else if(payload.direction==='right'&&screen==='presets')screen='dashboard';
      } else if (name === 'sleep' && awake && screen === 'settings') awake = false;
      else if (name === 'button_down' && !buttonDown) {
        buttonDown = true; buttonStarted = clock.now(); wakeCycle = !awake; awake = true;
        if(wakeCycle)feedback='Wake only';else requestHorn();
      } else if (name === 'button_up') { buttonDown = false; wakeCycle = false; buttonStarted = null; }
      else if (name === 'battery_refresh') { watchBattery = battery(); lastBattery = clock.now(); }
      else if(name==='open_connection'){if(awake)screen='connection';}
      else if(name==='devices'){devices=(payload.devices||[]).slice(0,4);}
      else if(name==='preset_slots'){
        if(!awake||recovery)throw new Error('Preset editing unavailable');
        leaveEditor();draft=null;screen='preset_slots';
      }else if(name==='preset_begin'){
        if(!awake||recovery)throw new Error('Preset editing unavailable');
        editor.open(config,payload.slot);presetPage=0;presetInput=null;validationError=null;screen='preset_editor';
      }else if(['preset_update','preset_cancel','preset_save','preset_include_dip','preset_page','preset_input_begin','preset_input_key','preset_input_page'].indexOf(name)>=0){
        editor.require(payload.editor_id);
        if(!awake||recovery)throw new Error('Preset editing unavailable');
        validationError=null;
        if(name==='preset_update'){
          var changes=configuration.copy(payload);delete changes.source;delete changes.editor_id;editor.update(changes);
          if(presetInput)presetInput.text=String(editor.view().draft[presetInput.field]);
        }else if(name==='preset_cancel'){leaveEditor();screen='preset_slots';}
        else if(name==='preset_save'){
          var proposedEditor;
          try{proposedEditor=editor.validate(config);}catch(error){validationError=String(error);return view();}
          if(saveEditor(proposedEditor)){leaveEditor();screen='preset_slots';}
        }else if(name==='preset_include_dip'){
          if(typeof payload.included!=='boolean')throw new Error('Choose explicit dip inclusion');
          editor.update({dip_included:payload.included});
        }else if(name==='preset_page'){
          if(typeof payload.page!=='number'||Math.floor(payload.page)!==payload.page||payload.page<0||payload.page>3)throw new Error('Invalid preset page');
          presetPage=payload.page;
          if(presetInput){var field=require('sw-preset-editor').fields[presetPage];presetInput={field:field,text:String(editor.view().draft[field]),letters:0,lowercase:false};}
        }else if(name==='preset_input_begin'){
          var inputField=require('sw-preset-editor').fields[presetPage];
          presetInput={field:inputField,text:String(editor.view().draft[inputField]),letters:0,lowercase:false};
        }else if(name==='preset_input_key'){
          if(!presetInput)throw new Error('No preset input is open');
          var key=payload.key;
          if(key==='Clear')presetInput.text='';
          else if(key==='<')presetInput.text=presetInput.text.slice(0,-1);
          else if(key==='a/A'&&presetInput.field==='name')presetInput.lowercase=!presetInput.lowercase;
          else if(typeof key==='string'&&(require('sw-preset-editor').keys(presetInput).indexOf(key)>=0||(key===' '&&presetInput.field==='name'))){if(presetInput.text.length<(presetInput.field==='name'?24:3))presetInput.text+=key;}
          else throw new Error('Invalid preset input key');
          var entered={};entered[presetInput.field]=presetInput.text;editor.update(entered);
        }else if(name==='preset_input_page'){
          if(!presetInput||presetInput.field!=='name'||(payload.delta!==1&&payload.delta!==-1))throw new Error('Invalid name keypad page');
          presetInput.letters=(presetInput.letters+payload.delta+3)%3;
        }
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
        leaveEditor();config=loaded;draft=null;thresholdInput=null;screen='dashboard';alerts.configure(config.alerts,clock.now());persistenceError=options.store.warning||null;
      }
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
      updateControl();
      if(!editor.view().draft)presetInput=null;
      updateAlerts();
      if (now - lastBattery >= 30) { watchBattery = battery(); lastBattery = now; }
      if (buttonDown && buttonStarted !== null && now - buttonStarted >= 30) { recovery = true; awake = true; feedback = 'Recovery mode'; if (options.recover&&!recoveryCalled) {recoveryCalled=true;options.recover();} }
      if (!established && !buttonDown && !recovery && !draft && !editor.view().request && now - lastInteraction >= 30) awake = false;
      if (options.present && now - lastPaint >= 0.2 - 0.000000001) {
        state = view();
        signature = JSON.stringify([state.awake,state.screen,state.recovery,state.dashboard,state.feedback,state.devices,state.transport,state.alerts_draft,state.alert_page,state.threshold_input,state.validation_error,state.persistence_error,state.presets,state.preset_attempt,state.confirmed_preset,state.confirmed_setting,state.actual_settings,state.horn_feedback,state.preset_editor,state.preset_draft,state.preset_page,state.preset_input,state.preset_clear_slot]);
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
