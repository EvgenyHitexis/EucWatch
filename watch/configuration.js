/* Versioned saved values only; no telemetry, commands or wheel confirmation. */
exports.copy=function(value){
  if(Array.isArray(value))return value.map(exports.copy);
  if(value&&typeof value==='object'){var result={};Object.keys(value).forEach(function(key){result[key]=exports.copy(value[key]);});return result;}
  return value;
};
exports.equal=function(left,right){
  if(left===right)return true;
  if(!left||!right||typeof left!=='object'||typeof right!=='object'||Array.isArray(left)!==Array.isArray(right))return false;
  var names=Object.keys(left);return names.length===Object.keys(right).length&&names.every(function(key){return Object.prototype.hasOwnProperty.call(right,key)&&exports.equal(left[key],right[key]);});
};
exports.defaults=function(){return {version:2,revision:0,presets:[['Jump',0,0,0],['Forest',70,0,0],['Road',30,25,10],['Drag',20,70,5]].map(function(row,index){return {id:index+1,name:row[0],configured:true,pedal_sensitivity:row[1],dynamic_assist:row[2],pedal_dip_compensation:row[3],dip_included:false};}),
  alerts:{pwm:{enabled:false,threshold:null},speed:{enabled:false,threshold:null},battery:{enabled:false,threshold:null},lost:{enabled:true}}};};
function keys(value,expected){return value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===expected.length&&expected.every(function(key){return Object.prototype.hasOwnProperty.call(value,key);});}
function readableName(text){
  /* Espruino 2v14 strings retain UTF-8 bytes, not UTF-16 code units. */
  if(typeof text!=='string')return false;
  var i=0,count=0,readable=false,code,first,next,remaining,min;
  while(i<text.length){
    first=text.charCodeAt(i++);code=first;remaining=0;min=0;
    if(first>=194&&first<=223){code=first&31;remaining=1;min=128;}
    else if(first>=224&&first<=239){code=first&15;remaining=2;min=2048;}
    else if(first>=240&&first<=244){code=first&7;remaining=3;min=65536;}
    else if(first>=128)return false;
    while(remaining--){if(i>=text.length)return false;next=text.charCodeAt(i++);if(next<128||next>191)return false;code=code*64+(next&63);}
    if(code<min||code>1114111||(code>=55296&&code<=57343)||code<32)return false;
    count++;if(count>24)return false;
    if(code!==32&&code!==133&&code!==160&&code!==5760&&!(code>=8192&&code<=8202)&&code!==8232&&code!==8233&&code!==8239&&code!==8287&&code!==12288)readable=true;
  }
  return count>0&&readable;
}
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
  if(!keys(config,['version','revision','presets','alerts'])||(config.version!==1&&config.version!==2)||typeof config.revision!=='number'||!isFinite(config.revision)||config.revision<0||Math.floor(config.revision)!==config.revision)throw new Error('Invalid or unsupported configuration');
  exports.validateAlerts(config.alerts);
  if(!Array.isArray(config.presets)||config.presets.length!==4)throw new Error('Exactly four fixed preset slots are required');
  config.presets.forEach(function(preset,index){
    var required=['id','name','configured'],fields=['pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
    if(!preset||preset.id!==index+1||typeof preset.configured!=='boolean'||!readableName(preset.name))throw new Error('Invalid fixed preset slot');
    if(preset.configured){required.push(fields[0],fields[1]);if(Object.prototype.hasOwnProperty.call(preset,fields[2]))required.push(fields[2]);}
    if(config.version===2){if(!preset.configured||typeof preset.dip_included!=='boolean')throw new Error('Explicit dip inclusion required');if(required.indexOf(fields[2])<0)required.push(fields[2]);required.push('dip_included');}
    if(!keys(preset,required))throw new Error('Invalid preset fields');
    fields.forEach(function(field){if(Object.prototype.hasOwnProperty.call(preset,field)&&(typeof preset[field]!=='number'||preset[field]<0||preset[field]>100||Math.floor(preset[field])!==preset[field]))throw new Error('Invalid preset percentage');});
  });
  var normalized=exports.copy(config);
  if(config.version===1){
    var defaults=exports.defaults();
    normalized.presets.forEach(function(preset,index){
      if(!preset.configured)normalized.presets[index]=defaults.presets[index];
      else {preset.dip_included=Object.prototype.hasOwnProperty.call(preset,'pedal_dip_compensation');if(!preset.dip_included)preset.pedal_dip_compensation=defaults.presets[index].pedal_dip_compensation;}
    });
    normalized.version=2;
  }
  return normalized;
};
