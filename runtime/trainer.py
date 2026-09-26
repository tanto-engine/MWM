# Source trainer UI for the sword runtime.
# TODO: Revisit EXE packaging only after the gameplay readiness gate passes.
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('NIOH_RUNTIME_HOME', ROOT/'runtime'))
CODE = Path(__file__).resolve().parent
os.environ['NIOH_RUNTIME_HOME'] = str(RUNTIME)
for folder in (CODE, ROOT/'catalogue'):
    sys.path.insert(0, str(folder))

from catalogue import load_catalogue
from engine_config import DEFAULT_PRESET, MOVE_VARIANTS, atomic_json, read_json, validate_preset, binding_for_preset
from game_controller import binding_buttons
from process_support import active_runtime, process_matches, worker_command


def launch(script, arguments, folder):
    # Start a hidden worker with stdout and stderr saved in its session folder.
    # Keep executable and script arguments separate, including paths with spaces.
    # Return the process handle so the UI can report worker exit.
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'stdout.txt').open('w') as out, (folder/'stderr.txt').open('w') as err:
        return subprocess.Popen(worker_command(script, *arguments), stdout=out, stderr=err,
                                cwd=RUNTIME, creationflags=subprocess.CREATE_NO_WINDOW)


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
        root.title('Nioh 1 Sword Mod')
        root.geometry('1030x760')
        root.minsize(900, 680)
        self.catalogue_path = Path((self.runtime_registration or {}).get('catalogue_path', os.environ.get('NIOH_CATALOGUE_PATH', ROOT/'outputs/Nioh1-Sword-Move-Observations.xlsx')))
        os.environ['NIOH_CATALOGUE_PATH'] = str(self.catalogue_path)
        self.catalogue = load_catalogue(self.catalogue_path)
        self.calibration = read_json(RUNTIME/'controller-calibration.json')
        if not self.calibration:
            raise ValueError('Saved controller mapping is missing from the runtime folder')
        self.preset = validate_preset(read_json(RUNTIME/'controller-binding.json'))
        self.binding = binding_for_preset(self.calibration,self.preset)
        self.button_choices = binding_buttons(self.calibration['device'])
        self.child = self.record_child = None
        self.record_folder = None
        self.device_matched = False
        self.last_buttons = 0
        self.status = tk.StringVar(value='Ready')
        self.inputs = tk.StringVar(value='Waiting for saved controller')
        self.notice = tk.StringVar(value='Low Triangle: Jin string D taps, launcher hold. High LB + Square: Jin somersault.')
        self.record_status = tk.StringVar(value='Record action data during a fight. Imports update known sword moves.')
        self.exe_path = tk.StringVar(value=read_json(RUNTIME/'trainer-settings.json', {}).get('nioh_exe', os.environ.get('NIOH_EXE', '')))
        if self.exe_path.get():
            os.environ['NIOH_EXE'] = self.exe_path.get()
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Nioh 1 Sword Mod', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
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
        research = ttk.Frame(notebook, padding=12)
        notebook.add(play, text='Moveset')
        notebook.add(research, text='Catalogue and recording')
        self.move_names = {'Disabled': None}
        # Recorded source actions remain visible in research without entering
        # playable selectors until an adapter explicitly marks them selectable.
        for move in self.catalogue['moves']:
            if move['id'] in MOVE_VARIANTS:
                self.move_names[f"{move['source']['actor']} — {move['name']}"] = move['id']
        self.tap = tk.StringVar()
        self.hold = tk.StringVar()
        self.name = tk.StringVar()
        self.modifier = tk.StringVar()
        self.trigger = tk.StringVar()
        self.threshold = tk.StringVar()
        self.control_row(play, 0, 'Moveset name', ttk.Entry(play, textvariable=self.name, width=42))
        self.tap_selector = ttk.Combobox(play, textvariable=self.tap, values=list(self.move_names), state='readonly', width=42)
        self.hold_selector = ttk.Combobox(play, textvariable=self.hold, values=list(self.move_names), state='readonly', width=42)
        self.control_row(play, 1, 'Tap / release', self.tap_selector)
        self.control_row(play, 2, 'Hold', self.hold_selector)
        self.control_row(play, 3, 'Modifier button', ttk.Combobox(play, textvariable=self.modifier, values=list(self.button_choices), width=20, state='readonly'))
        self.control_row(play, 4, 'Trigger button', ttk.Combobox(play, textvariable=self.trigger, values=list(self.button_choices), width=20, state='readonly'))
        self.control_row(play, 5, 'Hold threshold (seconds)', ttk.Spinbox(play, textvariable=self.threshold, from_=.08, to=2, increment=.01, width=10))
        self.native_choices = {'Native':None, 'Jin string C':'jin_hayabusa.action_0bc0',
                              'Jin string D':'jin_hayabusa.action_0c6e'}
        self.skill_choices = {'Native':None, 'Jin launcher':'jin_hayabusa.action_0c79',
                             'Jin downward slash':'jin_hayabusa.action_0c75', 'Jin somersault':'jin_hayabusa.action_0c81', 'Izuna Drop':'jin_hayabusa.izuna_drop', 'Flying Swallow':'jin_hayabusa.action_0c71'}
        self.native_fields = {}
        for row,(key,label,choices) in enumerate([('low_heavy','Low Triangle taps',self.native_choices),
                *[(stance,stance.title()+' Triangle hold',self.skill_choices) for stance in ('low','mid','high')]],6):
            self.native_fields[key]=tk.StringVar()
            self.control_row(play,row,label,ttk.Combobox(play,textvariable=self.native_fields[key],values=list(choices),state='readonly',width=42))
        frost=ttk.LabelFrame(play,text='Frost Moon: RB + same stance button twice',padding=10)
        frost.grid(row=0,column=2,rowspan=10,sticky='nw',padx=(24,0))
        self.frost_choices={'Disabled':None,'Jin downward slash':'jin_hayabusa.action_0c75', 'Jin somersault':'jin_hayabusa.action_0c81',
                            'Izuna Drop':'jin_hayabusa.izuna_drop','Flying Swallow':'jin_hayabusa.action_0c71'}
        self.frost_fields={stance:tk.StringVar() for stance in ('low','mid','high')}
        for row,(stance,field) in enumerate(self.frost_fields.items()):
            self.control_row(frost,row,stance.title(),ttk.Combobox(frost,textvariable=field,
                values=list(self.frost_choices),state='readonly',width=24))
        self.frost_window=tk.StringVar(); self.frost_speed=tk.StringVar()
        self.control_row(frost,3,'Window (seconds)',ttk.Spinbox(frost,textvariable=self.frost_window,from_=.1,to=1.5,increment=.05,width=8))
        self.control_row(frost,4,'Startup speed (1–8×)',ttk.Spinbox(frost,textvariable=self.frost_speed,from_=1,to=8,increment=1,width=8))
        ttk.Label(frost,text='Choose a different stance. Window begins when Ki Pulse becomes available.\nLow: Flying Swallow. Mid: somersault. High: downward sword slash.',wraplength=310).grid(row=5,column=0,columnspan=2,sticky='w',pady=8)
        self.native_toggles={field:tk.BooleanVar() for field in ('tiger_sprint','mid_light_ender')}
        for row,(field,label) in enumerate((('tiger_sprint','Tiger Sprint override'),('mid_light_ender','Mid light → LB + Triangle: Living Weapon heavy')),6):
            ttk.Checkbutton(frost,text=label,variable=self.native_toggles[field]).grid(row=row,column=0,columnspan=2,sticky='w')
        self.guard_choices=dict(self.frost_choices, **{'Okatsu dash':'okatsu.charged_rush','Okatsu leap':'okatsu.leaping_slash'})
        self.guard_light=tk.StringVar()
        self.control_row(frost,8,'High LB + Square',ttk.Combobox(frost,textvariable=self.guard_light,
            values=list(self.guard_choices),state='readonly',width=24))
        controls = ttk.Frame(play)
        controls.grid(row=10, column=0, columnspan=2, sticky='w', pady=12)
        for title, command in (('Apply', self.apply), ('Save moveset…', self.save), ('Load moveset…', self.load), ('Restore baseline', self.baseline)):
            ttk.Button(controls, text=title, command=command).pack(side='left', padx=(0,8))
        ttk.Label(play, text='Sword required. One hold threshold applies to the chord and Triangle. Gameplay acceptance remains pending.', wraplength=820).grid(row=11, column=0, columnspan=2, sticky='w', pady=8)
        location = ttk.Frame(play)
        location.grid(row=12, column=0, columnspan=2, sticky='ew', pady=8)
        ttk.Label(location, text='Game EXE (optional)').pack(side='left')
        ttk.Entry(location, textvariable=self.exe_path, width=55).pack(side='left', padx=8)
        ttk.Button(location, text='Browse…', command=self.choose_exe).pack(side='left')
        record_bar = ttk.Frame(research)
        # The recorder runs out of process; widget callbacks only launch it or
        # signal Stop, leaving retries and evidence flushing with the worker.
        record_bar.pack(fill='x')
        self.boss = tk.StringVar(value='okatsu')
        ttk.Label(record_bar, text='Boss').pack(side='left')
        ttk.Entry(record_bar, textvariable=self.boss, width=20).pack(side='left', padx=8)
        ttk.Button(record_bar, text='Record encounter', command=self.start_recording).pack(side='left', padx=4)
        ttk.Button(record_bar, text='Stop recording', command=self.stop_recording).pack(side='left', padx=4)
        ttk.Button(record_bar, text='Import recording…', command=self.import_recording).pack(side='left', padx=4)
        ttk.Label(research, textvariable=self.record_status, wraplength=880).pack(anchor='w', pady=8)
        self.table = ttk.Treeview(research, columns=('boss', 'move', 'action', 'motion', 'status'), show='headings', height=10)
        for col, title, width in [('boss','Boss',95), ('move','Move',260), ('action','Action',75), ('motion','Motion',75), ('status','Status',230)]:
            self.table.heading(col, text=title)
            self.table.column(col, width=width, stretch=col in ('move','status'))
        self.table.pack(fill='both', expand=True)
        ttk.Button(research, text='Name selected move…', command=self.rename_move).pack(anchor='w', pady=8)
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
        self.button_choices = binding_buttons(calibration['device'])
        self.device_matched = False
        self.last_buttons = 0
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
        # Populate move and button selectors from a validated preset.
        # Translate stable IDs and masks into displayed labels.
        # Keep saved configuration independent of UI selection order.
        names = {v:k for k,v in self.move_names.items()}
        self.name.set(preset['name'])
        self.tap.set(names[preset['tap_move']])
        self.hold.set(names[preset['hold_move']])
        labels = {mask: label for label, mask in self.button_choices.items()}
        self.modifier.set(labels[preset['modifier_mask']])
        self.trigger.set(labels[preset['trigger_mask']])
        self.threshold.set(str(preset['hold_seconds']))
        self.preset=preset
        for stance,field in self.frost_fields.items():
            field.set(next(label for label,identifier in self.frost_choices.items() if identifier==preset['frost_moon'][stance]))
        self.frost_window.set(str(preset['frost_window_seconds'])); self.frost_speed.set(str(preset['frost_startup_speed']))
        for field,variable in self.native_toggles.items():
            variable.set(any(b['source']=='tiger_sprint' for b in preset['skill_bindings']) if field=='tiger_sprint' else preset[field])
        self.guard_light.set(next(label for label,identifier in self.guard_choices.items() if identifier==next((b['move'] for b in preset['skill_bindings'] if b['source']=='guard_light' and b['stance']=='high'),None)))
        for key,field in self.native_fields.items():
            choices=self.native_choices if key=='low_heavy' else self.skill_choices
            value=preset[key] if key=='low_heavy' else preset['stance_holds'][key]
            field.set(next(label for label,identifier in choices.items() if identifier==value))

    def form(self):
        # Read the current selectors into the engine's preset schema.
        # Resolve displayed move names and button labels to stable values.
        # Validate before anything can replace the active binding file.
        return validate_preset(dict(self.preset, name=self.name.get(), tap_move=self.move_names[self.tap.get()],
            hold_move=self.move_names[self.hold.get()], modifier_mask=self.button_choices[self.modifier.get()],
            trigger_mask=self.button_choices[self.trigger.get()], hold_seconds=float(self.threshold.get()),
            low_heavy=self.native_choices[self.native_fields['low_heavy'].get()],
            skill_bindings=[b for b in self.preset['skill_bindings'] if b['source']!='tiger_sprint' and (b['source'],b['stance'])!=('guard_light','high')]
                +([next((b for b in self.preset['skill_bindings'] if b['source']=='tiger_sprint'),dict(source='tiger_sprint',stance='any',move='okatsu.charged_rush'))] if self.native_toggles['tiger_sprint'].get() else [])
                +([dict(source='guard_light',stance='high',move=self.guard_choices[self.guard_light.get()])] if self.guard_choices[self.guard_light.get()] else []),
            frost_moon={stance:self.frost_choices[field.get()] for stance,field in self.frost_fields.items()},
            frost_window_seconds=float(self.frost_window.get()),frost_startup_speed=int(self.frost_speed.get()),
            mid_light_ender=self.native_toggles['mid_light_ender'].get(),
            stance_holds={stance:self.skill_choices[self.native_fields[stance].get()] for stance in ('low','mid','high')}))

    def apply(self):
        # Persist the edited preset in the active runtime's binding format.
        # Use atomic replacement so the publisher sees one complete configuration.
        # Report failure without claiming that the new moveset was applied.
        try:
            preset = self.form()
            self.adopt_active_runtime()
            binding = binding_for_preset(self.calibration, preset)
            atomic_json(RUNTIME/'controller-binding.json', preset)
            self.binding, self.preset = binding, preset
            self.load_fields(preset)
            self.notice.set('Preset saved. An active engine will recover and reattach. Release controls to resume.')
            return True
        except (OSError, ValueError, KeyError) as error:
            self.error(error)
            return False

    def save(self):
        # Apply the current form before saving a reusable preset.
        # Write only after the user chooses a destination.
        # Keep exported presets consistent with the active moveset.
        from tkinter import filedialog
        if not self.apply(): return
        folder = RUNTIME/'presets'
        folder.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self.root, initialdir=folder, defaultextension='.json', filetypes=[('Movesets','*.json')])
        if path:
            try: atomic_json(path, self.preset)
            except OSError as error: self.error(error)

    def load(self):
        # Read a selected preset and populate the same validated form.
        # Apply through the normal binding path after parsing succeeds.
        # Avoid a separate import path with different runtime behavior.
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, initialdir=RUNTIME/'presets', filetypes=[('Movesets','*.json')])
        if path:
            try:
                self.load_fields(validate_preset(read_json(path)))
                self.apply()
            except (OSError, ValueError, KeyError) as error: self.error(error)

    def baseline(self):
        # Restore the maintained sword preset into the form.
        # Apply it through the normal binding persistence path.
        # Provide one reproducible baseline for gameplay comparisons.
        self.load_fields(DEFAULT_PRESET)
        self.apply()

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

    def start_recording(self):
        # Start or resume an encounter folder for the specified boss.
        # Reject a folder belonging to another boss and preserve existing takes.
        # Run capture in a worker so recording cannot block the UI.
        from tkinter import filedialog
        if self.record_child is not None and self.record_child.poll() is None: return
        parent = RUNTIME/'recordings'
        parent.mkdir(exist_ok=True)
        folder = filedialog.askdirectory(parent=self.root, initialdir=parent, title='Choose an encounter folder (existing captures resume)')
        if not folder: return
        try:
            from encounter_recording import validate_boss_id
            boss_id = validate_boss_id(self.boss.get().strip())
            recording_folder = Path(folder)
            manifest = read_json(recording_folder/'encounter.json', {})
            if manifest and manifest.get('boss_id') != boss_id:
                raise ValueError('This folder belongs to another boss. Choose that boss or a new folder.')
            self.record_folder = recording_folder
            stop = self.record_folder/'stop.flag'
            stop.unlink(missing_ok=True)
            self.record_logs = self.record_folder/'workers'/str(time.time_ns())
            self.record_child = launch(ROOT/'runtime/encounter_recording.py',
                ['--boss-id', boss_id, '--outdir', folder, '--stop-file', stop], self.record_logs)
            self.record_status.set('Starting encounter recording. Existing takes are preserved.')
        except (OSError, ValueError) as error: self.error(error)

    def stop_recording(self):
        # Request a cooperative recorder stop through its signal file.
        # Let the worker close the active take and reconstruct retained evidence.
        # Avoid terminating it while an event is being written.
        if self.record_folder:
            try:
                (self.record_folder/'stop.flag').write_text('stop\n')
                self.record_status.set('Stopping recording and reconstructing the retained actions…')
            except OSError as error: self.error(error)

    def import_recording(self):
        # Reconstruct a stopped encounter and merge its stable move identities.
        # Keep recorded but unimplemented actions unavailable for selection.
        # Refresh the catalogue view and synchronized workbook after import.
        from tkinter import filedialog
        folder = filedialog.askdirectory(parent=self.root, initialdir=self.record_folder or RUNTIME/'recordings', title='Import recorded encounter')
        if not folder: return
        try:
            from encounter_recording import reconstruct_encounter
            from catalogue import merge_recording
            folder = Path(folder)
            if (self.record_folder == folder and self.record_child is not None and
                    self.record_child.poll() is None):
                raise ValueError('Stop the encounter recording before importing its final observations.')
            reconstruct_encounter(folder)
            merge_recording(self.catalogue_path, folder/'reconstruction.json')
            self.refresh_table()
            self.sync_catalogue_workbook('Recorded observations imported; unimplemented actions stay unavailable for play.')
        except (OSError, ValueError, KeyError, TypeError) as error: self.error(error)

    def rename_move(self):
        # Rename the selected catalogue identity through the shared edit function.
        # Keep source IDs and implementation status unchanged.
        # Synchronize the workbook after saving the readable label.
        from tkinter import simpledialog
        selected = self.table.selection()
        if not selected: return
        name = simpledialog.askstring('Move name', 'Descriptive move name', parent=self.root, initialvalue=self.table.item(selected[0], 'values')[1])
        if name:
            try:
                from catalogue import rename_move
                rename_move(self.catalogue_path, selected[0], name)
                self.refresh_table()
                self.sync_catalogue_workbook('Catalogue name saved.')
            except (OSError, ValueError, KeyError) as error: self.error(error)

    def sync_catalogue_workbook(self, message):
        # Regenerate the workbook after a catalogue mutation succeeds.
        # Report file locks and sync errors separately from the saved catalogue edit.
        # Never imply that a failed spreadsheet write rolled back the catalogue.
        try:
            from spreadsheet_sync import sync_workbook
            sync_workbook(self.catalogue_path)
            self.notice.set(message + ' Workbook and Downloads copy synchronized.')
        except (OSError, ValueError) as error:
            # Catalogue mutation already succeeded. A workbook lock/import error
            # must never roll that result back or pretend the workbook updated.
            self.notice.set(message + ' Workbook sync failed: ' + str(error))

    def refresh_table(self):
        # Reload catalogue rows and rebuild the selectable move labels.
        # Preserve stable move IDs as table identities and preset values.
        # Display unclassified records without making them playable.
        self.catalogue = load_catalogue(self.catalogue_path)
        self.move_names = {'Disabled': None}
        for move in self.catalogue['moves']:
            if move.get('implementation', {}).get('selectable'):
                self.move_names[f"{move['source']['actor']} — {move['name']}"] = move['id']
        self.tap_selector.configure(values=list(self.move_names))
        self.hold_selector.configure(values=list(self.move_names))
        self.load_fields(self.preset)
        self.table.delete(*self.table.get_children())
        for move in self.catalogue['moves']:
            source = move.get('source', {})
            self.table.insert('', 'end', iid=move['id'], values=(move.get('boss_id') or 'Player', move['name'],
                source.get('action_hex') or '?', source.get('motion_id') if source.get('motion_id') is not None else '?',
                move.get('implementation', {}).get('status', 'unclassified')))

    def poll(self):
        # Refresh engine and recorder status without reading the game screen.
        # Combine process liveness with published telemetry and worker errors.
        # Schedule the next UI refresh after reporting recoverable read failures.
        try:
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
            if self.record_folder:
                state = read_json(self.record_folder/'status.json', {})
                returncode = self.record_child.poll() if self.record_child is not None else None
                if returncode is not None and returncode != 0:
                    log = getattr(self, 'record_logs', self.record_folder/'worker')/'stderr.txt'
                    message = log.read_text(encoding='utf8', errors='replace').strip().splitlines() if log.exists() else []
                    self.record_status.set('Recording stopped with an error: ' + (message[-1][-250:] if message else str(returncode)))
                elif state:
                    self.record_status.set(state.get('state','') + ': ' + str(state.get('detail',''))[:250])
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
        atomic_json(args.ui_smoke, dict(passed=True, rows=len(app.table.get_children()), game_access=False))
        root.after(200, root.destroy)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
