# Release notes

## 0.4.0

- Add five Ishida sword strings with 19 route-local phases and an editable preset. Preserve repeated C5B phases, shared endings, and C71's separate 91030 timing track.
- Add fixed move-specific cast-cancel windows across boss imports and William's 20 native Quick/Strong stages. Assign rounded 60% Onmyo / 70% shuriken eligibility, with overlap. Reject early buffered R1 and preserve the preceding native Pulse deadline.
- Fix #24: Okatsu's sequence is available in held custom input pickers and Browse. Fix #25: Input overrides has a visible primary tab.
- Address #26: Maria's terminal horizontal-string restart waits for its 126-frame landing clip; Pulse/dodge recovery stays available earlier.
- Expand native route, timing-boundary, alias and GUI regressions. Document the generated policy and verification limits. Release names now use only the version number.

Unresolved: crash reports #2 (Isle of Demons entry) and #27 (repeated re-enables) lack a reproduced cause. Ishida's grapple and two beam recordings remain unsupported. The new Ishida moves, variable cancel windows and Maria recovery adjustment require gameplay verification; passing offline checks does not establish combat behavior or resolve those crashes.

## 0.3.0

- Fix cast cancellation's 32-bit action-ID comparison. Onmyo and shurikens share an effect-release gate and the preceding sword Pulse window; native Pulse handles recovery without direct Ki or item writes.
- Add Maria quick, horizontal, kick and dodge-slash strings plus forward slash, with two editable presets. Correct the camera asset, supply High-stance continuation rows, and let fresh attack presses restart completed strings. Exclude automatic boss restart branches and unrelated action-ID collisions.
- Expose Maria presets and cast guidance in the GUI. Fix action-ID search, invalid Frost selections, stale preset/capture responses, rejected controller-capture mutations, and optional binding feedback.
- Preserve stance assignments regardless of JSON key order, limit binding-group remaps to the imported group, and avoid false preset cycling after pauses. Keep global chord inputs compatible with the native reservation protocol.
- Support all 64 compiled import slots. Validate native field widths, vocal categories and finite animation clocks; reject missing requested clips and restore resource callbacks on failure.
- Keep failed cleanup visible, find archives beside the verified running game, identify failed resource components, and clean incomplete portable EXE extraction.
- Reuse one validated catalogue per import batch. Ten Maria previews improved from 1385ms to 440ms in the measured source run, with fresh data still loaded for every preview.
- Consolidate repeated code, replace redundant comments with ownership and timing contracts, and add architecture diagrams and broader native, protocol, controller and Electron regressions.

The user verified Guardian Spirit Talisman and shuriken cancellation and the initial Maria moves. The later High-stance continuation and string restart fixes pass offline regressions but await a fresh gameplay check. Other Onmyo items, damage/contact coverage and another-PC acceptance remain unverified. The release receipt records the final automated results and exact artifact hashes.

## 0.3.0-alpha.18

- Add a native Pulse request for the recorded Guardian Spirit Talisman cast: retain the sword's actual Pulse deadline and wait until its timing stream passes the final non-sound event.
- Consume the carried cancel window after a successful native Pulse; preserve it after a refused request.
- Keep frame-generated finishers from competing with ranged triggers, item shortcuts, other attacks or menu inputs. Controller packet rollback requires release and a fresh press; movement and lock-on remain independent.
- Include the previously unpublished alpha.16/17 cleanup, stance-specific input menus, buffered-hold fixes and Quick/Strong string continuation rules below.

Cast shortening, Guardian Spirit persistence and actual Ki recovery still need live verification. Automated test counts and packaged UI results are recorded in the build receipt.

## 0.3.0-alpha.17

- Use the compiled Quick/Strong input family for Jin string continuations. A Jin string assigned to Quick now continues on Square instead of silently requiring Triangle; Strong retains Triangle.
- Includes the alpha.16 UI consolidation, native finishers, hold/teardown fixes, candidate classifications and import/damage documentation below.
- Native owned-memory regression checks both button families across all three Jin phases, including the final stop. Live acceptance remains deferred.

## 0.3.0-alpha.16

- Remove the duplicate Tkinter editor; retain controller remapping, saved movesets, lifecycle commands and the legacy launcher alias through Electron.
- Use shared input metadata for native sword dropdowns. Add Guard + Strong and Quick/Strong finishers in all three stances; preserve saved assignments and give internal phases readable names.
- Tag imported string phases by their assigned attack input. Reject conflicting custom/native chords and keep press-through strings out of Frost and the new skill slots.
- Preserve buffered holds across native string stages and retain the actual selected tap/ender on release.
- Drop owned weight overrides when a collider has disappeared, avoiding a native setter into torn-down collision state. The tournament crash still needs live reproduction.
- Retain verified native shortcut exits during imported attack recovery and extend the downward-slash Pulse hold window. Effect-safe cast cancellation remains unverified.
- Correct Maria candidate categories without enabling imports. Document damage-calibration boundaries and the Nioh 1-specific import architecture.

Live sword/controller acceptance is deferred. Offline and packaged UI results are recorded by the build receipt; they do not certify hitboxes, teleport behavior, cast effects or encounter transitions.

## 0.3.0-alpha.15

- The Moves tab now creates two-button tap or hold custom inputs directly; a three-button follow-up is optional. Per-route inputs accept any distinct pair among the five reviewed controller buttons. The desktop roundtrip saves both patterns.
- Touchpad preset cycling waits briefly for a delayed mirrored XInput press before switching and discards a partial double-tap on controller disconnect. Offline tests reproduce both false-switch paths and verify the fix.

The three-button runtime and cross-stance ordinary move fixes from alpha.14 remain included. Live DS4 preset cycling, Hideyori's first-hit movement snap, and additional native input source selection still need gameplay evidence. Recorded candidates without a William-safe action graph remain research-only.

## 0.3.0-alpha.14

- Custom controller chords now reserve their configured button pair before Nioh selects a competing skill. A fresh publisher heartbeat is required, so a stopped editor cannot keep consuming native inputs. Live Low L1+Triangle taps played Charged Rush instead of Nioh's Guard+Strong skill; L1+Circle and L1+L2 also worked in source trials.
- Hideyori's four-hit Mid Strong replacement retains Triangle for its continuations; the live source trace and player reached all four hits. Conflicting assignments of this graph to two input classes are rejected.
- Okatsu's quick/kick sequence is named accurately and can use a held controller chord. The player confirmed the full sequence on L1+L2. Removed the hidden LT+RT activation because it briefly entered the game's aim animation. The option now includes the sequence for explicit binding.
- Cataloged all 67 annotated sword recordings, including twelve older candidates previously absent from the move library. Edward Kelley remains excluded. Research-only candidates are clearly unavailable until their action ownership, complete graph, resources and William adaptation are established.
- Kept the desktop regression worker isolated from a live Engine registration and clarified that custom chords take priority over game actions on the same buttons.
- Allowed the same stance-neutral Okatsu action on Mid Frost Moon and a High custom input; multi-phase graphs still have one stance owner.
- Custom operators now accept a follow-up while the first button stays held, as well as after its release. Native interception follows the observed sequence stage so unarmed three-button input remains with Nioh.

Source-runtime observations do not certify the new EXE. Mission-entry crashes #2/#10, the Hideyori first-hit root-motion snap #16, live touchpad preset cycling #12, and further native input source expansion #11 remain open. The newer recording candidates remain research-only until their actor, phases, resources, and William adapter are verified.

## 0.3.0-alpha.13

- Fixed After Strong availability when ordinary Strong remains original but Hold Strong has a separate move. The Mid stance screenshot case now selects and saves both routes.
- Keep the moveset editor available after an unexpected controller capture or response-encoding error. The worker returns an error, records a capture traceback, and accepts another capture attempt without resetting the app.

Offline and packaged checks pass. Physical controller binding, live gameplay, the reported crashes and Hideyori dodge movement remain under investigation.

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
