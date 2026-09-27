# MWM  -  Multi-Weapon Moveset Mod

MWM is the shared application for ten planned Nioh weapon movesets, starting with single katana; Engine owns gameplay integration and Recorder supplies evidence for developer review.

`desktop/` is the Electron, TypeScript and CSS interface; `app/web_worker.py` connects it to Engine's reviewed configuration and lifecycle APIs. After `npm ci`, use `Trainer.ps1` or `npm start` with the pinned sibling Engine and Python. `Trainer.ps1 -LegacyUI` retains the previous trainer for comparison.

Collection shows the recorded moves, original notes and integration gaps. The Sword Rebuild 1 button loads its supported subset into the form; Apply saves it. Browsing the collection does not enable candidate moves. Product checks live in `tests/` and run through Engine's existing `Test-Offline.ps1`.

Bindings edits the custom chord and controller mapping; Overrides edits stance and native-action replacements; Tuning shows effective per-phase speeds. Blank speed fields inherit, while explicit `1` forces native playback. Live compilation flags conflicts before Apply, and Save as/Load preserve the complete draft. Recorder's artwork is bundled locally with a darker CSS overlay.

Reuse a binding group saves or loads the custom chord, stance overrides, native overrides or Frost Moon independently. Chord files preserve logical buttons across controller mappings; imports preserve unrelated settings and reject incompatible combinations. `app/binding_groups.py` owns this file contract. The runtime still supports one custom chord, alongside its native override slots.

`dataset/` holds 12 sword strings and one handgun candidate under weapon/boss folders, with exact notes, ordered IDs and hashed evidence. `intake.json` tracks every source session; `validate.py` checks records and archived evidence. Hashed original recordings are included in this private repository under `dataset/evidence/`, and uncertain or incomplete mappings remain explicit.

`data/` is legacy runtime integration input: the old catalogue, reviewed import graphs, resource fingerprints and preset v8 defaults. It is not merged into the new dataset. Move choices, bindings and bounded speeds remain editable; Ki Pulse, physics and Frost Moon timing stay Engine-owned.

`configurations/` specifies the new Sword Rebuild 1 sword layout and its four unfinished boss routes. `data/presets/sword-rebuild-1-supported.json` loads the five supported Jin routes; `data/move-policy.json` extends their recovery windows. See [configuration status](configurations/README.md) before using the subset.

`review_import.py` reports definition/evidence gaps. `Build.ps1` uses Engine's release gate to package one portable EXE with its own worker and data. The gate checks an isolated copy before release. `desktop/portable_worker.cjs` retains versioned workers in app data so closing the editor cannot remove an enabled Engine's files. See [CODE_GUIDE.md](CODE_GUIDE.md) for module boundaries and migration TODOs; gameplay and controller acceptance remain pending.
