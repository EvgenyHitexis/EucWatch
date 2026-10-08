/* Original bounded configuration JSONL endpoint. Native APIs: Espruino 2v14. */
var configuration=require('sw-configuration');
var MAX_CONTENT=4096,MAX_LINE=512,CHUNK=64;
function quoteBytes(text){
  /* 2v14 JSON.stringify escapes each high byte as a Unicode code point.
     Saved names are UTF-8 bytes; preserve those bytes on the protocol wire. */
  var quoted='"',i,c,code,escapes={8:'\\b',9:'\\t',10:'\\n',12:'\\f',13:'\\r',34:'\\"',92:'\\\\'};
  for(i=0;i<text.length;i++){c=text.charAt(i);code=text.charCodeAt(i);quoted+=escapes[code]|| (code<32?'\\u00'+('0'+code.toString(16)).slice(-2):c);}
  return quoted+'"';
}
function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(function(key){return quoteBytes(key)+':'+canonical(value[key]);}).join(',')+'}';
  if(typeof value==='string')return quoteBytes(value);
  return JSON.stringify(value);
}
function digest(text){
  var bytes=new Uint8Array(require('crypto').SHA256(text)),hex='',i;
  if(bytes.length!==32)throw new Error('Native SHA256 is required');
  for(i=0;i<bytes.length;i++)hex+=('0'+bytes[i].toString(16)).slice(-2);
  return hex;
}
function integer(value){return typeof value==='number'&&isFinite(value)&&Math.floor(value)===value;}
function utf8(code){
  if(code<2048)return String.fromCharCode(192|(code>>6),128|(code&63));
  if(code<65536)return String.fromCharCode(224|(code>>12),128|((code>>6)&63),128|(code&63));
  return String.fromCharCode(240|(code>>18),128|((code>>12)&63),128|((code>>6)&63),128|(code&63));
}
function escapedUnicode(text){
  var result='',inside=false,i=0,c,code,low;
  while(i<text.length){
    c=text.charAt(i++);
    if(c==='"'){inside=!inside;result+=c;continue;}
    if(inside&&c==='\\'){
      if(text.charAt(i)==='u'&&/^[0-9a-fA-F]{4}$/.test(text.slice(i+1,i+5))){
        code=parseInt(text.slice(i+1,i+5),16);
        if(code>=128){
          i+=5;
          if(code>=55296&&code<=56319){if(text.slice(i,i+2)!=='\\u'||!/^[0-9a-fA-F]{4}$/.test(text.slice(i+2,i+6)))throw new Error('Unpaired Unicode surrogate');low=parseInt(text.slice(i+2,i+6),16);if(low<56320||low>57343)throw new Error('Unpaired Unicode surrogate');code=65536+(code-55296)*1024+low-56320;i+=6;}
          else if(code>=56320&&code<=57343)throw new Error('Unpaired Unicode surrogate');
          result+=utf8(code);continue;
        }
      }
      result+=c;if(i<text.length)result+=text.charAt(i++);continue;
    }
    result+=c;
  }
  return result;
}
function parse(text){
  /* Native parser owns syntax; this bounded scan rejects ambiguous duplicate keys. */
  var stack=[],i=0,j,c,key,top;
  while(i<text.length){
    c=text.charAt(i);
    if(c==='"'){
      j=i+1;while(j<text.length){if(text.charAt(j)==='\\'){j+=2;continue;}if(text.charAt(j)==='"')break;j++;}
      top=stack.length?stack[stack.length-1]:null;
      if(top&&top.object&&top.key){key=JSON.parse(text.slice(i,j+1));if(top.seen.indexOf(key)>=0)throw new Error('Duplicate JSON field');top.seen.push(key);top.key=false;}
      i=j+1;continue;
    }
    if(c==='{'||c==='['){if(stack.length>=12)throw new Error('Configuration JSON nesting exceeds limit');stack.push({object:c==='{',key:c==='{',seen:[]});}
    else if(c==='}'||c===']')stack.pop();
    else if(c===','&&stack.length&&stack[stack.length-1].object)stack[stack.length-1].key=true;
    i++;
  }
  return JSON.parse(escapedUnicode(text));
}
function content(value){var text=canonical(configuration.validate(value));if(text.length>MAX_CONTENT)throw new Error('Watch configuration exceeds 4096 bytes');return text;}
function chunk(data,index){return {index:index,data:btoa(data),crc32:E.CRC32(data)>>>0};}
exports.endpoint=function(options){
  var store=options.store,snapshot='',staging=null;
  function active(){return configuration.validate(store.load()||configuration.defaults());}
  function staged(){if(!staging)throw new Error('No configuration is staged');return staging;}
  return {reset:function(){staging=null;snapshot='';store.discard();},status:function(){return {staging:!!staging,received:staging?staging.data.length:0,validated:!!(staging&&staging.candidate),snapshot_bytes:snapshot.length};},exchange:function(message){
    var row,op='',result={},saved,data,index,response;
    try{
      if(typeof message!=='string'||message.length>MAX_LINE||message.charAt(message.length-1)!=='\n'||message.slice(0,-1).indexOf('\n')>=0)throw new Error('Bounded JSONL message required');
      row=parse(message);op=row&&typeof row.op==='string'?row.op:'';
      if(!row||typeof row!=='object'||Array.isArray(row))throw new Error('Protocol object required');
      if(row.protocol!==1||!integer(row.protocol))throw new Error('Unsupported configuration protocol');
      if(op==='read'){
        saved=active();snapshot=content(saved);result={revision:saved.revision,size:snapshot.length,digest:digest(snapshot)};
      }else if(op==='read_chunk'){
        index=row.index;if(!integer(index)||index<0)throw new Error('Invalid chunk index');
        data=snapshot.slice(index*CHUNK,(index+1)*CHUNK);if(!data)throw new Error('Configuration snapshot chunk unavailable');result=chunk(data,index);
      }else if(op==='stage'){
        saved=active();
        if(!integer(row.size)||row.size<=0||row.size>MAX_CONTENT||!integer(row.expected_revision)||row.expected_revision!==saved.revision||row.expected_digest!==digest(content(saved))||typeof row.digest!=='string'||!/^[0-9a-f]{64}$/.test(row.digest))throw new Error('Invalid or stale configuration staging request');
        staging={size:row.size,digest:row.digest,expected_revision:row.expected_revision,expected_digest:row.expected_digest,data:'',next:0,candidate:null};result={staged:false};
      }else if(op==='chunk'){
        saved=staged();if(!integer(row.index)||row.index!==saved.next)throw new Error('Configuration chunks must arrive in order');
        if(typeof row.data!=='string'||row.data.length>88||!/^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(row.data))throw new Error('Invalid base64 chunk');
        data=atob(row.data);
        if(data.length<1||data.length>CHUNK||!integer(row.crc32)||row.crc32<0||row.crc32>4294967295||(E.CRC32(data)>>>0)!==row.crc32)throw new Error('Chunk CRC/size mismatch');
        if(saved.data.length+data.length>saved.size)throw new Error('Configuration staging overflow');
        saved.data+=data;saved.next++;saved.candidate=null;result={received:saved.data.length};
      }else if(op==='validate'){
        saved=staged();saved.candidate=null;
        if(saved.data.length!==saved.size||digest(saved.data)!==saved.digest)throw new Error('Incomplete or corrupt staged configuration');
        data=configuration.validate(parse(saved.data));if(data.revision<=saved.expected_revision)throw new Error('Activation requires a new revision');
        store.stage(data);saved.candidate=data;result={validated:true};
      }else if(op==='commit'){
        saved=staged();data=active();
        if(!saved.candidate||data.revision!==saved.expected_revision||digest(content(data))!==saved.expected_digest)throw new Error('Saved content changed or stage not validated');
        store.activate(saved.candidate);data=active();
        if(content(data)!==content(saved.candidate))throw new Error('Committed content readback mismatch');
        result={revision:data.revision};staging=null;
      }else if(op==='abort'){staging=null;store.discard();result={aborted:true};}
      else if(op==='finish'){active();staging=null;store.discard();result={returned:true};}
      else throw new Error('Unsupported configuration operation');
      response={protocol:1,ok:true,op:op};Object.keys(result).forEach(function(key){response[key]=result[key];});
    }catch(error){response={protocol:1,ok:false,op:op.slice(0,64),error:((op==='commit'?'Commit outcome unconfirmed; read active saved content: ':'')+String(error)).slice(0,160)};}
    return JSON.stringify(response)+'\n';
  }};
};
exports.create=function(options){
  var app=options.app,wheel=options.wheel,radio=options.radio,serial=options.serial,loopback=options.loopback,clock=options.clock;
  var endpoint=exports.endpoint({store:options.store}),generation=0,active=false,phase='inactive',error='',line='',drop=false,queue='',lastInput=0,lastWrite=0,closingAt=null,returning=false;
  var previousConsole=null,attached=false,advertised=false,session=null;
  function security(){var state=radio.getSecurityStatus();if(!state||typeof state.connected!=='boolean')throw new Error('Peripheral connection state unavailable');return state.connected;}
  function notify(){if(options.changed)options.changed();}
  function clearInput(){line='';drop=false;queue='';endpoint.reset();}
  function failed(reason){error=String(reason);phase='failed';returning=false;queue='';line='';drop=false;notify();}
  function enqueue(response){if(queue.length+response.length>1024)throw new Error('Configuration response queue full');queue+=response;}
  function data(bytes){
    if(!active||phase!=='ready'||returning)return;
    if(typeof bytes!=='string'){failed('UART byte string required');return;}
    var i,c,response,row;
    lastInput=clock.now();
    try{
      var owner=app.ownership();if(owner.recovery||owner.session!==session){adapter.stop();return;}
      if(!security())return;
      for(i=0;i<bytes.length;i++){
        c=bytes.charAt(i);
        if(drop){if(c==='\n'){drop=false;enqueue(JSON.stringify({protocol:1,ok:false,op:'',error:'Protocol line exceeds 512 bytes'})+'\n');}continue;}
        line+=c;
        if(line.length>MAX_LINE){line='';drop=c!=='\n';if(!drop)enqueue(JSON.stringify({protocol:1,ok:false,op:'',error:'Protocol line exceeds 512 bytes'})+'\n');continue;}
        if(c==='\n'){
          response=endpoint.exchange(line);line='';row=JSON.parse(response);enqueue(response);
          if(!row.ok)error=row.error;else if(row.op==='read'||row.op==='stage')error='';
          if(row.ok&&row.op==='finish'){returning=true;phase='sending return acknowledgement';lastWrite=clock.now();break;}
        }
      }
    }catch(exception){failed(exception);}
    notify();
  }
  function connected(){if(!active)return;generation++;try{clearInput();lastInput=clock.now();error='';if(advertised)phase='ready';notify();}catch(exception){failed(exception);}}
  function disconnected(){if(!active)return;generation++;var drained=returning&&!queue;try{clearInput();if(drained)confirmReturn();else{returning=false;if(advertised)phase='ready';error='Laptop disconnected; saved content retained; read active content';notify();}}catch(exception){failed(exception);}}
  function detach(){if(!attached)return;serial.removeListener('data',data);radio.removeListener('connect',connected);radio.removeListener('disconnect',disconnected);attached=false;}
  function confirmReturn(){
    if(!active||!returning)return;
    try{
      if(security())return;
      detach();active=false;advertised=false;phase='inactive';generation++;session=null;endpoint.reset();
      if(options.restoreConsole)options.restoreConsole(previousConsole);
      if(options.returned)options.returned();
    }catch(exception){active=true;failed(exception);}
    notify();
  }
  var adapter={status:function(){var saved=endpoint.status();return {active:active,generation:generation,phase:phase,error:error,staging:saved.staging,received:saved.received,validated:saved.validated,queued_bytes:queue.length,retained_line_bytes:line.length,returning:returning};},
    begin:function(){
      if(active)throw new Error('Configuration transfer already active');
      app.action('transfer_begin');session=app.ownership().session;generation++;active=true;returning=false;phase='disconnecting wheel';error='';closingAt=null;lastInput=clock.now();
      try{clearInput();previousConsole=options.consoleDevice?options.consoleDevice():null;loopback.setConsole(true);wheel.disconnect();}
      catch(exception){failed(exception);}
      notify();
    },receive:data,
    tick:function(){
      if(!active)return;
      var owned=app.ownership(),now=clock.now(),state,writingGeneration,result,flags;
      if(owned.recovery||owned.session!==session){adapter.stop();return;}
      try{
        if(phase==='disconnecting wheel'){
          state=wheel.status();
          if(state.connected||state.busy||state.active){if(state.link==='failed'||now-lastInput>12)failed('Wheel disconnect not confirmed; transfer unavailable');return;}
          radio.sleep();phase='disconnecting prior peripheral';closingAt=now;
        }
        if(phase==='disconnecting prior peripheral'){
          if(security()){if(now-closingAt>3)failed('Prior peripheral disconnect not confirmed');return;}
          if(!attached){serial.on('data',data);radio.on('connect',connected);radio.on('disconnect',disconnected);attached=true;}
          radio.setServices({},{uart:true});radio.setAdvertising({},{name:'Sherman-transfer'});radio.wake();advertised=true;phase='ready';lastInput=now;lastWrite=now;notify();
        }
        if(queue&&now-lastWrite>=0.02-1e-9){
          if(!security())throw new Error('Laptop disconnected before acknowledgement');
          writingGeneration=generation;result=serial.write(queue.slice(0,20));
          if(writingGeneration!==generation||!active)return;
          if(result===false){if(now-lastWrite>=3)throw new Error('UART output refused; read active content before retry');return;}
          flags=options.outputErrors?options.outputErrors():[];
          if(flags.indexOf('BUFFER_FULL')>=0||flags.indexOf('FIFO_FULL')>=0)throw new Error('UART bytes lost; reconnect and read active content');
          queue=queue.slice(20);lastWrite=now;
        }
        if(returning&&!queue&&phase!=='disconnecting laptop'&&now-lastWrite>=0.05){radio.sleep();phase='disconnecting laptop';closingAt=now;notify();}
        if(phase==='disconnecting laptop'){if(!security())confirmReturn();else if(now-closingAt>3)failed('Laptop disconnect not confirmed; Return can retry');}
        if(!returning&&phase==='ready'&&now-lastInput>=30&&(line||endpoint.status().staging)){clearInput();error='Transfer staging timed out; saved content retained';notify();}
      }catch(exception){failed(exception);}
    },returnToRiding:function(){
      if(!active)throw new Error('Configuration transfer is inactive');
      try{configuration.validate(options.store.load()||configuration.defaults());clearInput();returning=true;phase='disconnecting laptop';closingAt=clock.now();radio.sleep();confirmReturn();}
      catch(exception){failed(exception);}
    },stop:function(){
      generation++;active=false;advertised=false;returning=false;phase='inactive';detach();line='';queue='';drop=false;try{endpoint.reset();radio.sleep();}catch(exception){error=String(exception);}
    }
  };
  return adapter;
};
