# Release notes

## 0.3.0-alpha.4

- Incompatible bindings open a clear popup naming the move, conflicting inputs and how to correct them. Invalid drafts do not change saved settings.
- Complete graph validation runs before Save; changing assignments requires the mod to be disabled.
- The move is now named **bloodborne gun shot** throughout the move menus and documentation. Source IDs and recording evidence remain intact.
- Activation rejects retained code from another Engine build. Restart Nioh after updating; a game exit during resource loading now stops activation instead of retrying silently.

The earlier activation crash was observed during resource loading; its exact native cause and current-build gameplay acceptance remain unconfirmed.

## 0.3.0-alpha.3

- Current Sword Rebuild 1 is the default for new installs; existing settings and the original moveset remain available.
- Choose held Triangle/Y per stance, with separate launcher-only and launcher-plus-Izuna choices. Heavy replacements no longer swallow held bindings; matching custom chords take priority over competing native attacks. R1/RB remains reserved for Ki Pulse and Frost Moon.
- Rebind custom buttons, native overrides and Frost Moon independently. Invalid stance combinations explain how to correct them.
- Includes the confirmed Jin, Oda, Omnislice and bloodborne gun shot source setup, Hideyori Ki correction, handgun assets and temporary sword hiding.
- Portable EXE includes its worker, move definitions, artwork and collection. Packaged checks cover saving, rebinding and XInput translation without accessing the game.

Physical Xbox/PS5, broad enemy contact and another-PC checks remain pending.

## 0.3.0-alpha.2

First portable MWM desktop release candidate. The EXE includes its own Engine worker, reviewed move data, artwork and collection. Each launch extracts separately; versioned worker files survive editor closure so an enabled Engine can retain its runtime. Apply now saves the selected game path before refreshing the form. The release gate checks the copied EXE's startup, configuration and bundled assets with gameplay disabled.

Added independent binding-group save/load with controller translation, atomic chord-button swapping and compatible override seeding. Invalid saved presets open as editable baseline drafts without overwriting the original. Group imports preserve unrelated bindings and tuning, reject conflicts and remain pending until Apply. These source changes do not add extra runtime chord slots or constitute gameplay acceptance.

Sword Rebuild 1 provides five Jin routes. bloodborne gun shot, Hideyori's Low quick string, Omnislice after High heavy and Oda's Mid Frost Moon still need Engine adapters; the complete requested layout is not yet playable. Current-build gameplay, physical-controller and another-PC acceptance remain pending.

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
