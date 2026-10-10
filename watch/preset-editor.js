/* Local transient draft; saving never invokes a wheel writer. */
var configuration=require('sw-configuration');
exports.fields=['name','pedal_sensitivity','dynamic_assist','pedal_dip_compensation'];
exports.labels=['Name','Pedal sensitivity','Dynamic assist','Pedal dip compensation'];
exports.attemptName=function(attempt){return attempt.kind==='editor'?exports.labels[exports.fields.indexOf(Object.keys(attempt.fields)[0])]:attempt.name;};
exports.keys=function(input){if(input.field!=='name')return ['1','2','3','4','5','6','7','8','9','Clear','0','<'];var text='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.slice(input.letters*12,input.letters*12+12);return (input.lowercase?text.toLowerCase():text).split('');};
exports.slot=function(slot){if(typeof slot!=='number'||Math.floor(slot)!==slot||slot<1||slot>4)throw new Error('Choose one of the four fixed preset slots');return slot;};
exports.replacement=function(config,draft){var proposed=configuration.copy(config);proposed.presets[exports.slot(draft.id)-1]=configuration.copy(draft);proposed.revision++;return configuration.validate(proposed);};
exports.create=function(){
  var request=null,draft=null,nextId=1;
  return {
    open:function(config,slot){slot=exports.slot(slot);draft=configuration.copy(config.presets[slot-1]);request={id:nextId++,slot:slot,status:'ready',reason:''};},
    close:function(){request=null;draft=null;},
    require:function(id){if(!request||typeof id!=='number'||id!==request.id)throw new Error('Preset editor changed; open a fresh editor operation');},
    update:function(changes){
      if(!draft||!Object.keys(changes).length||Object.keys(changes).some(function(name){return exports.fields.concat(['dip_included']).indexOf(name)<0;}))throw new Error('Invalid preset draft field');
      Object.keys(changes).forEach(function(name){draft[name]=changes[name];});
    },
    validate:function(config){
      var selected=configuration.copy(draft);
      exports.fields.slice(1).forEach(function(field,index){
        var value=selected[field];if(typeof value==='string'&&/^[0-9]{1,3}$/.test(value))value=Number(value);
        if(typeof value!=='number'||Math.floor(value)!==value||value<0||value>100)throw new Error(exports.labels[index+1]+': enter a whole percentage 0-100');
        selected[field]=value;
      });
      return exports.replacement(config,selected);
    },
    view:function(){return {request:configuration.copy(request),draft:configuration.copy(draft)};}
  };
};
