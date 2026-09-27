# Release notes

## 0.3.0-alpha.1

Added an Electron/TypeScript/CSS interface with reviewed move choices, native overrides, Frost Moon destinations, bounded speeds and controller binding. A restricted worker reuses Engine validation and lifecycle; Load and Baseline edit the form, Apply saves, and Save as exports without enabling gameplay.

Prepared the shared release gate for a portable `MWM.exe` containing its own Engine worker and product data. `Trainer.ps1` now opens Electron; `-LegacyUI` retains the previous trainer. This source version has not yet produced a desktop EXE or new gameplay acceptance.

Renamed SKM to MWM (Multi-Weapon Moveset Mod), the shared application for the ten planned weapon movesets. The current backend and data remain sword-specific; saved presets and the legacy settings namespace stay compatible. No new EXE or multi-weapon runtime is included.

## 0.2.0-alpha.1

Renamed Tanto Sword Mod to SKM (single-katana moveset mod). Existing settings remain compatible. No new SKM executable or gameplay acceptance is included.

Source review adds player-readable function/callback comments and code guides. The updated Engine pin includes a reproduced single-hook disable context-translation correction with an owned-memory regression. It is available for the next SKM build; no current-build gameplay or crash outcome is asserted.

EXE builds require clean source, an exact Engine pin, the two maintained offline suites and immutable versioned artifacts. Live game, physical controller and another-PC acceptance remain pending.

## 0.1.0-alpha.1

Historical standalone preview. Later unversioned local EXEs are development builds and are not retroactively assigned this release identity.
