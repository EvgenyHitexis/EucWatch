/* Activated only by independent recovery startup; offline tests use fake hardware. */
exports.start=function(options){
  options=options||{};
  var hardware=options.hardware||require('sw-hardware').create();
  var renderer=require('sw-render'),transport=null,stopped=false;
  var store=options.store||require('sw-store').create(),clock=options.clock||{now:getTime},radio=options.radio||NRF;
  function ready(){if(!transport)throw new Error('Wheel transport not ready');return transport;}
  var core=require('sw-app').create({clock:clock,battery:hardware.readBattery,store:store,
    command_output:function(row){ready().submit(row);},
    transport:{discover:function(){ready().discover();},select:function(id){ready().select(id);},disconnect:function(){ready().disconnect();},
      status:function(){return transport?transport.status():null;}},
    vibration_output:hardware.vibrationOutput,vibration_status:hardware.vibrationStatus,
    memory:function(){return process.memory();},
    recover:function(){stopped=true;clearInterval(timer);if(transport)transport.disconnect();hardware.stop();require('Storage').write('sw-recovery','hold');reset();},
    present:function(state){if(!stopped){hardware.setAwake(state.awake);if(state.awake)renderer.draw(hardware.graphics,state);}}
  });
  transport=require('sw-transport').create({app:core,radio:radio,timers:options.timers||{setTimeout:setTimeout,clearTimeout:clearTimeout}});
  // Validation stays visible; a refused input does not stop input.
  hardware.bind(function(name,payload){try{core.gesture(name,payload);}catch(error){}},function(x,y){try{core.touch(x,y);}catch(error){}});
  var timer=setInterval(function(){transport.tick();core.tick();},50);
  return {core:core,transport:transport,stop:function(){if(stopped)return;stopped=true;clearInterval(timer);transport.disconnect();hardware.stop();}};
};
