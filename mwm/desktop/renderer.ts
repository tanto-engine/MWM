import { createControllerDiagram } from './controller_diagram';
// The form stores only pending choices; Engine validates the complete preset on Apply.
// Stable move IDs travel over IPC while readable names remain presentation data.
export {};
type Stance = 'low' | 'mid' | 'high';
type MoveRole = 'chord' | 'string_hold' | 'graph' | 'held' | 'heavy_string' | 'native' | 'speed' | 'string' | 'skill' | 'frost';
type Move = { id: string; name: string; input?: string; description?: string } & Record<MoveRole, boolean>;
type Calibration = { device: Record<string, unknown>; controller_slot?: number | null; [key: string]: unknown };
type ButtonKey = 'modifier_mask' | 'trigger_mask';
type RouteButtonKey = ButtonKey | 'followup_mask';
const routeTriggers = ['Circle / B', 'Triangle / Y', 'L2 / LT', 'Square / X'];
type BindingInput = { modifier_mask: number; trigger_mask: number; followup_mask?: number; gesture: 'tap' | 'hold' | 'sequence' | 'after_strong' | 'after_quick' };
type Binding = { source: string; stance: string; move: string; input?: BindingInput };
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
  capabilities: { moves: Move[]; native_sources: { id: string; label: string; input?: string; description?: string; stances?: string[]; role?: MoveRole }[]; chord_stances?: (Stance | 'any')[];
    stances: Stance[]; native_binding_limit?: number; custom_binding_limit?: number; custom_sequence?: { modifiers: string[]; buttons: string[]; window_seconds: number };
    attack_followup?: { gestures: string[]; window_seconds: number };
    speed: { min: number; max: number } };
};
type ResearchMove = { id: string; name: string; kind: string; weapon_id: string; boss_id: string; review_status: string; mapping_status?: string;
  priority: string | null; review_notes?: string[]; steps: { source: { action_id: string; motion_id: number } }[];
  evidence: { annotation_text: string }[] };
type Collection = { manifest: { weapons: Record<string, { name: string }>; bosses: Record<string, { name: string }> };
  moves: ResearchMove[]; intake: { sessions: { status: string }[] };
  unreviewed: { distinct_signatures: number; signatures: { boss_id: string; action_hex: string; motion_id: number; timing_id: number;
    observations: number; recording_id: string; recording_ids: string[]; journal_line: number; payload_prefix_sha256: string }[] };
  design: { routes: { id: string; dataset_id: string; status: string; blockers: string[] }[] } };
type PresetLibrary = { presets: { id: string; name: string; native_routes?: number; custom_routes?: number; speed_overrides?: number }[];
  selected_id: string | null; hotkey: { supported: boolean; label: string; reason?: string } };
declare global { interface Window { mwm: { request<T>(method: string, params?: unknown): Promise<T>;
  onPresetCycle?: (callback: (event: { result?: { presets: PresetLibrary; snapshot: Snapshot }; error?: string }) => void) => () => void } } }

let state: Snapshot;
let collection: Collection;
type CaptureTarget = { kind: 'global'; key: ButtonKey } | { kind: 'route'; binding: Binding; key: RouteButtonKey };
let tab = 'overview', dirty = false, busy = false, capture: CaptureTarget | null = null;
let controllerChoice = 'saved';
let bindingGroup = 'chord';
let activeStance: Stance = 'low';
let speedSelection = '';
let speedRefresh: (() => void) | null = null;
const editorLog: string[] = [];
let presetLibrary: PresetLibrary | null = null, presetSelection = '', presetLibraryRevision = 0;
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
  overview: ['Sword moves', 'Choose a stance. Each input row shows the move it will play; Original keeps the game action.', 'Hover a row for its exact input and move behavior. Save changes before enabling.'],
  speed: ['Speed modification', 'Select a move on the left, then adjust its playback percentage.', 'Inherit follows its sequence. 100% explicitly uses native speed.'],
  presets: ['Preset manager', 'Save named movesets and switch the active one in the app.', 'On a supported DS4 mapping, double-tap the touchpad click to cycle during gameplay.'],
  controls: ['Controller', 'Set the device mapping and the buttons for the global custom chord.', 'Input overrides can use additional chords with separate buttons.'],
  native: ['Input overrides', 'Original routes replace a named Nioh action. Custom routes use their own controller buttons.', 'A configured chord takes priority over a game action on the same buttons. Sequential operators keep the modifier held through both presses.'],
  frost: ['Stance-switch moves', 'Choose the move used when Frost Moon reaches each stance.', 'Trigger during a Ki Pulse window with R1 / RB and two stance taps.'],
  collection: ['Move library', 'Playable moves can be assigned in Moves or Input overrides. Recorded candidates remain research until adapted and reviewed.', 'A video or action ID alone does not establish that William can play a move.'],
  guide: ['Help', 'Choose moves, save the draft, then enable the mod.', 'Disable the mod before saving further changes.']
};
const builtInPresets: Record<string, string> = {
  baseline: 'Sword baseline', starter: 'Rebuild subset', trial: 'Sword Rebuild 1', maria: 'Maria sword', maria_dash: 'Maria dodge string', ishida: 'Ishida sword'
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
  'Hold modifier': ['Hold this controller button while pressing the trigger or first button.', 'A follow-up, when chosen, must use a different button.'],
  'Input pattern': ['Choose a two-button tap or hold, or add a separate follow-up press.', 'A follow-up needs the first press to be observed before it.'],
  'Trigger / first press': ['Press this button while holding the modifier.', 'With a follow-up pattern, keep it held or release it before pressing the follow-up.'],
  'First press': ['Press this button while holding the modifier. Keep it held or release it before the follow-up.', 'The Engine must observe this press before the follow-up; simultaneous presses do not activate the route.'],
  'Then press': ['Press this follow-up while still holding the modifier.', 'Press within 0.6s while the first button is held, or within 0.6s after releasing it.'],
  Source: ['The game-selected sword input replaced by this original route.', 'A custom chord leaves this named source unchanged but takes priority if its buttons overlap another game action.'],
  Activation: ['Original Nioh input replaces the selected game action. Custom controller chord starts from the buttons in this row.', 'A configured chord takes priority over a game action on those same buttons.'],
  Gesture: ['Tap starts on a short Trigger press. Hold starts after the custom chord hold threshold.', 'A tap and hold can use the same buttons for separate routes.'],
  Stance: ['The stance in which this route applies.', 'Any works where the selected move and original source permit it.'],
  Move: ['The reviewed move played by this route.', 'Remove the row to clear the route.'],
  'Okatsu grapple': ['When a sword grapple succeeds and its native contact condition is met, use the imported Okatsu grapple sequence.', 'This does not turn normal attacks into grapples.'],
  'Mid quick-attack finisher': ['While a native Mid quick-attack string is active, hold Guard (LB/L1) and press Strong attack (Y/Triangle) in its combo window for William’s native finisher.', 'It adds a finisher to three Mid quick strings; it does not replace every quick press.'],
  'Include Okatsu kicking string': ['Enable Okatsu’s quick/kick sequence, then assign it to a Hold custom input or the shared Hold chord in Moves.', 'Keep the chord held through the flip and grab attempt. Tap and native attack inputs do not support this sequence.'],
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
  maria: ['Loads Maria’s quick, horizontal slash, aerial kick and forward dodge slash bindings.', 'Review the inputs, then save to use them.'],
  ishida: ['Loads five recorded Ishida sword strings across Quick and Strong inputs.', 'One fresh press advances each phase. Gameplay verification is pending.'],
  maria_dash: ['Loads Maria’s dodge slash string in place of her Mid quick string.', 'The two strings share continuation phases; choose one per moveset.'],
  baseline: ['Loads the baseline sword configuration into a draft.', 'Save to make this your active setup.'],
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
window.addEventListener('mwm:bound', event => {
  chime('bound');
  if (hapticToggle.checked) void window.mwm.request('haptic', { slot: (event as CustomEvent<{ slot: number | null }>).detail.slot }).catch(() => {});
});

function errorText(error: unknown): string {
  return error && typeof error === 'object' && 'message' in error ? String(error.message) : String(error).replace(/^Error: /, '');
}

function explainError(error: unknown) {
  const incompatible = Boolean(error && typeof error === 'object' && 'kind' in error && error.kind === 'validation');
  document.querySelector('#error-title')!.textContent = incompatible ? 'Incompatible bind' : 'Could not complete action';
  document.querySelector('#error-reason')!.textContent = (incompatible ? 'This bind is incompatible because: ' : '') + errorText(error);
  document.querySelector('#error-guidance')!.textContent = incompatible ? 'Choose another move or clear the conflicting assignment. Your edits remain in the editor.' : 'Your edits remain in the editor. Resolve the reported problem, then try again.';
  if (!errorDialog.open) errorDialog.showModal();
}

function refreshActions() {
  // Export may run during gameplay; saving graph changes must wait until the mod stops.
  const label = document.querySelector<HTMLElement>('#validation')!, valid = label.dataset.state === 'valid';
  for (const button of document.querySelectorAll<HTMLButtonElement>('#apply, #save, #enable, [data-binding-export]')) button.disabled = !valid || (button.id === 'apply' ? !dirty || state.running : button.id === 'enable' && dirty);
  document.querySelector<HTMLButtonElement>('#apply')!.title = state.running ? 'Disable the mod before saving changes.' : '';
  document.querySelector<HTMLButtonElement>('#enable')!.title = dirty ? 'Save changes before enabling' : '';
  if (valid) label.textContent = dirty ? state.running ? 'Disable the mod before saving changes. Your edits remain in the editor.' : 'Unsaved changes · ready to save' : 'Saved moveset';
}

function message(text: string, error = false) {
  clearTimeout(noticeTimer);
  if (text && !error) noticeTimer = setTimeout(() => { notice.textContent = ''; }, 5000);
  notice.textContent = text; notice.classList.toggle('error', error);
}

function logEdit(text: string) {
  if (editorLog[0] !== text) editorLog.unshift(text);
  editorLog.length = Math.min(editorLog.length, 4);
  const list = document.querySelector<HTMLElement>('#editor-log');
  if (list) list.replaceChildren(...editorLog.map(item => element('li', item)));
}

function changed() {
  dirty = true;
  ++editGeneration;
  message('');
  schedulePreview();
}

function schedulePreview() {
  // Only the latest draft may unlock Save; discard delayed previews from older edits.
  const generation = ++draftGeneration;
  clearTimeout(draftTimer);
  const label = document.querySelector<HTMLElement>('#validation')!;
  label.textContent = 'Checking changes…'; label.dataset.state = 'checking'; label.classList.remove('error');
  const routeDiagnostic = document.querySelector<HTMLElement>('#route-diagnostic');
  if (routeDiagnostic) routeDiagnostic.textContent = 'Checking route conflicts…';
  for (const button of document.querySelectorAll<HTMLButtonElement>('#apply, #save, #enable, [data-binding-export]')) button.disabled = true;
  document.querySelector('#profile-name')!.textContent = state.preset.name + (dirty ? ' · unsaved' : '');
  draftTimer = setTimeout(async () => {
    // Reject browser-invalid numbers before JSON can turn NaN into null.
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
    speedRefresh?.();
  }, 180);
}

function params(value = state) {
  // The loaded runtime identity lets the worker reject writes after another Engine takes ownership.
  return { runtime: value.runtime, preset: value.preset, calibration: value.calibration, nioh_exe: value.nioh_exe };
}

async function action(operation: () => Promise<void>) {
  // Serialize mutations; overlapping requests must not replace each other's draft.
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
  // Catalogue strings remain text, including imported move names and errors.
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function field(label: string, input: HTMLElement, parent: HTMLElement) {
  const wrapper = element('label', undefined, 'field');
  wrapper.append(element('span', label), input); parent.append(wrapper);
  const help = fieldHelp[label] || ['Choose the reviewed action for this input.', 'The change remains in your draft until saved.'];
  annotate(wrapper, label, help[0], help[1]);
  return wrapper;
}

function select(options: [string, string][], value: string | null, update: (value: string) => void, markChanged = true) {
  const control = element('select');
  for (const [id, label] of options) control.add(new Option(label, id));
  control.value = value || '';
  control.onchange = () => {
    update(control.value); if (markChanged) changed();
  };
  return control;
}

function input(value: string | number, update: (value: string) => void, type = 'text') {
  // Keep numeric text editable; preview validates browser bounds and Engine restrictions.
  const control = element('input'); control.type = type; control.value = String(value);
  control.oninput = () => {
    update(control.value); changed();
  };
  return control;
}

function moveOptions(role: MoveRole, empty = 'Native', current: string | null = null): [string, string][] {
  // Only implemented capability roles are bindable; source recordings alone are not.
  const choices: [string, string][] = [['', empty]];
  for (const move of state.capabilities.moves) if (move[role] || role === 'string_hold' && move.chord) choices.push([move.id, move.name]);
  const saved = state.capabilities.moves.find(move => move.id === current);
  if (saved && !choices.some(([id]) => id === current)) choices.push([saved.id, saved.name + ' · saved assignment']);
  return choices;
}

function playable(id: string | null) { return state.capabilities.moves.find(move => move.id === id); }
function sourceInput(source: string) {
  const row = state.capabilities.native_sources.find(item => item.id === source);
  return row?.input || row?.label || source;
}
function buttonName(mask: number) {
  return Object.entries(state.buttons).find(([, value]) => value === mask)?.[0] || 'Unmapped button';
}
function routeMaskAllowed(binding: Binding, key: RouteButtonKey, mask: number, buttons = state.buttons) {
  const custom = !binding.input?.gesture.startsWith('after_') ? state.capabilities.custom_sequence : null;
  const names = custom ? key === 'modifier_mask' ? custom.modifiers : custom.buttons
    : key === 'modifier_mask' ? ['L1 / LB'] : routeTriggers;
  return names.some(name => buttons[name] === mask);
}
function routeInput(binding: Binding) {
  const input = binding.input;
  return input ? input.gesture === 'sequence'
    ? `Hold ${buttonName(input.modifier_mask)} + ${buttonName(input.trigger_mask)} → ${buttonName(input.followup_mask!)}`
    : input.gesture === 'after_strong' || input.gesture === 'after_quick'
    ? `After ${input.gesture === 'after_strong' ? 'Strong' : 'Quick'} · ${buttonName(input.modifier_mask)} + ${buttonName(input.trigger_mask)}`
    : `Hold ${buttonName(input.modifier_mask)} · ${input.gesture} ${buttonName(input.trigger_mask)}` : sourceInput(binding.source);
}
function moveHelp(id: string | null, context: string): [string, string] {
  const move = playable(id);
  return move ? [`${context}. ${move.description || 'Reviewed move; see its source notes in Move library.'}`,
    `${move.input ? `Expected input: ${move.input}. ` : ''}The replacement is pending until saved.`]
    : [context, 'Original keeps Nioh’s game-selected action.'];
}
function openMovePicker(target: HTMLSelectElement, title: string) {
  document.querySelector('#picker-title')!.textContent = title;
  pickerSearch.value = ''; pickerResults.replaceChildren();
  const rows: { node: HTMLElement; search: string }[] = [];
  // The picker must offer exactly the owning control's valid choices, including saved assignments.
  for (const { value: id, text: label } of target.options) {
    const move = playable(id), button = element('button', undefined, 'picker-choice'); button.type = 'button';
    button.append(element('strong', label));
    if (move) button.append(element('span', move.input || 'Input follows the selected route', 'picker-input'),
      element('small', move.description || 'Reviewed action; additional source notes are available in Move library.'));
    else button.append(element('small', 'Keep this input without a replacement.'));
    button.onclick = () => {
      picker.close();
      target.value = id; target.dispatchEvent(new Event('change', { bubbles: true })); target.focus();
    };
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
function browseMove(wrapper: HTMLElement, control: HTMLSelectElement, title: string) {
  const button = element('button', 'Browse', 'browse-move'); button.type = 'button';
  button.setAttribute('aria-label', `Browse reviewed moves for ${title}`);
  button.onclick = () => openMovePicker(control, title);
  wrapper.append(button);
}

function section(title: string, hint: string) {
  content.append(element('h2', title, 'section-title'), element('p', hint, 'hint'));
  const grid = element('div', undefined, 'fields'); content.append(grid); return grid;
}

function renderOverview() {
  const preset = state.preset;
  const custom = preset.skill_bindings.filter(binding => binding.input).length;
  const heading = element('div', undefined, 'overview-heading');
  heading.append(element('h2', 'Sword moves'), element('p', `${custom} custom input${custom === 1 ? '' : 's'} · changes stay in your draft`));
  content.append(heading, element('p', 'Choose a stance, then assign reviewed moves to the inputs you use. Original keeps Nioh’s action.', 'hint'));

  const map = element('section', undefined, 'skill-map');
  const stances = element('div', undefined, 'skill-stances');
  stances.setAttribute('role', 'tablist'); stances.setAttribute('aria-label', 'Sword stance');
  for (const stance of state.capabilities.stances) {
    const button = element('button', stance.toUpperCase(), 'skill-stance');
    button.type = 'button'; button.setAttribute('role', 'tab');
    button.classList.toggle('chosen', stance === activeStance);
    button.setAttribute('aria-selected', String(stance === activeStance));
    button.onclick = () => { activeStance = stance; render(); };
    stances.append(button);
  }
  map.append(stances);
  const columns = element('div', undefined, 'skill-columns');
  columns.append(element('span', 'INPUT'), element('span', 'REPLACEMENT'));
  map.append(columns);
  const rows = element('div', undefined, 'skill-rows'); map.append(rows);

  const addRow = (label: string, inputText: string, current: string | null, role: MoveRole, key: string,
    set: (value: string) => void, empty = 'Original action') => {
    const row = element('div', undefined, 'skill-row'); row.dataset.routeKey = key;
    const chip = element('div', undefined, 'skill-input');
    chip.append(element('strong', label), element('small', inputText));
    const choice = select(moveOptions(role, empty, current), current, value => {
      set(value);
      const [body, tip] = moveHelp(value, `Input: ${inputText}`);
      annotate(row, `${activeStance.toUpperCase()} · ${label}`, body, tip);
      explainTarget(choice);
    }, false);
    choice.dataset.assignment = key;
    choice.setAttribute('aria-label', `${activeStance} ${label} replacement`);
    const [body, tip] = moveHelp(current, `Input: ${inputText}`);
    annotate(row, `${activeStance.toUpperCase()} · ${label}`, body, tip);
    row.append(chip, choice); rows.append(row);
    return row;
  };

  if (activeStance === 'low') addRow('Strong string', 'Triangle / Y · Low', preset.low_heavy, 'heavy_string', 'low-heavy', value => {
    preset.low_heavy = value || null; changed();
  });
  const legacy = preset.skill_bindings.some(row => !row.input && row.source === 'high_heavy_followup');
  for (const source of state.capabilities.native_sources) {
    if (source.stances && !source.stances.includes(activeStance)) continue;
    if (source.id === 'high_heavy_followup' && !legacy || source.id === 'strong_followup' && activeStance === 'high' && legacy) continue;
    const binding = preset.skill_bindings.find(row => !row.input && row.source === source.id && (row.stance === activeStance || row.stance === 'any'));
    addRow(source.label, sourceInput(source.id) + (binding?.stance === 'any' ? ' · shared across stances' : ''), binding?.move || null, source.role || 'native',
      binding ? `native:${binding.stance}:${source.id}` : `empty:${activeStance}:${source.id}`, value => {
        if (binding) {
          if (binding.stance === 'any') void action(async () => {
            const candidate = structuredClone(state.preset);
            const index = candidate.skill_bindings.findIndex(row => !row.input && row.source === source.id && row.stance === 'any');
            candidate.skill_bindings.splice(index, 1);
            for (const stance of source.stances || state.capabilities.stances) {
              if (stance === 'any') continue;
              if (stance !== activeStance || value) candidate.skill_bindings.push({ ...binding, stance, move: stance === activeStance ? value : binding.move });
            }
            state.preset = (await window.mwm.request<Preview>('preview', { ...params(), preset: candidate })).preset;
            changed(); logEdit(`${source.label}: ${activeStance} split from shared route`); render();
          });
          else if (value) { binding.move = value; changed(); }
          else { preset.skill_bindings.splice(preset.skill_bindings.indexOf(binding), 1); changed(); render(); }
        } else if (value) void action(async () => {
          state.preset = await window.mwm.request<Preset>('add_override', { ...params(), source: source.id, stance: activeStance, move: value });
          changed(); logEdit(`${activeStance.toUpperCase()} ${source.label} assigned`); render();
        });
      });
  }
  addRow('Hold Strong', 'Hold Triangle / Y', preset.stance_holds[activeStance], 'held', `hold:${activeStance}`, value => {
    preset.stance_holds[activeStance] = value || null; changed();
  });
  addRow('Stance switch', 'Ki Pulse · R1 / RB + stance twice', preset.frost_moon[activeStance], 'frost', `frost:${activeStance}`, value => {
    preset.frost_moon[activeStance] = value || null; changed();
  }, 'Disabled');
  if (activeStance === 'mid') {
    const finisher = element('label', undefined, 'skill-toggle');
    const check = element('input'); check.type = 'checkbox'; check.checked = preset.mid_light_ender;
    check.onchange = () => { preset.mid_light_ender = check.checked; changed(); };
    finisher.append(element('span', 'Quick-string finisher'), element('small', 'During a native Mid quick string: hold Guard, then press Strong attack.'), check);
    annotate(finisher, 'Mid quick-string finisher', ...fieldHelp['Mid quick-attack finisher']);
    rows.append(finisher);
  }

  const customRows = preset.skill_bindings.filter(binding => binding.input && (binding.stance === activeStance || binding.stance === 'any'));
  if (customRows.length) rows.append(element('h3', 'Custom inputs', 'skill-subtitle'));
  for (const binding of customRows) {
    const key = `custom:${preset.skill_bindings.indexOf(binding)}`;
    const row = addRow('Custom input', routeInput(binding), binding.move, binding.input!.gesture === 'hold' ? 'string_hold' : 'chord', key, value => {
      if (value) { binding.move = value; changed(); }
      else { preset.skill_bindings.splice(preset.skill_bindings.indexOf(binding), 1); changed(); render(); }
    }, 'Remove input');
    const edit = element('button', 'Edit buttons', 'skill-edit'); edit.onclick = () => navigate('native', `[data-route-key="${key}"]`);
    row.append(edit);
  }
  const operator = element('details', undefined, 'custom-operator');
  operator.append(element('summary', '+ Add custom input'));
  const sequence = state.capabilities.custom_sequence;
  if (sequence) {
    operator.append(element('p', `Choose a two-button tap or hold. Add a follow-up only when you want a three-button sequence.`, 'hint'));
    const builder = element('div', undefined, 'operator-fields');
    const choices = (names: string[]): [string, string][] => names.filter(name => state.buttons[name] !== undefined).map(name => [name, name]);
    const pattern = select([['tap', 'Tap · two buttons'], ['hold', 'Hold · two buttons'], ['sequence', 'Follow-up · three buttons']], 'tap', value => {
      followupField.hidden = value !== 'sequence';
      // Hold-only sequences belong in both the builder and existing held-input menus.
      const previous = move.value;
      move.replaceChildren(...moveOptions(value === 'hold' ? 'string_hold' : 'chord', 'Choose a move').map(([id, name]) => new Option(name, id)));
      if ([...move.options].some(option => option.value === previous)) move.value = previous;
    }, false);
    const modifier = select(choices(sequence.modifiers), sequence.modifiers[0], () => {}, false);
    const first = select(choices(sequence.buttons), sequence.buttons.find(name => name !== modifier.value) || '', () => {}, false);
    const followup = select(choices(sequence.buttons), sequence.buttons.find(name => name !== modifier.value && name !== first.value) || '', () => {}, false);
    const move = select(moveOptions('chord', 'Choose a move'), '', () => {}, false);
    field('Input pattern', pattern, builder);
    field('Hold modifier', modifier, builder); field('Trigger / first press', first, builder);
    const followupField = field('Then press', followup, builder); followupField.hidden = true;
    browseMove(field('Move', move, builder), move, 'custom input');
    const add = element('button', 'Add operator', 'add-route');
    add.onclick = () => void action(async () => {
      if (!move.value) throw new Error('Choose a reviewed move for this operator.');
      const three = pattern.value === 'sequence';
      if (new Set(three ? [modifier.value, first.value, followup.value] : [modifier.value, first.value]).size !== (three ? 3 : 2))
        throw new Error(`Use ${three ? 'three' : 'two'} different controller buttons.`);
      const candidate = structuredClone(state.preset);
      candidate.skill_bindings.push({ source: 'tiger_sprint', stance: activeStance, move: move.value,
        input: { modifier_mask: state.buttons[modifier.value], trigger_mask: state.buttons[first.value],
          ...(three ? { followup_mask: state.buttons[followup.value] } : {}), gesture: three ? 'sequence' : pattern.value as 'tap' | 'hold' } });
      state.preset = (await window.mwm.request<Preview>('preview', { ...params(), preset: candidate })).preset;
      changed(); logEdit(`${activeStance.toUpperCase()} input added: ${modifier.value} + ${first.value}${three ? ` → ${followup.value}` : ''}`); render();
    });
    operator.append(builder, add);
  } else operator.append(element('p', 'This Engine does not expose sequential controller inputs.', 'hint'));
  map.append(operator);

  const shared = element('details', undefined, 'skill-shared');
  shared.append(element('summary', 'Shared controller input'));
  const sharedRows = element('div', undefined, 'skill-shared-rows');
  const globalInput = `${buttonName(preset.modifier_mask)} + ${buttonName(preset.trigger_mask)}`;
  for (const [key, label] of [['tap_move', 'Tap'], ['hold_move', 'Hold']] as const) {
    const row = element('label', undefined, 'skill-shared-row');
    row.append(element('span', `${globalInput} · ${label}`));
    const choice = select(moveOptions(key === 'hold_move' ? 'string_hold' : 'chord', 'Disabled'), preset[key], value => { preset[key] = value || null; });
    choice.dataset.assignment = key === 'tap_move' ? 'chord:tap' : 'chord:hold'; row.append(choice); sharedRows.append(row);
  }
  const editShared = element('button', 'Change shared buttons →', 'inline-button'); editShared.onclick = () => navigate('controls');
  shared.append(sharedRows, editShared); map.append(shared);
  content.append(map);

  const log = element('section', undefined, 'editor-activity');
  log.append(element('h3', 'Editor log'));
  const list = element('ul'); list.id = 'editor-log';
  list.replaceChildren(...(editorLog.length ? editorLog : ['No edits yet.']).map(item => element('li', item)));
  log.append(list); content.append(log);
}


function renderMoves() {
  const p = state.preset, grid = section('Global custom chord', 'Hold Modifier, then press Trigger. Choose separate moves for a tap and a hold. Input overrides can use additional chords.');
  field('Moveset name', input(p.name, value => {
    p.name = value;
  }), grid);
  field('Custom input stance', select((state.capabilities.chord_stances || state.capabilities.stances).map(stance => {
    return [stance, stance === 'any' ? 'ANY · single moves only' : stance.toUpperCase()];
  }), p.chord_stance, value => {
    p.chord_stance = value as Stance | 'any';
  }), grid);
  renderChordButtons(grid);
  for (const [key, label] of [['tap_move', 'Tap / release'], ['hold_move', 'Hold']] as const) {
    const role = key === 'hold_move' ? 'string_hold' : 'chord';
    const move = select(moveOptions(role, 'Disabled'), p[key], value => {
      p[key] = value || null;
    });
    const route = field(label, move, grid);
    const updateHelp = () => { const [body, tip] = moveHelp(move.value, `${label} of the Modifier + Trigger chord`); annotate(route, label, body, tip); };
    updateHelp(); move.addEventListener('change', () => { updateHelp(); explainTarget(move); });
    browseMove(route, move, label);
  }
  const threshold = input(state.preset.hold_seconds, value => {
    state.preset.hold_seconds = Number(value);
  }, 'number'); threshold.min = '.08'; threshold.max = '2'; threshold.step = 'any'; field('Hold threshold · seconds', threshold, grid);

}

function renderOverrides() {
  const p = state.preset, grid = section('Special sword routes', 'These switches affect specific native combo windows or imported strings. They do not replace every press of a base button.');
  const heavy = select(moveOptions('heavy_string'), p.low_heavy, value => {
    p.low_heavy = value || null;
  });
  const heavyField = field('Low heavy string', heavy, grid);
  heavyField.id = 'special-low-heavy';
  browseMove(heavyField, heavy, 'Low heavy string');
  for (const stance of state.capabilities.stances) {
    const held = select(moveOptions('graph'), p.stance_holds[stance], value => {
      p.stance_holds[stance] = value || null;
    });
    const heldField = field(stance.toUpperCase() + ' · hold Triangle / Y', held, grid);
    heldField.id = `special-held-${stance}`;
    annotate(heldField, `${stance.toUpperCase()} held strong`, `Hold Triangle / Y in ${stance} stance to start the selected reviewed sequence.`, 'The Izuna Drop continuation requires a successful launcher and contact.');
    browseMove(heldField, held, `${stance} held strong`);
  }
  for (const [key, label] of [['okatsu_grapple', 'Okatsu grapple'], ['mid_light_ender', 'Mid quick-attack finisher'], ['string_enabled', 'Include Okatsu kicking string']] as const) {
    const check = element('input'); check.type = 'checkbox'; check.checked = p[key];
    check.onchange = () => {
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
    element('p', 'Original routes replace a named game action. Custom chords take priority over game actions on the same buttons. After-attack inputs appear by stance in Sword.', 'hint'));
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
    const followup = binding.input?.gesture === 'after_strong' || binding.input?.gesture === 'after_quick';
    const row = element('div', undefined, 'binding');
    row.dataset.routeKey = binding.input ? `custom:${index}` : `native:${binding.stance}:${binding.source}`;
    row.classList.toggle('custom-route', Boolean(binding.input));
    row.dataset.search = `${routeInput(binding)} ${binding.stance} ${playable(binding.move)?.name || binding.move}`.toLowerCase();
    annotate(row, 'Input route', followup ? 'After a confirmed attack, press Guard with the shown button before its recovery window ends.' : binding.input ? binding.input.gesture === 'sequence' ? 'Hold the modifier, press the first button, then press the follow-up while keeping or releasing the first. The first pair takes priority over its game action.' : 'This custom chord takes priority over a game action on the same buttons.' : 'This route replaces the named Nioh input with a reviewed move.', 'Remove the row to clear this route.');
    const head = element('div', undefined, 'binding-head');
    head.append(element('span', `ROUTE ${String(index + 1).padStart(2, '0')}`, 'route-number'),
      element('span', routeInput(binding), 'route-notation'),
      element('span', binding.stance.toUpperCase(), 'stance-tag'));
    row.append(head);
    if (!binding.input) {
      const sources: [string, string][] = state.capabilities.native_sources.filter(source => source.id !== 'high_heavy_followup' || binding.source === source.id).map(source => [source.id, source.label]);
      field('Source', select(sources, binding.source, value => {
        binding.source = value;
        const stances = state.capabilities.native_sources.find(source => source.id === value)?.stances;
        if (stances && !stances.includes(binding.stance)) binding.stance = stances.length === 1 ? stances[0] : '';
        render();
      }), row);
    }
    const allowed = followup ? binding.input!.gesture === 'after_strong' ? ['low', 'mid'] : ['low', 'high']
      : binding.input ? ['any', 'low', 'mid', 'high'] : state.capabilities.native_sources.find(source => source.id === binding.source)?.stances || ['any', 'low', 'mid', 'high'];
    const stanceChoices: [string, string][] = allowed.map(stance => [stance, stance.toUpperCase()]);
    if (!binding.stance) stanceChoices.unshift(['', 'Choose stance…']);
    field('Stance', select(stanceChoices, binding.stance, value => {
      binding.stance = value; updateSlots();
    }), row);
    if (!followup) field('Activation', select([['original', 'Original Nioh input'], ['custom', 'Custom controller input']], binding.input ? 'custom' : 'original', value => {
      if (value === 'custom' && !binding.input) binding.input = suggestedInput(binding.stance);
      if (value === 'original') delete binding.input;
      const choices = moveOptions(binding.input?.gesture === 'hold' ? 'string_hold' : binding.input ? 'chord' : state.capabilities.native_sources.find(source => source.id === binding.source)?.role || 'native').slice(1);
      if (!choices.some(([id]) => id === binding.move)) binding.move = choices[0][0];
      void action(async () => { await cancelCapture(); render(); });
    }), row);
    const role = binding.input?.gesture === 'hold' ? 'string_hold' : binding.input ? 'chord' : state.capabilities.native_sources.find(source => source.id === binding.source)?.role || 'native';
    const replacement = select(moveOptions(role, 'Native', binding.move).slice(1), binding.move, value => {
      binding.move = value;
    });
    const replacementField = field('Move', replacement, row);
    const updateHelp = () => { const [body, tip] = moveHelp(replacement.value, `Input: ${routeInput(binding)}`); annotate(replacementField, 'Move', body, tip); };
    updateHelp(); replacement.addEventListener('change', () => { updateHelp(); explainTarget(replacement); });
    browseMove(replacementField, replacement, `route ${index + 1}`);
    if (binding.input) {
      const sequence = binding.input.gesture === 'sequence';
      if (followup) row.append(element('p', `${routeInput(binding)} within ${state.capabilities.attack_followup?.window_seconds || .6}s of the original attack’s recovery.`, 'control-note'));
      else {
      const buttons = sequence ? [['modifier_mask', 'Modifier'], ['trigger_mask', 'First press'], ['followup_mask', 'Then press']] as const
        : [['modifier_mask', 'Modifier'], ['trigger_mask', 'Trigger']] as const;
      for (const [key, label] of buttons) {
        const input = binding.input;
        buttonPicker(row, label, input[key]!, value => { input[key] = value; }, { kind: 'route', binding, key });
      }
      if (sequence) row.append(element('p', `Hold Modifier + First press, then press the follow-up within ${state.capabilities.custom_sequence?.window_seconds || .6}s while keeping First press held, or within that window after releasing it. Presses must be separate. The start pair takes priority over its game action.`, 'control-note'));
      else {
        field('Gesture', select([['tap', 'Tap / release'], ['hold', `Hold · ${p.hold_seconds}s`]], binding.input.gesture, value => {
          binding.input!.gesture = value as 'tap' | 'hold';
          const choices = moveOptions(value === 'hold' ? 'string_hold' : 'chord').slice(1);
          if (!choices.some(([id]) => id === binding.move)) binding.move = choices[0][0];
          render();
        }), row);
        row.append(element('p', 'Hold the modifier, then use the selected Trigger gesture. This pair takes priority over a game action on the same buttons.', 'control-note'));
      }
      if (capture?.kind === 'route' && capture.binding === binding) captureStatus(row);
      }
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
  const grid = section('Stance-switch moves', 'During a Ki Pulse window, hold R1 / RB and tap the destination stance button twice.');
  for (const stance of state.capabilities.stances) {
    const move = select(moveOptions('frost', 'Disabled'), state.preset.frost_moon[stance], value => {
      state.preset.frost_moon[stance] = value || null;
    });
    const route = field(stance.toUpperCase(), move, grid);
    route.id = `frost-${stance}`;
    const updateHelp = () => { const [body, tip] = moveHelp(move.value, `During a Ki Pulse window, hold R1 / RB and tap ${stance} stance twice`); annotate(route, `${stance.toUpperCase()} Frost Moon`, body, tip); };
    updateHelp(); move.addEventListener('change', () => { updateHelp(); explainTarget(move); });
    browseMove(route, move, `${stance} Frost Moon`);
  }
}

function renderSpeed() {
  content.append(element('h2', 'Speed modification', 'section-title'),
    element('p', 'Choose a move on the left. Adjust its playback on the right; 100% is native speed. The Engine supports 25–200%.', 'hint'));
  const workspace = element('div', undefined, 'speed-workspace');
  const moveList = element('div', undefined, 'speed-moves');
  const editor = element('section', undefined, 'speed-editor');
  workspace.append(moveList, editor); content.append(workspace);
  const show = element('input'); show.type = 'checkbox'; show.checked = showUnused;
  show.onchange = () => { showUnused = show.checked; speedRefresh?.(); };
  field('Show unused moves', show, content).classList.add('toggle');
  const buttons = new Map<string, HTMLButtonElement>();
  let percent: HTMLInputElement, slider: HTMLInputElement, effective: HTMLElement, mode: HTMLElement;
  const selectedMove = () => state.capabilities.moves.find(move => move.id === speedSelection)!;
  const setSpeed = (value: string) => {
    if (value === '' && !percent.validity.badInput) delete state.preset.move_settings[speedSelection];
    else state.preset.move_settings[speedSelection] = { speed: value === '' ? NaN : Number(value) / 100 };
    mode.textContent = value === '' ? 'Inherited from the move sequence' : 'Custom speed';
    if (value !== '') slider.value = value;
    changed();
  };
  const selectMove = (id: string) => {
    speedSelection = id;
    const move = selectedMove(); editor.replaceChildren();
    editor.append(element('span', 'SELECTED MOVE', 'speed-eyebrow'), element('h3', move.name),
      element('p', move.description || 'Reviewed move.', 'speed-description'));
    const controls = element('div', undefined, 'speed-controls');
    const value = state.preset.move_settings[id]?.speed;
    mode = element('p', value === undefined ? 'Inherited from the move sequence' : 'Custom speed', 'speed-mode');
    slider = element('input'); slider.type = 'range'; slider.min = String(state.capabilities.speed.min * 100); slider.max = String(state.capabilities.speed.max * 100); slider.step = '1';
    slider.value = String(Math.round((value ?? preview?.moves[id]?.speed ?? 1) * 100));
    percent = element('input'); percent.type = 'number'; percent.min = slider.min; percent.max = slider.max; percent.step = '1';
    percent.value = value === undefined ? '' : String(Math.round(value * 100)); percent.placeholder = 'Inherit';
    percent.setAttribute('aria-label', `${move.name} speed percentage`);
    slider.setAttribute('aria-label', `${move.name} speed slider`);
    slider.oninput = () => { percent.value = slider.value; setSpeed(slider.value); };
    percent.oninput = () => setSpeed(percent.value);
    const valueField = element('label', undefined, 'speed-value'); valueField.append(percent, element('span', '%'));
    controls.append(mode, slider, valueField, element('span', `${slider.min}%`, 'speed-min'), element('span', `${slider.max}%`, 'speed-max'));
    effective = element('p', undefined, 'speed-effective');
    const reset = element('button', 'Inherit speed'); reset.onclick = () => { percent.value = ''; setSpeed(''); };
    annotate(editor, move.name, `${move.description || 'Reviewed move.'} Playback speed applies only to this move.`, 'Blank inherits its sequence speed; 100% explicitly uses native speed.');
    editor.append(controls, effective, reset);
    for (const [key, button] of buttons) button.classList.toggle('selected', key === id);
    updateEditor();
  };
  const updateEditor = () => {
    const id = speedSelection, compiled = preview?.moves[id], saved = state.preset.move_settings[id]?.speed;
    if (!effective) return;
    effective.textContent = compiled && preview?.used.includes(id) ? `Effective ${Math.round(compiled.speed * 100)}% · ${saved === undefined ? 'inherited' : 'custom'}` : 'Effective speed appears after validation.';
    mode.textContent = saved === undefined ? 'Inherited from the move sequence' : 'Custom speed';
    if (document.activeElement !== percent) percent.value = saved === undefined ? '' : String(Math.round(saved * 100));
    if (document.activeElement !== slider) slider.value = String(Math.round((saved ?? compiled?.speed ?? 1) * 100));
    for (const [key, button] of buttons) {
      const speed = state.preset.move_settings[key]?.speed;
      button.querySelector('small')!.textContent = speed === undefined ? 'Inherit' : `${Math.round(speed * 100)}%`;
    }
  };
  for (const move of state.capabilities.moves) if (move.speed) {
    const button = element('button', undefined, 'speed-move'); button.type = 'button';
    button.dataset.moveId = move.id; button.append(element('strong', move.name), element('small', 'Inherit'));
    button.onclick = () => selectMove(move.id); buttons.set(move.id, button); moveList.append(button);
  }
  speedRefresh = () => {
    const visible = [...buttons].filter(([id]) => showUnused || !preview || preview.used.includes(id) || state.preset.move_settings[id]);
    for (const [id, button] of buttons) button.hidden = !visible.some(([key]) => key === id);
    if (visible.length && !visible.some(([id]) => id === speedSelection)) selectMove(visible[0][0]);
    updateEditor();
  };
  if (!buttons.has(speedSelection)) speedSelection = buttons.keys().next().value || '';
  if (speedSelection) selectMove(speedSelection);
  speedRefresh();
}

function renderPresets() {
  content.append(element('h2', 'Preset manager', 'section-title'),
    element('p', 'Save a setup to the library, then activate it here or cycle during gameplay. The editor keeps unsaved changes until you choose to replace them.', 'hint'));
  const templates = element('details', undefined, 'guide-glossary');
  templates.append(element('summary', 'Built-in movesets · load a draft'));
  const choices = element('div', undefined, 'preset-actions');
  for (const [id, label] of Object.entries(builtInPresets)) {
    const button = element('button', label); button.dataset.presetTemplate = id;
    button.onclick = () => void action(() => perform(id)); choices.append(button);
  }
  templates.append(element('p', 'Loading replaces the editor draft. Save changes to use it, or save a named copy in the library.'), choices);
  content.append(templates);
  if (!presetLibrary) { content.append(element('p', 'Reading saved presets…', 'hint')); void refreshPresetLibrary(); return; }
  const library = presetLibrary;
  if (!library.presets.some(item => item.id === presetSelection)) presetSelection = library.selected_id || library.presets[0]?.id || '';
  const workspace = element('div', undefined, 'preset-workspace');
  const list = element('div', undefined, 'preset-list');
  const viewer = element('section', undefined, 'preset-viewer');
  workspace.append(list, viewer); content.append(workspace);
  const selected = library.presets.find(item => item.id === presetSelection);
  list.append(element('h3', 'Saved movesets'));
  for (const item of library.presets) {
    const button = element('button', undefined, 'preset-item'); button.type = 'button';
    button.classList.toggle('selected', item.id === presetSelection);
    button.append(element('strong', item.name), element('small', item.id === library.selected_id ? 'Active' : 'Saved'));
    button.onclick = () => { presetSelection = item.id; render(); };
    list.append(button);
  }
  if (!library.presets.length) list.append(element('p', 'No saved presets yet. Save the current moveset to start a library.', 'hint'));
  const save = element('button', '+ Save current moveset', 'add-route');
  save.onclick = () => void action(async () => {
    const previous = new Set(presetLibrary?.presets.map(item => item.id));
    presetLibrary = await window.mwm.request<PresetLibrary>('preset_save', params());
    ++presetLibraryRevision;
    presetSelection = presetLibrary.presets.find(item => !previous.has(item.id))?.id || presetLibrary.presets.find(item => item.name === state.preset.name)?.id || presetSelection;
    logEdit(`Saved ${state.preset.name} to preset library`); render();
  });
  list.append(save);

  viewer.append(element('span', 'SELECTED PRESET', 'speed-eyebrow'), element('h3', selected?.name || 'Choose a preset'));
  if (selected) {
    viewer.append(element('p', selected.id === library.selected_id ? 'Active for gameplay' : 'Stored in your library', 'preset-status'));
    if (selected.native_routes !== undefined) viewer.append(element('p', `${selected.native_routes} original routes · ${selected.custom_routes} custom inputs · ${selected.speed_overrides} speed edits`, 'hint'));
    const actions = element('div', undefined, 'preset-actions');
    const load = element('button', dirty ? 'Replace unsaved draft' : 'Load into editor');
    load.onclick = () => void action(async () => {
      state.preset = await window.mwm.request<Preset>('preset_load', { ...params(), id: presetSelection, dirty, discard_draft: dirty });
      dirty = true; logEdit(`Loaded ${state.preset.name} into draft`); tab = 'overview'; render();
    });
    const activate = element('button', 'Activate now', 'primary');
    activate.disabled = selected.id === library.selected_id;
    activate.onclick = () => void switchPreset('preset_switch', { runtime: state.runtime, id: presetSelection });
    const remove = element('button', 'Delete preset');
    remove.onclick = () => void action(async () => {
      presetLibrary = await window.mwm.request<PresetLibrary>('preset_delete', { runtime: state.runtime, id: presetSelection });
      ++presetLibraryRevision;
      presetSelection = presetLibrary.selected_id || presetLibrary.presets[0]?.id || '';
      logEdit(`Deleted ${selected.name} from preset library`); render();
    });
    actions.append(load, activate, remove); viewer.append(actions);
  }
  const cycle = element('button', 'Switch to next preset');
  cycle.disabled = library.presets.length < 2;
  cycle.onclick = () => void switchPreset('preset_cycle', { runtime: state.runtime });
  const hotkey = element('div', undefined, 'preset-hotkey');
  hotkey.append(element('strong', 'Controller shortcut'),
    element('p', library.hotkey.supported ? library.hotkey.label : library.hotkey.reason || 'This controller does not expose a touchpad click to the app. Switch presets here.'));
  viewer.append(cycle, hotkey);
}

async function refreshPresetLibrary() {
  const revision = ++presetLibraryRevision;
  try {
    const list = await window.mwm.request<PresetLibrary>('preset_list');
    if (revision !== presetLibraryRevision) return;
    presetLibrary = list;
    if (tab === 'presets') render();
  } catch (error) { if (tab === 'presets') message(errorText(error), true); }
}

function adoptPresetSwitch(result: { presets: PresetLibrary; snapshot: Snapshot }) {
  ++actionGeneration; // A controller hotkey can finish while an older status poll is still in flight.
  ++presetLibraryRevision; presetLibrary = result.presets; presetSelection = result.presets.selected_id || presetSelection;
  if (!dirty) state = result.snapshot;
  if (!dirty || tab === 'presets') render();
  showRuntime(result.snapshot);
  const name = result.presets.presets.find(item => item.id === result.presets.selected_id)?.name || result.snapshot.preset.name;
  logEdit(`Active preset: ${name}`); message(`Active preset: ${name}${dirty ? '. Unsaved editor draft kept.' : ''}`);
}

async function switchPreset(method: 'preset_switch' | 'preset_cycle', params: unknown) {
  await action(async () => adoptPresetSwitch(await window.mwm.request<{ presets: PresetLibrary; snapshot: Snapshot }>(method, params)));
}

async function pollCapture() {
  // Keep one capture poll in flight; generation changes invalidate cancelled listeners.
  if (!capture) return;
  const generation = captureGeneration, target = capture;
  try {
    const result = await window.mwm.request<{ mask?: number; label?: string; status?: string; calibration?: Calibration }>('capture_poll');
    if (!capture || generation !== captureGeneration) return;
    if (result.mask !== undefined) {
      const index = target.kind === 'route' ? state.preset.skill_bindings.indexOf(target.binding) : -1;
      if (target.kind === 'route' && index < 0) { await cancelCapture(); return; }
      let mapped: Pick<Snapshot, 'calibration' | 'preset' | 'buttons'> | undefined;
      if (result.calibration && JSON.stringify(result.calibration) !== JSON.stringify(state.calibration)) {
        const preset = state.preset, revision = editGeneration;
        mapped = await window.mwm.request('controller',
          { ...params(), choice: 'detected', detected_calibration: result.calibration });
        if (!capture || generation !== captureGeneration) return;
        if (preset !== state.preset || revision !== editGeneration) {
          await cancelCapture(); render(); message('Draft changed while detecting the controller. Record the button again.'); return;
        }
      }
      // Reject unsupported buttons before adopting any remapped controller or draft fields.
      if (target.kind === 'route' && !routeMaskAllowed(target.binding, target.key, result.mask, mapped?.buttons)) {
        await cancelCapture(); render(); message('This button is unavailable for the selected input pattern.', true); return;
      }
      if (mapped) {
        Object.assign(state, mapped);
        if (target.kind === 'route') target.binding = state.preset.skill_bindings[index];
        controllerChoice = state.calibration.device.backend === 'xinput' ? String(Number(state.calibration.device.slot) + 1) : 'ds4';
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
  // Invalidate in-flight replies before closing the worker's temporary input listener.
  ++captureGeneration; capture = null; clearTimeout(timer); await window.mwm.request('capture_cancel');
}

function isCapturing(target: CaptureTarget) {
  if (!capture || capture.kind !== target.kind || capture.key !== target.key) return false;
  return capture.kind === 'global' || target.kind === 'route' && capture.binding === target.binding;
}
function captureLabel(target: CaptureTarget) {
  const label = target.key === 'modifier_mask' ? 'Modifier' : target.key === 'followup_mask' ? 'Follow-up' : 'Trigger';
  return target.kind === 'route' ? `Route ${state.preset.skill_bindings.indexOf(target.binding) + 1} ${label} · ` : '';
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
    .filter(([name]) => target.kind === 'global' || routeMaskAllowed(target.binding, target.key, state.buttons[name]))
    .map(([name, bit]) => [String(bit), name]);
  if (!buttons.some(([value]) => value === String(mask))) buttons.unshift([String(mask), `${buttonName(mask)} · choose a supported button`]);
  const wrapper = field(label, select(buttons, String(mask), value => { update(Number(value)); void action(cancelCapture); }), parent);
  if (target.kind === 'route') annotate(wrapper, label,
    target.binding.input?.gesture === 'sequence' ? 'Choose or record one distinct button in this three-step operator.' : 'Choose a distinct supported button for this custom input.',
    'Press to bind records a supported button on the connected controller.');
  const bind = element('button', isCapturing(target) ? 'Listening…' : 'Press to bind');
  bind.setAttribute('aria-label', target.kind === 'route' ? `Record ${label.toLowerCase()} for route ${state.preset.skill_bindings.indexOf(target.binding) + 1}` : `Record global ${label.toLowerCase()}`);
  bind.onclick = () => startCapture(target); wrapper.append(bind);
}

function renderChordButtons(grid: HTMLElement) {
  for (const [key, label] of [['modifier_mask', 'Modifier'], ['trigger_mask', 'Trigger']] as const) {
    buttonPicker(grid, label, state.preset[key], value => { state.preset[key] = value; }, { kind: 'global', key });
  }
  const swap = element('button', 'Swap buttons');
  swap.onclick = () => {
    // Cancel capture before swapping so a late input cannot undo half of the swap.
    void action(async () => {
      await cancelCapture();
      [state.preset.modifier_mask, state.preset.trigger_mask] = [state.preset.trigger_mask, state.preset.modifier_mask];
      changed(); render();
    });
  };
  swap.className = 'swap-buttons'; grid.append(swap);
  captureStatus(grid, true);
}

function renderGuide() {
  content.append(element('h2', 'Build a sword moveset', 'section-title'),
    element('p', 'Edits stay in a draft until Save changes. Each tab handles one part of the moveset.', 'hint'));
  const steps = element('div', undefined, 'guide-steps');
  for (const [number, title, body, destination] of [
    ['01', 'Assign moves', 'In Moves, choose Low, Mid or High. Each input has one replacement menu. Original keeps Nioh’s action. After Strong and After Quick add stance-specific follow-ups where their Guard combinations are free.', 'overview'],
    ['02', 'Add a custom input', 'In Moves, choose a two-button tap or hold and a reviewed move. Add a follow-up only if you want a three-button sequence; press it after the first button is observed.', 'overview'],
    ['03', 'Tune and save', 'Speed changes playback for one move at a time; blank inherits from its sequence. Save a valid draft before enabling the mod.', 'speed'],
    ['04', 'Keep setups', 'Presets stores named movesets. Activate one in the app or double-tap the touchpad click on a supported controller to cycle live during gameplay.', 'presets']
  ]) {
    const card = element('section', undefined, 'guide-step');
    card.append(element('span', number, 'guide-number'), element('h3', title), element('p', body));
    const button = element('button', `Open ${destination === 'overview' ? 'Moves' : destination === 'speed' ? 'Speed' : 'Presets'} →`, 'inline-button');
    button.onclick = () => navigate(destination); card.append(button); steps.append(card);
  }
  content.append(steps);
  for (const [title, body] of [
    ['Maria sword bindings', 'Load Maria sword from More or Presets. Low Quick uses the aerial kick string; Mid Quick uses the quick string; High Strong uses the horizontal slash string; Mid Guard + Strong uses the forward dodge slash. Press again for each phase and keep tapping as the final phase ends to restart. Maria dodge string replaces only the Mid Quick string.'],
    ['Onmyo and shuriken Ki Pulse', 'Each sword move has a fixed window across presets and eligible item types. Onmyo cancels work after 60% of supported moves; shuriken cancels after 70%, with overlap. Native William attacks are included. Cast after an attack, release Guard and attack buttons, then press R1 / RB shortly after the effect or projectile appears. Early presses are not buffered. Cancels preserve the effect and complete Ki Pulse before its original deadline; other moves keep normal cast recovery.']
  ]) {
    const feature = element('details', undefined, 'guide-glossary'); feature.open = true;
    feature.append(element('summary', title), element('p', body)); content.append(feature);
  }
  const glossary = element('details', undefined, 'guide-glossary');
  glossary.append(element('summary', 'What counts as a playable move?'));
  glossary.append(element('p', 'The move picker contains reviewed moves the Engine can route to William. Move library separately lists named recording candidates and unreviewed action signatures; neither becomes playable without William adaptation.'),
    element('p', 'A stance-switch move fires during a Ki Pulse window after R1/RB and two taps toward the destination stance. A held strong route uses a long Triangle/Y press. Input overrides exposes the full route table and controller recording.'));
  content.append(glossary);
}

function renderControls() {
  // Engine translates logical buttons when controller hardware changes.
  const grid = section('Controller mapping', 'Choose the controller Nioh uses. The diagram below shows its default buttons; custom inputs can be recorded while the game is open or closed.');
  const devices = select([['saved', 'Saved mapping'], ['ds4', 'DS4 mapping'], ['1', 'XInput controller 1'], ['2', 'XInput controller 2'], ['3', 'XInput controller 3'], ['4', 'XInput controller 4']], controllerChoice, value => {
    // Adopt calibration, buttons and preset together only after translation succeeds.
    void action(async () => {
      await cancelCapture(); Object.assign(state, await window.mwm.request('controller', { ...params(), choice: value })); controllerChoice = value; changed(); render();
    }).finally(() => { devices.value = controllerChoice; });
  }, false);
  field('Controller mapping', devices, grid);
  field('Game controller slot', select([['', 'Auto (one controller)'], ['0', '1'], ['1', '2'], ['2', '3'], ['3', '4']], state.calibration.controller_slot == null ? '' : String(state.calibration.controller_slot), value => {
    // The game slot is distinct from the raw OS controller identity.
    state.calibration.controller_slot = value === '' ? null : Number(value); void action(cancelCapture);
  }), grid);
  const game = element('details', undefined, 'game-path'); game.append(element('summary', 'Game launch · optional'));
  const path = element('button', state.nioh_exe || 'Choose nioh.exe (optional)'); path.onclick = () => {
    void action(async () => {
      const value = await window.mwm.request<string | null>('game_path'); if (value) { state.nioh_exe = value; changed(); render(); }
    });
  }; field('Game executable', path, game); return game;
}

function renderCollection() {
  // Playable capability rows and recorded research use separate views. A recording
  // never becomes a bindable choice simply because it appears in the library.
  content.append(element('h2', 'Move library', 'section-title'));
  content.append(element('p', 'Reviewed playable moves are available in Moves and Input overrides. Recorded candidates need William-specific adaptation and verification before binding.', 'hint'));
  const tabs = element('div', undefined, 'library-tabs');
  const playableTab = element('button', `Playable · ${state.capabilities.moves.length}`);
  const recordedTab = element('button', `Recorded candidates · ${collection.moves.length}`);
  const unreviewedTab = element('button', `Unreviewed actions · ${collection.unreviewed.distinct_signatures}`);
  tabs.append(playableTab, recordedTab, unreviewedTab); content.append(tabs);
  const search = element('input'); search.type = 'search'; search.placeholder = 'Search moves, boss, or action ID'; search.setAttribute('aria-label', 'Search move library'); content.append(search);
  const playablePane = element('div', undefined, 'library-list');
  const recordedPane = element('div', undefined, 'library-list');
  const unreviewedPane = element('div', undefined, 'library-list');
  const playableCards: { node: HTMLElement; text: string }[] = [];
  for (const move of state.capabilities.moves) {
    const card = element('article', undefined, 'library-move');
    card.append(element('h3', move.name), element('p', move.input || 'Input depends on the assigned route', 'library-input'),
      element('p', move.description || 'Reviewed for the supported route; see the source notes for details.', 'library-description'));
    annotate(card, move.name, move.description || 'Reviewed playable move.', move.input ? `Expected input: ${move.input}` : 'Input depends on the route you assign.');
    const kinds = [move.chord && 'Custom chord', move.string_hold && 'Held custom input', move.held && 'Held strong', move.native && 'Input route', move.heavy_string && 'Heavy string'].filter(Boolean);
    card.append(element('small', kinds.join(' · ') || 'Tuning only', 'move-kinds'));
    playablePane.append(card); playableCards.push({ node: card, text: `${move.id} ${move.name} ${move.input || ''} ${move.description || ''}`.toLowerCase() });
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
  recordedPane.append(element('p', `${collection.moves.length} candidate moves · ${collection.intake.sessions.length} source sessions · ${missing} incomplete sessions. Names and categories follow the source notes; action matching still needs review.`, 'hint'));
  const recordedCards: { node: HTMLElement; text: string }[] = [];
  for (const move of collection.moves) {
    const card = element('details', undefined, 'research-move');
    const weapon = collection.manifest.weapons[move.weapon_id].name, boss = collection.manifest.bosses[move.boss_id].name;
    const title = `${weapon} / ${boss} · ${move.name}`;
    card.append(element('summary', title));
    card.append(element('p', `${move.kind.replaceAll('_', ' ')} candidate · ${move.mapping_status === 'partial' ? 'Partial mapping' : 'Candidate mapping'} · Priority: ${move.priority || 'unset'}`, 'hint'));
    for (const evidence of move.evidence) card.append(element('p', evidence.annotation_text, 'recorded-note'));
    card.append(element('p', move.steps.map(step => `${step.source.action_id} (${step.source.motion_id})`).join(' → '), 'source-ids'));
    for (const note of move.review_notes || []) card.append(element('p', note, 'hint'));
    recordedCards.push({ node: card, text: [move.id, title, ...move.steps.map(step => `${step.source.action_id} ${step.source.motion_id}`), ...move.evidence.map(evidence => evidence.annotation_text)].join(' ').toLowerCase() });
    recordedPane.append(card);
  }
  unreviewedPane.append(element('p', 'These action signatures came from 55 sword recording sessions. The logs do not identify the actor reliably or prove William can play them. Search the evidence below; they cannot be assigned yet.', 'hint'));
  const unreviewedCount = element('p', '', 'hint'); unreviewedPane.append(unreviewedCount);
  const unreviewedResults = element('div'); unreviewedPane.append(unreviewedResults);
  const indexed = collection.unreviewed.signatures.map(signature => ({ signature,
    text: `${collection.manifest.bosses[signature.boss_id]?.name || signature.boss_id} ${signature.boss_id} ${signature.action_hex} ${signature.action_hex.replace(/^0+/, '')}`.toLowerCase() }));
  const empty = element('p', 'No moves match this search.', 'hint'); empty.hidden = true; content.append(playablePane, recordedPane, unreviewedPane, empty);
  let view: 'playable' | 'recorded' | 'unreviewed' = 'playable';
  const filter = () => {
    const query = search.value.trim().toLowerCase();
    if (view === 'unreviewed') {
      const matches = indexed.filter(item => item.text.includes(query));
      unreviewedCount.textContent = `${matches.length} matching signatures${matches.length > 60 ? ' · showing first 60' : ''}`;
      unreviewedResults.replaceChildren(...matches.slice(0, 60).map(({ signature }) => {
        const card = element('article', undefined, 'library-move');
        const boss = collection.manifest.bosses[signature.boss_id]?.name || signature.boss_id;
        card.append(element('h3', `${boss} · action ${signature.action_hex}`),
          element('p', `Motion ${signature.motion_id} · timing ${signature.timing_id} · ${signature.observations} observations in ${signature.recording_ids.length} recordings`, 'library-description'),
          element('small', `Recording ${signature.recording_id} · journal line ${signature.journal_line} · payload ${signature.payload_prefix_sha256.slice(0, 12)}`, 'move-kinds'));
        return card;
      }));
      empty.hidden = matches.length > 0; return;
    }
    const cards = view === 'playable' ? playableCards : recordedCards;
    for (const card of cards) card.node.hidden = !card.text.includes(query);
    empty.hidden = cards.some(card => !card.node.hidden);
  };
  const show = (next: 'playable' | 'recorded' | 'unreviewed') => {
    view = next; playablePane.hidden = view !== 'playable'; recordedPane.hidden = view !== 'recorded'; unreviewedPane.hidden = view !== 'unreviewed';
    playableTab.classList.toggle('selected', view === 'playable'); recordedTab.classList.toggle('selected', view === 'recorded'); unreviewedTab.classList.toggle('selected', view === 'unreviewed');
    filter();
  };
  playableTab.onclick = () => show('playable'); recordedTab.onclick = () => show('recorded'); unreviewedTab.onclick = () => show('unreviewed'); search.oninput = filter;
  show('playable');
}

function renderBindingModules() {
  // A group owns only its binding fields; selecting a group is not a draft edit.
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
      // Cancelled or rejected imports leave the entire draft intact.
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
  // Rebuild on structural changes only; ordinary input edits keep their DOM and focus.
  speedRefresh = null; content.replaceChildren(); content.setAttribute('aria-busy', 'false');
  explain(...pageHelp[tab]);
  for (const button of document.querySelectorAll<HTMLButtonElement>('nav button')) button.classList.toggle('selected', button.dataset.tab === tab);
  if (tab === 'overview') renderOverview();
  else if (tab === 'presets') renderPresets();
  else if (tab === 'collection') renderCollection();
  else if (tab === 'controls') { const game = renderControls(); content.append(createControllerDiagram(state.calibration.device.backend === 'xinput' ? 'xbox' : 'playstation'), game); renderMoves(); renderBindingModules(); }
  else if (tab === 'native') { renderNative(); renderOverrides(); renderBindingModules(); }
  else if (tab === 'frost') { renderFrost(); renderBindingModules(); }
  else if (tab === 'speed') renderSpeed();
  else renderGuide();
  schedulePreview();
}

async function reload() {
  // Explicit reload may discard edits; periodic status reads must preserve them.
  await cancelCapture(); state = await window.mwm.request<Snapshot>('snapshot'); controllerChoice = 'saved'; dirty = Boolean(state.load_warning); render();
  showRuntime(state);
  message(state.load_warning || '', Boolean(state.load_warning));
  void refreshPresetLibrary();
}

async function perform(name: string) {
  // Loading and exporting operate on the draft; only Apply persists active settings.
  if (name === 'reload') { await reload(); return; }
  await cancelCapture();
  if (name in builtInPresets || name === 'load') {
    const preset = await window.mwm.request<Preset | null>(name === 'load' ? 'import' : name, params());
    if (preset) { state.preset = preset; dirty = true; render(); message(`${builtInPresets[name] || 'Moveset'} loaded into draft.`); } return;
  }
  if (name === 'save') { if (await window.mwm.request('export', params())) message('Moveset exported. Runtime settings were not changed.'); return; }
  if (name === 'apply') { state = await window.mwm.request<Snapshot>('apply', params()); dirty = false; render(); showRuntime(state); message(''); chime('saved'); void refreshPresetLibrary(); return; }
  if (name === 'enable') { if (dirty) throw new Error('Save changes before enabling the mod.'); await window.mwm.request('enable', params()); showRuntime(await window.mwm.request<Snapshot>('snapshot')); message(''); return; }
  if (name === 'disable') { await window.mwm.request('disable'); showRuntime(await window.mwm.request<Snapshot>('snapshot')); message(''); }
}

function navigate(name: string, focus?: string) {
  void action(async () => {
    await cancelCapture(); tab = name; document.querySelector<HTMLDetailsElement>('#tools')!.open = false; render(); content.scrollTop = 0;
  }).then(() => {
    const target = focus ? content.querySelector<HTMLElement>(focus) : null;
    target?.scrollIntoView({ block: 'center' }); target?.querySelector<HTMLElement>('select')?.focus();
  });
}

for (const button of document.querySelectorAll<HTMLButtonElement>('nav [data-tab]')) button.onclick = () => navigate(button.dataset.tab!);
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-action]')) button.onclick = () => {
  document.querySelector<HTMLDetailsElement>('#tools')!.open = false;
  void action(() => perform(button.dataset.action!));
};

function showRuntime(snapshot: Snapshot) {
  // Runtime status is independent of the draft, including failures retained after Engine exits.
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
  // Adopt external saves only while clean and idle, rechecking after the asynchronous read.
  // Unchanged snapshots keep controls and focus intact.
  if (state && !busy && !capture) {
    const generation = actionGeneration;
    try {
      const snapshot = await window.mwm.request<Snapshot>('snapshot');
      if (generation === actionGeneration && !busy) {
        if (!dirty && !capture && JSON.stringify(params(snapshot)) !== JSON.stringify(params())) {
          state = snapshot; controllerChoice = 'saved'; dirty = Boolean(snapshot.load_warning);
          render(); message(snapshot.load_warning || '', Boolean(snapshot.load_warning));
          void refreshPresetLibrary();
        }
        showRuntime(snapshot);
      }
    } catch (error) { if (generation === actionGeneration && !busy) { document.querySelector('#runtime')!.textContent = 'Worker unavailable'; document.querySelector('#runtime-detail')!.textContent = errorText(error); } }
  }
  setTimeout(pollStatus, 1800);
}

async function start() {
  document.body.inert = true;
  try {
    collection = await window.mwm.request<Collection>('collection'); await reload();
    window.mwm.onPresetCycle?.(event => {
      if (event.result) adoptPresetSwitch(event.result);
      else if (event.error) message(event.error, true);
    });
    void pollStatus();
  } catch (error) { message(errorText(error), true); }
  finally { document.body.inert = false; }
}
void start();
