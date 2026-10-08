/* Offline bridge: the original watch endpoint and Storage adapter, no BLE. */
const readline=require('node:readline');
const {environment}=require('./transfer.cjs');
let env=environment(),store=env.store(),endpoint=env.endpoint(store);
readline.createInterface({input:process.stdin}).on('line',line=>{
  try {
    const row=JSON.parse(line);
    if(row.restart){
      const retained={...env.saved};env=environment();Object.assign(env.saved,retained);
      store=env.store();endpoint=env.endpoint(store);
    }
    if(row.fail!==undefined)env.fail(row.fail,row.partial===true);
    if(row.configuration)store.save(row.configuration);
    const response=row.message ? endpoint.exchange(Buffer.from(row.message,'base64').toString('latin1')) : '';
    process.stdout.write(JSON.stringify({response:Buffer.from(response,'latin1').toString('base64'),saved:store.load()})+'\n');
  }catch(error){process.stdout.write(JSON.stringify({error:String(error)})+'\n');}
});
