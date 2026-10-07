/* One WheelLog LkAp candidate; no established audible result/duration/stop command. */
exports.packet='4c6b41700e0080808001ca87e66f';
exports.create=function(options){
  var nextId=1,pending={},feedback=null,owner=null;
  function show(message,now,session){owner=session;feedback={message:message,expires_s:now+2};}
  return {show:show,request:function(now,session){
      var row={kind:'horn',request:nextId++,session:session,packet_hex:exports.packet,at_s:now};
      pending[row.request]=session;var keys=Object.keys(pending);if(keys.length>32)delete pending[keys[0]];show('Horn request submitting',now,session);
      try{options.send(row);}catch(error){delete pending[row.request];show('Horn request failed: '+String(error),now,session);}
    },result:function(row,now){
      if(pending[row.request]!==row.session)return;
      delete pending[row.request];
      if(row.request===nextId-1)show(row.success===true?'Horn request sent':'Horn request failed: '+(row.error||'Transport submission failed'),now,row.session);
    },tick:function(now,session){
      if(owner!==session)pending={};
      if(feedback&&(owner!==session||now>=feedback.expires_s-1e-9))feedback=null;
    },eligible:function(request,session){return pending[request]===session;},view:function(){return feedback?{message:feedback.message,expires_s:feedback.expires_s}:null;}
  };
};
