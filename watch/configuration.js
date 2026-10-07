/* Versioned saved values only; no telemetry, commands or wheel confirmation. */
exports.copy=function(value){return JSON.parse(JSON.stringify(value));};
exports.defaults=function(){return {version:1,revision:0,presets:[1,2,3,4].map(function(id){return {id:id,name:'Preset '+id,configured:false};}),
  alerts:{pwm:{enabled:false,threshold:null},speed:{enabled:false,threshold:null},battery:{enabled:false,threshold:null},lost:{enabled:true}}};};
function keys(value,expected){return value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===expected.length&&expected.every(function(key){return Object.prototype.hasOwnProperty.call(value,key);});}
exports.validateAlerts=function(alerts){
  if(!keys(alerts,['pwm','speed','battery','lost']))throw new Error('All four alert settings are required');
  Object.keys(alerts).forEach(function(name){
    var setting=alerts[name],threshold;
    if(!keys(setting,name==='lost'?['enabled']:['enabled','threshold'])||typeof setting.enabled!=='boolean')throw new Error('Invalid '+name+' alert setting');
    if(name==='lost')return;
    threshold=setting.threshold;
    if(threshold===null){if(setting.enabled)throw new Error('A threshold is required to enable '+name);}
    else if(typeof threshold!=='number'||!isFinite(threshold)||threshold<0||threshold>(name==='speed'?3276.7:100))throw new Error('Invalid '+name+' threshold');
  });
  return exports.copy(alerts);
};
exports.validate=function(config){
  if(!keys(config,['version','revision','presets','alerts'])||config.version!==1||typeof config.revision!=='number'||!isFinite(config.revision)||config.revision<0||Math.floor(config.revision)!==config.revision)throw new Error('Invalid or unsupported configuration');
  exports.validateAlerts(config.alerts);
  if(!Array.isArray(config.presets)||config.presets.length!==4)throw new Error('Exactly four fixed preset slots are required');
  config.presets.forEach(function(preset,index){
    var required=['id','name','configured'],fields=['pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
    if(!preset||preset.id!==index+1||typeof preset.configured!=='boolean'||typeof preset.name!=='string'||!preset.name.trim()||preset.name.length>24||/[\x00-\x1f]/.test(preset.name))throw new Error('Invalid fixed preset slot');
    if(preset.configured){required.push(fields[0],fields[1]);if(Object.prototype.hasOwnProperty.call(preset,fields[2]))required.push(fields[2]);}
    if(!keys(preset,required))throw new Error('Invalid preset fields');
    fields.forEach(function(field){if(Object.prototype.hasOwnProperty.call(preset,field)&&(typeof preset[field]!=='number'||preset[field]<0||preset[field]>100||Math.floor(preset[field])!==preset[field]))throw new Error('Invalid preset percentage');});
  });
  return exports.copy(config);
};
