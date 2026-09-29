type Layout = 'xbox' | 'playstation';

const actions = [
  { id: 'aim', keys: ['LT', 'L2'], name: 'Aim', x: 8, y: 32, path: 'M192 113 H160 V44 H132' },
  { id: 'guard', keys: ['LB', 'L1'], name: 'Guard', x: 8, y: 72, path: 'M199 136 H154 V84 H132' },
  { id: 'items', keys: ['D-pad', 'D-pad'], name: 'Item shortcuts', x: 8, y: 213, path: 'M246 240 H132 V225' },
  { id: 'move', keys: ['L stick', 'L stick'], name: 'Move', x: 8, y: 292, path: 'M212 191 V304 H132' },
  { id: 'shoot', keys: ['RT', 'R2'], name: 'Shoot while aiming', x: 418, y: 32, path: 'M368 113 H401 V44 H418' },
  { id: 'stance', keys: ['RB', 'R1'], name: 'Stance / Ki Pulse', x: 418, y: 72, path: 'M361 136 H406 V84 H418' },
  { id: 'strong', keys: ['Y', '△'], name: 'Strong', x: 418, y: 132, path: 'M409 144 H418' },
  { id: 'quick', keys: ['X', '□'], name: 'Quick', x: 418, y: 164, path: 'M409 176 H418' },
  { id: 'interact', keys: ['B', '○'], name: 'Interact', x: 418, y: 196, path: 'M409 208 H418' },
  { id: 'dodge', keys: ['A', '✕'], name: 'Dodge', x: 418, y: 228, path: 'M409 240 H418' },
  { id: 'camera', keys: ['R stick', 'R stick'], name: 'Camera', x: 418, y: 292, path: 'M322 240 V304 H418' }
] as const;

const ns = 'http://www.w3.org/2000/svg';
const tip = 'The diagram is a reference. Controller mapping below changes the actual device layout.';

export function createControllerDiagram(layout: Layout): HTMLElement {
  const section = document.createElement('section');
  section.className = 'controller-diagram';
  const header = document.createElement('div');
  header.className = 'controller-diagram__header';
  header.innerHTML = '<div><h2>Game input reference</h2><span>Default controller actions</span></div>';
  const switcher = document.createElement('div');
  switcher.className = 'controller-diagram__switch';
  switcher.setAttribute('role', 'group');
  switcher.setAttribute('aria-label', 'Diagram button labels');
  const buttons = (['xbox', 'playstation'] as const).map(value => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = value === 'xbox' ? 'Xbox' : 'PlayStation';
    button.onclick = () => show(value);
    switcher.append(button);
    return button;
  });
  header.append(switcher);

  const stage = document.createElement('div');
  stage.className = 'controller-diagram__stage';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 560 354');
  svg.setAttribute('role', 'group');
  svg.setAttribute('aria-label', 'Controller diagram with labeled default game actions');
  svg.innerHTML = `
    <defs>
      <linearGradient id="cd-shell" x2="0" y2="1"><stop stop-color="#405465"/><stop offset="1" stop-color="#233541"/></linearGradient>
      <linearGradient id="cd-inset" x2="0" y2="1"><stop stop-color="#273946"/><stop offset="1" stop-color="#172630"/></linearGradient>
    </defs>
    <path class="cd-shadow" d="M178 126 Q205 103 246 120 L262 127 H298 L314 120 Q355 103 382 126 C398 148 418 213 420 239 Q425 284 393 281 Q364 277 322 254 Q307 247 280 248 Q253 247 238 254 Q196 277 167 281 Q135 284 140 239 C142 213 162 148 178 126Z"/>
    <path class="cd-trigger" d="M179 124 L183 98 Q185 88 196 88 H214 L223 117Z M337 117 L346 88 H364 Q375 88 377 98 L381 124Z"/>
    <path class="cd-bumper" d="M171 129 Q183 111 221 119 L230 134 H166Z M330 134 L339 119 Q377 111 389 129 L394 134Z"/>
    <path class="cd-shell" d="M178 126 Q205 103 246 120 L262 127 H298 L314 120 Q355 103 382 126 C398 148 418 213 420 239 Q425 284 393 281 Q364 277 322 254 Q307 247 280 248 Q253 247 238 254 Q196 277 167 281 Q135 284 140 239 C142 213 162 148 178 126Z"/>
    <path class="cd-seam" d="M170 153 Q222 128 258 143 H302 Q338 128 390 153 M165 259 Q197 248 232 240 M328 240 Q363 248 395 259"/>
    <path class="cd-center" d="M249 139 H311 L321 179 Q280 194 239 179Z"/>
    <rect class="cd-menu" x="258" y="165" width="12" height="5" rx="2.5"/><rect class="cd-menu" x="290" y="165" width="12" height="5" rx="2.5"/>
    <circle class="cd-mark" cx="280" cy="172" r="8"/><path class="cd-mark-line" d="M277 172 H283 M280 169 V175"/>
    <circle class="cd-stick-ring" cx="212" cy="191" r="30"/><circle class="cd-stick" cx="212" cy="191" r="22"/><circle class="cd-stick-top" cx="212" cy="191" r="15"/>
    <circle class="cd-stick-ring" cx="322" cy="240" r="27"/><circle class="cd-stick" cx="322" cy="240" r="20"/><circle class="cd-stick-top" cx="322" cy="240" r="14"/>
    <path class="cd-dpad" d="M239 216 H253 V229 H266 V243 H253 V256 H239 V243 H226 V229 H239Z"/>
    <circle class="cd-face" cx="353" cy="154" r="12"/><circle class="cd-face" cx="330" cy="179" r="12"/><circle class="cd-face" cx="376" cy="179" r="12"/><circle class="cd-face" cx="353" cy="204" r="12"/>
    <text class="cd-face-symbol cd-north" data-pad="strong" x="353" y="158">Y</text><text class="cd-face-symbol cd-west" data-pad="quick" x="330" y="183">X</text><text class="cd-face-symbol cd-east" data-pad="interact" x="376" y="183">B</text><text class="cd-face-symbol cd-south" data-pad="dodge" x="353" y="208">A</text>
    <path class="cd-face-bracket" d="M391 181 H409 V144 M409 181 V240"/>
    <circle class="cd-anchor" cx="192" cy="113" r="3"/><circle class="cd-anchor" cx="199" cy="136" r="3"/><circle class="cd-anchor" cx="246" cy="240" r="3"/><circle class="cd-anchor" cx="212" cy="191" r="3"/>
    <circle class="cd-anchor" cx="368" cy="113" r="3"/><circle class="cd-anchor" cx="361" cy="136" r="3"/><circle class="cd-anchor" cx="322" cy="240" r="3"/>
  `;
  for (const action of actions) {
    const callout = document.createElementNS(ns, 'g');
    callout.classList.add('cd-callout');
    callout.setAttribute('tabindex', '0');
    callout.setAttribute('role', 'img');
    callout.setAttribute('data-control', action.id);
    const lines = action.name === 'Shoot while aiming' ? ['Shoot', 'while aiming']
      : action.name === 'Stance / Ki Pulse' ? ['Stance /', 'Ki Pulse'] : [action.name];
    callout.innerHTML = `<path class="cd-leader" d="${action.path}"/>
      <rect class="cd-badge" x="${action.x}" y="${action.y}" width="40" height="24" rx="5"/>
      <text class="cd-key" x="${action.x + 20}" y="${action.y + 16}"></text>
      <text class="cd-action" x="${action.x + 46}" y="${action.y + (lines.length === 1 ? 16 : 10)}">${lines.map((line, index) => `<tspan x="${action.x + 46}" dy="${index ? 12 : 0}">${line}</tspan>`).join('')}</text>`;
    callout.dataset.helpTitle = action.name;
    callout.dataset.helpBody = `Default game action: ${action.name}.`;
    callout.dataset.helpTip = tip;
    svg.append(callout);
  }
  const combo = document.createElementNS(ns, 'g');
  combo.classList.add('cd-callout', 'cd-combo');
  combo.setAttribute('tabindex', '0');
  combo.setAttribute('role', 'img');
  combo.innerHTML = '<rect class="cd-badge" x="177" y="324" width="73" height="24" rx="5"/><text class="cd-key" x="213.5" y="340"></text><text class="cd-action" x="258" y="340">Native skill input</text>';
  combo.dataset.helpTitle = 'Native skill input';
  combo.dataset.helpBody = 'Guard + Quick is a native skill input.';
  combo.dataset.helpTip = tip;
  svg.append(combo);
  stage.append(svg);

  const note = document.createElement('p');
  note.className = 'controller-diagram__note';
  note.textContent = 'MWM adds custom chords and selected sword routes. Nioh keeps its other controller inputs.';
  section.append(header, stage, note);

  function show(value: Layout) {
    buttons.forEach((button, index) => button.setAttribute('aria-pressed', String(value === (index ? 'playstation' : 'xbox'))));
    for (const action of actions) {
      const callout = svg.querySelector<SVGGElement>(`[data-control="${action.id}"]`)!;
      const key = action.keys[value === 'xbox' ? 0 : 1];
      callout.querySelector('.cd-key')!.textContent = key;
      callout.setAttribute('aria-label', `${key}: ${action.name}`);
      callout.dataset.helpTitle = `${key} · ${action.name}`;
      const pad = svg.querySelector(`[data-pad="${action.id}"]`);
      if (pad) pad.textContent = key;
    }
    const comboKey = value === 'xbox' ? 'LB + X' : 'L1 + □';
    combo.querySelector('.cd-key')!.textContent = comboKey;
    combo.setAttribute('aria-label', `${comboKey}: Native skill input`);
    combo.dataset.helpTitle = `${comboKey} · Native skill input`;
    section.dataset.layout = value;
  }
  show(layout);
  return section;
}
