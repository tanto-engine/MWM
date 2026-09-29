# Release notes

## 0.3.0-alpha.12

- Fixed the Move library crash that hid the 55 newer sword recording candidates. Added a searchable index of 918 distinct action signatures from those sessions, with source recording and journal line. All 70 eligible sessions remain indexed; Edward Kelley is excluded. Unassigned actor data remains research only until William adaptation is verified.
- Fixed Jin's heavy-string continuation retaining the imported action bank between William's Strong strikes.
- Added an owned-memory check for Hideyori's four-phase Low Quick replacement. All phases retain their imported descriptor and source bank; live Square timing still needs gameplay verification.
- Added stance-specific custom follow-ups after original Strong in Low/Mid and original Quick in Low/High. The input window begins at the confirmed attack's recovery, and incompatible source replacements are blocked. High Guard+Square and Mid Guard+Triangle remain with their occupied Nioh inputs.

Offline checks passed. Live Nioh acceptance, the two reported crashes, and Onmyo/Ninjutsu Pulse cancellation remain open. Cast action signatures and end timing have not been recorded, so this release does not invent their cancel transitions.

## 0.3.0-alpha.11

- Rebuilt Moves around direct Low, Mid and High input rows. The persistent guide explains each route; editing an all-stance route now splits it so other stances retain their moves. Speed uses one selected move and percentage control instead of duplicate fields.
- Added additive custom operators: hold a modifier with a first button, release that button, then press a follow-up within 0.6 seconds. The reviewed controls are L1/LB, Circle/B, Triangle/Y, L2/LT and Square/X; all three must differ. Original game inputs remain active.
- Added a saved preset library, draft loading, manual activation and safe live cycling. A supported direct DS4 WinMM touchpad click cycles on a clean double-tap; XInput and Steam Input mappings use the app switch. Active Engine cleanup completes before a preset is written and restarted. Unsaved editor drafts remain intact.
- Updated Controller and Input routes guidance, preset status, editing feedback and packaged UI checks. Fixed stale preset selection after normal Save, stale runtime requests during cycling, and XInput trigger duplication during touchpad detection.

Offline and packaged checks do not establish physical-controller or live Nioh acceptance. The two reported crashes remain open.

## 0.3.0-alpha.10

- The supervisor writes status only when state or details change, avoiding repeated disk writes while gameplay state is steady.
- Disable now signals the active runtime before copying any defaults or DLLs. Native DLLs stage once in the shared launch path when a new engine starts; the desktop worker and source trainer no longer duplicate that work.

Offline and packaged checks passed. Live gameplay and physical-controller acceptance remain pending; the two reported crashes remain open.

## 0.3.0-alpha.9

- Replaced the crowded Sword overview with one stance branch at a time. Named inputs show their current moves; selecting one shows its exact trigger, behavior, and move picker. Detailed assignments remain available in the list view and Input routes.
- Added a labeled, opaque controller diagram and moved the actual mapping controls above it. How to use is now a visible tab with a four-step workflow.
- Adding a Sword route now waits for a move choice. Closing the picker leaves the draft unchanged. Route selection keeps keyboard focus, and Edit input route focuses the matching controls.
- Removed a repeated stance label from the selected route's input line.

Offline and packaged UI checks do not establish live gameplay or physical-controller acceptance. The two reported crashes remain open.

## 0.3.0-alpha.7

- Input overrides can now use an original Nioh source or a separate controller chord on each row. Custom rows leave the original game action unchanged and can select independent tap or hold moves by stance. The editor records Modifier and Trigger from a connected controller on each row, shows conflicts before saving, and keeps the original global chord for existing presets.
- Reviewed custom chords use L1/LB with Circle/B, Triangle/Y, L2/LT or Square/X. The runtime supports up to 24 custom routes separately from 32 native override slots. Saved movesets and exported skill groups translate each row's buttons when the controller mapping changes.
- Dispatch now shares one monotonic command sequence across routes, rejects overlapping bindings and stale presses, and stops reading player stance while gameplay context is suspended. The packaged EXE tests two distinct custom routes and their controller remapping.
- Added an opaque sword icon to the portable EXE and tightened route labels, binding feedback, narrow layout and keyboard-accessible capture controls.

The supported chord set is limited to input pairs with reviewed native interception. Live Nioh, physical-controller and another-PC acceptance remain pending. The two reported crashes are unchanged.

## 0.3.0-alpha.6

- Rebuilt the opaque Sword editor around a stance skill map, input routes, controller guide, searchable move picker and separate playable/research library. The persistent right guide now explains the hovered input and move with concrete expected controls and behavior.
- Quick Attack overrides can target Low, Mid, High or all three stances. The source and stance selectors retain their choices when edited, and the native dispatcher matches each selected stance.
- Raised the authored sequence capacity to 64 phases and the native override table to 32 entries. Okatsu's Charged Rush is available on held Strong attack in every stance. The custom chord releases its button reservation after dispatch or expiry; LB+B no longer loses to the native dodge route.
- Opened Tachibana Omnislice's Ki Pulse recovery before its recorded action ends. Gameplay confirmation is still needed.
- Indexed 55 additional named sword recordings as research candidates, excluding Edward Kelley. They are intentionally unavailable for binding until the actor, action phases, resources and William adapter are reviewed. The repeatable intake verifies source archives and records conflicting action and motion keys.

Offline tests and packaged UI checks do not establish live gameplay, physical-controller or another-PC acceptance. The two reported crashes and remaining unsupported input sources are still under investigation.

## 0.3.0-alpha.5

- Press-to-bind now reads connected OS controllers whether Nioh is running or closed. A supported pad's actual mapping and XInput slot become pending with its button; Save applies both together. Unsupported layouts show guidance instead of waiting silently.
- The editor has a persistent right-hand field guide, clearer Tuning and Controller pages, responsive motion, quiet save/bind sounds with a mute switch, and optional gentle XInput binding haptics.
- Resource submission now waits for a validated player and ready data allocator. Long terminal preparation failures retain their stop/retry decision. These are preventive fixes; the reported Isle of Demons crash has not been reproduced with a dump or verified in live gameplay.

Physical-controller, gameplay and another-PC acceptance remain pending.

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
