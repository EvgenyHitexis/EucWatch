/* Staged, read-verified Storage copy and a validated previous good copy. */
var configuration=require('sw-configuration');
exports.create=function(options){
  options=options||{};
  var storage=options.storage||require('Storage'),adapter;
  function read(name){
    var text=storage.read(name);
    if(text===undefined)return null;
    if(typeof text!=='string'||text.length>4096)throw new Error('Saved configuration exceeds supported size');
    return configuration.validate(JSON.parse(text));
  }
  function write(name,text){if(storage.write(name,text)===false||storage.read(name)!==text)throw new Error('Configuration write/readback failed');}
  adapter={warning:null,load:function(){
      adapter.warning=null;
      try{var active=read('sw-config.json');if(active)return active;var backup=read('sw-config-backup.json');if(backup)adapter.warning='Recovered previous good configuration: active copy missing';return backup;}
      catch(error){var backup=read('sw-config-backup.json');if(!backup)throw error;adapter.warning='Recovered previous good configuration: '+String(error);return backup;}
    },save:function(value){
      var proposed=configuration.validate(value),text=JSON.stringify(proposed),previous=null;
      if(text.length>4096)throw new Error('Configuration exceeds supported size');
      write('sw-config-stage.json',text);
      if(JSON.stringify(read('sw-config-stage.json'))!==text)throw new Error('Staged configuration verification failed');
      try{previous=adapter.load();}catch(ignored){}
      if(!previous)previous=configuration.defaults();
      write('sw-config-backup.json',JSON.stringify(previous));
      write('sw-config.json',text);
      if(JSON.stringify(read('sw-config.json'))!==text)throw new Error('Active configuration verification failed');
      adapter.warning=null;
    }
  };
  return adapter;
};
