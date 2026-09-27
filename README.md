# MWM — Multi-Weapon Moveset Mod

MWM is the shared application for ten planned Nioh weapon movesets, starting with single katana; Engine owns gameplay integration and Recorder supplies evidence for developer review.

`desktop/` is the Electron, TypeScript and CSS interface; `app/web_worker.py` connects it to Engine's reviewed configuration and lifecycle APIs. After `npm ci`, use `Trainer.ps1` or `npm start` with the pinned sibling Engine and Python. `Trainer.ps1 -LegacyUI` retains the previous trainer for comparison.

`data/` contains move identities, reviewed import graphs, resource fingerprints and preset v8 defaults. Raw recordings stay outside Git. Move choices, bindings and bounded speeds are editable; Ki Pulse, physics and Frost Moon timing remain Engine-owned.

`review_import.py` reports definition/evidence gaps. `Build.ps1` uses Engine's release gate to package a portable EXE with its own worker and data. This desktop version awaits its first package and acceptance. See [CODE_GUIDE.md](CODE_GUIDE.md) for module boundaries and migration TODOs; offline checks do not establish gameplay acceptance.
