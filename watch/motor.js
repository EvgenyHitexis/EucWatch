/* Installed D16 active-high output; software timestamps are not motor onset. */
exports.create=function(options){
  var timer=null,on=false,events=[],eventCount=0,error=null,stopped=false;
  options.write(0);
  function record(value,source){eventCount++;events.push({phase:value?'start':'stop',at_s:options.now(),source:source});if(events.length>32)events.shift();}
  function off(source){if(timer!==null){options.timers.clearTimeout(timer);timer=null;}if(on){on=false;options.write(0);record(false,source);}}
  return {output:function(row){
      if(stopped)throw new Error('Watch vibration output unavailable after shutdown');
      if(row.phase==='stop'){off('scheduler');return;}
      if(row.phase!=='start'||(row.duration_s!==0.15&&row.duration_s!==0.5))throw new Error('Unsupported motor pulse');
      if(on)throw new Error('Motor output already active');
      try{options.write(1);on=true;record(true,'scheduler');}
      catch(exception){error=String(exception);try{options.write(0);}catch(ignored){}throw exception;}
      timer=options.timers.setTimeout(function(){timer=null;off('deadline');},row.duration_s*1000);
    },stop:function(){stopped=true;off('shutdown');options.write(0);},
    view:function(){return {active:on,error:error,event_count:eventCount,events:JSON.parse(JSON.stringify(events))};}
  };
};
