/* Original 240x240, 1-bpp presentation; Canvas layout carried to Espruino Graphics.
   The alert editor keeps its title above a message, wrapped at spaces into up to three 23-character lines, and the
   threshold keypad keeps the alert's name above "Invalid threshold", as the laptop Canvas does (frontend/src/main.ts). */
exports.draw = function (g, state) {
  var d = state.dashboard, i, x, y;
  function text(value, x, y, size, align) {
    g.setColor(1); g.setFont('Vector', size); g.setFontAlign(align || 0, -1);
    g.drawString(String(value), x, y);
  }
  function fittedSize(value,size,width){
    g.setFont('Vector',size);
    while(size>1&&g.stringWidth(String(value))>width){size--;g.setFont('Vector',size);}
    return size;
  }
  function wrap(value,width,count){
    var lines=[],cut;
    while(value&&lines.length<count){
      cut=value.length<=width?value.length:value.lastIndexOf(' ',width);if(cut<=0)cut=width;
      lines.push(value.slice(0,cut));value=value.slice(cut).replace(/^ +/,'');
    }
    return lines;
  }
  function controls(){require('sw-controls').targets(state).forEach(function(target){
    var r=target.rect,width=r[2]-r[0],size=target.action==='preset_input_begin'?22:width<=48?12:16;
    size=fittedSize(target.label,size,width-8);
    g.setColor(1);g.drawRect(r[0],r[1],r[2],r[3]);text(target.label,(r[0]+r[2])/2,(r[1]+r[3])/2-size/2,size);
  });}
  g.clear();
  if (!state.awake) return;
  if (state.recovery) { text('RECOVERY',120,90,24); text('Wheel controls unavailable',120,125,12); g.flip(); return; }
  if(state.screen==='preset_slots'){
    text(state.persistence_error?state.persistence_error.slice(0,38):'PRESETS',120,7,state.persistence_error?10:15);controls();
  }else if(state.screen==='preset_editor'){
    var slot=state.preset_draft,page=state.preset_page,labels=require('sw-preset-editor').labels;
    if(slot){
      var notice=(state.validation_error||state.persistence_error||'').replace(require('sw-configuration').saveFailed+'Error: ','Save failed: ').replace(/^Error: /,'');
      controls();
      if(state.preset_input){
        notice=notice.replace(/^.*: enter a whole percentage 0-100$/,'Enter whole % (0-100)');
        var input=state.preset_input,dip=input.field==='pedal_dip_compensation',center=dip?74:120,width=dip?124:216,length=dip?24:38;
        if(notice){text(notice.slice(0,length),center,1,10);text(notice.slice(length,length*2),center,13,10);}
        else text(dip?'Pedal dip %':labels[page],center,2,12);
        text(input.text||'-',center,notice?26:21,fittedSize(input.text||'-',notice?16:20,width));
      }else{
        var heading=notice||labels[page],split=notice?23:page===3?9:heading.length;
        text(heading.slice(0,split),120,8,notice?10:12);text(heading.slice(split,notice?split*2:undefined),120,23,notice?10:12);
        text('SLOT '+slot.id+' - '+(page+1)+'/4',120,49,12);
      }
    }
  }else if (state.screen === 'presets') {
    text('RIDING PRESETS',120,10,15);
    var result=state.preset_attempt;
    if(result&&!result.pending)text('At attempt: actual/requested · now = fresh value',120,28,8);
    var presetTargets=require('sw-controls').targets(state);
    for (i=0;i<presetTargets.length;i++) {
      var target=presetTargets[i],r=target.rect,height=r[3]-r[1];
      g.setColor(1);g.drawRect(r[0],r[1],r[2],r[3]);
      var size=fittedSize(target.label,14,r[2]-r[0]-8);
      text(target.label,(r[0]+r[2])/2,r[1]+height/2-size/2,size);
      if(target.disabled)text(state.presets[i].configured?'Unavailable':'Unconfigured',(r[0]+r[2])/2,r[3]-18,10);
    }
    if(result&&!result.pending&&!state.horn_feedback){
      var labels={pedal_sensitivity:'Sensitivity',dynamic_assist:'Assist',pedal_dip_compensation:'Dip'};
      Object.keys(result.fields).forEach(function(name,index){var field=result.fields[name],line=labels[name]+' '+(field.actual===null?'?':field.actual)+'/'+field.requested+' '+field.state;
        var current=state.fresh&&state.actual_settings?state.actual_settings[name]:null;
        if(current!==null&&current!==field.actual)line+=' now '+current;
        text(line,120,200+index*12,9);
      });
    }else if(state.horn_feedback){g.setColor(0);g.fillRect(0,0,239,31);text(state.horn_feedback.message,120,10,11);}
  } else if (state.screen === 'settings') {
    var message=state.horn_feedback?state.horn_feedback.message:state.validation_error|| (state.persistence_error?'Configuration needs review':'');
    text(message||'SETTINGS',120,10,message?10:15);controls();
  }else if(state.screen==='alerts'){
    var name=['pwm','speed','battery','lost'][state.alert_page],label=require('sw-configuration').alertDefinitions[name].label;
    controls();
    var message=state.validation_error||state.persistence_error||(state.vibration.output_error?'Vibration output unavailable':'')||(state.horn_feedback?state.horn_feedback.message:'');
    if(message){text(label,120,2,12);wrap(message.replace(/^Error: /,''),23,3).forEach(function(line,index){text(line,120,16+index*11,10);});}
    else {text(label,120,6,12);text((state.alert_page+1)+'/4',120,24,12);}
    if(name==='lost')text('1 short pulse',120,111,14);
  }else if(state.screen==='threshold'){
    var entry=state.threshold_entry,definition=require('sw-configuration').alertDefinitions[entry.alert],refused=!!state.validation_error;
    text(definition.label,120,refused?1:2,12);if(refused)text('Invalid threshold',120,14,10);
    text((entry.text||'-')+' '+definition.unit,120,refused?27:20,20);controls();
  } else if(state.screen==='connection'){
    text('SELECT WHEEL',120,10,15);
    if(state.horn_feedback)text(state.horn_feedback.message,120,27,8);
    if(!state.devices.length)text(state.transport&&state.transport.error?'Discovery failed':'Discovering...',120,90,14);
    for(i=0;i<state.devices.length;i++){
      y=40+i*38;g.setColor(1);g.drawRect(8,y,232,y+34);
      text((state.devices[i].name||'Unnamed wheel').slice(0,22),120,y+4,13);
      text(state.devices[i].id,120,y+19,9);
    }
  } else {
    text('SHERMAN L',12,9,11,-1);
    text('W '+d.watch_battery_percent+'%',228,9,11,1);
    g.setColor(1); g.drawRect(179,8,189,20); g.fillRect(182,5,186,7);
    if (d.charging) text('+',173,7,13,1);
    text(d.speed,120,33,69); text('km/h',120,110,12);
    if(state.horn_feedback)text(state.horn_feedback.message,120,121,10);
    else if(state.preset_attempt){var attempt=state.preset_attempt,current=state.confirmed_preset;text(attempt.name+' · '+(attempt.pending?'Applying':attempt.status==='Confirmed'&&!current?'Unconfirmed':attempt.status),120,121,10);}
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
