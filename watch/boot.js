/* Independent .bootrst recovery. Intact startup/runtime remain prerequisites. */
(function(){
  var storage=require('Storage');
  D15.write(1);
  E.enableWatchdog(30,false);E.kickWatchdog();
  var kick=setInterval(function(){if(!BTN1.read())E.kickWatchdog();},3000);
  function recovery(reason){
    storage.write('sw-recovery',reason);
    NRF.setServices({},{uart:true});NRF.setAdvertising({},{name:'Sherman-recovery'});
    global.ShermanRecovery={reason:reason,exit:function(){storage.erase('sw-recovery');storage.erase('sw-starting');reset();}};
    print('Sherman recovery: '+reason+'; use BLE console. Intact recovery startup required.');
  }
  if(BTN1.read()||storage.read('sw-recovery')||storage.read('sw-starting')){recovery('Requested or incomplete startup');return;}
  if(process.env.VERSION!=='2v14'){recovery('Expected installed Espruino 2v14');return;}
  var active=storage.readJSON('sw-active.json',true);
  if(!active||typeof active.main!=='string'){recovery('No verified active application');return;}
  storage.write('sw-starting','1');
  try{global.ShermanWatch=require(active.main).start();storage.erase('sw-starting');}
  catch(exception){recovery('Application startup failed: '+String(exception));}
})();
