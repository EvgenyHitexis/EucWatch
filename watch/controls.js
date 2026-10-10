/* Shared rendered rectangles and touch targets: [left,top,right,bottom]. */
exports.targets=function(state){
  if(!state.awake||state.recovery)return [];
  function target(rect,label,action,payload){payload=payload||{};if(action.indexOf('preset_')===0&&state.preset_editor){payload.editor_id=state.preset_editor.id;if(state.preset_input)payload.entry_id=state.preset_input.id;}return {rect:rect,label:label,action:action,payload:payload};}
  if(state.screen==='settings')return [
    target([12,26,228,52],state.transport&&(state.transport.active||state.transport.connected)?'Disconnect wheel':'Connect wheel','transport_toggle'),
    target([12,60,228,110],'Sleep screen','sleep'),target([12,120,228,170],'Vibration alerts','alerts_begin'),
    target([12,180,228,212],'Presets','preset_slots')];
  if(state.screen==='preset_slots')return state.presets.map(function(slot,index){var y=36+index*44;return target([12,y,228,y+38],slot.id+' '+slot.name,'preset_begin',{slot:slot.id});});
  if(state.screen==='preset_editor'){
    if(!state.preset_draft)return [];
    var page=state.preset_page,field=require('sw-preset-editor').fields[page];
    var rows=state.preset_input?[]:[target([12,2,62,28],'<','preset_page',{page:(page+3)%4}),target([178,2,228,28],'>','preset_page',{page:(page+1)%4})];
    if(state.preset_input){
      var input=state.preset_input;
      rows=rows.concat(require('sw-preset-editor').keys(input).map(function(key,index){var x=16+index%3*70,y=59+Math.floor(index/3)*31;return target([x,y,x+66,y+28],key,'preset_input_key',{key:key});}));
      if(input.field==='name')rows=rows.concat([
        target([12,185,54,209],'a/A','preset_input_key',{key:'a/A'}),target([57,185,102,209],'Space','preset_input_key',{key:' '}),
        target([105,185,150,209],'Clear','preset_input_key',{key:'Clear'}),target([153,185,183,209],'<','preset_input_key',{key:'<'}),
        target([186,185,228,209],(input.letters+1)+'/3','preset_input_page',{delta:1})]);
      if(input.field==='pedal_dip_compensation')rows.push(target([12,185,228,209],state.preset_draft.dip_included?'Dip included':'Dip omitted','preset_include_dip',{included:!state.preset_draft.dip_included}));
    }else{
      rows.push(target([12,65,228,103],String(state.preset_draft[field]),'preset_input_begin'));
      if(field==='pedal_dip_compensation')rows.push(target([12,111,228,141],state.preset_draft.dip_included?'Dip included':'Dip omitted','preset_include_dip',{included:!state.preset_draft.dip_included}));
    }
    return rows.concat([target([12,214,116,238],'Cancel',state.preset_input?'preset_input_cancel':'preset_cancel'),target([124,214,228,238],state.preset_input?'OK':'Save',state.preset_input?'preset_input_accept':'preset_save')]);
  }
  if(state.screen==='alerts'&&state.alerts_draft){
    var name=['pwm','speed','battery','lost'][state.alert_page],setting=state.alerts_draft[name];
    var rows=[target([168,31,228,65],setting.enabled?'ON':'OFF','alerts_update',{alert:name,enabled:!setting.enabled})];
    if(name!=='lost')rows=rows.concat([
      target([12,77,50,113],'-','alerts_adjust',{alert:name,delta:-1}),
      target([59,77,180,113],setting.threshold===null?'Set value':String(setting.threshold),'threshold_begin',{alert:name}),
      target([190,77,228,113],'+','alerts_adjust',{alert:name,delta:1})]);
    return rows.concat([target([12,124,228,150],'Test vibration','alert_test',{alert:name}),
      target([12,170,110,195],'< Previous','alerts_page',{page:(state.alert_page+3)%4}),target([130,170,228,195],'Next >','alerts_page',{page:(state.alert_page+1)%4}),
      target([12,204,110,236],'Cancel','alerts_cancel'),target([130,204,228,236],'Save','alerts_save')]);
  }
  if(state.screen==='threshold'){
    var keys=['1','2','3','4','5','6','7','8','9','.','0','backspace'];
    return keys.map(function(key,index){var x=12+(index%3)*75,y=40+Math.floor(index/3)*40;return target([x,y,x+66,y+35],key==='backspace'?'<':key,'threshold_key',{key:key});}).concat([
      target([12,204,110,236],'Cancel','threshold_cancel'),target([130,204,228,236],'Done','threshold_done')]);
  }
  if(state.screen==='connection')return state.devices.map(function(device,index){return target([8,40+index*38,232,74+index*38],device.name,'device_select',{id:device.id});});
  if(state.screen==='presets')return state.presets.map(function(preset,index){var x=9+(index%2)*115,y=43+Math.floor(index/2)*81;
    return {rect:[x,y,x+105,y+71],label:preset.name,action:'preset_apply',payload:{slot:preset.id},disabled:!state.presets_menu[index].available};});
  return [];
};
exports.hit=function(state,x,y){var targets=exports.targets(state),i,r;for(i=0;i<targets.length;i++){r=targets[i].rect;if(!targets[i].disabled&&x>=r[0]&&x<=r[2]&&y>=r[1]&&y<=r[3])return targets[i];}return null;};
