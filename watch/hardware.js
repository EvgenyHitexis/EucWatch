/* Original scoped hardware adapter. Pin/register provenance: THIRD_PARTY.md. */
exports.create=function(options){
  options=options||{};
  var g=require('sw-display').create(options), i2c=new I2C(), watches=[], touchTimer=null;
  var awake=true, touchWatch=null, onAction=function(){}, onTap=function(){}, touchStart=null;
  D15.write(1); // Installed button supply enable.
  D16.write(0); // Installed vibration active level is 1; keep startup inactive.
  var motor=require('sw-motor').create({write:function(value){D16.write(value);},now:getTime,timers:{setTimeout:setTimeout,clearTimeout:clearTimeout}});
  i2c.setup({scl:D7,sda:D6,bitrate:100000});
  function readBattery(){
    var voltage=7.1*analogRead(D31), percent;
    poke32(0x50000700+(D31*4),2); // Disconnect analog pin after each sample.
    percent=voltage<=3.5?0:voltage>=4.19?100:Math.floor((voltage-3.5)/(4.19-3.5)*100);
    return {voltage:voltage,percent:percent,charging:!!digitalRead(D19)};
  }
  function touchInterrupt(){
    i2c.writeTo(0x15,0);
    var bytes=i2c.readFrom(0x15,7), gesture=bytes[1];
    var x=((bytes[3]&15)<<8)|bytes[4], y=((bytes[5]&15)<<8)|bytes[6];
    if(!awake) return;
    if(gesture===0&&bytes[2]&&!touchStart)touchStart={x:x,y:y};
    if(gesture===3) onAction('swipe',{direction:'left'});
    else if(gesture===4) onAction('swipe',{direction:'right'});
    else if(gesture===2) onAction('swipe',{direction:'up'});
    else if(gesture===1) onAction('swipe',{direction:'down',from_top:touchStart?touchStart.y<=45:y<=45});
    else if(gesture===5 || gesture===12) {onAction('interact');onTap(x,y);}
    if(gesture!==0||!bytes[2])touchStart=null;
  }
  function startTouch(){
    if(touchTimer!==null)clearTimeout(touchTimer);
    digitalPulse(D10,1,[5,50]);
    touchTimer=setTimeout(function(){
      touchTimer=null;if(!awake)return;
      i2c.writeTo(0x15,0xEC,0);
      i2c.writeTo(0x15,0xF5,35);i2c.writeTo(0x15,0xF6,3);i2c.writeTo(0x15,0xF7,7);
      i2c.writeTo(0x15,0xF8,50);i2c.writeTo(0x15,0xF9,2);i2c.writeTo(0x15,0xFA,17);
      i2c.writeTo(0x15,0xFE,1);
      if(touchWatch===null) touchWatch=setWatch(touchInterrupt,D28,{repeat:true,edge:'falling'});
    },200);
  }
  startTouch();
  return {graphics:g,readBattery:readBattery,vibrationOutput:motor.output,vibrationStatus:motor.view,
    bind:function(action,tap){
      onAction=action;onTap=tap;
      watches.push(setWatch(function(event){onAction(event.state?'button_down':'button_up');},BTN1,{repeat:true,edge:'both',debounce:50}));
      watches.push(setWatch(function(){onAction('battery_refresh');},D19,{repeat:true,edge:'both',debounce:500}));
    },
    setAwake:function(value){
      if(value===awake) {if(value)g.on();return;}
      awake=value;
      if(value){g.on();startTouch();}
      else {if(touchTimer!==null){clearTimeout(touchTimer);touchTimer=null;}touchStart=null;g.off();i2c.writeTo(0x15,0xE5,3);}
    },
    stop:function(){
      watches.forEach(function(id){clearWatch(id);});if(touchTimer!==null)clearTimeout(touchTimer);
      if(touchWatch!==null)clearWatch(touchWatch);
      motor.stop();
      g.off();
    }
  };
};
