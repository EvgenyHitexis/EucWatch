/* Original serialized preset behavior. Packet offsets mirror verified laptop evidence. */
var protocol=require('sw-protocol'),copy=function(value){return JSON.parse(JSON.stringify(value));};
var fields=['pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
exports.command=function(field,value){
  var index=fields.indexOf(field),identifiers=[15,31,33],offsets=[10,26,28],bytes=[],i,crc;
  if(index<0||typeof value!=='number'||Math.floor(value)!==value||value<0||value>100)throw new Error('Setting must be a whole supported percentage');
  for(i=0;i<=offsets[index];i++)bytes.push(128);
  [76,100,65,112,identifiers[index],1,2].forEach(function(byte,position){bytes[position]=byte;});
  bytes[offsets[index]]=value;crc=protocol.crc(bytes,bytes.length);
  return bytes.concat([crc>>>24,(crc>>>16)&255,(crc>>>8)&255,crc&255]);
};
exports.hex=function(bytes){return bytes.map(function(byte){return ('0'+byte.toString(16)).slice(-2);}).join('');};
exports.create=function(options){
  var attempt=null,confirmed=null,actual=null,actualSession=null,nextId=1,api;
  function pending(){return !!(attempt&&attempt.pending);}
  function finish(now,reason){if(!pending())return;attempt.status=Object.keys(attempt.fields).some(function(name){return attempt.fields[name].state==='confirmed';})?'Partially applied':'Not confirmed';attempt.pending=false;attempt.reason=reason;attempt.finished_s=now;attempt.awaiting=null;confirmed=null;}
  function dispatch(now){
    var names=Object.keys(attempt.fields),name=names[attempt.next_index],value=attempt.fields[name].requested;
    attempt.awaiting=attempt.next_index;
    options.send({kind:'preset',attempt:attempt.id,session:attempt.session,index:attempt.awaiting,field:name,value:value,packet_hex:exports.hex(exports.command(name,value)),at_s:now});
  }
  api={pending:pending,invalidate:function(now,reason){confirmed=null;finish(now,reason);},start:function(preset,revision,session,now){
      var selected={};fields.forEach(function(name){if(Object.prototype.hasOwnProperty.call(preset,name))selected[name]={requested:preset[name],actual:null,state:'unknown',submitted_s:null,matches:0};});
      confirmed=null;attempt={id:nextId++,slot:preset.id,name:preset.name,revision:revision,session:session,status:'submitting',pending:true,requested_s:now,submitted_s:null,finished_s:null,reason:'',fields:selected,readbacks:[],matching_frames:0,next_index:0,awaiting:null};dispatch(now);
    },result:function(row,now){
      if(!pending()||row.attempt!==attempt.id||row.session!==attempt.session||row.index!==attempt.awaiting)return;
      if(row.success!==true){finish(now,row.error||'Transport submission failed');return;}
      var name=Object.keys(attempt.fields)[row.index];attempt.fields[name].submitted_s=now;attempt.next_index++;attempt.awaiting=null;
      if(attempt.next_index===Object.keys(attempt.fields).length){attempt.status='confirming';attempt.submitted_s=now;}
      else dispatch(now);
    },tick:function(now,state){
      if(actualSession!==state.session)actual=null;
      if(confirmed&&(!state.fresh||confirmed.session!==state.session||confirmed.revision!==state.revision))confirmed=null;
      if(!pending())return;
      if(attempt.session!==state.session)finish(now,'Wheel session ended');
      else if(attempt.revision!==state.revision)finish(now,'Saved configuration changed');
      else if(!state.fresh||state.recovery)finish(now,'Telemetry is stale, disconnected or recovery active');
      else if(attempt.submitted_s===null&&now-attempt.requested_s>=5-1e-9)finish(now,'Submission timeout');
      else if(attempt.submitted_s!==null&&now-attempt.submitted_s>=10-1e-9)finish(now,'Confirmation timeout');
    },observe:function(values,now,session){
      actual=copy(values);actualSession=session;
      if(confirmed&&Object.keys(confirmed.values).some(function(name){return values[name]!==confirmed.values[name];}))confirmed=null;
      if(!pending()||session!==attempt.session||now<=attempt.requested_s)return;
      attempt.readbacks.push(now);if(attempt.readbacks.length>64)attempt.readbacks.shift();
      Object.keys(attempt.fields).forEach(function(name){var field=attempt.fields[name],value=values[name];field.actual=value;
        if(field.submitted_s===null||now<=field.submitted_s||value===null||value===undefined){field.matches=0;field.state='unknown';}
        else if(value!==field.requested){field.matches=0;field.state='mismatched';}
        else {field.matches++;field.state=field.matches>=2?'confirmed':'unknown';}
      });
      if(attempt.submitted_s===null||now<=attempt.submitted_s)return;
      if(Object.keys(attempt.fields).every(function(name){return values[name]===attempt.fields[name].requested;}))attempt.matching_frames++;else attempt.matching_frames=0;
      if(attempt.matching_frames>=2){attempt.status='Confirmed';attempt.pending=false;attempt.finished_s=now;var requested={};Object.keys(attempt.fields).forEach(function(name){requested[name]=attempt.fields[name].requested;});confirmed={slot:attempt.slot,name:attempt.name,revision:attempt.revision,session:session,values:requested};}
    },view:function(){return {attempt:attempt?copy(attempt):null,confirmed:confirmed?copy(confirmed):null,actual:actual?copy(actual):null};}
  };return api;
};
