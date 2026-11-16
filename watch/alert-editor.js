/* Alert editor: alert draft, alert page and threshold entry with their rules. Only the caller's Save replaces saved alerts. */
var configuration=require('sw-configuration');
/* Every editor-scoped action; alerts_begin stays the core's, since it decides when editing may open. */
exports.actions=['alerts_update','alerts_page','alerts_adjust','alerts_save','alerts_cancel','threshold_begin','threshold_key','threshold_done','threshold_cancel'];
/* The threshold keypad, in its on-screen order, and the most characters a threshold entry holds ('.' included). */
exports.keys=['1','2','3','4','5','6','7','8','9','.','0','backspace'];
exports.entryLength=8;
/* create(reason): reason is an optional {get,set}, as for the Preset editor; the core passes the validation error both
   editors share. Comments stay outside the function: Espruino keeps function text in RAM.
   - open(alerts) starts a draft of those alerts on page 0; close() discards the draft and the entry; editing() and
     entryOpen() say whether a draft and a threshold entry are open without copying them, so the core picks its screen.
   - action(name,payload,config): one name from exports.actions. A refused action throws; a refused Save or Set value
     also sets the reason. Every other accepted action clears the reason; an accepted Save leaves it to the caller's
     close(). Returns null, {leave:true} for Cancel, or {save:proposed}, the validated replacement configuration, for
     the caller to persist.
   - view(): the alert draft, the alert page, the threshold entry ({alert,text} or null) and the reason. */
exports.create=function(reason){
  var draft=null,page=0,entry=null,definitions=configuration.alertDefinitions;
  if(!reason){var text='';reason={get:function(){return text;},set:function(value){text=value;}};}
  function measured(name){return Object.prototype.hasOwnProperty.call(definitions,name)&&definitions[name].limit!==null;}
  function update(payload){
    if(!draft||!Object.prototype.hasOwnProperty.call(draft,payload.alert))throw new Error('Open a valid alert draft before editing');
    var allowed=payload.alert==='lost'?['alert','enabled']:['alert','enabled','threshold'];
    if(Object.keys(payload).some(function(key){return allowed.indexOf(key)<0;})||Object.keys(payload).length<2)throw new Error('Invalid alert draft field');
    if(Object.prototype.hasOwnProperty.call(payload,'enabled'))draft[payload.alert].enabled=payload.enabled;
    if(Object.prototype.hasOwnProperty.call(payload,'threshold'))draft[payload.alert].threshold=payload.threshold;
  }
  function save(config){
    if(!draft)throw new Error('No alert draft is open');
    var proposed=configuration.copy(config);
    try{proposed.alerts=configuration.validateAlerts(draft);proposed.revision++;return {save:configuration.validate(proposed)};}
    catch(error){reason.set(String(error));throw error;}
  }
  function adjust(name,delta){
    if(!draft||!measured(name)||(delta!==1&&delta!==-1))throw new Error('Invalid threshold adjustment');
    var value=draft[name].threshold;
    draft[name].threshold=value===null?0:Math.max(0,Math.min(definitions[name].limit,value+delta));
  }
  function key(value){
    if(!entry)throw new Error('No threshold entry is open');
    if(value==='backspace')entry.text=entry.text.slice(0,-1);
    else if(typeof value==='string'&&/^[0-9.]$/.test(value)){if(entry.text.length<exports.entryLength&&(value!=='.'||entry.text.indexOf('.')<0))entry.text+=value;}
    else throw new Error('Invalid threshold key');
  }
  function done(){
    if(!entry||!draft)throw new Error('No threshold entry is open');
    var number=entry.text===''?null:Number(entry.text);
    if(number!==null&&(!isFinite(number)||number<0||number>definitions[entry.alert].limit)){reason.set('Threshold outside supported range');throw new Error(reason.get());}
    draft[entry.alert].threshold=number;entry=null;
  }
  function run(name,payload,config){
    if(name==='alerts_update')update(payload);
    else if(name==='alerts_save')return save(config);
    else if(name==='alerts_cancel'){close();return {leave:true};}
    else if(name==='alerts_page'){
      if(!draft||typeof payload.page!=='number'||Math.floor(payload.page)!==payload.page||payload.page<0||payload.page>3)throw new Error('Invalid alert page');
      page=payload.page;
    }else if(name==='alerts_adjust')adjust(payload.alert,payload.delta);
    else if(name==='threshold_begin'){
      if(!draft||!measured(payload.alert))throw new Error('Select a measurement alert threshold');
      entry={alert:payload.alert,text:draft[payload.alert].threshold===null?'':String(draft[payload.alert].threshold)};
    }else if(name==='threshold_key')key(payload.key);
    else if(name==='threshold_done')done();
    else if(name==='threshold_cancel')entry=null;
    reason.set('');
    return null;
  }
  function close(){draft=null;entry=null;reason.set('');}
  return {
    open:function(alerts){draft=configuration.copy(alerts);page=0;entry=null;reason.set('');},
    close:close,
    editing:function(){return draft!==null;},
    entryOpen:function(){return entry!==null;},
    action:function(name,payload,config){return run(name,payload||{},config);},
    view:function(){return {draft:configuration.copy(draft),page:page,entry:configuration.copy(entry),reason:reason.get()||''};}
  };
};
