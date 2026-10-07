/* Original 240x240, 1-bpp presentation; Canvas layout carried to Espruino Graphics. */
exports.draw = function (g, state) {
  var d = state.dashboard, i, x, y;
  function text(value, x, y, size, align) {
    g.setColor(1); g.setFont('Vector', size); g.setFontAlign(align || 0, -1);
    g.drawString(String(value), x, y);
  }
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
    g.setColor(1); g.drawRect(12,71,228,131);
    text('Sleep screen',120,91,20);
    g.drawRect(12,145,228,194);text(state.transport&&(state.transport.active||state.transport.connected)?'Disconnect wheel':'Connect wheel',120,160,18);
    text('Swipe right to return',120,216,11);
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
