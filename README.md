# SKM — Single-Katana Moveset Mod

SKM adapts reviewed boss moves for William's single katana in Nioh. Its EXE packages the configuration UI, selected Tanto runtime and required native libraries. Players do not need either source repository.

The UI chooses reviewed moves, stance/source overrides, bounded speeds and controller bindings. Preset v8 stores those choices. The engine controls Ki Pulse, physics and Frost Moon timing; a new recording must be reviewed and adapted before it becomes selectable.

Move names live in `data/moves.json`, action graphs in `data/imports/`, resource identities in `data/resources/`, and default bindings in `data/preset.json`. These definitions identify installed-game resources rather than distribute game archives.

Enable / attach starts the configured runtime; Disable restores owned state. Closing the UI leaves an enabled session running. Settings remain in `%LOCALAPPDATA%/Tanto/Sword/runtime`.

Controller support uses saved mappings, the retained DS4 mapping or a selected XInput slot. Press-to-bind reads supported controller observations. PS4, PS5 and Xbox physical acceptance remains pending; arbitrary hardware support is not established.

Develop with the pinned sibling `tanto-engine` checkout. `Trainer.ps1` opens the source UI, `review_import.py` checks authored imports, and `Build.ps1` packages a versioned EXE. Run Engine's `Test-Offline.ps1` for offline checks; gameplay needs separate verification.

See [CODE_GUIDE.md](CODE_GUIDE.md) for implementation details and Engine's [release contract](../tanto-engine/RELEASES.md) for source pins, hashes and immutable releases.
