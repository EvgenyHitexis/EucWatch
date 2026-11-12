/* Preset editor: Preset draft, Preset value entry, field page and their rules. Local only; saving never invokes a wheel writer. */
var configuration=require('sw-configuration');
exports.fields=['name','pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
exports.labels=['Name','Pedal sensitivity','Dynamic assist','Pedal dip compensation'];
/* The actions that act on the open Preset value entry, so they need its entry id. */
var entryActions=['preset_input_key','preset_input_page','preset_input_accept','preset_input_cancel'];
/* Every editor-scoped action. */
exports.actions=['preset_update','preset_cancel','preset_save','preset_include_dip','preset_page','preset_input_begin'].concat(entryActions);
exports.validateValue=function(field,value){
  if(field==='name')configuration.validatePresetName(value);
  else{
    if(typeof value==='string'&&/^[0-9]{1,3}$/.test(value))value=Number(value);
    if(typeof value!=='number'||Math.floor(value)!==value||value<0||value>100)throw new Error(exports.labels[exports.fields.indexOf(field)]+': enter a whole percentage 0-100');
  }
  return value;
};
/* The keypad key set of a Preset value entry. */
function keys(input){if(input.field!=='name')return ['1','2','3','4','5','6','7','8','9','Clear','0','<'];var text='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.slice(input.letters*12,input.letters*12+12);return (input.lowercase?text.toLowerCase():text).split('');}
exports.slot=function(slot){if(typeof slot!=='number'||Math.floor(slot)!==slot||slot<1||slot>4)throw new Error('Choose one of the four fixed preset slots');return slot;};
exports.replacement=function(config,draft){var proposed=configuration.copy(config);proposed.presets[exports.slot(draft.id)-1]=configuration.copy(draft);proposed.revision++;return configuration.validate(proposed);};
/* create(reason): reason is an optional {get,set} holding the editor's reason ('' when clear). The core passes the
   validation error it shares with the alert editor, so the last reason set by either editor shows in both; without one
   the editor keeps its own. Comments stay outside the function: Espruino keeps function text in RAM.
   - action(name,payload,editable,config): one name from exports.actions (the caller routes only those here), checked
     against the editor id, then the entry id, then editable; it clears the reason first. Returns null, {leave:true},
     {invalid:true} when Save is refused (reason set) or {save:proposed} for the caller to persist.
   - swipe(payload): left/right turn the field page unless an entry is open; up closes the entry, otherwise returns
     {leave:true}.
   - view(): the complete editor view: request (with its reason), Preset draft, field page, Preset value entry, the
     entry's keypad key set ([] without an entry) and the field pages the previous and next page controls turn to. */
exports.create=function(reason){
  var request=null,draft=null,page=0,input=null,nextId=1,nextEntryId=1;
  if(!reason){var text='';reason={get:function(){return text;},set:function(value){text=value;}};}
  function current(payload,entry){
    if(!request||typeof payload.editor_id!=='number'||payload.editor_id!==request.id)throw new Error('Preset editor changed; open a fresh editor operation');
    if(entry||payload.entry_id!=null){if(!input||typeof payload.entry_id!=='number'||payload.entry_id!==input.id)throw new Error('Preset value entry changed; open a fresh entry');}
  }
  function update(changes){
    if(!draft||!Object.keys(changes).length||Object.keys(changes).some(function(name){return exports.fields.concat(['dip_included']).indexOf(name)<0;}))throw new Error('Invalid preset draft field');
    Object.keys(changes).forEach(function(name){draft[name]=changes[name];});
  }
  function turn(delta){return (page+delta+4)%4;}
  function setPage(value){
    if(typeof value!=='number'||Math.floor(value)!==value||value<0||value>3)throw new Error('Invalid preset page');
    if(!input)page=value;
  }
  function key(value){
    if(!input)throw new Error('No preset input is open');
    if(value==='Clear')input.text='';
    else if(value==='<')input.text=input.text.slice(0,-1);
    else if(value==='a/A'&&input.field==='name')input.lowercase=!input.lowercase;
    else if(typeof value==='string'&&(keys(input).indexOf(value)>=0||(value===' '&&input.field==='name'))){if(input.text.length<(input.field==='name'?24:3))input.text+=value;}
    else throw new Error('Invalid preset input key');
  }
  function save(config){
    try{
      if(input)throw new Error('Finish the current preset value entry first');
      var selected=configuration.copy(draft);
      exports.fields.forEach(function(field){selected[field]=exports.validateValue(field,selected[field]);});
      return {save:exports.replacement(config,selected)};
    }catch(error){reason.set(String(error));return {invalid:true};}
  }
  function accept(){
    try{var accepted={};accepted[input.field]=exports.validateValue(input.field,input.text);update(accepted);input=null;}
    catch(error){reason.set(String(error));}
  }
  function run(name,payload,config){
    reason.set('');
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
    else if(name==='preset_input_cancel')input=null;
    return null;
  }
  return {
    open:function(config,slot){slot=exports.slot(slot);draft=configuration.copy(config.presets[slot-1]);request={id:nextId++,slot:slot,status:'ready'};page=0;input=null;reason.set('');},
    close:function(){request=null;draft=null;page=0;input=null;reason.set('');},
    action:function(name,payload,editable,config){
      current(payload,entryActions.indexOf(name)>=0);
      if(!editable)throw new Error('Preset editing unavailable');
      return run(name,payload,config);
    },
    swipe:function(payload){
      current(payload,!!input);
      if(payload.direction==='up')return input?run('preset_input_cancel'):{leave:true};
      if((payload.direction==='left'||payload.direction==='right')&&!input)run('preset_page',{page:turn(payload.direction==='left'?1:-1)});
      return null;
    },
    view:function(){
      var shown=configuration.copy(request);if(shown)shown.reason=reason.get()||'';
      return {request:shown,draft:configuration.copy(draft),page:page,input:configuration.copy(input),keys:input?keys(input):[],previous_page:turn(-1),next_page:turn(1)};
    }
  };
};
