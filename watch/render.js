/* Original 240x240, 1-bpp presentation; Canvas layout carried to Espruino Graphics. */
exports.draw = function (g, state) {
  var d = state.dashboard, i, x, y;
  function text(value, x, y, size, align) {
    g.setColor(1); g.setFont('Vector', size); g.setFontAlign(align || 0, -1);
    g.drawString(String(value), x, y);
  }
  function controls(){require('sw-controls').targets(state).forEach(function(target){var r=target.rect;g.setColor(1);g.drawRect(r[0],r[1],r[2],r[3]);text(target.label,(r[0]+r[2])/2,(r[1]+r[3])/2-7,target.label.length>12?13:15);});}
  g.clear();
  if (!state.awake) return;
  if (state.recovery) { text('RECOVERY',120,90,24); text('Wheel controls unavailable',120,125,12); g.flip(); return; }
  if (state.screen === 'presets') {
    text('RIDING PRESETS',120,10,15);
    for (i=0;i<4;i++) {
      x=9+(i%2)*115; y=43+Math.floor(i/2)*81;
      g.setColor(1); g.drawRect(x,y,x+105,y+71);
      text(state.presets[i].name,x+53,y+22,14);
      text('Unconfigured',x+53,y+48,10);
    }
    text('Swipe right to return',120,216,11);
  } else if (state.screen === 'settings') {
    text('SETTINGS',120,10,15);
    controls();
    if(state.persistence_error)text('Configuration needs review',120,188,12);
    text('Swipe right to return',120,216,11);
  }else if(state.screen==='alerts'){
    var name=['pwm','speed','battery','lost'][state.alert_page];
    text('VIBRATION ALERTS '+(state.alert_page+1)+'/4',120,9,14);
    text({pwm:'High PWM',speed:'High speed',battery:'Low wheel battery',lost:'Lost telemetry'}[name],12,41,13,-1);
    controls();
    if(name==='lost')text('One short pulse',120,90,14);
    else text(name==='speed'?'km/h':'%',120,114,10);
    if(state.validation_error||state.persistence_error)text((state.validation_error||state.persistence_error).replace(/^Error: /,'').slice(0,35),120,153,11);
    else if(state.vibration.output_error)text('Vibration output unavailable',120,153,11);
  }else if(state.screen==='threshold'){
    text(state.threshold_input.text||'Enter threshold',120,9,18);controls();
    if(state.validation_error)text('Invalid threshold',120,27,11);
  } else if(state.screen==='connection'){
    text('SELECT WHEEL',120,10,15);
    if(!state.devices.length)text(state.transport&&state.transport.error?'Discovery failed':'Discovering...',120,90,14);
    for(i=0;i<state.devices.length;i++){
      y=40+i*38;g.setColor(1);g.drawRect(8,y,232,y+34);
      text((state.devices[i].name||'Unnamed wheel').slice(0,22),120,y+4,13);
      text(state.devices[i].id,120,y+19,9);
    }
    text('Swipe right to return',120,216,11);
  } else {
    text('SHERMAN L',12,9,11,-1);
    text('W '+d.watch_battery_percent+'%',228,9,11,1);
    g.setColor(1); g.drawRect(179,8,189,20); g.fillRect(182,5,186,7);
    if (d.charging) text('+',173,7,13,1);
    text(d.speed,120,33,69); text('km/h',120,110,12);
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
