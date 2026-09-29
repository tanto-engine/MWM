// The form stores only pending choices; Engine validates the complete preset on Apply.
// Stable move IDs travel over IPC while readable names remain presentation data.
export {};
type Stance = 'low' | 'mid' | 'high';
type MoveRole = 'chord' | 'graph' | 'held' | 'heavy_string' | 'native' | 'speed';
type Move = { id: string; name: string; input?: string; description?: string } & Record<MoveRole, boolean>;
type Calibration = { device: Record<string, unknown>; controller_slot?: number | null; [key: string]: unknown };
type ButtonKey = 'modifier_mask' | 'trigger_mask';
const routeTriggers = ['Circle / B', 'Triangle / Y', 'L2 / LT', 'Square / X'];
type Binding = { source: string; stance: string; move: string; input?: { modifier_mask: number; trigger_mask: number; gesture: 'tap' | 'hold' } };
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
  capabilities: { moves: Move[]; native_sources: { id: string; label: string; description?: string; stances?: string[] }[]; stances: Stance[]; chord_stances?: (Stance | 'any')[]; native_binding_limit?: number; custom_binding_limit?: number; speed: { min: number; max: number } };
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
type CaptureTarget = { kind: 'global'; key: ButtonKey } | { kind: 'route'; binding: Binding; key: ButtonKey };
let tab = 'overview', dirty = false, busy = false, capture: CaptureTarget | null = null;
let controllerChoice = 'saved';
let bindingGroup = 'chord';
let timer: ReturnType<typeof setTimeout> | undefined;
let captureGeneration = 0, draftGeneration = 0;
let actionGeneration = 0;
let editGeneration = 0, explainedEdit = 0;
let draftTimer: ReturnType<typeof setTimeout> | undefined;
let noticeTimer: ReturnType<typeof setTimeout> | undefined;
type Preview = { preset: Preset; used: string[]; moves: Record<string, { speed: number; percent: number; fill_frames: number; hold_frames: number }> };
let preview: Preview | null = null, showUnused = false;
const content = document.querySelector<HTMLElement>('#content')!;
const notice = document.querySelector<HTMLElement>('#notice')!;
const errorDialog = document.querySelector<HTMLDialogElement>('#binding-error')!;
const helpTitle = document.querySelector<HTMLElement>('#help-title')!;
const helpBody = document.querySelector<HTMLElement>('#help-body')!;
const helpTip = document.querySelector<HTMLElement>('#help-tip')!;
const soundToggle = document.querySelector<HTMLInputElement>('#sound-toggle')!;
const hapticToggle = document.querySelector<HTMLInputElement>('#haptic-toggle')!;
const picker = document.querySelector<HTMLDialogElement>('#move-picker')!;
const pickerSearch = document.querySelector<HTMLInputElement>('#picker-search')!;
const pickerResults = document.querySelector<HTMLElement>('#picker-results')!;
soundToggle.checked = localStorage.getItem('mwm.sound') !== 'off';
hapticToggle.checked = localStorage.getItem('mwm.haptic') === 'on';

const pageHelp: Record<string, [string, string, string]> = {
  overview: ['Sword skill map', 'Original routes replace a Nioh input; custom routes use their own controller buttons.', 'Open Input routes to choose the activation for each replacement.'],
  speed: ['Move tuning', 'Set the playback speed of a move or one phase of a string.', 'Blank inherits its string speed. Enter 1 for native speed.'],
  controls: ['Controller', 'Set the device mapping and the buttons for the global custom chord.', 'Input routes can use additional chords with separate buttons.'],
  native: ['Input routes', 'Choose Original Nioh input or Custom controller chord for each reviewed move.', 'Custom routes add a new input and leave original game actions alone.'],
  frost: ['Stance-switch moves', 'Choose the move used when Frost Moon reaches each stance.', 'Trigger during a Ki Pulse window with R1 / RB and two stance taps.'],
  collection: ['Move library', 'Playable moves can be assigned in Sword or Input routes. Recorded candidates remain research until adapted and reviewed.', 'A video or action ID alone does not establish that William can play a move.'],
  guide: ['Help', 'Choose moves, save the draft, then enable the mod.', 'Disable the mod before saving further changes.']
};
const fieldHelp: Record<string, [string, string]> = {
  'Moveset name': ['Names this saved configuration in the editor.', 'It does not change the game weapon.'],
  'Custom input stance': ['Limits the two-button input to a stance. Graph moves need Low, Mid or High.', 'Any works only for single moves.'],
  Modifier: ['The first button in your custom two-button input. Hold it while pressing Trigger.', 'Use Press to bind to record directly from the controller.'],
  Trigger: ['The second button in your custom input. Tap or hold it while Modifier is down.', 'Modifier and Trigger must be different buttons.'],
  'Tap / release': ['The move performed by a short press of the custom input.', 'Choose No replacement or Disabled to leave it unused.'],
  Hold: ['The move performed when the custom input passes its hold threshold.', 'Tap and hold can use different moves.'],
  'Hold threshold · seconds': ['How long Trigger stays down before the Hold move wins.', 'A shorter time makes holds easier to trigger.'],
  'Controller mapping': ['Select the device layout used to translate button names and masks.', 'PlayStation controllers using Steam Input appear as XInput.'],
  'Game controller slot': ['Choose which game controller is used when several are connected.', 'Auto works when exactly one eligible controller is active.'],
  'Game executable': ['Choose nioh.exe for launching the game from this app.', 'Changing the path does not launch the game.'],
  'Show unused moves': ['Include speed controls for moves outside this moveset.', 'Saved overrides on unused moves remain available.'],
  Source: ['The game-selected sword input replaced by this original route.', 'Switch Activation to custom buttons to leave the original input unchanged.'],
  Activation: ['Original Nioh input replaces the selected game action. Custom controller chord starts from the buttons in this row.', 'A custom route adds an input without changing original game actions.'],
  Gesture: ['Tap starts on a short Trigger press. Hold starts after the custom chord hold threshold.', 'A tap and hold can use the same buttons for separate routes.'],
  Stance: ['The stance in which this route applies.', 'Any works where the selected move and original source permit it.'],
  Move: ['The reviewed move played by this route.', 'Remove the row to clear the route.'],
  'Okatsu grapple': ['When a sword grapple succeeds and its native contact condition is met, use the imported Okatsu grapple sequence.', 'This does not turn normal attacks into grapples.'],
  'Mid quick-attack finisher': ['While a native Mid quick-attack string is active, hold Guard (LB/L1) and press Strong attack (Y/Triangle) in its combo window for William’s native finisher.', 'It adds a finisher to three Mid quick strings; it does not replace every quick press.'],
  'Okatsu dual-trigger string': ['After both analog triggers return to neutral, hold LT+RT (L2+R2) past their threshold to start the optional Okatsu imported string.', 'This is separate from replacing Nioh’s ordinary Quick attack source.'],
  'Low heavy string': ['Replaces Low stance’s ordinary heavy-attack sequence with the selected reviewed string.', 'Its later phases continue from the first attack; set phase speeds in Tuning.']
};

function explain(title: string, body: string, tip: string) {
  if (helpTitle.textContent === title && helpBody.textContent === body) return;
  helpTitle.textContent = title; helpBody.textContent = body; helpTip.textContent = tip;
  const copy = helpTitle.parentElement!;
  copy.classList.remove('reveal'); void copy.offsetWidth; copy.classList.add('reveal');
}
function annotate(node: HTMLElement, title: string, body: string, tip: string) {
  node.dataset.helpTitle = title; node.dataset.helpBody = body; node.dataset.helpTip = tip;
}
function explainTarget(target: EventTarget | null) {
  const node = (target as Element | null)?.closest?.<HTMLElement>('[data-help-title]');
  if (node) explain(node.dataset.helpTitle!, node.dataset.helpBody!, node.dataset.helpTip!);
}
document.addEventListener('pointerover', event => explainTarget(event.target));
document.addEventListener('focusin', event => explainTarget(event.target));
annotate(soundToggle.closest('label')!, 'Soft sounds', 'Play quiet cues after recording an input or saving changes.', 'Turn this off to mute the editor.');
annotate(hapticToggle.closest('label')!, 'Haptics', 'Give a short gentle pulse after an XInput button is recorded.', 'Requires an active XInput controller slot.');
for (const button of document.querySelectorAll<HTMLButtonElement>('nav [data-tab]')) {
  const [title, body, tip] = pageHelp[button.dataset.tab!]; annotate(button, title, body, tip);
}
const actionHelp: Record<string, [string, string]> = {
  enable: ['Starts the mod with your saved moveset.', 'Save pending changes first.'],
  disable: ['Stops the mod so you can safely edit and save.', 'Your draft stays in the editor.'],
  apply: ['Validates and saves your pending moveset.', 'Disable the mod before saving.'],
  trial: ['Loads Sword Rebuild 1 into a draft.', 'Review it, then save to use it.'],
  starter: ['Loads a smaller Rebuild subset into a draft.', 'Review it, then save to use it.'],
  baseline: ['Loads Nioh’s original moveset into a draft.', 'Save to make this your active setup.'],
  load: ['Imports a moveset file into your draft.', 'Saving is a separate step.'],
  save: ['Exports the current moveset to a file.', 'Exporting does not enable the mod.'],
  reload: ['Discards local edits and reloads the saved moveset.', 'Changes from another editor appear after reloading.']
};
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-action]')) {
  const [body, tip] = actionHelp[button.dataset.action!]; annotate(button, button.textContent!, body, tip);
}
annotate(document.querySelector('#tools>summary')!, 'More', 'Open presets, import and export, recorded moves, and advanced inputs.', 'Your current draft stays in place when you switch pages.');

let audio: AudioContext | undefined;
function prepareAudio() {
  if (soundToggle.checked) { audio ||= new AudioContext(); void audio.resume(); }
}
document.addEventListener('pointerdown', prepareAudio, { once: true });
document.addEventListener('keydown', prepareAudio, { once: true });
function chime(kind: 'bound' | 'saved') {
  if (!soundToggle.checked) return;
  prepareAudio();
  const tones = kind === 'bound' ? [523, 784] : [440, 659];
  tones.forEach((frequency, index) => {
    const start = audio!.currentTime + index * .075;
    const tone = audio!.createOscillator(), gain = audio!.createGain();
    tone.type = 'sine'; tone.frequency.value = frequency;
    gain.gain.setValueAtTime(.0001, start);
    gain.gain.exponentialRampToValueAtTime(.008, start + .018);
    gain.gain.exponentialRampToValueAtTime(.0001, start + .15);
    tone.connect(gain).connect(audio!.destination); tone.start(start); tone.stop(start + .16);
  });
}
soundToggle.onchange = () => { localStorage.setItem('mwm.sound', soundToggle.checked ? 'on' : 'off'); prepareAudio(); };
hapticToggle.onchange = () => { localStorage.setItem('mwm.haptic', hapticToggle.checked ? 'on' : 'off'); };
document.addEventListener('mwm:bound', event => {
  chime('bound');
  if (hapticToggle.checked) void window.mwm.request('haptic', { slot: (event as CustomEvent<{ slot: number | null }>).detail.slot }).catch(() => {});
});

function errorText(error: unknown): string {
  // Read worker failures without exposing Electron's transport implementation.
  // Browser-local exceptions keep their useful message.
  // Names and paths remain plain text even when supplied by a failed import.
  return error && typeof error === 'object' && 'message' in error ? String(error.message) : String(error).replace(/^Error: /, '');
}

function explainError(error: unknown) {
  // Keep rejected drafts editable behind an accessible explanation.
  // Operation and IO failures remain distinct from incompatible bindings.
  // Dismissing the native dialog restores focus, including when using Escape.
  const incompatible = Boolean(error && typeof error === 'object' && 'kind' in error && error.kind === 'validation');
  document.querySelector('#error-title')!.textContent = incompatible ? 'Incompatible bind' : 'Could not complete action';
  document.querySelector('#error-reason')!.textContent = (incompatible ? 'This bind is incompatible because: ' : '') + errorText(error);
  document.querySelector('#error-guidance')!.textContent = incompatible ? 'Choose another move or clear the conflicting assignment. Your edits remain in the editor.' : 'Your edits remain in the editor. Resolve the reported problem, then try again.';
  if (!errorDialog.open) errorDialog.showModal();
}

function refreshActions() {
  // Allow saving valid drafts only while gameplay is stopped.
  // Export does not change the running configuration and remains available.
  // Status polling updates controls without revalidating or showing another popup.
  const label = document.querySelector<HTMLElement>('#validation')!, valid = label.dataset.state === 'valid';
  for (const button of document.querySelectorAll<HTMLButtonElement>('#apply, #save, #enable, [data-binding-export]')) button.disabled = !valid || (button.id === 'apply' ? !dirty || state.running : button.id === 'enable' && dirty);
  document.querySelector<HTMLButtonElement>('#apply')!.title = state.running ? 'Disable the mod before saving changes.' : '';
  document.querySelector<HTMLButtonElement>('#enable')!.title = dirty ? 'Save changes before enabling' : '';
  if (valid) label.textContent = dirty ? state.running ? 'Disable the mod before saving changes. Your edits remain in the editor.' : 'Unsaved changes · ready to save' : 'Saved moveset';
}

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
  ++editGeneration;
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
  const routeDiagnostic = document.querySelector<HTMLElement>('#route-diagnostic');
  if (routeDiagnostic) routeDiagnostic.textContent = 'Checking route conflicts…';
  for (const button of document.querySelectorAll<HTMLButtonElement>('#apply, #save, #enable, [data-binding-export]')) button.disabled = true;
  document.querySelector('#profile-name')!.textContent = state.preset.name + (dirty ? ' · unsaved' : '');
  draftTimer = setTimeout(async () => {
    // Capture browser-invalid number fields before blank/NaN values reach JSON serialization.
    // Worker compilation remains authoritative for cross-field and import-graph restrictions.
    // Errors stay separate from messages about binding, loading and saving.
    try {
      const invalid = content.querySelector<HTMLInputElement>('input:invalid');
      if (invalid) throw { kind: 'validation', message: `${invalid.closest('label')?.querySelector('span')?.textContent || 'Value'}: ${invalid.validationMessage}` };
      if (state.preset.skill_bindings.some(binding => !binding.stance)) throw { kind: 'validation', message: 'Choose a stance for the new input route.' };
      const result = await window.mwm.request<Preview>('preview', params());
      if (generation !== draftGeneration) return;
      preview = result; label.dataset.state = 'valid'; label.classList.remove('error'); refreshActions();
      if (routeDiagnostic?.isConnected) { routeDiagnostic.textContent = 'Routes compatible · ready to save'; routeDiagnostic.classList.remove('error'); }
    } catch (error) {
      if (generation !== draftGeneration) return;
      preview = null; label.dataset.state = 'invalid'; label.textContent = errorText(error); label.classList.add('error');
      if (routeDiagnostic?.isConnected) { routeDiagnostic.textContent = errorText(error); routeDiagnostic.classList.add('error'); }
      if (editGeneration > explainedEdit && !state.preset.skill_bindings.some(binding => !binding.stance)) { explainedEdit = editGeneration; explainError(error); }
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
  ++actionGeneration; busy = true; document.body.inert = true;
  try { await operation(); } catch (error) {
    message(errorText(error), true); explainError(error);
    if (error && typeof error === 'object' && 'kind' in error && error.kind === 'validation') {
      explainedEdit = editGeneration;
      schedulePreview();
    }
  }
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
  const help = fieldHelp[label] || (parent.classList.contains('speed-row')
    ? ['Sets this move’s playback speed.', 'Blank inherits; 1 uses native speed.']
    : ['Choose the reviewed action for this input.', 'The change remains in your draft until saved.']);
  annotate(wrapper, label, help[0], help[1]);
  return wrapper;
}

function select(options: [string, string][], value: string | null, update: (value: string) => void, markChanged = true) {
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
    update(control.value); if (markChanged) changed();
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
  for (const move of state.capabilities.moves) if (move[role]) choices.push([move.id, move.name]);
  return choices;
}

function playable(id: string | null) { return state.capabilities.moves.find(move => move.id === id); }
const sourceInputs: Record<string, string> = {
  light_attack: 'Quick attack · Square / X', heavy_attack: 'Strong attack · Triangle / Y',
  dodge_attack: 'Dodge → attack', guard_light: 'Hold Guard + Quick attack',
  high_heavy_followup: 'High Strong attack → Hold Guard + Quick attack',
  tiger_sprint: 'Equipped Tiger Sprint → sheathe / Iai preparation'
};
function sourceInput(source: string) {
  return sourceInputs[source] || state.capabilities.native_sources.find(item => item.id === source)?.label || source;
}
function buttonName(mask: number) {
  return Object.entries(state.buttons).find(([, value]) => value === mask)?.[0] || 'Unmapped button';
}
function routeMaskAllowed(key: ButtonKey, mask: number) {
  return (key === 'modifier_mask' ? ['L1 / LB'] : routeTriggers).some(name => state.buttons[name] === mask);
}
function routeInput(binding: Binding) {
  const input = binding.input;
  return input ? `Hold ${buttonName(input.modifier_mask)} · ${input.gesture} ${buttonName(input.trigger_mask)}` : sourceInput(binding.source);
}
function moveHelp(id: string | null, context: string): [string, string] {
  const move = playable(id);
  return move ? [`${context}. ${move.description || 'Reviewed move; see its source notes in Move library.'}`,
    `${move.input ? `Expected input: ${move.input}. ` : ''}The replacement is pending until saved.`]
    : [context, 'Original keeps Nioh’s game-selected action.'];
}
function openMovePicker(role: MoveRole, target: HTMLSelectElement, title: string) {
  document.querySelector('#picker-title')!.textContent = title;
  pickerSearch.value = ''; pickerResults.replaceChildren();
  const choices = moveOptions(role, 'Original').filter(([id]) => id || [...target.options].some(option => option.value === ''));
  const rows: { node: HTMLElement; search: string }[] = [];
  for (const [id, label] of choices) {
    const move = playable(id), button = element('button', undefined, 'picker-choice'); button.type = 'button';
    button.append(element('strong', label));
    if (move) button.append(element('span', move.input || 'Input follows the selected route', 'picker-input'),
      element('small', move.description || 'Reviewed action; additional source notes are available in Move library.'));
    else button.append(element('small', 'Keep Nioh’s original action on this input.'));
    button.onclick = () => { picker.close(); target.value = id; target.dispatchEvent(new Event('change', { bubbles: true })); target.focus(); };
    if (target.value === id) button.classList.add('current');
    pickerResults.append(button);
    rows.push({ node: button, search: `${label} ${move?.input || ''} ${move?.description || ''}`.toLowerCase() });
  }
  pickerSearch.oninput = () => {
    const query = pickerSearch.value.trim().toLowerCase();
    for (const row of rows) row.node.hidden = !row.search.includes(query);
  };
  picker.showModal(); pickerSearch.focus();
}
document.querySelector<HTMLButtonElement>('#picker-close')!.onclick = () => picker.close();
function browseMove(wrapper: HTMLElement, control: HTMLSelectElement, role: MoveRole, title: string) {
  const button = element('button', 'Browse', 'browse-move'); button.type = 'button';
  button.setAttribute('aria-label', `Browse reviewed moves for ${title}`);
  button.onclick = () => openMovePicker(role, control, title);
  wrapper.append(button);
}

function section(title: string, hint: string) {
  // Give each tab a clear purpose and a short explanation of its limits.
  // Keep the actual controls in a shared responsive grid below the introduction.
  // Returning that grid avoids multiple competing spacing conventions.
  content.append(element('h2', title, 'section-title'), element('p', hint, 'hint'));
  const grid = element('div', undefined, 'fields'); content.append(grid); return grid;
}

function assignment(parent: HTMLElement, label: string, key: string, role: MoveRole, value: string | null, update: (value: string) => void, expected = label) {
  // Each overview row edits the same preset field as the detailed controls.
  // Native/disabled choices clear only their own assignment.
  // Worker preview still validates interactions across every row and page.
  const control = select(moveOptions(role, 'Original action'), value, update);
  control.dataset.assignment = key;
  control.setAttribute('aria-label', label);
  const wrapper = field(label, control, parent); wrapper.className = 'assignment';
  wrapper.insertBefore(element('span', expected, 'route-notation'), control);
  const updateHelp = () => { const [body, tip] = moveHelp(control.value, `Game input: ${expected}`); annotate(wrapper, label, body, tip); };
  updateHelp(); control.addEventListener('change', () => { updateHelp(); explainTarget(control); });
  browseMove(wrapper, control, role, label);
}

function renderOverview() {
  // Group actual assignments by stance, keeping shared inputs separate.
  // Display existing native rows directly rather than reconstructing a second preset model.
  // Editing a choice remains a draft until the single Save changes action succeeds.
  const p = state.preset;
  const heading = element('div', undefined, 'overview-heading');
  const custom = p.skill_bindings.filter(binding => binding.input).length;
  heading.append(element('h2', 'Sword skill map'), element('p', `${p.skill_bindings.length - custom} original input routes · ${custom} custom button routes`));
  content.append(heading);
  const cards = element('div', undefined, 'stance-grid'); content.append(cards);
  const labels: Record<string, string> = { light_attack: 'Quick attack', heavy_attack: 'Heavy attack',
    dodge_attack: 'Dodge + heavy', guard_light: 'Guard + quick attack', high_heavy_followup: 'After heavy · guard + quick' };
  const nativeRow = (parent: HTMLElement, binding: Binding) => {
    // Keep custom source names readable while preserving Engine's exact route identity.
    // Removing an assignment restores that source through the ordinary validator.
    // A structural removal rebuilds the overview without touching unrelated routes.
    const label = labels[binding.source] || state.capabilities.native_sources.find(source => source.id === binding.source)?.label || binding.source;
    const key = binding.input ? `custom:${p.skill_bindings.indexOf(binding)}` : `native:${binding.stance}:${binding.source}`;
    assignment(parent, binding.input ? 'Custom chord' : label, key, binding.input ? 'chord' : 'native', binding.move, value => {
      if (value) binding.move = value;
      else { p.skill_bindings.splice(p.skill_bindings.indexOf(binding), 1); render(); }
    }, routeInput(binding));
  };
  for (const stance of state.capabilities.stances) {
    const card = element('section', undefined, 'stance-card'); card.dataset.stance = stance;
    annotate(card, `${stance[0].toUpperCase() + stance.slice(1)} stance`, 'These inputs apply while Nioh is in this stance.', 'Choose No replacement to keep the original action.');
    card.append(element('h3', `${stance[0].toUpperCase() + stance.slice(1)} stance`)); cards.append(card);
    if (stance === 'low') assignment(card, 'Heavy attack string', 'low-heavy', 'heavy_string', p.low_heavy, value => { p.low_heavy = value || null; }, 'Low · Strong attack → follow-up strikes');
    for (const binding of p.skill_bindings.filter(row => row.stance === stance)) nativeRow(card, binding);
    assignment(card, 'Hold Triangle / Y', `hold:${stance}`, 'held', p.stance_holds[stance], value => { p.stance_holds[stance] = value || null; }, 'Hold Strong attack · Triangle / Y');
    assignment(card, 'Frost Moon · stance switch', `frost:${stance}`, 'chord', p.frost_moon[stance], value => { p.frost_moon[stance] = value || null; }, `Ki Pulse window · RB/R1 + ${stance} stance twice`);
  }
  const shared = element('section', undefined, 'shared-routes');
  annotate(shared, 'Global custom chord', 'The original two-button chord can play one move on tap and another on hold.', 'Open Controller to record or change its buttons.');
  const description = element('div');
  description.append(element('h3', `${buttonName(p.modifier_mask)} + ${buttonName(p.trigger_mask)}`), element('p', p.chord_stance === 'any' ? 'Global chord · all stances' : `Global chord · ${p.chord_stance} stance`));
  const setup = element('button', 'Edit buttons →', 'inline-button'); setup.onclick = () => navigate('controls'); description.append(setup); shared.append(description);
  assignment(shared, 'Tap / release', 'chord:tap', 'chord', p.tap_move, value => { p.tap_move = value || null; }, `${buttonName(p.modifier_mask)} + tap ${buttonName(p.trigger_mask)}`);
  assignment(shared, `Hold · ${p.hold_seconds}s`, 'chord:hold', 'chord', p.hold_move, value => { p.hold_move = value || null; }, `${buttonName(p.modifier_mask)} + hold ${buttonName(p.trigger_mask)}`);
  const globalBindings = p.skill_bindings.filter(row => row.stance === 'any');
  shared.classList.toggle('has-global-bindings', globalBindings.length > 0);
  for (const binding of globalBindings) nativeRow(shared, binding);
  content.append(shared);
  const extras = [p.okatsu_grapple && 'Okatsu grapple', p.mid_light_ender && 'mid quick finisher', p.string_enabled && 'Okatsu trigger string'].filter(Boolean);
  const extra = element('details', undefined, 'overview-extra'); extra.append(element('summary', extras.length ? 'Special routes · ' + extras.join(', ') : 'Special routes · optional'));
  const fields = element('div', undefined, 'fields'); extra.append(fields);
  for (const [key, label] of [['okatsu_grapple', 'Okatsu grapple'], ['mid_light_ender', 'Mid quick-attack finisher'], ['string_enabled', 'Okatsu dual-trigger string']] as const) {
    const check = element('input'); check.type = 'checkbox'; check.checked = p[key];
    check.onchange = () => { p[key] = check.checked; extra.querySelector('summary')!.textContent = 'Special routes · optional'; changed(); };
    const control = field(label, check, fields); control.classList.add('toggle'); control.append(element('p', fieldHelp[label][0], 'control-note'));
  }
  const more = element('button', 'Edit other inputs →', 'inline-button'); more.onclick = () => navigate('native'); fields.append(more);
  content.append(extra);
}

function renderMoves() {
  // Present the existing sword preset's custom chord and native hold choices.
  // Each move menu uses its own capability flag rather than a universal catalogue list.
  // Weapon selection stays sword-only until Engine implements reviewed weapon routing.
  const p = state.preset, grid = section('Global custom chord', 'Hold Modifier, then press Trigger. Choose separate moves for a tap and a hold. Input routes can use additional chords.');
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
    const move = select(moveOptions('chord', 'Disabled'), p[key], value => {
      // Store the chosen reviewed action by its stable identity.
      // Clearing the option disables this half of the chord.
      // Tap and hold remain independently configurable.
      p[key] = value || null;
    });
    const route = field(label, move, grid);
    const updateHelp = () => { const [body, tip] = moveHelp(move.value, `${label} of the Modifier + Trigger chord`); annotate(route, label, body, tip); };
    updateHelp(); move.addEventListener('change', () => { updateHelp(); explainTarget(move); });
    browseMove(route, move, 'chord', label);
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
  const p = state.preset, grid = section('Special sword routes', 'These switches affect specific native combo windows or imported strings. They do not replace every press of a base button.');
  const heavy = select(moveOptions('heavy_string'), p.low_heavy, value => {
    // Select a reviewed heavy-string graph rather than an arbitrary animation.
    // Native clears only this particular replacement.
    // Continuation and recovery still belong to Engine.
    p.low_heavy = value || null;
  });
  const heavyField = field('Low heavy string', heavy, grid);
  browseMove(heavyField, heavy, 'heavy_string', 'Low heavy string');
  for (const stance of state.capabilities.stances) {
    const held = select(moveOptions('graph'), p.stance_holds[stance], value => {
      // Bind a reviewed graph to this stance's held-heavy slot.
      // Shared source actions retain their Engine-authored graph transitions.
      // A blank value restores the native held-heavy behavior.
      p.stance_holds[stance] = value || null;
    });
    const heldField = field(stance.toUpperCase() + ' · hold Triangle / Y', held, grid);
    annotate(heldField, `${stance.toUpperCase()} held strong`, `Hold Triangle / Y in ${stance} stance to start the selected reviewed sequence.`, 'The Izuna Drop continuation requires a successful launcher and contact.');
    browseMove(heldField, held, 'graph', `${stance} held strong`);
  }
  for (const [key, label] of [['okatsu_grapple', 'Okatsu grapple'], ['mid_light_ender', 'Mid quick-attack finisher'], ['string_enabled', 'Okatsu dual-trigger string']] as const) {
    const check = element('input'); check.type = 'checkbox'; check.checked = p[key];
    check.onchange = () => {
      // Toggle one established sword adaptation without exposing its internal timing.
      // Engine validates this together with all related binding choices.
      // The running moveset does not change until Apply.
      p[key] = check.checked; changed();
    };
    const control = field(label, check, grid); control.classList.add('toggle');
    control.append(element('p', fieldHelp[label]?.[0] || 'Uses this reviewed move in its specific native input window.', 'control-note'));
  }
}

function renderNative() {
  // A route either replaces Nioh's source or starts from its own controller chord.
  // The same source can label several custom routes without consuming native slots.
  const p = state.preset;
  content.append(element('h2', 'Input overrides', 'section-title'),
    element('p', 'Choose how each reviewed move starts. Original Nioh input replaces a game action. Custom controller chord adds a new input without changing original actions. Per-route chords use L1/LB + B, Y, LT or X; hold uses the global chord threshold on Controller.', 'hint'));
  const toolbar = element('div', undefined, 'route-toolbar');
  const search = element('input'); search.type = 'search'; search.placeholder = 'Filter source, buttons, stance, or move'; search.setAttribute('aria-label', 'Filter input routes');
  search.oninput = () => { const query = search.value.trim().toLowerCase(); for (const row of content.querySelectorAll<HTMLElement>('.binding')) row.hidden = !row.dataset.search?.includes(query); };
  const slots = element('span', undefined, 'slot-count');
  const updateSlots = () => {
    const used = Object.values(state.preset.stance_holds).filter(Boolean).length
      + state.preset.skill_bindings.reduce((sum, binding) => sum + (binding.input ? 0 : binding.source === 'heavy_attack' && binding.stance === 'any' ? 3 : 1), 0);
    const custom = state.preset.skill_bindings.filter(binding => binding.input).length;
    slots.textContent = `${used} / ${state.capabilities.native_binding_limit || 32} original slots · ${custom} / ${state.capabilities.custom_binding_limit || 24} custom routes`;
  };
  updateSlots(); toolbar.append(search, slots); content.append(toolbar);
  const diagnostic = element('p', 'Checking route conflicts…', 'route-diagnostic'); diagnostic.id = 'route-diagnostic'; diagnostic.setAttribute('role', 'status'); content.append(diagnostic);
  const overlap = (a: string, b: string) => a === 'any' || b === 'any' || a === b;
  const suggestedInput = (stance: string): NonNullable<Binding['input']> => {
    const modifier_mask = state.buttons['L1 / LB'];
    const triggers = routeTriggers.map(name => state.buttons[name]).filter((mask): mask is number => mask !== undefined);
    const occupied = (modifier: number, trigger: number, gesture: 'tap' | 'hold') => {
      const conflict = (a: number, b: number, kind: string) => a === trigger && b === modifier || a === modifier && b === trigger && kind === gesture;
      return p.skill_bindings.some(row => row.input && overlap(stance, row.stance) && conflict(row.input.modifier_mask, row.input.trigger_mask, row.input.gesture))
        || overlap(stance, p.chord_stance) && Boolean(p.tap_move && conflict(p.modifier_mask, p.trigger_mask, 'tap') || p.hold_move && conflict(p.modifier_mask, p.trigger_mask, 'hold'));
    };
    for (const gesture of ['tap', 'hold'] as const) for (const trigger_mask of triggers)
      if (!occupied(modifier_mask, trigger_mask, gesture)) return { modifier_mask, trigger_mask, gesture };
    return { modifier_mask, trigger_mask: triggers[0], gesture: 'tap' };
  };
  for (const [index, binding] of state.preset.skill_bindings.entries()) {
    const row = element('div', undefined, 'binding');
    row.classList.toggle('custom-route', Boolean(binding.input));
    row.dataset.search = `${routeInput(binding)} ${binding.stance} ${playable(binding.move)?.name || binding.move}`.toLowerCase();
    annotate(row, 'Input route', binding.input ? 'This custom chord plays a reviewed move without replacing a Nioh input.' : 'This route replaces the named Nioh input with a reviewed move.', 'Remove the row to clear this route.');
    const head = element('div', undefined, 'binding-head');
    head.append(element('span', `ROUTE ${String(index + 1).padStart(2, '0')}`, 'route-number'),
      element('span', routeInput(binding), 'route-notation'),
      element('span', binding.stance.toUpperCase(), 'stance-tag'));
    row.append(head);
    if (!binding.input) {
      const sources: [string, string][] = state.capabilities.native_sources.map(source => [source.id, source.label]);
      field('Source', select(sources, binding.source, value => {
        binding.source = value;
        const stances = state.capabilities.native_sources.find(source => source.id === value)?.stances;
        if (stances && !stances.includes(binding.stance)) binding.stance = stances.length === 1 ? stances[0] : '';
        render();
      }), row);
    }
    const allowed = binding.input ? ['any', 'low', 'mid', 'high'] : state.capabilities.native_sources.find(source => source.id === binding.source)?.stances || ['any', 'low', 'mid', 'high'];
    const stanceChoices: [string, string][] = allowed.map(stance => [stance, stance.toUpperCase()]);
    if (!binding.stance) stanceChoices.unshift(['', 'Choose stance…']);
    field('Stance', select(stanceChoices, binding.stance, value => {
      // Any is valid only where the selected action permits it.
      // Graphs requiring a concrete stance are rejected by Engine.
      // No automatic conflict resolution silently removes another row.
      binding.stance = value; updateSlots();
    }), row);
    field('Activation', select([['original', 'Original Nioh input'], ['custom', 'Custom controller chord']], binding.input ? 'custom' : 'original', value => {
      if (value === 'custom' && !binding.input) binding.input = suggestedInput(binding.stance);
      if (value === 'original') delete binding.input;
      const choices = moveOptions(binding.input ? 'chord' : 'native').slice(1);
      if (!choices.some(([id]) => id === binding.move)) binding.move = choices[0][0];
      void action(async () => { await cancelCapture(); render(); });
    }), row);
    const role = binding.input ? 'chord' : 'native';
    const replacement = select(moveOptions(role).slice(1), binding.move, value => {
      // Expose only actions reviewed for native-source replacement.
      // This stores an ID, never a raw game address.
      // Apply still checks source-specific restrictions.
      binding.move = value;
    });
    const replacementField = field('Move', replacement, row);
    const updateHelp = () => { const [body, tip] = moveHelp(replacement.value, `Input: ${routeInput(binding)}`); annotate(replacementField, 'Move', body, tip); };
    updateHelp(); replacement.addEventListener('change', () => { updateHelp(); explainTarget(replacement); });
    browseMove(replacementField, replacement, role, `route ${index + 1}`);
    if (binding.input) {
      for (const [key, label] of [['modifier_mask', 'Modifier'], ['trigger_mask', 'Trigger']] as const) {
        const input = binding.input;
        buttonPicker(row, label, input[key], value => { input[key] = value; }, { kind: 'route', binding, key });
      }
      field('Gesture', select([['tap', 'Tap / release'], ['hold', `Hold · ${p.hold_seconds}s`]], binding.input.gesture, value => {
        binding.input!.gesture = value as 'tap' | 'hold';
      }), row);
      row.append(element('p', 'Original Nioh inputs stay unchanged. Hold L1/LB, then use the selected Trigger gesture.', 'control-note'));
      if (capture?.kind === 'route' && capture.binding === binding) captureStatus(row);
    }
    const remove = element('button', 'Remove'); remove.onclick = () => {
      void action(async () => {
        await cancelCapture(); state.preset.skill_bindings.splice(state.preset.skill_bindings.indexOf(binding), 1); changed(); render();
      });
    };
    row.append(remove); content.append(row);
  }
  for (const [mode, label] of [['original', '+ Add original route'], ['custom', '+ Add custom input']] as const) {
    const add = element('button', label, 'add-route'); add.onclick = () => {
      void action(async () => {
        await cancelCapture(); state.preset = await window.mwm.request<Preset>('add_override', { ...params(), mode });
        changed(); render();
      });
    };
    toolbar.append(add);
  }
}

function renderFrost() {
  // Let users choose only the destination action for each Frost Moon route.
  // Activation windows, startup speed, Ki Pulse and physics remain Engine-owned.
  // This separates configurable move selection from adaptation internals.
  const grid = section('Stance-switch moves', 'During a Ki Pulse window, hold R1 / RB and tap the destination stance button twice.');
  for (const stance of state.capabilities.stances) {
    const move = select(moveOptions('chord', 'Disabled'), state.preset.frost_moon[stance], value => {
    // Change this destination stance's reviewed move.
    // Clearing disables its replacement without changing other routes.
    // Actual route acceptance remains a separate gameplay check.
    state.preset.frost_moon[stance] = value || null;
    });
    const route = field(stance.toUpperCase(), move, grid);
    const updateHelp = () => { const [body, tip] = moveHelp(move.value, `During a Ki Pulse window, hold R1 / RB and tap ${stance} stance twice`); annotate(route, `${stance.toUpperCase()} Frost Moon`, body, tip); };
    updateHelp(); move.addEventListener('change', () => { updateHelp(); explainTarget(move); });
    browseMove(route, move, 'chord', `${stance} Frost Moon`);
  }
}

function renderSpeed() {
  // A blank field inherits its string speed; 1 explicitly restores this phase to native speed.
  // Engine previews resolve the final value, including paired/airborne restrictions.
  // Keep unused overrides editable while making the active move list the default view.
  const grid = section('Move tuning', 'Adjust the moves you use. Blank inherits speed; 1× restores native speed.');
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
    annotate(row, move.name, `${move.description || 'Reviewed move.'} Set its playback speed here.`, `${move.input ? `Input: ${move.input}. ` : ''}Blank inherits; enter 1 for native speed.`);
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
    const speedField = field(move.name, control, row);
    annotate(speedField, move.name, `${move.description || 'Reviewed move.'} Set its playback speed here.`, `${move.input ? `Input: ${move.input}. ` : ''}Blank inherits; enter 1 for native speed.`);
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
    const result = await window.mwm.request<{ mask?: number; label?: string; status?: string; calibration?: Calibration }>('capture_poll');
    if (!capture || generation !== captureGeneration) return;
    if (result.mask !== undefined) {
      if (result.calibration && JSON.stringify(result.calibration) !== JSON.stringify(state.calibration)) {
        const index = target.kind === 'route' ? state.preset.skill_bindings.indexOf(target.binding) : -1;
        if (target.kind === 'route' && index < 0) { await cancelCapture(); return; }
        const mapped = await window.mwm.request<Pick<Snapshot, 'calibration' | 'preset' | 'buttons'>>('controller',
          { ...params(), choice: 'detected', detected_calibration: result.calibration });
        if (!capture || generation !== captureGeneration) return;
        Object.assign(state, mapped);
        if (target.kind === 'route') target.binding = state.preset.skill_bindings[index];
        controllerChoice = state.calibration.device.backend === 'xinput' ? String(Number(state.calibration.device.slot) + 1) : 'ds4';
      }
      if (target.kind === 'route' && !routeMaskAllowed(target.key, result.mask)) {
        await cancelCapture(); render(); message('Per-route custom inputs use L1/LB as Modifier and B, Y, LT or X as Trigger.', true); return;
      }
      if (target.kind === 'global') state.preset[target.key] = result.mask;
      else if (state.preset.skill_bindings.includes(target.binding) && target.binding.input) target.binding.input[target.key] = result.mask;
      else { await cancelCapture(); return; }
      capture = null; changed(); render();
      message('Bound ' + result.label + '. Choose Save changes to use it.');
      window.dispatchEvent(new CustomEvent('mwm:bound', { detail: { slot: state.calibration.controller_slot ?? null } }));
    }
    else {
      const status = result.status || 'Waiting for input';
      message(status);
      document.querySelector('#capture-status')!.textContent = captureLabel(target) + status;
      timer = setTimeout(pollCapture, 70);
    }
  } catch (error) { if (generation === captureGeneration) { capture = null; render(); message(errorText(error), true); } }
}

async function cancelCapture() {
  // End an armed binding before switching tabs or controller mappings.
  // A late polling reply observes the cleared target and cannot overwrite the new form.
  // The worker closes the temporary OS controller listener.
  ++captureGeneration; capture = null; clearTimeout(timer); await window.mwm.request('capture_cancel');
}

function isCapturing(target: CaptureTarget) {
  if (!capture || capture.kind !== target.kind || capture.key !== target.key) return false;
  return capture.kind === 'global' || target.kind === 'route' && capture.binding === target.binding;
}
function captureLabel(target: CaptureTarget) {
  return target.kind === 'route' ? `Route ${state.preset.skill_bindings.indexOf(target.binding) + 1} ${target.key === 'modifier_mask' ? 'Modifier' : 'Trigger'} · ` : '';
}
function startCapture(target: CaptureTarget) {
  void action(async () => {
    await cancelCapture();
    const started = await window.mwm.request<{ status: string }>('capture_start', { calibration: state.calibration });
    capture = target; render(); document.querySelector('#capture-status')!.textContent = captureLabel(target) + started.status; void pollCapture();
  });
}
function captureStatus(parent: HTMLElement, always = false) {
  if (!capture && !always) return;
  const status = element('p', 'Listening for a button…', 'capture-status');
  status.id = 'capture-status'; status.setAttribute('role', 'status'); status.hidden = !capture; parent.append(status);
  if (capture) {
    const cancel = element('button', 'Cancel binding');
    cancel.onclick = () => { void action(async () => { await cancelCapture(); render(); message('Binding cancelled.'); }); };
    parent.append(cancel);
  }
}

function buttonPicker(parent: HTMLElement, label: string, mask: number, update: (mask: number) => void, target: CaptureTarget) {
  const buttons: [string, string][] = Object.entries(state.buttons)
    .filter(([name]) => target.kind === 'global' || (target.key === 'modifier_mask' ? name === 'L1 / LB' : routeTriggers.includes(name)))
    .map(([name, bit]) => [String(bit), name]);
  if (!buttons.some(([value]) => value === String(mask))) buttons.unshift([String(mask), `${buttonName(mask)} · choose a supported button`]);
  const wrapper = field(label, select(buttons, String(mask), value => { update(Number(value)); void action(cancelCapture); }), parent);
  if (target.kind === 'route') annotate(wrapper, label,
    target.key === 'modifier_mask' ? 'Per-route custom chords use L1/LB as Modifier.' : 'Per-route custom chords support B, Y, LT or X as Trigger.',
    'Press to bind records a supported button on the connected controller.');
  const bind = element('button', isCapturing(target) ? 'Listening…' : 'Press to bind');
  bind.setAttribute('aria-label', target.kind === 'route' ? `Record ${label.toLowerCase()} for route ${state.preset.skill_bindings.indexOf(target.binding) + 1}` : `Record global ${label.toLowerCase()}`);
  bind.onclick = () => startCapture(target); wrapper.append(bind);
}

function renderChordButtons(grid: HTMLElement) {
  // Keep the chord's actual buttons beside its tap/hold actions.
  // Binding captures target one pending field and never change runtime input directly.
  // Controller-specific labels come from the same calibration used by validation.
  for (const [key, label] of [['modifier_mask', 'Modifier'], ['trigger_mask', 'Trigger']] as const) {
    buttonPicker(grid, label, state.preset[key], value => { state.preset[key] = value; }, { kind: 'global', key });
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
  captureStatus(grid, true);
}

function renderControllerMap() {
  const diagram = element('section', undefined, 'controller-map');
  const heading = element('div', undefined, 'map-heading');
  heading.append(element('h2', 'Game input reference'), element('span', 'Default controller actions'));
  diagram.append(heading);
  const layout = element('div', undefined, 'pad-layout');
  const left = element('div', undefined, 'pad-legend');
  const center = element('div', undefined, 'pad-face');
  const right = element('div', undefined, 'pad-legend');
  for (const [key, label] of [['LT / L2', 'Aim'], ['LB / L1', 'Guard'], ['D-pad', 'Item shortcuts'], ['Left stick', 'Move']]) {
    const item = element('div', undefined, 'pad-key'); item.append(element('kbd', key), element('span', label)); left.append(item);
  }
  center.append(element('span', 'MWM', 'pad-mark'));
  for (const [key, label] of [['Y / △', 'Strong'], ['X / □', 'Quick'], ['B / ○', 'Interact'], ['A / ✕', 'Dodge']]) {
    const item = element('div', undefined, 'face-key'); item.append(element('kbd', key), element('span', label)); center.append(item);
  }
  for (const [key, label] of [['RT / R2', 'Shoot while aiming'], ['RB / R1', 'Stance / Ki Pulse'], ['Right stick', 'Camera'], ['Guard + Quick', 'Native skill input']]) {
    const item = element('div', undefined, 'pad-key'); item.append(element('kbd', key), element('span', label)); right.append(item);
  }
  layout.append(left, center, right); diagram.append(layout);
  diagram.append(element('p', 'MWM adds custom chords and selected sword routes. Nioh keeps its other controller inputs.', 'hint'));
  content.append(diagram);
}

function renderControls() {
  // Present calibrated button meanings and supported OS controller backends.
  // Remapping goes through Engine so changing hardware preserves logical button choices.
  // Physical controller acceptance is not inferred from successfully editing this form.
  const grid = section('Device & game', 'Choose the controller layout used for every custom chord. Press to bind on this page or Input routes detects a supported controller while Nioh is open or closed.');
  const devices = select([['saved', 'Saved mapping'], ['ds4', 'DS4 mapping'], ['1', 'XInput controller 1'], ['2', 'XInput controller 2'], ['3', 'XInput controller 3'], ['4', 'XInput controller 4']], controllerChoice, value => {
    // Cancel the previous controller listener before translating button masks.
    // Failed remapping preserves the current pending preset.
    // Successful selection remains unsaved until Apply.
    void action(async () => {
      // Ask Engine to preserve logical button meaning across mappings.
      // Replace calibration, buttons and preset as one UI state update.
      // No file writes occur in this translation request.
      await cancelCapture(); Object.assign(state, await window.mwm.request('controller', { ...params(), choice: value })); controllerChoice = value; changed(); render();
    }).finally(() => { devices.value = controllerChoice; });
  }, false);
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
  // Playable capability rows and recorded research use separate views. A recording
  // never becomes a bindable choice simply because it appears in the library.
  content.append(element('h2', 'Move library', 'section-title'));
  content.append(element('p', 'Reviewed playable moves are available in Sword and Input routes. Recorded candidates need William-specific adaptation and verification before binding.', 'hint'));
  const tabs = element('div', undefined, 'library-tabs');
  const playableTab = element('button', `Playable · ${state.capabilities.moves.length}`);
  const recordedTab = element('button', `Recorded candidates · ${collection.moves.length}`);
  tabs.append(playableTab, recordedTab); content.append(tabs);
  const search = element('input'); search.type = 'search'; search.placeholder = 'Search name, input, boss, or behavior'; search.setAttribute('aria-label', 'Search move library'); content.append(search);
  const playablePane = element('div', undefined, 'library-list');
  const recordedPane = element('div', undefined, 'library-list');
  const playableCards: { node: HTMLElement; text: string }[] = [];
  for (const move of state.capabilities.moves) {
    const card = element('article', undefined, 'library-move');
    card.append(element('h3', move.name), element('p', move.input || 'Input depends on the assigned route', 'library-input'),
      element('p', move.description || 'Reviewed for the supported route; see the source notes for details.', 'library-description'));
    annotate(card, move.name, move.description || 'Reviewed playable move.', move.input ? `Expected input: ${move.input}` : 'Input depends on the route you assign.');
    const kinds = [move.chord && 'Custom chord', move.held && 'Held strong', move.native && 'Input route', move.heavy_string && 'Heavy string'].filter(Boolean);
    card.append(element('small', kinds.join(' · ') || 'Tuning only', 'move-kinds'));
    playablePane.append(card); playableCards.push({ node: card, text: `${move.name} ${move.input || ''} ${move.description || ''}`.toLowerCase() });
  }
  recordedPane.append(element('h3', 'Sword Rebuild routes', 'section-title'));
  recordedPane.append(element('p', 'The curated subset contains Jin moves; Sword Rebuild 1 adds Oda, Tachibana, Hideyori, and a gun shot. Route status below shows what is adapted.', 'hint'));
  const labels: Record<string, string> = { handgun: 'LB + LT', low_heavy: 'Low · heavy', low_dodge_attack: 'Low · dodge + heavy',
    mid_heavy: 'Mid · heavy', mid_dodge_attack: 'Mid · dodge + heavy', low_quick: 'Low · quick', high_heavy_omnislice: 'High heavy → LB + Square',
    frost_high: 'High Frost Moon', frost_mid: 'Mid Frost Moon', frost_low: 'Low Frost Moon' };
  const actions: Record<string, string> = { handgun: 'bloodborne gun shot', low_dodge_attack: 'Jin · second heavy', mid_heavy: 'Jin · five-hit quick string B', mid_dodge_attack: 'Jin · five-hit quick string B',
    frost_mid: 'Oda · final two slashes', frost_low: 'Jin · Flying Swallow', high_heavy_omnislice: 'Tachibana · Omnislice attack immediately' };
  const routes = element('dl', undefined, 'route-list');
  for (const route of collection.design.routes) {
    const move = collection.moves.find(move => move.id === route.dataset_id);
    routes.append(element('dt', labels[route.id] || route.id));
    const value = element('dd', `${actions[route.id] || move?.name || route.dataset_id} · ${route.status.replaceAll('_', ' ')}`);
    if (route.blockers.length) value.append(element('p', route.blockers.join(' '), 'hint'));
    routes.append(value);
  }
  recordedPane.append(routes, element('h3', 'Source recordings', 'section-title'));
  const missing = collection.intake.sessions.filter(session => session.status !== 'curated_candidate').length;
  recordedPane.append(element('p', `${collection.moves.length} candidate strings · ${collection.intake.sessions.length} source sessions · ${missing} incomplete sessions. Names follow the source notes; action matching still needs review.`, 'hint'));
  const recordedCards: { node: HTMLElement; text: string }[] = [];
  for (const move of collection.moves) {
    const card = element('details', undefined, 'research-move');
    const weapon = collection.manifest.weapons[move.weapon_id].name, boss = collection.manifest.bosses[move.boss_id].name;
    const title = `${weapon} / ${boss} · ${move.name}`;
    card.append(element('summary', title));
    card.append(element('p', `${move.mapping_status === 'partial' ? 'Partial mapping' : 'Candidate mapping'} · Priority: ${move.priority || 'unset'}`, 'hint'));
    for (const evidence of move.evidence) card.append(element('p', evidence.annotation_text, 'recorded-note'));
    card.append(element('p', move.steps.map(step => `${step.source.action_id} (${step.source.motion_id})`).join(' → '), 'source-ids'));
    for (const note of move.review_notes) card.append(element('p', note, 'hint'));
    recordedCards.push({ node: card, text: [title, ...move.evidence.map(evidence => evidence.annotation_text)].join(' ').toLowerCase() });
    recordedPane.append(card);
  }
  const empty = element('p', 'No moves match this search.', 'hint'); empty.hidden = true; content.append(playablePane, recordedPane, empty);
  let view: 'playable' | 'recorded' = 'playable';
  const filter = () => {
    const query = search.value.trim().toLowerCase();
    const cards = view === 'playable' ? playableCards : recordedCards;
    for (const card of cards) card.node.hidden = !card.text.includes(query);
    empty.hidden = cards.some(card => !card.node.hidden);
  };
  const show = (next: 'playable' | 'recorded') => {
    view = next; playablePane.hidden = view !== 'playable'; recordedPane.hidden = view !== 'recorded';
    playableTab.classList.toggle('selected', view === 'playable'); recordedTab.classList.toggle('selected', view === 'recorded');
    filter();
  };
  playableTab.onclick = () => show('playable'); recordedTab.onclick = () => show('recorded'); search.oninput = filter;
  show('playable');
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
        message(operation === 'binding_import' ? 'Binding group loaded. Other groups and tuning are unchanged. Choose Save changes to use it.' : 'Binding group exported.');
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
  explain(...pageHelp[tab]);
  for (const button of document.querySelectorAll<HTMLButtonElement>('nav button')) button.classList.toggle('selected', button.dataset.tab === tab);
  if (tab === 'overview') renderOverview();
  else if (tab === 'collection') renderCollection();
  else if (tab === 'controls') { renderControllerMap(); renderMoves(); renderControls(); renderBindingModules(); }
  else if (tab === 'native') { renderNative(); renderOverrides(); renderBindingModules(); }
  else if (tab === 'frost') { renderFrost(); renderBindingModules(); }
  else if (tab === 'speed') renderSpeed();
  else {
    const guide = element('article', undefined, 'guide');
    guide.append(element('h2', 'Edit, save, enable.'));
    for (const text of ['1. Choose moves in Sword. Input routes lets each override use its original Nioh input or separate custom buttons.', '2. Set a stance, then set Modifier, Trigger and Tap or Hold for each custom route. Controller keeps the global chord and device mapping.', '3. Disable the mod before Save changes; enable it after saving. Review the status above.']) guide.append(element('p', text));
    guide.append(element('h2', 'Sword Rebuild 1 defaults'));
    for (const text of ['Low Triangle / Y and dodge + heavy use Jin’s cyclone string. Mid Triangle / Y and dodge + heavy use Jin’s five strikes. Low Square / X uses Hideyori’s four-hit string.', 'Low LB + LT tap uses bloodborne gun shot. High heavy → LB + Square / X uses Tachibana’s Omnislice.', 'During a Ki Pulse window, hold R1 / RB and tap the destination stance button twice. Low uses Flying Swallow, Mid uses Oda’s final two slashes, High uses the downward slash.', 'Choose Hold Triangle / Y separately in each stance. Launcher only and Launcher + Izuna Drop must use different stances; the drop requires contact.', 'Use Reuse a binding group under Controller or More → Other inputs & options to export or load one group. Other groups and speed settings stay unchanged.']) guide.append(element('p', text));
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
  if (name === 'apply') { state = await window.mwm.request<Snapshot>('apply', params()); dirty = false; render(); showRuntime(state); message(''); chime('saved'); return; }
  if (name === 'enable') { if (dirty) throw new Error('Save changes before enabling the mod.'); await window.mwm.request('enable', params()); showRuntime(await window.mwm.request<Snapshot>('snapshot')); message(''); return; }
  if (name === 'disable') { await window.mwm.request('disable'); showRuntime(await window.mwm.request<Snapshot>('snapshot')); message(''); }
}

function navigate(name: string) {
  // Navigation retains the pending model while cancelling any physical binding listener.
  // Closing More keeps its secondary commands out of the workspace.
  // A page change never saves or starts gameplay.
  void action(async () => { await cancelCapture(); tab = name; document.querySelector<HTMLDetailsElement>('#tools')!.open = false; render(); content.scrollTop = 0; });
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
  refreshActions();
}

async function pollStatus() {
  // Adopt external saved changes only while the editor is still clean and idle.
  // Recheck after awaiting the worker so an in-flight read cannot overwrite a new draft.
  // Unchanged snapshots update runtime status without rebuilding controls or moving focus.
  if (state && !busy && !capture) {
    const generation = actionGeneration;
    try {
      const snapshot = await window.mwm.request<Snapshot>('snapshot');
      if (generation === actionGeneration && !busy) {
        if (!dirty && !capture && JSON.stringify(params(snapshot)) !== JSON.stringify(params())) {
          state = snapshot; controllerChoice = 'saved'; dirty = Boolean(snapshot.load_warning);
          render(); message(snapshot.load_warning || '', Boolean(snapshot.load_warning));
        }
        showRuntime(snapshot);
      }
    } catch (error) { if (generation === actionGeneration && !busy) { document.querySelector('#runtime')!.textContent = 'Worker unavailable'; document.querySelector('#runtime-detail')!.textContent = errorText(error); } }
  }
  setTimeout(pollStatus, 1800);
}

async function start() {
  // Load configuration before enabling any app commands.
  // Startup failure stays visible instead of presenting an empty ready form.
  // Status polling is read-only and does not attach to Nioh.
  document.body.inert = true;
  try { collection = await window.mwm.request<Collection>('collection'); await reload(); void pollStatus(); } catch (error) { message(errorText(error), true); }
  finally { document.body.inert = false; }
}
void start();
