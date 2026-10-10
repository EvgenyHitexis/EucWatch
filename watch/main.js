/* Activated only by independent recovery startup; offline tests use fake hardware. */
exports.start=function(options){
  options=options||{};
  var hardware=options.hardware||require('sw-hardware').create();
  var renderer=require('sw-render'),transport=null,stopped=false;
  var store=options.store||require('sw-store').create(),clock=options.clock||{now:getTime},radio=options.radio||NRF;
  var core=require('sw-app').create({clock:clock,battery:hardware.readBattery,store:store,
    command_output:function(row){if(!transport)throw new Error('Wheel transport not ready');transport.submit(row);},
    vibration_output:hardware.vibrationOutput,vibration_status:hardware.vibrationStatus,
    memory:function(){return process.memory();},
    transportStatus:function(){return transport?transport.status():null;},
    recover:function(){stopped=true;clearInterval(timer);if(transport)transport.disconnect();hardware.stop();require('Storage').write('sw-recovery','hold');reset();},
    present:function(state){if(!stopped){hardware.setAwake(state.awake);if(state.awake)renderer.draw(hardware.graphics,state);}}
  });
  transport=require('sw-transport').create({app:core,radio:radio,timers:options.timers||{setTimeout:setTimeout,clearTimeout:clearTimeout}});
  hardware.bind(function(name,payload){var editor=core.view().preset_editor;if(name==='swipe'&&editor)payload.editor_id=editor.id;core.action(name,payload);},function(x,y){
    var state=core.view(),target=require('sw-controls').hit(state,x,y);
    if(!target)return;
    try{
      if(target.action==='transport_toggle'){if(state.transport&&(state.transport.active||state.transport.connected))transport.disconnect();else transport.discover();}
      else if(target.action==='device_select')transport.select(target.payload.id);
      else core.action(target.action,target.payload);
    }catch(error){/* Validation stays visible; a touch failure does not stop input. */}
  });
  var timer=setInterval(function(){transport.tick();core.tick();},50);
  return {core:core,transport:transport,stop:function(){if(stopped)return;stopped=true;clearInterval(timer);transport.disconnect();hardware.stop();}};
};
