// The form stores only pending choices; Engine validates the complete preset on Apply.
// Stable move IDs travel over IPC while readable names remain presentation data.
export {};
type Stance = 'low' | 'mid' | 'high';
type MoveRole = 'chord' | 'graph' | 'heavy_string' | 'native' | 'speed';
type Move = { id: string; name: string } & Record<MoveRole, boolean>;
type Calibration = { device: Record<string, unknown>; controller_slot?: number | null; [key: string]: unknown };
type Binding = { source: string; stance: string; move: string };
type Preset = {
  schema_version: number; name: string; weapon: string; tap_move: string | null; hold_move: string | null;
  modifier_mask: number; trigger_mask: number; hold_seconds: number; chord_stance: Stance | 'any';
  low_heavy: string | null; stance_holds: Record<Stance, string | null>; frost_moon: Record<Stance, string | null>;
  skill_bindings: Binding[]; move_settings: Record<string, { speed: number }>;
  okatsu_grapple: boolean; mid_light_ender: boolean; string_enabled: boolean;
};
type Snapshot = {
  runtime: string; preset: Preset; calibration: Calibration; buttons: Record<string, number>; nioh_exe: string;
  running: boolean; status: string; detail: string;
  binding_groups: { id: string; label: string }[]; load_warning?: string;
  capabilities: { moves: Move[]; native_sources: { id: string; label: string; stances?: string[] }[]; stances: Stance[]; chord_stances?: (Stance | 'any')[]; speed: { min: number; max: number } };
};
type ResearchMove = { id: string; name: string; weapon_id: string; boss_id: string; review_status: string; mapping_status?: string;
  priority: string | null; review_notes: string[]; steps: { source: { action_id: string; motion_id: number } }[];
  evidence: { annotation_text: string }[] };
type Collection = { manifest: { weapons: Record<string, { name: string }>; bosses: Record<string, { name: string }> };
  moves: ResearchMove[]; intake: { sessions: { status: string }[] };
  design: { routes: { id: string; dataset_id: string; status: string; blockers: string[] }[] } };
declare global { interface Window { mwm: { request<T>(method: string, params?: unknown): Promise<T> } } }

let state: Snapshot;
let collection: Collection;
let tab = 'overview', dirty = false, busy = false, capture: 'modifier_mask' | 'trigger_mask' | null = null;
let controllerChoice = 'saved';
let bindingGroup = 'chord';
let timer: ReturnType<typeof setTimeout> | undefined;
let captureGeneration = 0, draftGeneration = 0;
let draftTimer: ReturnType<typeof setTimeout> | undefined;
let noticeTimer: ReturnType<typeof setTimeout> | undefined;
type Preview = { preset: Preset; used: string[]; moves: Record<string, { speed: number; percent: number; fill_frames: number; hold_frames: number }> };
let preview: Preview | null = null, showUnused = false;
const content = document.querySelector<HTMLElement>('#content')!;
const notice = document.querySelector<HTMLElement>('#notice')!;

function message(text: string, error = false) {
  // Show one current operation result without hiding it behind modal dialogs.
  // textContent prevents descriptions or Engine errors from becoming executable markup.
  // Error color adds emphasis while the full text remains available to assistive technology.
  clearTimeout(noticeTimer);
  if (text && !error) noticeTimer = setTimeout(() => { notice.textContent = ''; }, 5000);
  notice.textContent = text; notice.classList.toggle('error', error);
}

function changed() {
  // Mark local edits pending without writing settings on each keystroke.
  // Apply validates the combined form, including conflicts across different tabs.
  // Reload remains available to discard edits and reread the Engine's actual state.
  dirty = true;
  message('');
  schedulePreview();
}

function refreshTuning() {
  // Display Engine's compiled speed, including inheritance and landing phases.
  // Update only explanatory text and visibility so typing never loses focus.
  // Keep explicitly configured but unused moves visible instead of hiding saved settings.
  for (const row of document.querySelectorAll<HTMLElement>('[data-speed-id]')) {
    const id = row.dataset.speedId!, compiled = preview?.moves[id];
    const used = preview?.used.includes(id);
    row.hidden = !showUnused && preview !== null && !used && !state.preset.move_settings[id];
    row.querySelector('output')!.textContent = compiled && used ? `Effective ${compiled.speed}× · ${state.preset.move_settings[id] ? 'custom speed' : 'inherited'}` : preview ? 'Not assigned in this moveset' : 'Resolve settings to preview';
  }
}

function schedulePreview() {
  // Validate the whole draft after a short typing pause, without persisting it.
  // Ignore responses from older drafts so a delayed success cannot enable an invalid Apply.
  // Compilation checks graph capacity and inherited settings as well as field bounds.
  const generation = ++draftGeneration;
  clearTimeout(draftTimer);
  const label = document.querySelector<HTMLElement>('#validation')!;
  label.textContent = 'Checking changes…'; label.dataset.state = 'checking'; label.classList.remove('error');
  for (const button of document.querySelectorAll<HTMLButtonElement>('#apply, #save, #enable, [data-binding-export]')) button.disabled = true;
  document.querySelector('#profile-name')!.textContent = state.preset.name + (dirty ? ' · unsaved' : '');
  draftTimer = setTimeout(async () => {
    // Capture browser-invalid number fields before blank/NaN values reach JSON serialization.
    // Worker compilation remains authoritative for cross-field and import-graph restrictions.
    // Errors stay separate from messages about binding, loading and saving.
    try {
      const invalid = content.querySelector<HTMLInputElement>('input:invalid');
      if (invalid) throw new Error(`${invalid.closest('label')?.querySelector('span')?.textContent || 'Value'}: ${invalid.validationMessage}`);
      const result = await window.mwm.request<Preview>('preview', params());
      if (generation !== draftGeneration) return;
      preview = result; label.textContent = dirty ? 'Unsaved changes · ready to save' : 'Saved moveset'; label.dataset.state = 'valid'; label.classList.remove('error');
      for (const button of document.querySelectorAll<HTMLButtonElement>('#apply, #save, #enable, [data-binding-export]')) button.disabled = button.id === 'apply' ? !dirty : button.id === 'enable' && dirty;
      document.querySelector<HTMLButtonElement>('#enable')!.title = dirty ? 'Save changes before enabling' : '';
    } catch (error) {
      if (generation !== draftGeneration) return;
      preview = null; label.dataset.state = 'invalid'; label.textContent = String(error).replace(/^Error: /, ''); label.classList.add('error');
    }
    refreshTuning();
  }, 180);
}

function params(value = state) {
  // Include the runtime identity shown when the form was loaded.
  // The worker rejects writes if another Engine became active meanwhile.
  // No game pointer or arbitrary file path is included in this form payload.
  return { runtime: value.runtime, preset: value.preset, calibration: value.calibration, nioh_exe: value.nioh_exe };
}

async function action(operation: () => Promise<void>) {
  // Serialize user mutations so two operations cannot replace each other's pending form.
  // Disable the form during a request and surface worker validation errors in place.
  // Re-enable controls even if a dialog is cancelled or the worker fails.
  if (busy || !state) return;
  busy = true; document.body.inert = true;
  try { await operation(); } catch (error) { message(String(error).replace(/^Error: /, ''), true); }
  finally { busy = false; document.body.inert = false; }
}

function element<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  // Build interface nodes without interpolating catalog strings into HTML.
  // Names remain ordinary text even when future imported labels contain punctuation.
  // The helper centralizes only repeated DOM creation, leaving behavior at each call site.
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function field(label: string, input: HTMLElement, parent: HTMLElement) {
  // Pair each input with a real label for keyboard and screen-reader navigation.
  // Shared CSS keeps spacing consistent across selects, numbers and binding rows.
  // Layout never infers a gameplay role from a label's spelling.
  const wrapper = element('label', undefined, 'field');
  wrapper.append(element('span', label), input); parent.append(wrapper);
  return wrapper;
}

function select(options: [string, string][], value: string | null, update: (value: string) => void) {
  // Render only caller-supplied reviewed options using stable IDs as values.
  // A blank value means Native/Disabled according to the owning control.
  // Changing the selection modifies the pending form only.
  const control = element('select');
  for (const [id, label] of options) control.add(new Option(label, id));
  control.value = value || '';
  control.onchange = () => {
    // Read the option value rather than trying to reverse-map its visible name.
    // The owner stores the appropriate nullable ID, stance or controller choice.
    // All tab edits share one explicit Apply boundary.
    update(control.value); changed();
  };
  return control;
}

function input(value: string | number, update: (value: string) => void, type = 'text') {
  // Keep incomplete numeric text editable until the user applies the form.
  // Browser bounds guide input; Engine validation enforces the actual rules.
  // No keystroke writes directly to the runtime's files.
  const control = element('input'); control.type = type; control.value = String(value);
  control.oninput = () => {
    // Pass the current string to the field-specific conversion.
    // Invalid numbers remain pending and are rejected before persistence.
    // Updating the form does not start Engine.
    update(control.value); changed();
  };
  return control;
}

function moveOptions(role: MoveRole, empty = 'Native'): [string, string][] {
  // Filter the imported capability rows by their implemented runtime role.
  // Research-only catalogue records never appear in these controls.
  // The Engine repeats this check when validating a submitted preset.
  const choices: [string, string][] = [['', empty]];
  for (const move of state.capabilities.moves) if (move[role]) choices.push([move.id, moveName(move)]);
  return choices;
}

function section(title: string, hint: string) {
  // Give each tab a clear purpose and a short explanation of its limits.
  // Keep the actual controls in a shared responsive grid below the introduction.
  // Returning that grid avoids multiple competing spacing conventions.
  content.append(element('h2', title, 'section-title'), element('p', hint, 'hint'));
  const grid = element('div', undefined, 'fields'); content.append(grid); return grid;
}

function moveName(move: Move): string {
  // UI names describe recorded moves; stable IDs still cross the worker boundary.
  // Trial labels come from the curated route descriptions, not inferred gameplay effects.
  // Source addresses remain available only in the research collection.
  const names: Record<string, string> = {
    'jin_hayabusa.action_0c6e': 'Jin · Cyclone slash string',
    'jin_hayabusa.action_0c6f': 'Jin · Second cyclone slash',
    'jin_hayabusa.action_0bbf': 'Jin · Five-strike sword string',
    'jin_hayabusa.action_0c79': 'Jin · Launcher only',
    'jin_hayabusa.izuna_drop': 'Jin · Launcher + Izuna Drop',
    'oda_nobunaga.action_0c6e': 'Oda · Final two slashes',
    'oda_nobunaga.action_0c6f': 'Oda · Final slash',
    'sanada_yukimura.action_0c6a': 'Sanada · Handgun shot',
    'tachibana_muneshige.action_0d8d': 'Tachibana · Omnislice',
    'toyotomi_hideyori.action_0d30': 'Hideyori · Four-hit string',
    'toyotomi_hideyori.action_0d31': 'Hideyori · Second strike',
    'toyotomi_hideyori.action_0d32': 'Hideyori · Third strike',
    'toyotomi_hideyori.action_0d33': 'Hideyori · Final strike'
  };
  const boss = move.id.startsWith('jin_hayabusa.') ? 'Jin' : move.id.startsWith('okatsu.') ? 'Okatsu' : '';
  return names[move.id] || (boss ? `${boss} · ${move.name}` : move.name);
}

function assignment(parent: HTMLElement, label: string, key: string, role: MoveRole, value: string | null, update: (value: string) => void) {
  // Each overview row edits the same preset field as the detailed controls.
  // Native/disabled choices clear only their own assignment.
  // Worker preview still validates interactions across every row and page.
  const control = select(moveOptions(role, 'No replacement'), value, update);
  control.dataset.assignment = key;
  control.setAttribute('aria-label', label);
  field(label, control, parent).className = 'assignment';
}

function renderOverview() {
  // Group actual assignments by stance, keeping shared inputs separate.
  // Display existing native rows directly rather than reconstructing a second preset model.
  // Editing a choice remains a draft until the single Save changes action succeeds.
  const p = state.preset;
  const heading = element('div', undefined, 'overview-heading');
  heading.append(element('h2', 'Move assignments'), element('p', 'Choose a move for each input.'));
  content.append(heading);
  const cards = element('div', undefined, 'stance-grid'); content.append(cards);
  const labels: Record<string, string> = { light_attack: 'Quick attack', heavy_attack: 'Heavy attack',
    dodge_attack: 'Dodge + heavy', guard_light: 'Guard + quick attack', high_heavy_followup: 'After heavy · guard + quick' };
  const nativeRow = (parent: HTMLElement, binding: Binding) => {
    // Keep custom source names readable while preserving Engine's exact route identity.
    // Removing an assignment restores that source through the ordinary validator.
    // A structural removal rebuilds the overview without touching unrelated routes.
    const label = labels[binding.source] || state.capabilities.native_sources.find(source => source.id === binding.source)?.label || binding.source;
    assignment(parent, label, `native:${binding.stance}:${binding.source}`, 'native', binding.move, value => {
      if (value) binding.move = value;
      else { p.skill_bindings.splice(p.skill_bindings.indexOf(binding), 1); render(); }
    });
  };
  for (const stance of state.capabilities.stances) {
    const card = element('section', undefined, 'stance-card'); card.dataset.stance = stance;
    card.append(element('h3', `${stance[0].toUpperCase() + stance.slice(1)} stance`)); cards.append(card);
    if (stance === 'low') assignment(card, 'Heavy attack string', 'low-heavy', 'heavy_string', p.low_heavy, value => { p.low_heavy = value || null; });
    for (const binding of p.skill_bindings.filter(row => row.stance === stance)) nativeRow(card, binding);
    assignment(card, 'Hold Triangle / Y', `hold:${stance}`, 'graph', p.stance_holds[stance], value => { p.stance_holds[stance] = value || null; });
    assignment(card, 'Frost Moon · stance switch', `frost:${stance}`, 'chord', p.frost_moon[stance], value => { p.frost_moon[stance] = value || null; });
  }
  const shared = element('section', undefined, 'shared-routes');
  const description = element('div');
  const buttonName = (mask: number) => Object.entries(state.buttons).find(([, value]) => value === mask)?.[0] || 'Unmapped button';
  description.append(element('h3', `${buttonName(p.modifier_mask)} + ${buttonName(p.trigger_mask)}`), element('p', p.chord_stance === 'any' ? 'Custom input · all stances' : `Custom input · ${p.chord_stance} stance`));
  const setup = element('button', 'Edit buttons →', 'inline-button'); setup.onclick = () => navigate('controls'); description.append(setup); shared.append(description);
  assignment(shared, 'Tap / release', 'chord:tap', 'chord', p.tap_move, value => { p.tap_move = value || null; });
  assignment(shared, `Hold · ${p.hold_seconds}s`, 'chord:hold', 'chord', p.hold_move, value => { p.hold_move = value || null; });
  const globalBindings = p.skill_bindings.filter(row => row.stance === 'any');
  shared.classList.toggle('has-global-bindings', globalBindings.length > 0);
  for (const binding of globalBindings) nativeRow(shared, binding);
  content.append(shared);
  const extras = [p.okatsu_grapple && 'Okatsu grapple', p.mid_light_ender && 'mid quick finisher', p.string_enabled && 'quick-attack string'].filter(Boolean);
  const extra = element('details', undefined, 'overview-extra'); extra.append(element('summary', extras.length ? 'Extra moves · ' + extras.join(', ') : 'Extra moves'));
  const fields = element('div', undefined, 'fields'); extra.append(fields);
  for (const [key, label] of [['okatsu_grapple', 'Okatsu grapple'], ['mid_light_ender', 'Mid quick-attack finisher'], ['string_enabled', 'Imported quick-attack string']] as const) {
    const check = element('input'); check.type = 'checkbox'; check.checked = p[key];
    check.onchange = () => { p[key] = check.checked; extra.querySelector('summary')!.textContent = 'Extra moves'; changed(); };
    field(label, check, fields).classList.add('toggle');
  }
  const more = element('button', 'Edit other inputs →', 'inline-button'); more.onclick = () => navigate('native'); fields.append(more);
  content.append(extra);
}

function renderMoves() {
  // Present the existing sword preset's custom chord and native hold choices.
  // Each move menu uses its own capability flag rather than a universal catalogue list.
  // Weapon selection stays sword-only until Engine implements reviewed weapon routing.
  const p = state.preset, grid = section('Custom input', 'Choose two buttons and assign a tap or hold move. Imported graphs require a Low, Mid or High stance. Launcher only and Launcher + Izuna Drop require different stances.');
  field('Moveset name', input(p.name, value => {
    // Preserve a readable profile name apart from its stable move IDs.
    // Engine enforces its length and nonempty value during Apply.
    // Renaming a preset does not change weapon support.
    p.name = value;
  }), grid);
  field('Custom input stance', select((state.capabilities.chord_stances || state.capabilities.stances).map(stance => {
    // Each stance maps directly to the Engine's canonical value.
    // No priority label from a recording enters this selector.
    // Titles remain cosmetic.
    return [stance, stance === 'any' ? 'ANY · single moves only' : stance.toUpperCase()];
  }), p.chord_stance, value => {
    // Save the concrete stance required by the custom chord.
    // Engine rejects unsupported cross-stance combinations.
    // This edits only the draft.
    p.chord_stance = value as Stance | 'any';
  }), grid);
  renderChordButtons(grid);
  for (const [key, label] of [['tap_move', 'Tap / release'], ['hold_move', 'Hold']] as const) {
    field(label, select(moveOptions('chord', 'Disabled'), p[key], value => {
      // Store the chosen reviewed action by its stable identity.
      // Clearing the option disables this half of the chord.
      // Tap and hold remain independently configurable.
      p[key] = value || null;
    }), grid);
  }
  const threshold = input(state.preset.hold_seconds, value => {
    // Express hold duration in seconds for the existing chord interpreter.
    // Engine enforces the reviewed 0.08–2 second range.
    // This is separate from developer-owned animation phase timing.
    state.preset.hold_seconds = Number(value);
  }, 'number'); threshold.min = '.08'; threshold.max = '2'; threshold.step = 'any'; field('Hold threshold · seconds', threshold, grid);

}

function renderOverrides() {
  // Group stance replacements separately from the custom button chord.
  // Every control edits the same pending preset; nothing is applied on selection.
  // Native overrides below provide explicit source and stance routing.
  const p = state.preset, grid = section('Stance overrides', 'Native keeps the original action. Hold Triangle / Y for the chosen held move. Launcher only and Launcher + Izuna Drop require different stances; the drop requires contact.');
  field('Low heavy string', select(moveOptions('heavy_string'), p.low_heavy, value => {
    // Select a reviewed heavy-string graph rather than an arbitrary animation.
    // Native clears only this particular replacement.
    // Continuation and recovery still belong to Engine.
    p.low_heavy = value || null;
  }), grid);
  for (const stance of state.capabilities.stances) {
    field(stance.toUpperCase() + ' · hold Triangle / Y', select(moveOptions('graph'), p.stance_holds[stance], value => {
      // Bind a reviewed graph to this stance's held-heavy slot.
      // Shared source actions retain their Engine-authored graph transitions.
      // A blank value restores the native held-heavy behavior.
      p.stance_holds[stance] = value || null;
    }), grid);
  }
  for (const [key, label] of [['okatsu_grapple', 'Okatsu grapple'], ['mid_light_ender', 'Mid light ender'], ['string_enabled', 'Imported light string']] as const) {
    const check = element('input'); check.type = 'checkbox'; check.checked = p[key];
    check.onchange = () => {
      // Toggle one established sword adaptation without exposing its internal timing.
      // Engine validates this together with all related binding choices.
      // The running moveset does not change until Apply.
      p[key] = check.checked; changed();
    };
    field(label, check, grid).classList.add('toggle');
  }
}

function renderNative() {
  // Edit a list of explicit source/stance replacements instead of guessing from move names.
  // Engine rejects duplicate, overlapping or incompatible bindings on Apply.
  // Removing a row restores that source's native behavior after Apply.
  section('Input overrides', 'Replace a native action in a chosen stance. Remove a row to restore its original behavior. Conflicts appear below before you apply.');
  for (const [index, binding] of state.preset.skill_bindings.entries()) {
    const row = element('div', undefined, 'binding');
    const sources: [string, string][] = [];
    for (const source of state.capabilities.native_sources) sources.push([source.id, source.label]);
    field('Source', select(sources, binding.source, value => {
      // Change the native entry point for this pending override.
      // Source IDs come from Engine's maintained list.
      // Semantic overlap is checked with the entire preset.
      binding.source = value;
      const stances = state.capabilities.native_sources.find(source => source.id === value)?.stances;
      if (stances && !stances.includes(binding.stance)) binding.stance = stances[0];
      render();
    }), row);
    field('Stance', select((state.capabilities.native_sources.find(source => source.id === binding.source)?.stances || ['any', 'low', 'mid', 'high']).map(stance => [stance, stance.toUpperCase()]), binding.stance, value => {
      // Any is valid only where the selected action permits it.
      // Graphs requiring a concrete stance are rejected by Engine.
      // No automatic conflict resolution silently removes another row.
      binding.stance = value;
    }), row);
    field('Replacement', select(moveOptions('native').slice(1), binding.move, value => {
      // Expose only actions reviewed for native-source replacement.
      // This stores an ID, never a raw game address.
      // Apply still checks source-specific restrictions.
      binding.move = value;
    }), row);
    const remove = element('button', 'Remove'); remove.onclick = () => {
      // Delete exactly the row whose Remove action was pressed.
      // Rerender reassigns displayed indices after deletion.
      // The saved Engine preset remains untouched until Apply.
      state.preset.skill_bindings.splice(index, 1); changed(); render();
    };
    row.append(remove); content.append(row);
  }
  const add = element('button', '+ Add replacement'); add.onclick = () => {
    // Ask the worker for an unoccupied source/stance with a compatible reviewed move.
    // Capacity and graph restrictions are checked before a row reaches the form.
    // The returned row remains editable and is not applied automatically.
    void action(async () => {
      await cancelCapture(); state.preset = await window.mwm.request<Preset>('add_override', params());
      changed(); render();
    });
  };
  content.append(add);
}

function renderFrost() {
  // Let users choose only the destination action for each Frost Moon route.
  // Activation windows, startup speed, Ki Pulse and physics remain Engine-owned.
  // This separates configurable move selection from adaptation internals.
  const grid = section('Stance-switch moves', 'During a Ki Pulse window, hold R1 / RB and tap the destination stance button twice.');
  for (const stance of state.capabilities.stances) field(stance.toUpperCase(), select(moveOptions('chord', 'Disabled'), state.preset.frost_moon[stance], value => {
    // Change this destination stance's reviewed move.
    // Clearing disables its replacement without changing other routes.
    // Actual route acceptance remains a separate gameplay check.
    state.preset.frost_moon[stance] = value || null;
  }), grid);
}

function renderSpeed() {
  // A blank field inherits its string speed; 1 explicitly restores this phase to native speed.
  // Engine previews resolve the final value, including paired/airborne restrictions.
  // Keep unused overrides editable while making the active move list the default view.
  const grid = section('Move tuning', 'Speed: 0.25–2×. Leave blank to inherit the string speed; enter 1 for explicit native speed. Ki Pulse, physics and Frost startup stay developer-controlled.');
  grid.className = 'speed-list';
  const show = element('input'); show.type = 'checkbox'; show.checked = showUnused;
  show.onchange = () => {
    // This controls visibility only, never the saved moveset.
    // Existing values stay in the draft when their rows are hidden.
    // No worker request is necessary to filter already compiled rows.
    showUnused = show.checked; refreshTuning();
  };
  field('Show unused moves', show, content).classList.add('toggle'); content.append(grid);
  for (const move of state.capabilities.moves) if (move.speed) {
    const row = element('div', undefined, 'speed-row'); row.dataset.speedId = move.id;
    const control = element('input'); control.type = 'number'; control.placeholder = 'Inherit';
    control.value = state.preset.move_settings[move.id] ? String(state.preset.move_settings[move.id].speed) : '';
    control.min = String(state.capabilities.speed.min); control.max = String(state.capabilities.speed.max); control.step = 'any';
    control.oninput = () => {
      // Preserve explicit 1x: removing it would incorrectly inherit a changed graph root.
      // A genuinely empty field clears only this phase's override.
      // Incomplete numeric input stays invalid until corrected, even after changing tabs.
      if (control.value === '' && !control.validity.badInput) delete state.preset.move_settings[move.id];
      else state.preset.move_settings[move.id] = { speed: control.valueAsNumber };
      changed();
    };
    field(moveName(move), control, row);
    const reset = element('button', 'Inherit'); reset.title = 'Remove this speed override';
    reset.onclick = () => {
      // Restore inheritance for this phase without resetting any other setting.
      // Update the existing input in place so keyboard focus stays stable.
      // The next preview supplies the effective graph value.
      delete state.preset.move_settings[move.id]; control.value = ''; changed();
    };
    row.append(reset, element('output')); grid.append(row);
  }
  refreshTuning();
}

async function pollCapture() {
  // Poll input only while the player has explicitly armed press-to-bind.
  // Wait for each reply before scheduling another request to prevent queue growth.
  // A captured mask updates the pending field and then closes the listener.
  if (!capture) return;
  const generation = captureGeneration, target = capture;
  try {
    const result = await window.mwm.request<{ mask?: number; label?: string; status?: string }>('capture_poll');
    if (!capture || generation !== captureGeneration) return;
    if (result.mask !== undefined) { state.preset[target] = result.mask; capture = null; changed(); render(); message('Bound ' + result.label + '. Apply to save.'); }
    else { message(result.status || 'Waiting for input'); timer = setTimeout(pollCapture, 70); }
  } catch (error) { if (generation === captureGeneration) { capture = null; render(); message(String(error), true); } }
}

async function cancelCapture() {
  // End an armed binding before switching tabs or controller mappings.
  // A late polling reply observes the cleared target and cannot overwrite the new form.
  // The worker closes any native trace handle associated with this listener.
  ++captureGeneration; capture = null; clearTimeout(timer); await window.mwm.request('capture_cancel');
}

function renderChordButtons(grid: HTMLElement) {
  // Keep the chord's actual buttons beside its tap/hold actions.
  // Binding captures target one pending field and never change runtime input directly.
  // Controller-specific labels come from the same calibration used by validation.
  const buttons: [string, string][] = [];
  for (const [label, mask] of Object.entries(state.buttons)) buttons.push([String(mask), label]);
  for (const [key, label] of [['modifier_mask', 'Modifier'], ['trigger_mask', 'Trigger']] as const) {
    const wrapper = field(label, select(buttons, String(state.preset[key]), value => {
      // Store the selected calibrated bit rather than a display label.
      // Engine rejects identical modifier and trigger buttons.
      // Both roles remain draft values until Apply.
      state.preset[key] = Number(value);
      void action(cancelCapture);
    }), grid);
    const bind = element('button', capture === key ? 'Listening…' : 'Press to bind'); bind.onclick = () => {
      // Arm this specific pending field after cancelling any earlier request.
      // Engine requires neutral input before returning a single supported button.
      // Binding never enables the mod by itself.
      void action(async () => {
        // Keep listener creation ordered with previous cancellation.
        // Start polling only after the worker confirms its listener exists.
        // The UI target names the field that receives a completed mask.
        await cancelCapture(); await window.mwm.request('capture_start', { calibration: state.calibration }); capture = key; render(); void pollCapture();
      });
    };
    wrapper.append(bind);
  }
  const swap = element('button', 'Swap buttons');
  swap.onclick = () => {
    // Exchange both halves of the chord as one draft change, avoiding an intermediate duplicate.
    // Cancel binding capture so a delayed physical press cannot overwrite the swap.
    // Move choices, hold duration and all Frost destinations remain unchanged.
    void action(async () => {
      await cancelCapture();
      [state.preset.modifier_mask, state.preset.trigger_mask] = [state.preset.trigger_mask, state.preset.modifier_mask];
      changed(); render();
    });
  };
  swap.className = 'swap-buttons'; grid.append(swap);
  if (capture) {
    const cancel = element('button', 'Cancel binding');
    cancel.onclick = () => {
      // Cancel this listener explicitly without saving a captured value.
      // The generation check also rejects any reply already in transit.
      // Return the controls to their normal editable state.
      void action(async () => { await cancelCapture(); render(); message('Binding cancelled.'); });
    };
    grid.append(cancel);
  }
}

function renderControls() {
  // Present calibrated button meanings and supported OS controller backends.
  // Remapping goes through Engine so changing hardware preserves logical button choices.
  // Physical controller acceptance is not inferred from successfully editing this form.
  const grid = section('Controller & custom input', 'Xbox: use XInput. PS5: enable Steam Input for Nioh, then use its XInput slot. Release all controls before press-to-bind; disable the mod before changing mappings.');
  const devices = select([['saved', 'Saved mapping'], ['ds4', 'DS4 mapping'], ['1', 'XInput controller 1'], ['2', 'XInput controller 2'], ['3', 'XInput controller 3'], ['4', 'XInput controller 4']], controllerChoice, value => {
    // Cancel the previous controller listener before translating button masks.
    // Failed remapping preserves the current pending preset.
    // Successful selection remains unsaved until Apply.
    void action(async () => {
      // Ask Engine to preserve logical button meaning across mappings.
      // Replace calibration, buttons and preset as one UI state update.
      // No file writes occur in this translation request.
      await cancelCapture(); Object.assign(state, await window.mwm.request('controller', { ...params(), choice: value })); controllerChoice = value; render(); changed();
    });
  });
  field('Controller mapping', devices, grid);
  field('Game controller slot', select([['', 'Auto (one controller)'], ['0', '1'], ['1', '2'], ['2', '3'], ['3', '4']], state.calibration.controller_slot == null ? '' : String(state.calibration.controller_slot), value => {
    // Keep the game's controller slot distinct from raw OS controller identity.
    // Automatic selection requires one valid controller at runtime.
    // Changing this cancels a listener created under the previous selection.
    state.calibration.controller_slot = value === '' ? null : Number(value); void action(cancelCapture);
  }), grid);
  const path = element('button', state.nioh_exe || 'Choose nioh.exe (optional)'); path.onclick = () => {
    // Delegate executable selection to a native dialog in the main process.
    // Choosing a path changes the next explicit Enable request only.
    // Cancelling preserves the previously selected path.
    void action(async () => {
      // Receive only the file chosen by the user.
      // Store it as a pending launch preference rather than launching it now.
      // No renderer-supplied path is trusted by the native dialog channel.
      const value = await window.mwm.request<string | null>('game_path'); if (value) { state.nioh_exe = value; changed(); render(); }
    });
  }; field('Game executable', path, grid);
}

function renderCollection() {
  // Show the full research collection without exposing candidate moves as playable choices.
  // The layout and exact notes explain which recorded sequences still need adaptation.
  // Filtering only hides cards; it never edits the pending moveset or loses keyboard focus.
  content.append(element('h2', 'Sword Rebuild 1', 'section-title'));
  content.append(element('p', 'The subset contains Jin moves. Sword Rebuild 1 adds Oda, Tachibana, Hideyori and Sanada. Save changes stores the draft; Enable mod activates it. See each route for its acceptance status.', 'hint'));
  const labels: Record<string, string> = { handgun: 'LB + LT', low_heavy: 'Low · heavy', low_dodge_attack: 'Low · dodge + heavy',
    mid_heavy: 'Mid · heavy', mid_dodge_attack: 'Mid · dodge + heavy', low_quick: 'Low · quick', high_heavy_omnislice: 'High heavy → LB + Square',
    frost_high: 'High Frost Moon', frost_mid: 'Mid Frost Moon', frost_low: 'Low Frost Moon' };
  const actions: Record<string, string> = { low_dodge_attack: 'Jin · second heavy', mid_heavy: 'Jin · five-hit quick string B', mid_dodge_attack: 'Jin · five-hit quick string B',
    frost_mid: 'Oda · final two slashes', frost_low: 'Jin · Flying Swallow', high_heavy_omnislice: 'Tachibana · Omnislice attack immediately' };
  const routes = element('dl', undefined, 'route-list');
  for (const route of collection.design.routes) {
    const move = collection.moves.find(move => move.id === route.dataset_id);
    routes.append(element('dt', labels[route.id] || route.id));
    const value = element('dd', `${actions[route.id] || move?.name || route.dataset_id} · ${route.status.replaceAll('_', ' ')}`);
    if (route.blockers.length) value.append(element('p', route.blockers.join(' '), 'hint'));
    routes.append(value);
  }
  content.append(routes, element('h2', 'Recorded moves', 'section-title'));
  const missing = collection.intake.sessions.filter(session => session.status !== 'curated_candidate').length;
  content.append(element('p', `${collection.moves.length} candidate strings · ${collection.intake.sessions.length} source sessions · ${missing} incomplete sessions. Names follow your notes; action matching still needs review.`, 'hint'));
  const search = element('input'); search.type = 'search'; search.placeholder = 'Find a boss, move or description'; search.setAttribute('aria-label', 'Search recorded moves');
  content.append(search);
  const cards: { node: HTMLElement; text: string }[] = [];
  for (const move of collection.moves) {
    const card = element('details', undefined, 'research-move');
    const weapon = collection.manifest.weapons[move.weapon_id].name, boss = collection.manifest.bosses[move.boss_id].name;
    const title = `${weapon} / ${boss} · ${move.name}`;
    card.append(element('summary', title));
    card.append(element('p', `${move.mapping_status === 'partial' ? 'Partial mapping' : 'Candidate mapping'} · Priority: ${move.priority || 'unset'}`, 'hint'));
    for (const evidence of move.evidence) card.append(element('p', evidence.annotation_text, 'recorded-note'));
    card.append(element('p', move.steps.map(step => `${step.source.action_id} (${step.source.motion_id})`).join(' → '), 'source-ids'));
    for (const note of move.review_notes) card.append(element('p', note, 'hint'));
    cards.push({ node: card, text: [title, ...move.evidence.map(evidence => evidence.annotation_text)].join(' ').toLowerCase() });
    content.append(card);
  }
  const empty = element('p', 'No recorded moves match.', 'hint'); empty.hidden = true; content.append(empty);
  search.oninput = () => {
    // Match boss, weapon, title and original notes as plain text.
    // Keep this browsing action separate from configuration dirty state.
    // The empty result message stays inside the collection rather than overwriting Apply status.
    const query = search.value.trim().toLowerCase();
    for (const card of cards) card.node.hidden = !card.text.includes(query);
    empty.hidden = cards.some(card => !card.node.hidden);
  };
}

function renderBindingModules() {
  // Reuse one binding group across movesets without overwriting name, speed or unrelated routes.
  // File dialogs stay in the main process; the worker validates and remaps the merged draft.
  // Selecting a group is a UI preference and must not mark the moveset dirty.
  const panel = element('details', undefined, 'binding-modules');
  panel.append(element('summary', 'Reuse a binding group'));
  const controls = element('div', undefined, 'module-controls');
  const groups = element('select'); groups.setAttribute('aria-label', 'Binding group');
  for (const group of state.binding_groups) groups.add(new Option(group.label, group.id));
  groups.value = bindingGroup;
  groups.onchange = () => { bindingGroup = groups.value; };
  controls.append(groups);
  for (const [operation, label] of [['binding_export', 'Save group…'], ['binding_import', 'Load group…']]) {
    const button = element('button', label);
    if (operation === 'binding_export') button.dataset.bindingExport = '';
    button.onclick = () => {
      // A cancelled dialog leaves the draft intact; a loaded group replaces only its owned fields.
      // Failed cross-group compatibility checks preserve every original draft value.
      // Group loading never applies settings or enables the mod.
      void action(async () => {
        await cancelCapture();
        const result = await window.mwm.request<Preset | boolean | null>(operation, { ...params(), group: bindingGroup });
        if (!result) return;
        if (operation === 'binding_import') { state.preset = result as Preset; changed(); render(); }
        message(operation === 'binding_import' ? 'Binding group loaded. Other groups and tuning are unchanged. Apply to save.' : 'Binding group exported.');
      });
    };
    controls.append(button);
  }
  panel.append(controls, element('p', 'Only the selected group is replaced. Chord buttons translate to your current controller; incompatible combinations are rejected.', 'hint'));
  content.append(panel);
}

function render() {
  // Rebuild only the selected tab from the pending model.
  // Ordinary input edits stay in place; tab changes and structural edits request a rebuild.
  // All text supplied by data remains escaped by DOM construction.
  content.replaceChildren(); content.setAttribute('aria-busy', 'false');
  if (['native', 'frost'].includes(tab)) renderBindingModules();
  for (const button of document.querySelectorAll<HTMLButtonElement>('nav button')) button.classList.toggle('selected', button.dataset.tab === tab);
  if (tab === 'overview') renderOverview();
  else if (tab === 'collection') renderCollection();
  else if (tab === 'controls') { renderMoves(); renderControls(); renderBindingModules(); }
  else if (tab === 'native') { renderOverrides(); renderNative(); }
  else if (tab === 'frost') renderFrost();
  else if (tab === 'speed') renderSpeed();
  else {
    const guide = element('article', undefined, 'guide');
    guide.append(element('h2', 'Edit, save, enable.'));
    for (const text of ['1. Choose moves for your inputs, then Save changes.', '2. Open Controller to set your device and custom buttons if needed.', '3. Enable mod and test your moves. Check its status above; use Disable mod when finished.']) guide.append(element('p', text));
    guide.append(element('h2', 'Sword Rebuild 1 defaults'));
    for (const text of ['Low Triangle / Y and dodge + heavy use Jin’s cyclone string. Mid Triangle / Y and dodge + heavy use Jin’s five strikes. Low Square / X uses Hideyori’s four-hit string.', 'Low LB + LT tap fires Sanada’s handgun. High heavy → LB + Square / X uses Tachibana’s Omnislice.', 'During a Ki Pulse window, hold R1 / RB and tap the destination stance button twice. Low uses Flying Swallow, Mid uses Oda’s final two slashes, High uses the downward slash.', 'Choose Hold Triangle / Y separately in each stance. Launcher only and Launcher + Izuna Drop must use different stances; the drop requires contact.', 'Use Reuse a binding group under Controller or More → Other inputs & options to export or load one group. Other groups and speed settings stay unchanged.']) guide.append(element('p', text));
    content.append(guide);
  }
  schedulePreview();
}

async function reload() {
  // Read a fresh snapshot only when explicitly loading or discarding pending edits.
  // Keep periodic runtime status reads separate so they never overwrite form choices.
  // Display actual process-backed Engine status alongside the loaded configuration.
  await cancelCapture(); state = await window.mwm.request<Snapshot>('snapshot'); controllerChoice = 'saved'; dirty = Boolean(state.load_warning); render();
  showRuntime(state);
  message(state.load_warning || '', Boolean(state.load_warning));
}

async function perform(name: string) {
  // Route footer/lifecycle actions through the same pending form and worker validation.
  // Import, Baseline and Export do not implicitly enable or apply a moveset.
  // No UI path bypasses Engine's preset validator.
  await cancelCapture();
  if (name === 'reload') { await reload(); return; }
  if (name === 'baseline' || name === 'starter' || name === 'trial' || name === 'load') {
    const preset = await window.mwm.request<Preset | null>(name === 'load' ? 'import' : name, params());
    if (preset) { state.preset = preset; dirty = true; render(); message(name === 'trial' ? 'Sword Rebuild 1 loaded into draft.' : name === 'starter' ? 'Subset loaded into draft.' : 'Moveset loaded into draft.'); } return;
  }
  if (name === 'save') { if (await window.mwm.request('export', params())) message('Moveset exported. Runtime settings were not changed.'); return; }
  if (name === 'apply') { state = await window.mwm.request<Snapshot>('apply', params()); dirty = false; render(); showRuntime(state); message(''); return; }
  if (name === 'enable') { if (dirty) throw new Error('Save changes before enabling the mod.'); await window.mwm.request('enable', params()); showRuntime(await window.mwm.request<Snapshot>('snapshot')); message(''); return; }
  if (name === 'disable') { await window.mwm.request('disable'); showRuntime(await window.mwm.request<Snapshot>('snapshot')); message(''); }
}

function navigate(name: string) {
  // Navigation retains the pending model while cancelling any physical binding listener.
  // Closing More keeps its secondary commands out of the workspace.
  // A page change never saves or starts gameplay.
  void action(async () => { await cancelCapture(); tab = name; document.querySelector<HTMLDetailsElement>('#tools')!.open = false; render(); });
}

for (const button of document.querySelectorAll<HTMLButtonElement>('nav [data-tab]')) button.onclick = () => navigate(button.dataset.tab!);
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-action]')) button.onclick = () => {
  // Keep all explicit mutations on the serialized worker path.
  // The only primary button saves; file and lifecycle operations stay distinct.
  // Closing the menu also prevents it covering the result of an action.
  document.querySelector<HTMLDetailsElement>('#tools')!.open = false;
  void action(() => perform(button.dataset.action!));
};

function showRuntime(snapshot: Snapshot) {
  // Runtime facts come from a fresh worker snapshot, independently of the draft.
  // Show only the lifecycle action relevant to the reported process state.
  // Preserve terminal failure details after Engine exits instead of claiming readiness.
  state.running = snapshot.running; state.status = snapshot.status; state.detail = snapshot.detail;
  const runtime = document.querySelector<HTMLElement>('.runtime')!;
  runtime.dataset.running = String(snapshot.running);
  const failed = /error|fail|blocked|fatal|attention|missing/.test(snapshot.status);
  runtime.dataset.error = String(failed);
  if (failed && !notice.classList.contains('error')) message('');
  const labels: Record<string, string> = { disabled: 'Mod off', preparation_failed: 'Mod could not start', start_failed: 'Mod could not start', cleanup_needs_attention: 'Recovery needs attention', runtime_missing: 'Runtime unavailable' };
  document.querySelector('#runtime')!.textContent = labels[snapshot.status] || snapshot.status.replaceAll('_', ' ');
  const detail = document.querySelector<HTMLElement>('#runtime-detail')!; detail.textContent = snapshot.detail; detail.title = snapshot.detail;
  document.querySelector<HTMLButtonElement>('#enable')!.hidden = snapshot.running;
  document.querySelector<HTMLButtonElement>('#disable')!.hidden = !snapshot.running;
}

async function pollStatus() {
  // Adopt external saved changes only while the editor is still clean and idle.
  // Recheck after awaiting the worker so an in-flight read cannot overwrite a new draft.
  // Unchanged snapshots update runtime status without rebuilding controls or moving focus.
  if (state && !busy && !capture) {
    try {
      const snapshot = await window.mwm.request<Snapshot>('snapshot');
      if (!dirty && !busy && !capture && JSON.stringify(params(snapshot)) !== JSON.stringify(params())) {
        state = snapshot; controllerChoice = 'saved'; dirty = Boolean(snapshot.load_warning);
        render(); message(snapshot.load_warning || '', Boolean(snapshot.load_warning));
      }
      showRuntime(snapshot);
    } catch (error) { document.querySelector('#runtime')!.textContent = 'Worker unavailable'; document.querySelector('#runtime-detail')!.textContent = String(error); }
  }
  setTimeout(pollStatus, 1800);
}

async function start() {
  // Load configuration before enabling any app commands.
  // Startup failure stays visible instead of presenting an empty ready form.
  // Status polling is read-only and does not attach to Nioh.
  document.body.inert = true;
  try { collection = await window.mwm.request<Collection>('collection'); await reload(); void pollStatus(); } catch (error) { message(String(error), true); }
  finally { document.body.inert = false; }
}
void start();
