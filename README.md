# MWM — Multi-Weapon Moveset Mod

MWM is the shared application for ten planned Nioh weapon movesets, starting with single katana; Engine owns gameplay integration and Recorder supplies evidence for developer review.

`desktop/` is the Electron, TypeScript and CSS interface; `app/web_worker.py` connects it to Engine's reviewed configuration and lifecycle APIs. After `npm ci`, use `Trainer.ps1` or `npm start` with the pinned sibling Engine and Python. `Trainer.ps1 -LegacyUI` retains the previous trainer for comparison.

`dataset/` is the fresh move collection: one JSON move string per weapon/boss, with ordered action IDs, review status and hashed recording references. `dataset/validate.py` checks structure and archived evidence. Raw recordings stay outside Git; new data begins with Tachibana's unconfirmed Omnislice preparation → attack.

`data/` is legacy runtime integration input: the old catalogue, reviewed import graphs, resource fingerprints and preset v8 defaults. It is not merged into the new dataset. Move choices, bindings and bounded speeds remain editable; Ki Pulse, physics and Frost Moon timing stay Engine-owned.

`review_import.py` reports definition/evidence gaps. `Build.ps1` uses Engine's release gate to package a portable EXE with its own worker and data. This desktop version awaits its first package and acceptance. See [CODE_GUIDE.md](CODE_GUIDE.md) for module boundaries and migration TODOs; offline checks do not establish gameplay acceptance.
