/* Original 240x240, 1-bpp presentation; Canvas layout carried to Espruino Graphics. */
exports.draw = function (g, state) {
  var d = state.dashboard, i, x, y;
  function text(value, x, y, size, align) {
    g.setColor(1); g.setFont('Vector', size); g.setFontAlign(align || 0, -1);
    g.drawString(String(value), x, y);
  }
  function controls(){require('sw-controls').targets(state).forEach(function(target){var r=target.rect,preset=state.screen==='preset_slots'||state.screen==='preset_editor',size=preset?Math.max(8,Math.min(15,Math.floor((r[2]-r[0]-8)/(target.label.length*0.65)))):target.label.length>12?13:15;g.setColor(1);g.drawRect(r[0],r[1],r[2],r[3]);text(target.label,(r[0]+r[2])/2,(r[1]+r[3])/2-(preset?size/2:7),size);});}
  g.clear();
  if (!state.awake) return;
  if (state.recovery) { text('RECOVERY',120,90,24); text('Wheel controls unavailable',120,125,12); g.flip(); return; }
  if(state.screen==='preset_slots'){
    text('SETTINGS - PRESETS',120,9,14);controls();text((state.persistence_error||'Tap to edit; swipe up to return').slice(0,36),120,221,10);
  }else if(state.screen==='preset_editor'){
    var slot=state.preset_draft,page=state.preset_page,labels=require('sw-preset-editor').labels;
    if(slot){
      text(labels[page],120,9,12);controls();
      var notice=state.validation_error||state.persistence_error||'';
      if(state.preset_input){
        var input=state.preset_input;
        text(notice?notice.slice(0,40):input.text||'-',120,33,notice?10:Math.min(18,Math.floor(216/(Math.max(1,input.text.length)*0.65))));
      }else{
        text('SLOT '+slot.id+' - '+(page+1)+'/4',120,36,14);
        text('Left/right fields; up cancels',120,148,12);text(notice.slice(0,38),120,183,10);
      }
    }
  }else if (state.screen === 'presets') {
    text('RIDING PRESETS',120,10,15);
    var result=state.preset_attempt;
    if(result&&!result.pending)text('At attempt: actual/requested · now = fresh value',120,28,8);
    for (i=0;i<4;i++) {
      x=9+(i%2)*115; y=43+Math.floor(i/2)*81;
      g.setColor(1); g.drawRect(x,y,x+105,y+71);
      text(state.presets[i].name,x+53,y+22,14);
      text(state.presets[i].configured?(state.presets_menu[i].available?'Tap to apply':'Unavailable'):'Unconfigured',x+53,y+48,10);
    }
    if(result&&!result.pending&&!state.horn_feedback){
      var labels={pedal_sensitivity:'Sensitivity',dynamic_assist:'Assist',pedal_dip_compensation:'Dip'};
      Object.keys(result.fields).forEach(function(name,index){var field=result.fields[name],line=labels[name]+' '+(field.actual===null?'?':field.actual)+'/'+field.requested+' '+field.state;
        var current=state.fresh&&state.actual_settings?state.actual_settings[name]:null;
        if(current!==null&&current!==field.actual)line+=' now '+current;
        text(line,120,200+index*12,9);
      });
    }else text(state.horn_feedback?state.horn_feedback.message:'Swipe right to return',120,216,11);
  } else if (state.screen === 'settings') {
    text('SETTINGS',120,10,15);
    controls();
    text(state.horn_feedback?state.horn_feedback.message:state.validation_error?state.validation_error:state.persistence_error?'Configuration needs review':'Swipe up to return',120,228,9);
  }else if(state.screen==='alerts'){
    var name=['pwm','speed','battery','lost'][state.alert_page];
    text('VIBRATION ALERTS '+(state.alert_page+1)+'/4',120,9,14);
    if(state.horn_feedback)text(state.horn_feedback.message,120,25,8);
    text({pwm:'High PWM',speed:'High speed',battery:'Low wheel battery',lost:'Lost telemetry'}[name],12,41,13,-1);
    controls();
    if(name==='lost')text('One short pulse',120,90,14);
    else text(name==='speed'?'km/h':'%',120,114,10);
    if(state.validation_error||state.persistence_error)text((state.validation_error||state.persistence_error).replace(/^Error: /,'').slice(0,35),120,153,11);
    else if(state.vibration.output_error)text('Vibration output unavailable',120,153,11);
  }else if(state.screen==='threshold'){
    text(state.threshold_input.text||'Enter threshold',120,9,18);controls();
    if(state.horn_feedback)text(state.horn_feedback.message,120,28,8);
    else if(state.validation_error)text('Invalid threshold',120,27,11);
  } else if(state.screen==='connection'){
    text('SELECT WHEEL',120,10,15);
    if(state.horn_feedback)text(state.horn_feedback.message,120,27,8);
    if(!state.devices.length)text(state.transport&&state.transport.error?'Discovery failed':'Discovering...',120,90,14);
    for(i=0;i<state.devices.length;i++){
      y=40+i*38;g.setColor(1);g.drawRect(8,y,232,y+34);
      text((state.devices[i].name||'Unnamed wheel').slice(0,22),120,y+4,13);
      text(state.devices[i].id,120,y+19,9);
    }
    text('Swipe up to return',120,216,11);
  } else {
    text('SHERMAN L',12,9,11,-1);
    text('W '+d.watch_battery_percent+'%',228,9,11,1);
    g.setColor(1); g.drawRect(179,8,189,20); g.fillRect(182,5,186,7);
    if (d.charging) text('+',173,7,13,1);
    text(d.speed,120,33,69); text('km/h',120,110,12);
    if(state.horn_feedback)text(state.horn_feedback.message,120,121,10);
    else if(state.preset_attempt){var attempt=state.preset_attempt,current=attempt.kind==='editor'?state.confirmed_setting:state.confirmed_preset;text(require('sw-preset-editor').attemptName(attempt)+' · '+(attempt.pending?'Applying':attempt.status==='Confirmed'&&!current?'Unconfirmed':attempt.status),120,121,10);}
    text('PWM',13,145,13,-1); text(d.pwm+'%',228,132,33,1);
    g.setColor(1); g.drawLine(12,176,228,176);
    text(d.wheel_battery_percent+'% est.',12,182,18,-1);
    text(d.average_cell_voltage+' V/cell',228,187,13,1);
    if (d.wheel_battery_dimmed) {
      // Spatial dithering dims this region within a one-bit framebuffer.
      g.setColor(0);
      for (y=180;y<204;y++) for (x=12+(y%2);x<229;x+=2) g.setPixel(x,y,0);
    }
    if (!state.fresh) { g.setColor(1); g.drawRect(8,210,232,233); }
    text(d.connection,120,215,12);
  }
  g.flip();
};
