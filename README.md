# MWM  -  Multi-Weapon Moveset Mod

MWM is the shared application for ten planned Nioh weapon movesets, starting with single katana; Engine owns gameplay integration and Recorder supplies evidence for developer review.

`desktop/` is the Electron, TypeScript and CSS interface; `app/web_worker.py` connects it to Engine's configuration and lifecycle APIs. After `npm ci`, use `Trainer.ps1` with the sibling Engine and Python. Source launch builds current native DLLs and the UI; opening the editor does not attach to Nioh or package an EXE.

Moves groups actual assignments by stance, with the custom input underneath. **Save changes** validates and saves the draft; **Enable mod** separately requests attachment. More contains the full Rebuild trial, Jin subset, previous preset, imports, exports and Collection. Product checks run through Engine's `Test-Offline.ps1`.

Controller edits buttons and device mapping; Speed edits per-phase playback. Blank speeds inherit, while explicit `1` forces native playback. Detailed replacements remain available under More. The same Engine validator checks every editor path, and runtime errors remain visible after a failed supervisor exits. Recorder's artwork stays dim behind compact controls.

Reuse a binding group saves or loads the custom chord, stance overrides, native overrides or Frost Moon independently. Chord files preserve logical buttons across controller mappings; imports preserve unrelated settings and reject incompatible combinations. `app/binding_groups.py` owns this file contract. The runtime still supports one custom chord, alongside its native override slots.

`dataset/` holds 12 sword strings and one handgun candidate under weapon/boss folders, with exact notes, ordered IDs and hashed evidence. `intake.json` tracks every source session; `validate.py` checks records and archived evidence. Hashed original recordings are included in this private repository under `dataset/evidence/`, and uncertain or incomplete mappings remain explicit.

`data/` contains runtime definitions: selectable moves, import graphs, resource fingerprints and schema-v8 presets. `dataset/compile_trial.py` matches recorded action bytes to installed archives and generates the four new boss imports; extracted game assets are not stored here. Move choices, bindings and bounded speeds remain editable; Ki Pulse, physics and Frost Moon timing stay Engine-owned.

`configurations/` documents the complete Sword Rebuild 1 layout. Hideyori, Oda, Tachibana and Sanada now have source trial adapters alongside Jin; their behavior on William still needs gameplay review. `data/move-policy.json` gives the selected graph roots shared Ki recovery leeway. See [configuration status](configurations/README.md) for bindings and uncertainties.

**Earlier full-trial failure:** the initial 2026-09-27 multi-boss source trial was disabled after reported left-stick drift and a missing death screen. Its trace contains 3,572 action calls, zero intended substitutions and zero custom dispatches; the last sampled resource slots were original. Hideyori's timing/motion/camera load remained pending. These observations focus investigation on attachment and lifecycle handling but do not establish the cause.

A subsequent isolated test reproduced a loader hook remaining attached while archive loading was pending. Engine now detaches it after submission and on errors/timeouts, and stops activation on native load failure. The regression passes offline; new boss routes still need separate source checks before retrying the full preset.

**Local source checks, 2026-09-27:** the user confirmed all six Jin inputs: Low heavy, Low dodge-heavy, Mid heavy, Mid dodge-heavy and Low/High Frost Moon. The isolated Low-heavy test also passed normal movement and death/retry. Native traces matched all 15 phases without intended-substitution mismatches, including Mid dodge entry `BC8 → BBF` and continuation `C63 → C64 → C65 → C66`. These results cover the Jin subset, not the full multi-boss preset or every contact/physics case.

Oda's Mid Frost Moon subsequently played both slashes (`C6E → C6F`, motions `1010 → 1011`). Both now inherit 1.1× speed, which the user preferred. Tachibana's Omnislice also played from High heavy → LB+Square, with `D8D`/motion `5011` in the trace. These source checks confirm playback and binding, not every damage, contact or recovery case.

Hideyori's four Low-quick phases play, but their zero boss Ki cost prevented Pulse. William's private copies now use his native Low-quick costs (19, then 14 per strike). The native regression passes; live telemetry shows an opener spending 14.25 after modifiers and creating 5.7 recoverable Ki. Pulse/Frost Moon input feedback remains pending.

Sanada uses a Low-stance LB+LT tap and release; holding is unassigned. The user confirmed firing, 1.15× speed and the equipped sword disappearing during the action. Source effects request object `229757` at frame 13 and projectile `944393` at frame 78; their factory keys `3257` and `3258` now load before activation. Subsequent missed inputs were in Mid stance or during an existing shot. Damage ownership still needs a separate check.

Boss action IDs are bank-local keys, not universal move names or boss identifiers. Jin and Oda both use `0x00000C6E`/`0x00000C6F` for different motions. Preserve the full 32-bit key, boss/source bank, payload bytes, motion/timing keys and game build together. One execution can contain several hits, and consecutive IDs do not prove a combo. Actor addresses can change or be reused after a death; generation and action-counter continuity matter more than the address alone.

Hideyori's `0x00000D30 → D31 → D32 → D33` has consecutive observed counters 219–222 and native transition links: enough evidence for a four-phase trial, without inventing a fifth hit. Tachibana's `D8C → D8D` matches the proposed preparation/Omnislice order; the step-back/sheath interpretation is still a hypothesis. Oda's `C6E → C6F` has a native frame-40 continuation. Sanada's `C6A` was observed twice at counters 402/403; `C6B` is only an available native branch. Counter 404 was missed, and a later previous-action pointer suggests `BB8`; neither fact proves another gunshot or its execution time.

The new source action packages match recorded payload prefixes in `archive_00.lnk` entries 147 (Hideyori), 103 (Oda), 107 (Tachibana) and 134 (Sanada). Companion timing/motion/camera triples in `archive_01.lnk` are 4048–4050, 3996–3998, 4005–4007 and 4038–4040 respectively. Their reviewed key sets and adjacency support the trial mapping; matching asset bytes does not prove correct behavior on William. `dataset/compile_trial.py` reproduces these fingerprints without storing extracted game assets.

Match descriptions against the final few relevant executions before Stop, looking past idle/recovery and across all captured actor candidates. A written pause or death is timing context, not proof of an observed memory event. Raw captures stay in their recording library; local development outputs stay inside the repos. Earlier exported previews are retained under ignored `local-artifacts/previous-exports/`.

`review_import.py` reports definition/evidence gaps. `Build.ps1` uses Engine's release gate to package one portable EXE with its own worker and data. The gate checks an isolated copy before release. `desktop/portable_worker.cjs` retains versioned workers in app data so closing the editor cannot remove an enabled Engine's files. See [CODE_GUIDE.md](CODE_GUIDE.md) for module boundaries and migration TODOs; gameplay and controller acceptance remain pending.
