interface ScenarioDefinition {
  name: string; version: number; seed: number; clock: string; input: string;
  simulator: Record<string, unknown>; steps: Record<string, unknown>[];
}

export interface ScenarioView {
  definition: ScenarioDefinition | null; preview: ScenarioDefinition | null;
  position: number; total: number; active: boolean; error: string | null;
  persistence_error: string | null; provenance: string; higher_level_injections: string[];
}

export function mountScenarios(
  action: (name: string, payload?: Record<string, unknown>) => Promise<boolean>,
  getView: () => ScenarioView | null | undefined,
  epoch: () => string,
): (enabled: boolean) => void {
  const section = document.createElement('section');
  section.innerHTML = `<div class="divider"></div><h2>Reproducible scenarios</h2>
    <p class="intro">Save the complete simulator inputs. Seed 0 means fixed inputs; there is no random generator. Imported files need review and an explicit Start. Steps drive controlled time and protocol traffic, with no wheel commands.</p>
    <label>Scenario name<input id="scenario-name" maxlength="80" value="Dashboard and freshness"></label>
    <div class="actions"><button id="scenario-save">Save current inputs</button><button id="scenario-export">Export scenario</button></div>
    <label>Scenario file<input id="scenario-file" type="file" accept=".json,application/json"></label>
    <div class="actions"><button id="scenario-review">Review file</button><button id="scenario-start">Start reviewed or saved scenario</button><button id="scenario-step">Next scenario step</button></div>
    <p id="scenario-status" role="status"></p><pre id="scenario-preview" class="metadata"></pre>`;
  document.querySelector('.panel')!.append(section);
  let reading = false, generation = 0, enabled = false, message = '';
  const status = section.querySelector<HTMLElement>('#scenario-status')!;
  const fileInput = section.querySelector<HTMLInputElement>('#scenario-file')!;
  const button = (name: string) => section.querySelector<HTMLButtonElement>(`#scenario-${name}`)!;
  function update(available: boolean): void {
    enabled = available;
    const view = getView(), content = view?.preview ?? view?.definition;
    section.querySelectorAll<HTMLButtonElement>('button').forEach(control => control.disabled = !enabled || reading);
    fileInput.disabled = !enabled || reading;
    section.querySelector<HTMLInputElement>('#scenario-name')!.disabled = !enabled || reading;
    button('start').disabled ||= !content;
    button('export').disabled ||= !content;
    button('step').disabled ||= !view?.active;
    status.textContent = [message, view?.error, view?.persistence_error,
      view ? `${view.position}/${view.total} steps · ${view.provenance}` : 'Scenarios unavailable',
      view?.higher_level_injections.length ? `Higher-level control injections: ${view.higher_level_injections.join(', ')}` : '',
    ].filter(Boolean).join(' · ');
    section.querySelector<HTMLElement>('#scenario-preview')!.textContent = content ? `${view?.preview ? 'Reviewed import; not saved or started' : 'Saved definition; no automatic start'}\n${JSON.stringify(content, null, 2)}` : '';
  }
  fileInput.addEventListener('change', () => { generation++; message = ''; });
  button('save').addEventListener('click', async () => {
    generation++;
    const name = section.querySelector<HTMLInputElement>('#scenario-name')!.value;
    if (await action('scenario_save', {name})) message = getView()?.persistence_error ?? 'Complete simulator inputs saved locally.';
    update(enabled);
  });
  button('review').addEventListener('click', async () => {
    if (reading) return;
    const file = fileInput.files?.[0];
    if (!file) { message = 'Choose a scenario JSON file.'; update(enabled); return; }
    if (file.size > 32768) { message = 'Scenario exceeds 32 KiB; saved content preserved.'; update(enabled); return; }
    const started = epoch(), ticket = ++generation;
    reading = true; update(enabled);
    try {
      const content = await file.text();
      if (started !== epoch() || ticket !== generation) { message = 'Session changed while reading; review again.'; return; }
      message = await action('scenario_review', {content}) ? 'Review complete inputs and steps, then Start explicitly.' : 'Scenario validation failed; saved content preserved.';
    } catch (error) {
      message = error instanceof Error ? error.message : 'Scenario file could not be read.';
    } finally { reading = false; update(enabled); }
  });
  button('start').addEventListener('click', async () => {
    generation++;
    message = await action('scenario_start') ? 'Scenario started in a fresh controlled simulator session.' : 'Scenario start refused.';
    update(enabled);
  });
  button('step').addEventListener('click', async () => {
    message = await action('scenario_step') ? 'Scenario step completed through the behavior backend.' : 'Scenario step refused; start explicitly again.';
    update(enabled);
  });
  button('export').addEventListener('click', async () => {
    if (!await action('scenario_export')) return;
    const content = getView()?.preview ?? getView()?.definition;
    if (!content) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(content) + '\n'], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'eucwatch-scenario.json'; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    message = 'Validated scenario exported.'; update(enabled);
  });
  return update;
}
