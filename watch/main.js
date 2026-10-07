/* Activated only by independent recovery startup; offline tests use fake hardware. */
exports.start=function(options){
  options=options||{};
  var hardware=options.hardware||require('sw-hardware').create();
  var renderer=require('sw-render'),transport=null,stopped=false;
  var core=require('sw-app').create({clock:options.clock||{now:getTime},battery:hardware.readBattery,
    memory:function(){return process.memory();},
    transportStatus:function(){return transport?transport.status():null;},
    recover:function(){if(transport)transport.disconnect();require('Storage').write('sw-recovery','hold');reset();},
    present:function(state){if(!stopped){hardware.setAwake(state.awake);if(state.awake)renderer.draw(hardware.graphics,state);}}
  });
  transport=require('sw-transport').create({app:core,radio:options.radio||NRF,timers:options.timers||{setTimeout:setTimeout,clearTimeout:clearTimeout}});
  hardware.bind(function(name,payload){core.action(name,payload);},function(x,y){
    var state=core.view();
    if(state.screen==='settings'&&x>=12&&x<=228){
      if(y>=71&&y<=131)core.action('sleep');
      else if(y>=145&&y<=194){if(state.transport&&(state.transport.active||state.transport.connected))transport.disconnect();else transport.discover();}
    }else if(state.screen==='connection'&&y>=40&&y<192){
      var item=state.devices[Math.floor((y-40)/38)];if(item)transport.select(item.id);
    }
  });
  var timer=setInterval(function(){transport.tick();core.tick();},50);
  return {core:core,transport:transport,stop:function(){if(stopped)return;stopped=true;clearInterval(timer);transport.disconnect();hardware.stop();}};
};
