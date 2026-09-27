# Source trainer UI for the sword runtime.
# Packaged UI uses the same validated settings; gameplay acceptance remains separate.
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(os.environ.get('TANTO_MOD_ROOT', Path(__file__).resolve().parents[1]))
RUNTIME = Path(os.environ.get('NIOH_RUNTIME_HOME', ROOT/'runtime'))
CODE = Path(os.environ.get('TANTO_ENGINE_ROOT', ROOT.parent/'tanto-engine'))/'runtime' if not (ROOT/'runtime/engine_config.py').is_file() else ROOT/'runtime'
os.environ['TANTO_MOD_ROOT'] = str(ROOT)
os.environ['NIOH_RUNTIME_HOME'] = str(RUNTIME)
for folder in (CODE,):
    sys.path.insert(0, str(folder))

from catalogue import load_catalogue
from engine_config import DEFAULT_PRESET, move_capabilities, atomic_json, read_json, validate_preset, binding_for_preset
from game_controller import BindingCapture, GameController, binding_buttons, game_button_mask
from controller_reader import ControllerReader
from trace_reader import Trace
from process_support import active_runtime, process_matches, worker_command


def remap_preset(preset, source, target):
    # Keep a player's chosen physical buttons when switching controller mappings.
    # Translate saved bits through logical game buttons, then back into the destination mapping.
    # Reject missing equivalents and validate the translated preset before it can replace saved settings.
    """Preserve physical button meaning when the saved mask namespace changes."""
    buttons=binding_buttons(target['device'],target.get('button_map'))
    masks={game_button_mask(target['device'],mask,target.get('button_map')):mask for mask in buttons.values()}
    result=dict(preset)
    for key in ('modifier_mask','trigger_mask'):
        logical=game_button_mask(source['device'],preset[key],source.get('button_map'))
        if logical not in masks: raise ValueError('This controller mapping does not support a saved input')
        result[key]=masks[logical]
    return validate_preset(result)


def saved_moveset(value, calibration):
    # Load either a controller-aware moveset file or an older bare preset.
    # New bundles validate their shape and translate logical controls into the current calibration.
    # Old presets retain the current saved-mask namespace and still pass normal preset validation.
    if isinstance(value,dict) and value.get('kind')=='sword_moveset':
        if value.get('schema_version')!=1 or set(value)!={'schema_version','kind','preset','controller'}:
            raise ValueError('Unsupported saved moveset bundle')
        return remap_preset(validate_preset(value['preset']),value['controller'],calibration)
    return validate_preset(value)


def launch(script, arguments, folder):
    # Start a hidden worker with stdout and stderr saved in its session folder.
    # Keep executable and script arguments separate, including paths with spaces.
    # Return the process handle so the UI can report worker exit.
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'stdout.txt').open('w') as out, (folder/'stderr.txt').open('w') as err:
        return subprocess.Popen(worker_command(script, *arguments), stdout=out, stderr=err,
                                cwd=RUNTIME, creationflags=subprocess.CREATE_NO_WINDOW,
                                env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1') if getattr(sys,'frozen',False) else None)


def launch_engine():
    # Reuse an existing registered engine instead of launching another publisher.
    # Clear the stop signal only when starting a new session.
    # Keep UI reopening independent from gameplay attachment.
    if active_runtime() is not None:
        return None
    if process_matches(read_json(RUNTIME/'play-process.json')):
        return None
    if not (RUNTIME/'native/build/nioh_skill_runtime.dll').is_file():
        raise ValueError('Runtime is missing. Run runtime/native/Build.ps1 first.')
    (RUNTIME/'stop.flag').unlink(missing_ok=True)
    return launch(CODE/'supervisor.py', [], RUNTIME/'sessions'/('launcher-'+str(time.time_ns())))


def disable_engine():
    # Signal the registered runtime through its stop file.
    # Resolve the active runtime directory before writing the request.
    # Native recovery remains responsible for safe detachment.
    registration = active_runtime()
    runtime = Path(registration['runtime_path']) if registration else RUNTIME
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime/'stop.flag').write_text('stop\n')


class Trainer:
    def __init__(self, root, adopt_running=True):
        # Build the source trainer around saved mappings and the maintained catalogue.
        # Adopt an active engine before constructing move selectors and status widgets.
        # Keep recording and moveset editing accessible without repeated calibration.
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root = tk, ttk, root
        self.adopt_running = adopt_running
        self.next_runtime_check = 0
        self.runtime_registration = None
        # Resolve the running singleton before loading settings; opening another
        # UI must not create a second set of bindings for the same game process.
        if adopt_running:
            registration = active_runtime()
            if registration:
                self.set_runtime(registration)
        root.title('SKM · Single-Katana Moveset Mod')
        root.geometry('1030x760')
        root.minsize(900, 680)
        self.catalogue_path = Path((self.runtime_registration or {}).get('catalogue_path', os.environ.get('NIOH_CATALOGUE_PATH', ROOT/'data/moves.json')))
        os.environ['NIOH_CATALOGUE_PATH'] = str(self.catalogue_path)
        self.catalogue = load_catalogue(self.catalogue_path)
        self.calibration = read_json(RUNTIME/'controller-calibration.json')
        if not self.calibration:
            raise ValueError('Saved controller mapping is missing from the runtime folder')
        self.preset = validate_preset(read_json(RUNTIME/'controller-binding.json'))
        self.binding = binding_for_preset(self.calibration,self.preset)
        self.saved_calibration = self.calibration
        self.button_choices = binding_buttons(self.calibration['device'], self.calibration.get('button_map'))
        self.capture = self.capture_reader = self.capture_trace = None
        self.child = None
        self.status = tk.StringVar(value='Ready')
        self.inputs = tk.StringVar(value='Waiting for saved controller')
        self.notice = tk.StringVar(value='Edit a moveset, then Apply. Gameplay acceptance remains pending.')
        self.exe_path = tk.StringVar(value=read_json(RUNTIME/'trainer-settings.json', {}).get('nioh_exe', os.environ.get('NIOH_EXE', '')))
        if self.exe_path.get():
            os.environ['NIOH_EXE'] = self.exe_path.get()
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='SKM · Single-Katana Moveset Mod', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(outer, textvariable=self.status, font=('Segoe UI', 11)).pack(anchor='w', pady=(8, 4))
        bar = ttk.Frame(outer)
        bar.pack(fill='x')
        ttk.Button(bar, text='Enable / attach', command=self.enable).pack(side='left')
        ttk.Button(bar, text='Disable', command=self.disable).pack(side='left', padx=8)
        ttk.Label(bar, text='Closing this window leaves enabled moves running.').pack(side='left', padx=8)
        ttk.Label(outer, textvariable=self.inputs).pack(anchor='w', pady=8)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill='both', expand=True)
        play = ttk.Frame(notebook, padding=12)
        notebook.add(play, text='Moveset')
        self.capabilities = move_capabilities()
        def choices(flag, empty='Disabled'):
            # Build readable selector entries from reviewed capability rows.
            # Apply the caller's role predicate before exposing any move in that selector.
            # The resulting label-to-ID dictionary keeps display names separate from stable configuration identities.
            return {empty: None, **{move['name']+' ['+move['id']+']': move['id']
                for move in self.capabilities['moves'] if move[flag]}}
        self.move_names = choices('chord')
        self.skill_choices = choices('graph', 'Native')
        self.native_choices = choices('heavy_string', 'Native')
        self.frost_choices = choices('chord')
        self.native_move_choices = choices('native', 'Native')
        self.source_choices = {source['label']: source['id'] for source in self.capabilities['native_sources']}
        self.name, self.tap, self.hold = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.modifier, self.trigger, self.threshold = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.chord_stance = tk.StringVar()
        self.device_choice, self.slot_choice = tk.StringVar(value='Saved mapping'), tk.StringVar()
        self.slot_choice.trace_add('write', lambda *_: (
            # Cancel a pending controller binding when the selection it depends on changes.
            # Tk passes trace arguments that this callback intentionally does not use.
            # Discarding the partial press prevents it from binding under a different controller selection.
            self.cancel_capture()
        ))
        self.control_row(play, 0, 'Moveset name', ttk.Entry(play, textvariable=self.name, width=52))
        self.control_row(play, 1, 'Chord stance', ttk.Combobox(play, textvariable=self.chord_stance,
            values=self.capabilities['stances'], state='readonly'))
        for row, (label, variable) in enumerate((('Tap / release', self.tap), ('Hold', self.hold)), 2):
            self.control_row(play, row, label, ttk.Combobox(play, textvariable=variable,
                values=list(self.move_names), state='readonly', width=65))
        self.button_selectors = []
        for row, (label, variable) in enumerate((('Modifier', self.modifier), ('Trigger', self.trigger)), 4):
            frame = ttk.Frame(play)
            selector = ttk.Combobox(frame, textvariable=variable, values=list(self.button_choices), width=24, state='readonly')
            selector.pack(side='left')
            self.button_selectors.append(selector)
            ttk.Button(frame, text='Press to bind', command=lambda v=variable: (
                # Start press-to-bind for this particular form field.
                # Capture the loop's current variable as a default argument instead of the final loop value.
                # The result edits that field only; Apply remains responsible for saving the preset.
                self.begin_capture(v)
            )).pack(side='left', padx=8)
            self.control_row(play, row, label, frame)
        self.control_row(play, 6, 'Hold threshold (seconds)', ttk.Spinbox(play, textvariable=self.threshold, from_=.08, to=2, increment=.01, width=10))
        device = ttk.Combobox(play, textvariable=self.device_choice,
            values=['Saved mapping', 'DS4 mapping', *[f'XInput controller {n}' for n in range(1,5)]], state='readonly', width=24)
        device.bind('<<ComboboxSelected>>', self.choose_controller)
        self.control_row(play, 7, 'Controller mapping', device)
        self.control_row(play, 8, 'Game controller slot', ttk.Combobox(play, textvariable=self.slot_choice,
            values=['Auto (one controller)', '1', '2', '3', '4'], state='readonly', width=24))
        ttk.Label(play, text='Xbox and PS4/PS5 via XInput use slots 1–4. Saved mapping supports calibrated DS4. '
            'Direct HID requires a supported mapping. Release all controls before binding.', wraplength=780).grid(row=9, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(play, text='Cancel binding', command=self.cancel_capture).grid(row=10, column=1, sticky='w')
        native = ttk.Frame(notebook, padding=12)
        notebook.add(native, text='Native overrides')
        self.native_fields = {}
        for row, (key, label, options) in enumerate([('low_heavy', 'Low heavy string', self.native_choices),
                *[(stance, stance.title()+' heavy hold', self.skill_choices) for stance in self.capabilities['stances']]]):
            self.native_fields[key] = tk.StringVar()
            self.control_row(native, row, label, ttk.Combobox(native, textvariable=self.native_fields[key],
                values=list(options), state='readonly', width=65))
        self.native_toggles = {field: tk.BooleanVar() for field in ('okatsu_grapple', 'mid_light_ender', 'string_enabled')}
        for row, (field, label) in enumerate((('okatsu_grapple','Okatsu grapple'),
                ('mid_light_ender','Mid light ender'),('string_enabled','Imported light string')),4):
            ttk.Checkbutton(native, text=label, variable=self.native_toggles[field]).grid(row=row,column=0,columnspan=2,sticky='w')
        self.binding_table = ttk.Treeview(native, columns=('source','stance','move'), show='headings', height=5)
        for key, width in (('source',190),('stance',80),('move',550)):
            self.binding_table.heading(key,text=key.title()); self.binding_table.column(key,width=width,stretch=True)
        self.binding_table.grid(row=7,column=0,columnspan=2,sticky='ew',pady=8)
        self.binding_table.bind('<<TreeviewSelect>>', self.select_native_binding)
        editor = ttk.Frame(native); editor.grid(row=8,column=0,columnspan=2,sticky='w')
        self.binding_source, self.binding_stance, self.binding_move = tk.StringVar(), tk.StringVar(value='low'), tk.StringVar(value='Native')
        for variable, values, width in ((self.binding_source,list(self.source_choices),22),
                (self.binding_stance,['any',*self.capabilities['stances']],7),
                (self.binding_move,list(self.native_move_choices),58)):
            ttk.Combobox(editor,textvariable=variable,values=values,state='readonly',width=width).pack(side='left',padx=(0,6))
        actions=ttk.Frame(native); actions.grid(row=9,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Button(actions,text='Add / replace source + stance',command=self.set_native_binding).pack(side='left')
        ttk.Button(actions,text='Remove selected',command=self.remove_native_binding).pack(side='left',padx=8)
        ttk.Label(native,text='Only reviewed native sources are listed. Running/dodge attacks keep native priority. '
            'Graphs require one consistent stance. Low dodge follow-up requires Low Jin D.',wraplength=860).grid(row=10,column=0,columnspan=2,sticky='w')
        frost=ttk.Frame(notebook,padding=12); notebook.add(frost,text='Frost Moon')
        self.frost_fields={stance:tk.StringVar() for stance in self.capabilities['stances']}
        for row,(stance,field) in enumerate(self.frost_fields.items()):
            self.control_row(frost,row,stance.title(),ttk.Combobox(frost,textvariable=field,
                values=list(self.frost_choices),state='readonly',width=65))
        ttk.Label(frost,text='R1 / RB + the destination stance button twice. The engine owns the activation window '
            'and startup speed.',wraplength=780).grid(row=3,column=0,columnspan=2,sticky='w',pady=12)
        speed=ttk.Frame(notebook,padding=12); notebook.add(speed,text='Move speed')
        self.speed_fields={move['id']:tk.StringVar() for move in self.capabilities['moves'] if move['speed']}
        self.speed_choice=tk.StringVar(); self.speed_value=tk.StringVar(value='1')
        self.speed_choices={move['name']+' ['+move['id']+']':move['id'] for move in self.capabilities['moves'] if move['speed']}
        selector=ttk.Combobox(speed,textvariable=self.speed_choice,values=list(self.speed_choices),state='readonly',width=72)
        selector.bind('<<ComboboxSelected>>',self.select_speed)
        self.control_row(speed,0,'Move',selector)
        self.control_row(speed,1,'Speed multiplier',ttk.Spinbox(speed,textvariable=self.speed_value,
            from_=self.capabilities['speed']['min'],to=self.capabilities['speed']['max'],increment=.05,width=10))
        ttk.Button(speed,text='Set move speed',command=self.set_speed).grid(row=2,column=1,sticky='w')
        self.speed_summary=tk.Text(speed,height=12,width=95,wrap='word',state='disabled')
        self.speed_summary.grid(row=3,column=0,columnspan=2,sticky='ew',pady=12)
        scrollbar=ttk.Scrollbar(speed,command=self.speed_summary.yview)
        scrollbar.grid(row=3,column=2,sticky='ns'); self.speed_summary.configure(yscrollcommand=scrollbar.set)
        ttk.Label(speed,text='1 = original speed. Entire clips retain their start and end. Paired animations keep '
            'engine timing; Frost startup remains engine-owned.',wraplength=840).grid(row=4,column=0,columnspan=2,sticky='w')
        controls=ttk.Frame(outer); controls.pack(fill='x',pady=8)
        for title,command in (('Apply',self.apply),('Save moveset…',self.save),('Load moveset…',self.load),('Restore baseline',self.baseline)):
            ttk.Button(controls,text=title,command=command).pack(side='left',padx=(0,8))
        location=ttk.Frame(outer); location.pack(fill='x')
        ttk.Label(location,text='Game EXE (optional)').pack(side='left')
        ttk.Entry(location,textvariable=self.exe_path,width=65).pack(side='left',padx=8)
        ttk.Button(location,text='Browse…',command=self.choose_exe).pack(side='left')
        ttk.Label(outer, textvariable=self.notice, wraplength=950).pack(anchor='w', pady=(10,0))
        self.load_fields(self.preset)
        self.refresh_table()
        root.after(40, self.poll)

    def set_runtime(self, registration):
        # Adopt the directory published by the active engine registration.
        # Update both the UI path and worker environment.
        # Ensure subsequent controls address the same running engine.
        global RUNTIME
        RUNTIME = Path(registration['runtime_path'])
        os.environ['NIOH_RUNTIME_HOME'] = str(RUNTIME)
        self.runtime_registration = registration

    def adopt_active_runtime(self):
        # Reconnect the UI when another valid engine registration appears.
        # Load its catalogue and saved controller configuration before switching paths.
        # Avoid editing a stale runtime copy while another publisher is active.
        # Reconnect controls to the active singleton instead of editing another copy.
        if not self.adopt_running:
            return False
        registration = active_runtime()
        if registration is None or registration == self.runtime_registration:
            return False
        runtime = Path(registration['runtime_path'])
        calibration = read_json(runtime/'controller-calibration.json')
        preset = validate_preset(read_json(runtime/'controller-binding.json'))
        if not calibration:
            raise ValueError('Active runtime controller mapping is missing or inconsistent')
        binding = binding_for_preset(calibration,preset)
        catalogue_path = Path(registration.get('catalogue_path', self.catalogue_path))
        catalogue = load_catalogue(catalogue_path)
        if not isinstance(catalogue, dict) or 'moves' not in catalogue:
            raise ValueError('Active runtime catalogue is missing')
        self.set_runtime(registration)
        self.catalogue_path, self.catalogue = catalogue_path, catalogue
        os.environ['NIOH_CATALOGUE_PATH'] = str(catalogue_path)
        self.calibration, self.binding, self.preset = calibration, binding, preset
        self.cancel_capture()
        self.saved_calibration = calibration
        self.button_choices = binding_buttons(calibration['device'], calibration.get('button_map'))
        for selector in self.button_selectors: selector.configure(values=list(self.button_choices))
        self.refresh_table()
        self.notice.set('Connected to the running engine in ' + str(RUNTIME))
        return True

    def control_row(self, frame, number, label, widget):
        # Place a label and its input widget in the moveset grid.
        # Use the same column spacing for each setting.
        # Keep related controls aligned without duplicating geometry options.
        self.ttk.Label(frame, text=label).grid(row=number, column=0, sticky='w', padx=(0,20), pady=6)
        widget.grid(row=number, column=1, sticky='w', pady=6)

    def error(self, error):
        # Show an operation's failure in the trainer notice field.
        # Preserve the exception's concrete explanation.
        # Keep recoverable UI errors visible without opening another dialog.
        self.notice.set(str(error))

    def load_fields(self, preset):
        # Show a validated preset in the trainer's editable controls.
        # Convert stable move IDs and saved button masks into readable labels, then refresh binding and speed summaries.
        # These are form values; displaying a preset does not attach to Nioh or apply it to a running session.
        names = {v:k for k,v in self.move_names.items()}
        self.name.set(preset['name'])
        self.tap.set(names[preset['tap_move']]); self.hold.set(names[preset['hold_move']])
        labels = {mask:label for label,mask in self.button_choices.items()}
        self.modifier.set(labels[preset['modifier_mask']]); self.trigger.set(labels[preset['trigger_mask']])
        self.threshold.set(str(preset['hold_seconds'])); self.chord_stance.set(preset['chord_stance'])
        self.slot_choice.set(str(self.calibration['controller_slot']+1) if self.calibration.get('controller_slot') is not None else 'Auto (one controller)')
        self.preset = preset
        for stance,field in self.frost_fields.items():
            field.set(next(label for label,identifier in self.frost_choices.items() if identifier==preset['frost_moon'][stance]))
        for field,variable in self.native_toggles.items(): variable.set(preset[field])
        for key,field in self.native_fields.items():
            choices=self.native_choices if key=='low_heavy' else self.skill_choices
            value=preset[key] if key=='low_heavy' else preset['stance_holds'][key]
            field.set(next(label for label,identifier in choices.items() if identifier==value))
        self.skill_bindings=[dict(binding) for binding in preset['skill_bindings']]
        self.refresh_bindings()
        for identifier,field in self.speed_fields.items(): field.set(str(preset['move_settings'].get(identifier,{}).get('speed',1)))
        self.refresh_speeds()

    def form(self):
        # Collect the currently edited moveset without saving it yet.
        # Translate displayed labels back to IDs and numeric values, preserving unrelated preset fields.
        # Run the same engine validator used at startup so invalid combinations cannot bypass the UI.
        return validate_preset(dict(self.preset, name=self.name.get(), tap_move=self.move_names[self.tap.get()],
            hold_move=self.move_names[self.hold.get()], modifier_mask=self.button_choices[self.modifier.get()],
            trigger_mask=self.button_choices[self.trigger.get()], hold_seconds=float(self.threshold.get()),
            chord_stance=self.chord_stance.get(), low_heavy=self.native_choices[self.native_fields['low_heavy'].get()],
            skill_bindings=self.skill_bindings,
            frost_moon={stance:self.frost_choices[field.get()] for stance,field in self.frost_fields.items()},
            stance_holds={stance:self.skill_choices[self.native_fields[stance].get()] for stance in self.capabilities['stances']},
            move_settings={identifier:dict(speed=float(field.get())) for identifier,field in self.speed_fields.items() if float(field.get())!=1},
            **{field:variable.get() for field,variable in self.native_toggles.items()}))

    def refresh_bindings(self):
        # Redraw the list of native skill replacements the player has selected.
        # Use list indices as row IDs and translate source/move IDs into their readable labels.
        # Rebuilding the table changes presentation only; Apply remains the persistence boundary.
        self.binding_table.delete(*self.binding_table.get_children())
        names={value:key for key,value in self.native_move_choices.items()}
        sources={value:key for key,value in self.source_choices.items()}
        for index,binding in enumerate(self.skill_bindings):
            self.binding_table.insert('', 'end', iid=str(index), values=(sources[binding['source']],binding['stance'],names[binding['move']]))

    def select_native_binding(self, event=None):
        # Copy the highlighted replacement into the row editor.
        # Read the table's source, stance and move labels in the same order they were displayed.
        # No selection leaves the current editor values alone and writes no settings.
        selected=self.binding_table.selection()
        if selected:
            values=self.binding_table.item(selected[0],'values')
            for field,value in zip((self.binding_source,self.binding_stance,self.binding_move),values): field.set(value)

    def set_native_binding(self):
        # Replace just one native skill and stance combination in the pending form.
        # Temporarily install the candidate list and validate the entire moveset, rolling back on failure.
        # Choosing Native removes that override; other skill/stance replacements remain intact.
        try:
            source,stance,move=self.source_choices[self.binding_source.get()],self.binding_stance.get(),self.native_move_choices[self.binding_move.get()]
            bindings=[binding for binding in self.skill_bindings if (binding['source'],binding['stance'])!=(source,stance)]
            if move is not None: bindings.append(dict(source=source,stance=stance,move=move))
            previous=self.skill_bindings; self.skill_bindings=bindings
            try: self.form()
            except (ValueError,KeyError): self.skill_bindings=previous; raise
            self.refresh_bindings()
            self.notice.set('Native binding edited. Apply to save.')
        except (ValueError,KeyError) as error: self.error(error)

    def remove_native_binding(self):
        # Remove highlighted overrides so those inputs return to native behavior.
        # Delete selected list indices from highest to lowest to avoid shifting later targets.
        # Refresh the pending table; the player must still Apply to save the edited moveset.
        for index in sorted(map(int,self.binding_table.selection()),reverse=True): self.skill_bindings.pop(index)
        self.refresh_bindings()

    def select_speed(self, event=None):
        # Show the selected move's current multiplier in the speed editor.
        # Read its existing form variable rather than inventing a new default on every selection.
        # Selecting a move does not change its speed or write the preset.
        self.speed_value.set(self.speed_fields[self.speed_choices[self.speed_choice.get()]].get())

    def set_speed(self):
        # Try a new multiplier for the selected reviewed move.
        # Validate the full form and restore the previous field if conversion or bounds checks fail.
        # A successful edit updates the summary but waits for Apply before saving.
        try:
            identifier=self.speed_choices[self.speed_choice.get()]
            old=self.speed_fields[identifier].get(); self.speed_fields[identifier].set(self.speed_value.get())
            try: self.form()
            except (ValueError,KeyError): self.speed_fields[identifier].set(old); raise
            self.refresh_speeds()
            self.notice.set('Move speed edited. Apply to save.')
        except (ValueError,KeyError) as error: self.error(error)

    def refresh_speeds(self):
        # Summarize only moves whose playback differs from their original speed.
        # Temporarily unlock the read-only text widget, replace its contents, then lock it again.
        # Keep the separate numeric editor synchronized with the selected move's form value.
        self.speed_summary.configure(state='normal')
        self.speed_summary.delete('1.0','end')
        self.speed_summary.insert('1.0','\n'.join(f'{label}: {self.speed_fields[identifier].get()}×' for label,identifier in self.speed_choices.items()
            if float(self.speed_fields[identifier].get())!=1) or 'All moves: original speed (1×)')
        self.speed_summary.configure(state='disabled')
        if self.speed_choice.get(): self.select_speed()

    def choose_controller(self, event=None):
        # Switch mappings while keeping the intended logical buttons in the moveset.
        # Cancel pending capture, remap through the old/new calibrations and rebuild the available button labels.
        # Hardware protocol support is checked here; this does not certify a physical controller in gameplay.
        try:
            self.cancel_capture()
            preset=self.form()
            previous=self.calibration
            choice=self.device_choice.get()
            calibration=(self.saved_calibration if choice=='Saved mapping' else
                read_json(ROOT/'data/controller-calibration.json') if choice=='DS4 mapping' else dict(schema=1,
                device=dict(backend='xinput',slot=int(choice[-1])-1),lb_mask=0x100,
                lt=dict(axis='lt',neutral=0,full=255),controller_slot=int(choice[-1])-1))
            preset=remap_preset(preset,previous,calibration)
            self.calibration=calibration
            self.button_choices=binding_buttons(calibration['device'],calibration.get('button_map'))
            for selector in self.button_selectors: selector.configure(values=list(self.button_choices))
            self.load_fields(preset)
            self.notice.set('Controller selected. Apply to save; press to bind after releasing controls.')
        except (ValueError,KeyError) as error: self.error(error)

    def begin_capture(self, variable):
        # Arm press-to-bind for one pending trainer field.
        # Use the running engine's controller observations when available, otherwise use the OS reader.
        # Keep trace resources owned by this capture and close them if setup fails or capture is cancelled.
        try:
            self.cancel_capture()
            calibration=dict(self.calibration,controller_slot=None if self.slot_choice.get().startswith('Auto') else int(self.slot_choice.get())-1)
            self.capture=BindingCapture(calibration); self.capture_target=variable
            if process_matches(read_json(RUNTIME/'play-process.json')):
                session=read_json(RUNTIME/'boss-session.json')
                self.capture_trace=Trace(session['session']['pid'],'NiohBossRepeatTrace_v2',tag=session['config_tag'])
                self.capture_reader=ControllerReader(backends=[GameController(self.capture_trace,calibration)])
            else: self.capture_reader=ControllerReader()
            self.notice.set(self.capture.status)
        except (OSError,ValueError,KeyError,TypeError) as error:
            self.cancel_capture(); self.error(error)

    def cancel_capture(self):
        # Stop press-to-bind without changing the pending or saved button choice.
        # Drop the temporary reader and release any shared-memory trace handle.
        # This also clears partially observed presses before another binding starts.
        self.capture=self.capture_reader=None
        if self.capture_trace: self.capture_trace.close()
        self.capture_trace=None

    def poll_capture(self):
        # Advance the binding listener from its latest controller observations.
        # A successful single-button result updates the target form label and closes the temporary capture.
        # Until then, show release/reconnect guidance; Apply still controls saving the choice.
        if not self.capture: return
        for event in self.capture_reader.poll():
            result=self.capture.process(event)
            if result:
                label=next(label for label,mask in self.button_choices.items() if mask==result['mask'])
                self.capture_target.set(label)
                self.cancel_capture()
                self.notice.set('Bound '+label+'. Apply to save.')
                return
            self.notice.set(self.capture.status)

    def apply(self):
        # Persist the edited preset in the active runtime's binding format.
        # Use atomic replacement so the publisher sees one complete configuration.
        # Report failure without claiming that the new moveset was applied.
        try:
            preset = self.form()
            calibration=dict(self.calibration,controller_slot=None if self.slot_choice.get().startswith('Auto') else int(self.slot_choice.get())-1)
            self.cancel_capture()
            self.adopt_active_runtime()
            self.calibration=calibration
            self.button_choices=binding_buttons(calibration['device'],calibration.get('button_map'))
            for selector in self.button_selectors: selector.configure(values=list(self.button_choices))
            binding = binding_for_preset(self.calibration, preset)
            atomic_json(RUNTIME/'controller-calibration.json', self.calibration)
            atomic_json(RUNTIME/'controller-binding.json', preset)
            self.binding, self.preset = binding, preset
            self.load_fields(preset)
            self.notice.set('Preset saved. An active engine will recover and reattach. Release controls to resume.')
            return True
        except (OSError, ValueError, KeyError) as error:
            self.error(error)
            return False

    def save(self):
        # Choose a destination before applying a reusable preset.
        # Write only after the user chooses a destination.
        # Keep exported presets consistent with the active moveset.
        from tkinter import filedialog
        folder = RUNTIME/'presets'
        folder.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self.root, initialdir=folder, defaultextension='.json', filetypes=[('Movesets','*.json')])
        if path:
            if not self.apply(): return
            try: atomic_json(path,dict(schema_version=1,kind='sword_moveset',preset=self.preset,
                controller={key:self.calibration[key] for key in ('device','button_map') if key in self.calibration}))
            except OSError as error: self.error(error)

    def load(self):
        # Read a selected preset and populate the same validated form.
        # Apply through the normal binding path after parsing succeeds.
        # Avoid a separate import path with different runtime behavior.
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, initialdir=RUNTIME/'presets', filetypes=[('Movesets','*.json')])
        if path:
            try:
                self.load_fields(saved_moveset(read_json(path),self.calibration))
                self.apply()
            except (OSError, ValueError, KeyError) as error: self.error(error)

    def baseline(self):
        # Restore the maintained sword preset into the form.
        # Apply it through the normal binding persistence path.
        # Provide one reproducible baseline for gameplay comparisons.
        try:
            baseline=read_json(ROOT/'data/controller-calibration.json')
            self.load_fields(remap_preset(DEFAULT_PRESET,baseline,self.calibration))
            self.apply()
        except (OSError,ValueError,KeyError) as error: self.error(error)

    def choose_exe(self):
        # Store a user-selected Nioh executable path in the form.
        # Defer startup changes until Enable is requested.
        # Avoid replacing a running process during path selection.
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, title='Select nioh.exe', filetypes=[('Nioh','nioh.exe')])
        if path:
            self.exe_path.set(path)
            self.notice.set('Game path selected. Enable uses it after the current session has stopped.')

    def enable(self):
        # Apply the selected moveset and persist the optional executable path.
        # Launch the existing supervisor only when its worker is absent.
        # Let the engine handle process attachment and lifecycle recovery.
        if not self.apply(): return
        try:
            if self.exe_path.get(): os.environ['NIOH_EXE'] = self.exe_path.get()
            else: os.environ.pop('NIOH_EXE', None)
            atomic_json(RUNTIME/'trainer-settings.json', dict(nioh_exe=self.exe_path.get()))
            if self.child is None or self.child.poll() is not None:
                self.child = launch_engine()
            self.notice.set('Attachment requested. The engine waits for valid gameplay and reuses the saved mapping.')
        except (OSError, ValueError) as error: self.error(error)

    def disable(self):
        # Resolve the current engine and request its normal stop sequence.
        # Keep the UI open while native recovery completes.
        # Avoid tearing down an imported move mid-animation.
        try:
            self.adopt_active_runtime()
            disable_engine()
            self.notice.set('Disable requested. Any active move keeps its native recovery before detaching.')
        except (OSError, ValueError, KeyError) as error: self.error(error)

    def refresh_table(self):
        # Refresh product labels after adopting a running instance.
        # Product JSON owns the move definitions.
        # Recording and catalogue editing belong to the recorder.
        self.catalogue = load_catalogue(self.catalogue_path)
        self.load_fields(self.preset)

    def poll(self):
        # Refresh engine and recorder status without reading the game screen.
        # Combine process liveness with published telemetry and worker errors.
        # Schedule the next UI refresh after reporting recoverable read failures.
        try:
            self.poll_capture()
            if time.monotonic() >= self.next_runtime_check:
                self.adopt_active_runtime()
                self.next_runtime_check = time.monotonic() + .5
            value = read_json(RUNTIME/'play-status.json', {})
            alive = process_matches(read_json(RUNTIME/'play-process.json'))
            # A retained status file cannot establish a live publisher after a
            # crash. Read input telemetry only while its process identity matches.
            live = read_json(Path(value['trace'])/'live.json', {}) if alive and 'trace' in value else {}
            self.inputs.set(live.get('controller', 'Waiting for engine controller detection') +
                            ' | ' + (', '.join(live.get('buttons', [])) or 'No buttons held'))
            active_state = value.get('state', 'disabled')
            if not alive and active_state in ('enabled', 'preparing', 'starting', 'waiting_for_resources', 'refreshing_encounter', 'waiting_for_recovery'):
                active_state = 'publisher stopped'
            detail = value.get('limitation', value.get('detail', ''))
            self.status.set(active_state.replace('_', ' ').capitalize() + (': '+str(detail)[-180:] if detail else ''))
        except (OSError, ValueError, KeyError) as error:
            self.error(error)
        self.root.after(100, self.poll)


def main(argv=None):
    # Route source UI and headless lifecycle controls through the same functions.
    # Parse only maintained controls before constructing any widgets.
    # Disable remains cooperative and can run without opening the trainer.
    parser = argparse.ArgumentParser(description='Control the Nioh sword runtime')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--enable', action='store_true', help='Enable without opening the UI')
    mode.add_argument('--disable', action='store_true', help='Cooperatively disable without opening the UI')
    parser.add_argument('--ui-smoke', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    import shutil
    for source,target in [('controller-calibration.json','controller-calibration.json'),('preset.json','controller-binding.json')]:
        if not (RUNTIME/target).exists(): shutil.copyfile(ROOT/'data'/source,RUNTIME/target)
    native = RUNTIME/'native/build'
    native.mkdir(parents=True,exist_ok=True)
    for source in (CODE/'native/build').glob('*.dll'):
        if source.resolve() != (native/source.name).resolve(): shutil.copyfile(source,native/source.name)
    if args.disable:
        disable_engine()
        return 0
    if args.enable:
        settings = read_json(RUNTIME/'trainer-settings.json', {})
        if settings.get('nioh_exe'): os.environ['NIOH_EXE'] = settings['nioh_exe']
        launch_engine()
        return 0
    import tkinter as tk
    root = tk.Tk()
    if args.ui_smoke: root.withdraw()
    app = Trainer(root, adopt_running=not bool(args.ui_smoke))
    if args.ui_smoke:
        atomic_json(args.ui_smoke, dict(passed=True, rows=len(app.catalogue['moves']), game_access=False))
        root.after(200, root.destroy)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
