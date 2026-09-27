# MWM — Multi-Weapon Moveset Mod

MWM is the shared application for ten planned Nioh weapon movesets, starting with single katana; Engine owns gameplay integration and Recorder supplies evidence for developer review.

`desktop/` is the Electron, TypeScript and CSS interface; `app/web_worker.py` connects it to Engine's reviewed configuration and lifecycle APIs. After `npm ci`, use `Trainer.ps1` or `npm start` with the pinned sibling Engine and Python. `Trainer.ps1 -LegacyUI` retains the previous trainer for comparison.

`dataset/` holds 12 sword strings and one handgun candidate under weapon/boss folders, with exact notes, ordered IDs and hashed evidence. `intake.json` tracks every source session; `validate.py` checks records and archived evidence. Raw recordings stay outside Git, and uncertain or incomplete mappings remain explicit.

`data/` is legacy runtime integration input: the old catalogue, reviewed import graphs, resource fingerprints and preset v8 defaults. It is not merged into the new dataset. Move choices, bindings and bounded speeds remain editable; Ki Pulse, physics and Frost Moon timing stay Engine-owned.

`configurations/` specifies the new First Collection sword layout and its four unfinished boss routes. `data/presets/first-collection-supported.json` loads the five supported Jin routes; `data/move-policy.json` extends their recovery windows. See [configuration status](configurations/README.md) before using the subset.

`configurations/` defines Sword Rebuild 1 with dataset references and explicit adapter gaps. `data/presets/sword-rebuild-1-supported.json` is its loadable Jin-only subset; the complete new layout is not yet executable.

`review_import.py` reports definition/evidence gaps. `Build.ps1` uses Engine's release gate to package a portable EXE with its own worker and data. This desktop version awaits its first package and acceptance. See [CODE_GUIDE.md](CODE_GUIDE.md) for module boundaries and migration TODOs; offline checks do not establish gameplay acceptance.
