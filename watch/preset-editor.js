/* Session-bound editor. Saved definitions supply names and dip inclusion only. */
var configuration=require('sw-configuration');
exports.fields=['name','pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
exports.labels=['Name','Pedal sensitivity','Dynamic assist','Pedal dip compensation'];
exports.attemptName=function(attempt){return attempt.kind==='editor'?exports.labels[exports.fields.indexOf(Object.keys(attempt.fields)[0])]:attempt.name;};
exports.keys=function(input){if(input.field!=='name')return ['1','2','3','4','5','6','7','8','9','Clear','0','<'];var text='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.slice(input.letters*12,input.letters*12+12);return (input.lowercase?text.toLowerCase():text).split('');};
exports.slot=function(slot){if(typeof slot!=='number'||Math.floor(slot)!==slot||slot<1||slot>4)throw new Error('Choose one of the four fixed preset slots');return slot;};
exports.replacement=function(config,draft){var proposed=configuration.copy(config);proposed.presets[exports.slot(draft.id)-1]=configuration.copy(draft);proposed.revision++;return configuration.validate(proposed);};
exports.create=function(){
  var request=null,draft=null,values=null;
  return {
    open:function(slot,session,now){draft=null;values=null;request={slot:exports.slot(slot),session:session,requested_s:now,status:'waiting',reason:'',seeded_s:null};},
    close:function(){request=null;draft=null;values=null;},
    tick:function(now,session,connected){
      if(!request||request.status==='unavailable')return;
      var reason=request.session!==session||!connected?'Wheel session ended; reopen for fresh settings':request.status==='waiting'&&now-request.requested_s>=5-1e-9?'Current wheel settings unavailable (readback timeout)':'';
      if(reason){request.status='unavailable';request.reason=reason;draft=null;values=null;}
    },
    observe:function(config,settings,session,now){
      if(!request||request.session!==session||request.status==='unavailable')return;
      values=configuration.copy(settings);
      if(request.status!=='waiting'||exports.fields.slice(1).some(function(field){return settings[field]===null||settings[field]===undefined;}))return;
      var saved=config.presets[request.slot-1];
      draft={id:saved.id,name:saved.name,configured:true,pedal_sensitivity:settings.pedal_sensitivity,dynamic_assist:settings.dynamic_assist};
      if(Object.prototype.hasOwnProperty.call(saved,'pedal_dip_compensation'))draft.pedal_dip_compensation=settings.pedal_dip_compensation;
      request.status='ready';request.seeded_s=now;
    },
    update:function(config,changes){
      if(!draft)throw new Error('Wait for fresh settings before editing');
      var names=Object.keys(changes),field=names[0],proposed=configuration.copy(draft);
      if(names.length!==1||exports.fields.indexOf(field)<0)throw new Error('Complete one field adjustment at a time');
      if(field==='pedal_dip_compensation'&&changes[field]===null)delete proposed[field];else proposed[field]=changes[field];
      var configNext=exports.replacement(config,proposed);draft=proposed;return configNext;
    },
    view:function(){return {request:configuration.copy(request),draft:configuration.copy(draft),values:configuration.copy(values)};}
  };
};
