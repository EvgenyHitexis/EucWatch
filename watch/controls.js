/* Shared rendered rectangles and touch targets: [left,top,right,bottom]. */
exports.targets=function(state){
  if(!state.awake||state.recovery)return [];
  function target(rect,label,action,payload){return {rect:rect,label:label,action:action,payload:payload||{}};}
  if(state.screen==='settings')return [
    target([12,26,228,52],state.transport&&(state.transport.active||state.transport.connected)?'Disconnect wheel':'Connect wheel','transport_toggle'),
    target([12,60,228,110],'Sleep screen','sleep'),target([12,120,228,170],'Vibration alerts','alerts_begin')];
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
  return [];
};
exports.hit=function(state,x,y){var targets=exports.targets(state),i,r;for(i=0;i<targets.length;i++){r=targets[i].rect;if(x>=r[0]&&x<=r[2]&&y>=r[1]&&y<=r[3])return targets[i];}return null;};
