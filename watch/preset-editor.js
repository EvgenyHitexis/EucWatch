/* Preset editor: Preset draft, Preset value entry, field page and their rules. Local only; saving never invokes a wheel writer. */
var configuration=require('sw-configuration');
exports.fields=['name','pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
exports.labels=['Name','Pedal sensitivity','Dynamic assist','Pedal dip compensation'];
/* Every editor-scoped action; the last four act on the open Preset value entry. */
exports.actions=['preset_update','preset_cancel','preset_save','preset_include_dip','preset_page','preset_input_begin','preset_input_key','preset_input_page','preset_input_accept','preset_input_cancel'];
exports.validateValue=function(field,value){
  if(field==='name')configuration.validatePresetName(value);
  else{
    if(typeof value==='string'&&/^[0-9]{1,3}$/.test(value))value=Number(value);
    if(typeof value!=='number'||Math.floor(value)!==value||value<0||value>100)throw new Error(exports.labels[exports.fields.indexOf(field)]+': enter a whole percentage 0-100');
  }
  return value;
};
/* The keypad key set of a Preset value entry. */
exports.keys=function(input){if(input.field!=='name')return ['1','2','3','4','5','6','7','8','9','Clear','0','<'];var text='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.slice(input.letters*12,input.letters*12+12);return (input.lowercase?text.toLowerCase():text).split('');};
exports.slot=function(slot){if(typeof slot!=='number'||Math.floor(slot)!==slot||slot<1||slot>4)throw new Error('Choose one of the four fixed preset slots');return slot;};
exports.replacement=function(config,draft){var proposed=configuration.copy(config);proposed.presets[exports.slot(draft.id)-1]=configuration.copy(draft);proposed.revision++;return configuration.validate(proposed);};
exports.create=function(){
  var request=null,draft=null,page=0,input=null,nextId=1,nextEntryId=1;
  function current(payload,entry){
    if(!request||typeof payload.editor_id!=='number'||payload.editor_id!==request.id)throw new Error('Preset editor changed; open a fresh editor operation');
    if(entry||payload.entry_id!=null){if(!input||typeof payload.entry_id!=='number'||payload.entry_id!==input.id)throw new Error('Preset value entry changed; open a fresh entry');}
  }
  function update(changes){
    if(!draft||!Object.keys(changes).length||Object.keys(changes).some(function(name){return exports.fields.concat(['dip_included']).indexOf(name)<0;}))throw new Error('Invalid preset draft field');
    Object.keys(changes).forEach(function(name){draft[name]=changes[name];});
  }
  function setPage(value){
    if(typeof value!=='number'||Math.floor(value)!==value||value<0||value>3)throw new Error('Invalid preset page');
    if(!input)page=value;
  }
  function key(value){
    if(!input)throw new Error('No preset input is open');
    if(value==='Clear')input.text='';
    else if(value==='<')input.text=input.text.slice(0,-1);
    else if(value==='a/A'&&input.field==='name')input.lowercase=!input.lowercase;
    else if(typeof value==='string'&&(exports.keys(input).indexOf(value)>=0||(value===' '&&input.field==='name'))){if(input.text.length<(input.field==='name'?24:3))input.text+=value;}
    else throw new Error('Invalid preset input key');
  }
  function save(config){
    try{
      if(input)throw new Error('Finish the current preset value entry first');
      var selected=configuration.copy(draft);
      exports.fields.forEach(function(field){selected[field]=exports.validateValue(field,selected[field]);});
      return {save:exports.replacement(config,selected)};
    }catch(error){request.reason=String(error);return {invalid:true};}
  }
  function accept(){
    try{var accepted={};accepted[input.field]=exports.validateValue(input.field,input.text);update(accepted);input=null;}
    catch(error){request.reason=String(error);}
  }
  return {
    open:function(config,slot){slot=exports.slot(slot);draft=configuration.copy(config.presets[slot-1]);request={id:nextId++,slot:slot,status:'ready',reason:''};page=0;input=null;},
    close:function(){request=null;draft=null;page=0;input=null;},
    /* One editor-scoped action, checked against the current editor and entry ids, then against editable.
       Returns null, {leave:true}, {invalid:true} when Save is refused (reason set) or {save:proposed} for the caller to persist. */
    action:function(name,payload,editable,config){
      var index=exports.actions.indexOf(name);
      if(index<0)throw new Error('Unknown action: '+name);
      current(payload,index>=6);
      if(!editable)throw new Error('Preset editing unavailable');
      request.reason='';
      if(name==='preset_update'){
        if(input)throw new Error('Finish the current preset value entry first');
        var changes=configuration.copy(payload);delete changes.source;delete changes.editor_id;delete changes.entry_id;update(changes);
      }else if(name==='preset_cancel')return {leave:true};
      else if(name==='preset_save')return save(config);
      else if(name==='preset_include_dip'){
        if(typeof payload.included!=='boolean')throw new Error('Choose explicit dip inclusion');
        update({dip_included:payload.included});
      }else if(name==='preset_page')setPage(payload.page);
      else if(name==='preset_input_begin'){
        if(!input){var field=exports.fields[page];input={id:nextEntryId++,field:field,text:String(draft[field]),letters:0,lowercase:false};}
      }else if(name==='preset_input_key')key(payload.key);
      else if(name==='preset_input_page'){
        if(input.field!=='name'||(payload.delta!==1&&payload.delta!==-1))throw new Error('Invalid name keypad page');
        input.letters=(input.letters+payload.delta+3)%3;
      }else if(name==='preset_input_accept')accept();
      else input=null;
      return null;
    },
    /* An in-editor swipe: left/right turn the field page, up closes the open entry, otherwise the editor. Returns {leave:true} to leave. */
    swipe:function(payload){
      current(payload,!!input);
      if(payload.direction==='left'||payload.direction==='right'){
        if(!input){request.reason='';setPage((page+(payload.direction==='left'?1:3))%4);}
      }else if(payload.direction==='up'){
        if(!input)return {leave:true};
        input=null;request.reason='';
      }
      return null;
    },
    view:function(){return {request:configuration.copy(request),draft:configuration.copy(draft),page:page,input:configuration.copy(input)};}
  };
};
