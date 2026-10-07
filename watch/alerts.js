/* ES5 nonoverlapping accepted patterns; events describe software output calls. */
var names=['lost','pwm','speed','battery'];
var patterns={lost:[0.15],pwm:[0.15,0.15,0.15],speed:[0.15,0.15],battery:[0.5]};
var repeats={pwm:2,speed:5};
exports.create=function(options){
  options=options||{};
  var queue=[],pattern=null,events=[],eventCount=0,outputError=null,settings=options.settings,hadFresh=false,lostReported=false;
  var active={pwm:false,speed:false,battery:false},nextRepeat={},fresh=false;
  var batteryArmed=true,batteryRearmSince=null;
  function cancel(now){if(pattern&&pattern.on)emit('stop',now);pattern=null;}
  function emit(phase,now){
    var row={alert:pattern.alert,test:pattern.test,phase:phase,at_s:now,duration_s:patterns[pattern.alert][pattern.index]};
    eventCount++;events.push(row);if(events.length>32)events.shift();
    if(options.output){try{options.output(JSON.parse(JSON.stringify(row)));}catch(error){outputError=String(error);}}
  }
  function enqueue(name,test){
    if(!patterns[name])throw new Error('Unknown alert pattern');
    if(pattern&&pattern.alert===name&&pattern.test===test)return;
    if(queue.some(function(item){return item.alert===name&&item.test===test;}))return;
    queue.push({alert:name,test:test});
  }
  function start(now){
    if(pattern||!queue.length)return;
    queue.sort(function(a,b){return names.indexOf(a.alert)-names.indexOf(b.alert);});
    var next=queue.shift();pattern={alert:next.alert,test:next.test,index:0,on:true,started_s:now,deadline:now+patterns[next.alert][0]};
    if(!next.test&&repeats[next.alert])nextRepeat[next.alert]=now+repeats[next.alert];
    emit('start',now);
  }
  function tick(now){
    if(pattern&&now+1e-9>=pattern.deadline){
      if(pattern.on){
        emit('stop',now);pattern.on=false;
        if(pattern.index+1===patterns[pattern.alert].length||now-pattern.deadline>=0.15-1e-9)pattern=null;
        else pattern.deadline=now+0.15;
      }else if(now-pattern.deadline>=patterns[pattern.alert][pattern.index+1]-1e-9)pattern=null;
      else{pattern.index++;pattern.on=true;pattern.started_s=now;pattern.deadline=now+patterns[pattern.alert][pattern.index];emit('start',now);}
    }
    if(fresh)Object.keys(nextRepeat).forEach(function(name){if(active[name]&&now+1e-9>=nextRepeat[name])enqueue(name,false);});
    start(now);
  }
  function evaluate(now,state){
    fresh=state.fresh;
    if(fresh){
      hadFresh=true;lostReported=false;
      ['pwm','speed'].forEach(function(name){
        var setting=settings[name],value=state[name],hysteresis=name==='pwm'?3:2;
        if(!setting.enabled||value===null)return;
        if(active[name]&&value<=setting.threshold-hysteresis){
          active[name]=false;delete nextRepeat[name];queue=queue.filter(function(item){return item.alert!==name||item.test;});
          if(pattern&&pattern.alert===name&&!pattern.test)cancel(now);
        }else if(!active[name]&&value>=setting.threshold){active[name]=true;enqueue(name,false);}
      });
      var setting=settings.battery;
      if(setting.enabled&&state.battery!==null){
        if(state.battery<=setting.threshold&&batteryArmed){batteryArmed=false;batteryRearmSince=null;enqueue('battery',false);}
        else if(state.battery>=setting.threshold+3){
          if(batteryRearmSince===null)batteryRearmSince=now;
          if(now-batteryRearmSince>=5-1e-9)batteryArmed=true;
        }else batteryRearmSince=null;
      }
    }
    else{
      queue=queue.filter(function(item){return item.alert==='lost'||item.test;});
      if(pattern&&pattern.alert!=='lost'&&!pattern.test)cancel(now);
      active={pwm:false,speed:false,battery:false};nextRepeat={};
      batteryRearmSince=null;
      if(hadFresh&&!lostReported&&settings.lost.enabled){enqueue('lost',false);lostReported=true;}
    }
    tick(now);
  }
  return {configure:function(value,now){
      names.forEach(function(name){if(JSON.stringify(value[name])!==JSON.stringify(settings[name])){
        active[name]=false;delete nextRepeat[name];queue=queue.filter(function(item){return item.alert!==name||item.test;});
        if(pattern&&pattern.alert===name&&!pattern.test)cancel(now);
        if(name==='battery'){batteryArmed=true;batteryRearmSince=null;}
      }});settings=value;
    },evaluate:evaluate,test:function(name,now){enqueue(name,true);tick(now);},tick:tick,
    view:function(){return {simulated:false,current:pattern&&pattern.on?{alert:pattern.alert,test:pattern.test,started_s:pattern.started_s,duration_s:patterns[pattern.alert][pattern.index]}:null,
      events:JSON.parse(JSON.stringify(events)),event_count:eventCount,queued:queue.map(function(item){return item.alert;}),output_error:outputError};}
  };
};
