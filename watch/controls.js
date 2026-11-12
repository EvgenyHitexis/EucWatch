/* Shared rendered rectangles and touch targets: [left,top,right,bottom]. */
exports.targets=function(state){
  if(!state.awake||state.recovery)return [];
  function target(rect,label,action,payload){payload=payload||{};if(action.indexOf('preset_')===0&&state.preset_editor){payload.editor_id=state.preset_editor.id;if(state.preset_input)payload.entry_id=state.preset_input.id;}return {rect:rect,label:label,action:action,payload:payload};}
  if(state.screen==='settings')return [
    target([12,32,228,76],state.transport&&(state.transport.active||state.transport.connected)?'Disconnect wheel':'Connect wheel','transport_toggle'),
    target([12,82,228,126],'Sleep screen','sleep'),target([12,132,228,176],'Vibration alerts','alerts_begin'),
    target([12,182,228,226],'Presets','preset_slots')];
  if(state.screen==='preset_slots')return state.presets.map(function(slot,index){var y=32+index*50;return target([12,y,228,y+44],slot.id+' '+slot.name,'preset_begin',{slot:slot.id});});
  if(state.screen==='preset_editor'){
    if(!state.preset_draft)return [];
    var page=state.preset_page,field=require('sw-preset-editor').fields[page];
    var rows=state.preset_input?[]:[target([8,4,56,44],'<','preset_page',{page:state.preset_previous_page}),target([184,4,232,44],'>','preset_page',{page:state.preset_next_page})];
    if(state.preset_input){
      var input=state.preset_input,isNameEntry=input.field==='name';
      rows=rows.concat(state.preset_keys.map(function(key,index){var x=12+index%(isNameEntry?4:3)*(isNameEntry?56:74),y=(isNameEntry?44:52)+Math.floor(index/(isNameEntry?4:3))*(isNameEntry?38:35);return target([x,y,x+(isNameEntry?48:68),y+32],key,'preset_input_key',{key:key});}));
      if(isNameEntry)rows=rows.concat([
        target([12,158,52,190],'a/A','preset_input_key',{key:'a/A'}),target([56,158,96,190],'Space','preset_input_key',{key:' '}),
        target([100,158,140,190],'Clear','preset_input_key',{key:'Clear'}),target([144,158,184,190],'<','preset_input_key',{key:'<'}),
        target([188,158,228,190],(input.letters+1)+'/3','preset_input_page',{delta:1})]);
      if(field==='pedal_dip_compensation')rows.push(target([144,4,228,44],state.preset_draft.dip_included?'Included':'Omitted','preset_include_dip',{included:!state.preset_draft.dip_included}));
    }else{
      rows.push(target([12,72,228,field==='pedal_dip_compensation'?132:184],String(state.preset_draft[field]),'preset_input_begin'));
      if(field==='pedal_dip_compensation')rows.push(target([12,140,228,184],state.preset_draft.dip_included?'Dip included':'Dip omitted','preset_include_dip',{included:!state.preset_draft.dip_included}));
    }
    return rows.concat([target([12,196,116,236],'Cancel',state.preset_input?'preset_input_cancel':'preset_cancel'),target([124,196,228,236],state.preset_input?'OK':'Save',state.preset_input?'preset_input_accept':'preset_save')]);
  }
  if(state.screen==='alerts'&&state.alerts_draft){
    var name=['pwm','speed','battery','lost'][state.alert_page],setting=state.alerts_draft[name];
    var rows=[target([8,0,56,44],'<','alerts_page',{page:(state.alert_page+3)%4}),target([184,0,232,44],'>','alerts_page',{page:(state.alert_page+1)%4}),
      target([12,52,228,92],setting.enabled?'Enabled':'Disabled','alerts_update',{alert:name,enabled:!setting.enabled})];
    if(name!=='lost')rows=rows.concat([
      target([12,100,60,140],'-','alerts_adjust',{alert:name,delta:-1}),
      target([68,100,172,140],setting.threshold===null?'Not set':String(setting.threshold)+(name==='speed'?' km/h':' %'),'threshold_begin',{alert:name}),
      target([180,100,228,140],'+','alerts_adjust',{alert:name,delta:1})]);
    return rows.concat([target([12,148,228,188],'Test vibration','alert_test',{alert:name}),
      target([12,196,116,236],'Cancel','alerts_cancel'),target([124,196,228,236],'Save','alerts_save')]);
  }
  if(state.screen==='threshold'){
    var keys=['1','2','3','4','5','6','7','8','9','.','0','backspace'];
    return keys.map(function(key,index){var x=12+(index%3)*74,y=52+Math.floor(index/3)*35;return target([x,y,x+68,y+32],key==='backspace'?'<':key,'threshold_key',{key:key});}).concat([
      target([12,196,116,236],'Cancel','threshold_cancel'),target([124,196,228,236],'Set value','threshold_done')]);
  }
  if(state.screen==='connection')return state.devices.map(function(device,index){return target([8,40+index*38,232,74+index*38],device.name,'device_select',{id:device.id});});
  if(state.screen==='presets')return state.presets.map(function(preset,index){var detail=state.preset_attempt&&!state.preset_attempt.pending&&!state.horn_feedback,x=9+(index%2)*115,y=(detail?43:36)+Math.floor(index/2)*(detail?81:98);
    return {rect:[x,y,x+105,y+(detail?71:90)],label:preset.name,action:'preset_apply',payload:{slot:preset.id},disabled:!state.presets_menu[index].available};});
  return [];
};
exports.hit=function(state,x,y){var targets=exports.targets(state),i,r;for(i=0;i<targets.length;i++){r=targets[i].rect;if(!targets[i].disabled&&x>=r[0]&&x<=r[2]&&y>=r[1]&&y<=r[3])return targets[i];}return null;};
