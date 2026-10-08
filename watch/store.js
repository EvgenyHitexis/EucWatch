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
    },stage:function(value){
      var proposed=configuration.validate(value),text=JSON.stringify(proposed);
      if(text.length>4096)throw new Error('Configuration exceeds supported size');
      write('sw-config-stage.json',text);
      if(!configuration.equal(read('sw-config-stage.json'),proposed))throw new Error('Native JSON precision changed configuration meaning; review required');
    },activate:function(value){
      var proposed=configuration.validate(value),text=JSON.stringify(proposed),previous=null;
      if(text.length>4096||!configuration.equal(read('sw-config-stage.json'),proposed))throw new Error('Staged configuration changed before activation');
      try{previous=read('sw-config.json');}catch(ignored){}
      if(previous)write('sw-config-backup.json',JSON.stringify(previous));
      else{
        /* A recovered backup may be our only valid copy. Keep it intact until
           the replacement active content has been written and verified. */
        try{previous=read('sw-config-backup.json');}catch(ignoredBackup){}
        if(!previous)write('sw-config-backup.json',JSON.stringify(configuration.defaults()));
      }
      write('sw-config.json',text);
      if(!configuration.equal(read('sw-config.json'),proposed))throw new Error('Active configuration verification failed');
      adapter.warning=null;
    },save:function(value){adapter.stage(value);adapter.activate(value);},discard:function(){storage.erase('sw-config-stage.json');}
  };
  return adapter;
};
