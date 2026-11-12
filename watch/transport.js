/* Direct Espruino 2v14 NRF/GATT session; explicit guarded control writes only. */
exports.create=function(options){
  var radio=options.radio,app=options.app,timers=options.timers;
  var generation=0,desired=false,busy=false,gatt=null,selected=null,devices=[],recovering=false;
  var error='',link='idle',retry=null,attempts=0,token=null,cleanupPending=false,cleanupGeneration=0,scanTimer=null;
  var wheelCharacteristic=null,write=null;
  function writeResult(row,success,reason){app.action(row.kind==='horn'?'horn_result':'command_result',{attempt:row.attempt,request:row.request,session:row.session,index:row.index,success:success,error:reason||''});}
  function writeOwned(operation){return !operation.cancelled&&operation.generation===generation&&operation.client===gatt&&gatt&&gatt.connected!==false&&(!gatt.device||gatt.device.connected!==false)&&operation.characteristic.properties&&operation.characteristic.properties.writeWithoutResponse===true&&owned(operation.generation)&&link==='subscribed'&&app.commandEligible(operation.row);}
  function cancelWrite(reason){
    if(!write||write.cancelled)return;
    write.cancelled=true;if(write.timeout!==null){timers.clearTimeout(write.timeout);write.timeout=null;}
    writeResult(write.row,false,reason);
    // A timed-out native BLE task still owns its writer until settlement/disconnect.
  }
  function settledDisconnect(candidate){if(write&&write.client===candidate){cancelWrite('Wheel session disconnected; no retry');write=null;}}
  function sendChunk(operation){
    if(!writeOwned(operation)){cancelWrite('Command session ended or telemetry stale; no retry');return;}
    var limit=operation.row.kind==='horn'?operation.row.at_s+3:app.view().preset_attempt.requested_s+5;
    var remaining=limit-app.view().elapsed_s;
    if(remaining<=0){cancelWrite('Command submission timeout; no retry');return;}
    operation.timeout=timers.setTimeout(function(){if(write===operation)cancelWrite('Command submission timeout; no retry');},Math.min(3,remaining)*1000);
    var result;
    try{result=operation.characteristic.writeValue(new Uint8Array(operation.bytes.slice(operation.offset,operation.offset+20)));if(!result||typeof result.then!=='function')throw new Error('writeValue did not return a 2v14 Promise');}
    catch(exception){timers.clearTimeout(operation.timeout);operation.timeout=null;write=null;writeResult(operation.row,false,String(exception));return;}
    result.then(function(){
      if(operation.timeout!==null){timers.clearTimeout(operation.timeout);operation.timeout=null;}
      if(write!==operation)return;
      if(!writeOwned(operation)){cancelWrite('Command ended during write; no retry');write=null;return;}
      operation.offset+=20;
      if(operation.offset<operation.bytes.length){sendChunk(operation);return;}
      write=null;writeResult(operation.row,true);
    },function(exception){
      if(operation.timeout!==null){timers.clearTimeout(operation.timeout);operation.timeout=null;}
      if(write!==operation)return;
      write=null;if(!operation.cancelled)writeResult(operation.row,false,String(exception));
    });
  }
  function publish(){app.tick();}
  function owned(value){var state=app.ownership();return value===generation&&desired&&token===state.session&&!state.recovery;}
  function rawBytes(value){
    var bytes=[],i;
    for(i=0;i<value.byteLength;i++)bytes.push(value.getUint8(i));
    return bytes;
  }
  function close(candidate){
    if(!candidate)return true;
    if(cleanupPending&&gatt===candidate)return false;
    var result,timeout,terminal=link==='failed',reconnecting=desired&&link==='reconnecting',cleanupToken=++cleanupGeneration;
    gatt=candidate;cleanupPending=true;link='disconnecting';
    function failed(exception){
      if(cleanupToken!==cleanupGeneration)return;
      cleanupPending=false;desired=false;link='failed';error='Bluetooth cleanup failed: '+String(exception);publish();
    }
    function finished(){
      if(timeout!==undefined)timers.clearTimeout(timeout);
      if(cleanupToken!==cleanupGeneration)return;
      if(candidate.connected===true||(candidate.device&&candidate.device.connected===true)){failed('Connection remains active');return;}
      if(gatt===candidate)gatt=null;
      settledDisconnect(candidate);wheelCharacteristic=null;
      cleanupPending=false;
      if(reconnecting&&desired){link='reconnecting';schedule();}
      else if(!desired)link=terminal?'failed':'disconnected';
      publish();
    }
    try{
      result=candidate.disconnect();
      if(result&&result.then){
        timeout=timers.setTimeout(function(){failed('Disconnect timed out');},10000);
        result.then(finished,function(exception){timers.clearTimeout(timeout);failed(exception);});
        return false;
      }
      finished();return gatt!==candidate;
    }catch(exception){failed(exception);return false;}
  }
  function schedule(){
    if(busy||cleanupPending||gatt)return;
    if(desired&&attempts<3&&retry===null){
      attempts++;retry=timers.setTimeout(function(){retry=null;if(desired)connect();},1000*Math.pow(2,attempts-1));
    }else if(desired){desired=false;link='failed';error='Reconnect limit reached';publish();}
  }
  function lost(value){
    if(!owned(value))return;
    app.action('disconnect',{session:token});generation++;token=null;
    settledDisconnect(gatt);wheelCharacteristic=null;error='Wheel disconnected';link='reconnecting';recovering=true;gatt=null;publish();schedule();
  }
  function connect(){
    if(busy){error='Previous Bluetooth operation is still pending';publish();return;}
    busy=true;
    var value=++generation,candidate=null,timeout;
    token=app.action('session_start').session;
    link='connecting';error='';publish();
    timeout=timers.setTimeout(function(){
      if(!owned(value))return;
      generation++;app.action('disconnect',{session:token});token=null;
      desired=false;link='failed';error='Bluetooth operation timed out';close(candidate);publish();
      // An unresolved native connect retains ownership until its late result is cleaned.
    },10000);
    function ensure(){if(!owned(value))throw new Error('Ended Bluetooth session');}
    var operation;
    try{operation=radio.connect(selected);}catch(exception){operation=Promise.reject(exception);}
    operation.then(function(server){
      candidate=server;ensure();gatt=server;
      if(server.device&&server.device.on)server.device.on('gattserverdisconnected',function(){lost(value);});
      return server.getPrimaryService('ffe0');
    }).then(function(service){ensure();return service.getCharacteristic('ffe1');}).then(function(characteristic){
      ensure();app.action('connected',{session:token});
      wheelCharacteristic=characteristic;
      var currentToken=token;
      characteristic.on('characteristicvaluechanged',function(event){if(owned(value))app.receive(currentToken,rawBytes(event.target?event.target.value:event.value));});
      return characteristic.startNotifications();
    }).then(function(){
      timers.clearTimeout(timeout);busy=false;
      if(!owned(value)){close(candidate);if(desired&&link==='reconnecting')schedule();return;}
      link='subscribed';attempts=0;recovering=false;publish();
    },function(exception){
      timers.clearTimeout(timeout);busy=false;
      if(!owned(value)){close(candidate);if(desired&&link==='reconnecting')schedule();return;}
      app.action('disconnect',{session:token});token=null;
      if(recovering){
        generation++;link='reconnecting';error=String(exception);
        if(close(candidate))schedule();publish();return;
      }
      link='failed';error=String(exception);desired=false;generation++;
      close(candidate);publish();
    });
  }
  var adapter={status:function(){return {link:link,error:error,selected:selected,active:desired,busy:busy||cleanupPending,connected:!!gatt,control_busy:!!write};},
    submit:function(row){
      if(!row||typeof row!=='object')throw new Error('Invalid command intent');
      row=JSON.parse(JSON.stringify(row));
      if(write)throw new Error('Control writer busy; request discarded');
      if(!owned(generation)||link!=='subscribed'||!gatt||gatt.connected===false||(gatt.device&&gatt.device.connected===false)||!wheelCharacteristic||!app.commandEligible(row))throw new Error('Control connection unavailable or stale');
      if(!wheelCharacteristic.properties||wheelCharacteristic.properties.writeWithoutResponse!==true)throw new Error('FFE1 write-without-response property required');
      if(typeof row.packet_hex!=='string'||!/^([0-9a-f]{2})+$/.test(row.packet_hex))throw new Error('Invalid command packet');
      var bytes=[];for(var i=0;i<row.packet_hex.length;i+=2)bytes.push(parseInt(row.packet_hex.slice(i,i+2),16));
      write={row:row,bytes:bytes,offset:0,client:gatt,characteristic:wheelCharacteristic,generation:generation,timeout:null,cancelled:false};sendChunk(write);
    },
    tick:function(){var state=app.ownership();if(write&&!writeOwned(write))cancelWrite('Command no longer eligible; no retry');if(desired&&(state.recovery||(token!==null&&token!==state.session)))adapter.disconnect();},
    discover:function(){
      if(busy||gatt){error='Disconnect the wheel before discovery';publish();return;}
      if(scanTimer!==null)timers.clearTimeout(scanTimer);
      var value=++generation;
      desired=false;devices=[];link='discovering';error='';app.action('open_connection');app.action('devices',{devices:[]});
      scanTimer=timers.setTimeout(function(){
        scanTimer=null;if(value!==generation)return;
        generation++;link='failed';error='Discovery timed out';publish();
      },6000);
      try{radio.findDevices(function(found){
        if(value!==generation)return;
        timers.clearTimeout(scanTimer);scanTimer=null;
        devices=found.slice(0,4).map(function(device){return {id:device.id,name:device.name||'Unnamed wheel'};});
        link='discovered';app.action('devices',{devices:devices});publish();
      },{timeout:5000,filters:[{services:['ffe0']}]});}
      catch(exception){timers.clearTimeout(scanTimer);scanTimer=null;link='failed';error=String(exception);publish();}
    },
    select:function(id){
      if(busy||gatt)throw new Error('Disconnect the selected wheel first');
      var allowed=devices.some(function(device){return device.id===id;});
      if(!allowed)throw new Error('Select a device from explicit discovery');
      selected=id;desired=true;recovering=false;attempts=0;app.action('wheel_selected');connect();
    },
    disconnect:function(){
      cancelWrite('Wheel disconnect requested; no retry');
      desired=false;recovering=false;generation++;
      if(scanTimer!==null){timers.clearTimeout(scanTimer);scanTimer=null;}
      if(retry!==null){timers.clearTimeout(retry);retry=null;}
      if(token!==null)app.action('disconnect',{session:token});token=null;
      if(gatt&&!cleanupPending)link='disconnecting';
      if(close(gatt))link='disconnected';publish();
    }
  };
  return adapter;
};
