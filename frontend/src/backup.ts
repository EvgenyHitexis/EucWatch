interface Preview { content: unknown; base_revision: number; migration: { from:number; to:number; changes:string[] } }
interface BackupView { configuration_preview: Preview | null; configuration_export: unknown; config:{revision:number}; persistence_error:string|null }

export function mountBackup(action:(name:string,payload?:Record<string,unknown>)=>Promise<boolean>,getView:()=>BackupView|null,epoch:()=>string): (enabled:boolean)=>void {
  const section=document.createElement('section');
  section.innerHTML=`<div class="divider"></div><h2>Configuration backup</h2>
    <p class="intro">Back up the four saved preset definitions and alert settings. Restore only after reviewing the complete content. Wheel readings and confirmation are excluded.</p>
    <button id="configuration-export" data-control>Export saved configuration</button>
    <label>Configuration file<input id="configuration-file" type="file" accept=".json,application/json"></label>
    <div class="actions"><button id="configuration-review" data-control>Review import</button><button id="configuration-restore" data-control>Restore reviewed configuration</button><button id="configuration-cancel" data-control>Cancel import</button></div>
    <p id="configuration-status" role="status"></p><pre id="configuration-preview" class="metadata"></pre>`;
  document.querySelector('.panel')!.append(section);
  const status=section.querySelector<HTMLElement>('#configuration-status')!;
  let reading=false;
  section.querySelector('#configuration-export')!.addEventListener('click',async()=>{
    if(!await action('configuration_export')) return;
    const content=getView()?.configuration_export;
    if(!content) return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)+'\n'],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='eucwatch-configuration.json';link.click();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    status.textContent='Exported validated saved configuration.';
  });
  section.querySelector('#configuration-review')!.addEventListener('click',async()=>{
    const file=section.querySelector<HTMLInputElement>('#configuration-file')!.files?.[0];
    if(!file){status.textContent='Choose a configuration file.';return;}
    if(file.size>32768){status.textContent='Configuration exceeds 32 KiB; active content preserved.';return;}
    const started=epoch();reading=true;
    try {
      const content=await file.text();
      if(started!==epoch()){status.textContent='Session or saved content changed while reading; review again.';return;}
      const accepted=await action('configuration_import_prepare',{content});
      status.textContent=accepted ? 'Review the complete candidate, then Restore or Cancel.' : 'Import refused; active content preserved. See the validation message.';
    } catch(error){status.textContent=error instanceof Error ? error.message : 'Configuration file could not be read.';}
    finally {reading=false;}
  });
  section.querySelector('#configuration-restore')!.addEventListener('click',async()=>{
    if(await action('configuration_import_commit')) status.textContent=getView()?.persistence_error ?? 'Configuration restored locally; no wheel command sent.';
    else status.textContent='Restoration refused; review again. Active content preserved.';
  });
  section.querySelector('#configuration-cancel')!.addEventListener('click',async()=>{
    if(await action('configuration_import_cancel'))status.textContent='Import cancelled; saved content unchanged.';
  });
  return enabled=>{
    section.querySelectorAll<HTMLButtonElement>('button').forEach(button=>button.disabled=!enabled || reading);
    const preview=getView()?.configuration_preview;
    section.querySelector<HTMLButtonElement>('#configuration-restore')!.disabled ||= !preview;
    section.querySelector<HTMLButtonElement>('#configuration-cancel')!.disabled ||= !preview;
    section.querySelector<HTMLElement>('#configuration-preview')!.textContent=preview ? `Saved revision at review: ${preview.base_revision}\nSchema ${preview.migration.from} → ${preview.migration.to}; preserves meaning\n${JSON.stringify(preview.content,null,2)}` : '';
  };
}
