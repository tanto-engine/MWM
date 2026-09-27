# Read MWM as a Nioh player

MWM means **Multi-Weapon Moveset Mod**. This repository is the shared weapon application, starting with the existing single-katana moveset. It owns selectable moves, defaults and the consumer interface; `tanto-engine` owns native integration and reviewed adaptations. Recorder remains separate, and incoming captures stay outside these source repositories.

Reviewed intake snapshots now live in this private repo under `dataset/evidence/`; working Recorder folders remain in Downloads. `desktop/build.mjs` embeds the readable dataset and design in the app, while raw archives stay out of the consumer package. MWM's product-specific tests live in `tests/`; Engine's existing offline entrypoint loads them alongside generic Engine checks.

Keep 3–5 direct opening comments per function/callback: player-facing purpose, mechanism and the important constraint. Use additional inline comments for ownership, conversion or persistence rules that are easy to get wrong.

## Follow a settings change

The source UI uses `desktop/renderer.ts` for a pending preset, `desktop/preload.cjs` for one restricted IPC method, and `desktop/main.cjs` for dialogs and a private JSON-line pipe. `app/web_worker.py` reuses Engine validation and the existing trainer lifecycle without constructing Tk. Save changes stores settings; Load and Original only edit the form; Export moveset writes a reusable file without applying. Engine owns attachment, recovery and native timing. `Trainer.ps1` and `npm start` open Electron; `Trainer.ps1 -LegacyUI` retains the comparison UI.

The worker pipe explicitly uses UTF-8 so Windows code pages cannot corrupt preset names. Preview expands the same import graphs and effective speeds as live preparation without touching Nioh. Draft generations reject stale validation results; binding generations reject replies from cancelled listeners. Explicit speed `1` is stored, while clearing a field restores inheritance. `tests/desktop_ui.cjs` runs this renderer against a temporary real worker, with simulated hardware input and forbidden game lifecycle calls.

`app/binding_groups.py` defines four disjoint groups using exact field lists. A schema-1 `mwm_binding_group` document stores its group, sword weapon and copied bindings; only chord files include source controller identity. Import merges into a copy, remaps chord masks and compiles the complete candidate before returning it. Files cannot patch speed, name or other groups. New override rows also compile against existing slot ownership before appearing in the draft. Invalid saved presets open as a remapped baseline draft with a warning; recovery never overwrites the original file.

1. `Trainer.ps1` launches `launch.py`, or explicitly asks it to enable/disable the runtime. `launch.py` selects packaged code or the sibling Engine, sets product/state paths, and dispatches only its allowed worker modules. Existing packaged preferences remain under `Tanto/Sword/runtime` despite the product rename.
2. `app/trainer.py` obtains reviewed capabilities from Engine. A displayed name is mapped to a stable move ID; controller labels map to saved button bits. The form distinguishes pending edits from Apply, and Save cancellation does not apply a pending moveset.
3. The Engine validator checks the complete preset, not just the last edited box. Native skill overrides are scoped by source and stance. Speed changes affect reviewed playback, while paired phases, Frost startup, Ki Pulse authoring and physics remain controlled by Engine.
4. Press-to-bind first requires all controls to be released. It accepts one calibrated input from the selected controller and changes the form only. Changing devices translates through logical button meaning; a device's name alone does not establish compatibility.
5. Enable starts the Engine lifecycle. Disable asks it to restore owned state cooperatively. Closing the trainer is separate from disabling an enabled session. Live gameplay and physical-controller acceptance remain distinct from configuration tests.

## Read the product data

| File | What it describes | Important boundary |
|---|---|---|
| `product.json` | EXE name, backend kind, version and exact Engine commit | A release version is different from a preset schema version; an Engine pin identifies source, not gameplay acceptance. |
| `data/mod.json` | Stable product identity and readable MWM name | Renaming the display/repository does not require changing the legacy settings namespace. |
| `data/preset.json` | Default stance, native/custom bindings and reviewed speeds | Schema v8 settings are validated; private physics/Pulse/timing policy is not an unrestricted user field. |
| `data/controller-calibration.json` | Saved controller layout and raw/logical button meaning | A bitmask represents button states; a source-device bit may differ from its game-facing equivalent. |
| `dataset/weapons/<weapon>/<boss>/*.json` | Fresh move strings, ordered source IDs, hypotheses and evidence references | Candidate names and descriptions are unconfirmed until reviewed; archived bytes are retained in `dataset/evidence/`. |
| `data/moves.json` | Runtime catalogue of existing adapters and new source trials | Runtime choices remain separate from immutable research evidence and gameplay acceptance. |
| `data/imports/*.json` | Reviewed source signatures, graph phases, continuations, recovery and voice events | Full bank/action identity matters. Identical small action numbers from different bosses are not interchangeable. |
| `data/resources/*.json` | Installed archive entries, sizes, hashes and motion/timing mappings | These identify game assets; they are not extracted animation archives shipped with the mod. |

An import's `source_voices` can retain events that preparation must verify; `voices` identifies the subset routed through the player voice adapter. A source flag or byte prefix with no proven interpretation remains identity evidence, not a freely editable mechanic. JSON must remain valid data, so explanations live here and beside its validators instead of being inserted as invalid JSON comments.

`review_import.py` compares an authored import with catalogue/resource definitions and optional reconstruction evidence. Its `reviewed` flag records developer review only. The helper writes a report; it never installs a recording or marks a move executable/gameplay-accepted.

Match each description against the last few action executions before recording Stop, using its saved take/time window when available. Capture and inspect IDs from every observed actor; actor roles are context, not a reason to discard evidence. Merge polling duplicates only within the same execution; preserve genuine repeated actions, order, timing and the complete raw take. Recovery or idle IDs can follow the described move, so inspect farther back when needed. Verify full source-bank/action identities before authoring an import, and keep review priority separate from stance.

## Concrete migration boundaries

- **Evidence intake:** retain immutable raw JSONL and original descriptions in private `dataset/evidence/` archives. Index by file hash, session, take and time; review the tail across all actor candidates. Missing takes remain missing evidence, never synthetic move definitions.
- **Current source trial:** `dataset/compile_trial.py` derives four boss import manifests from recorded payload prefixes and installed archive fingerprints. The full Sword Rebuild 1 preset links their phases and bindings; companion resources and combat behavior still need gameplay validation. A native resource-loading failure is distinct from missing recorded action evidence.
- **Catalogue normalization:** extract shared source actions, then reference them from move graphs and weapon adaptations. Use stable IDs and JSON Schema; generate the existing catalogue/import format first so the current 39-ID baseline can be compared without a simultaneous runtime rewrite.
- **Weapon support:** Engine currently discovers specific sword imports. A reviewed weapon manifest and equipped-weapon routing must exist before exposing another weapon tab. `move_capabilities()` remains the UI authority; new data cannot bypass an unimplemented adapter.
- **Packaging:** Engine's gate compiles `launch.py` as the console `MWMWorker.exe` with bundled `app/`, `runtime/` and `data/`, then copies its onedir output into `desktop-worker/`. Electron Builder includes that directory as `resources/worker/` and launches `MWMWorker.exe --desktop-worker`; `--worker` remains the allowlisted gameplay subprocess route. The UI itself needs only `desktop-dist/`, product metadata and release notes inside ASAR. UI compilation alone is not an EXE release; standalone lifecycle acceptance remains required.
- **Acceptance:** confirm physical controller binding, current sword routes, native recovery and a second reviewed weapon before claiming multi-weapon readiness. Closing either UI leaves explicitly enabled Engine gameplay running.

## Builds and repository hygiene

`Build.ps1` delegates every EXE compilation to Engine's shared release gate. `CHANGELOG.md` describes version changes; Engine's `RELEASES.md` explains the required clean commits, exact pin, offline checks, immutable artifacts and tags. `.gitignore` excludes builds and local runtime state. `.gitattributes` preserves appropriate text/binary treatment.

Tests live in Engine and run through `Test-Offline.ps1`; do not create a second product-specific test workflow. A source comment change does not modify an already released EXE, and this review does not claim new MWM gameplay acceptance.
