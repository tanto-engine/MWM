# Read the Engine as a Nioh player

Tanto Engine is the private workshop. MWM supplies the sword moveset and its menu; Recorder collects observations. A recording is evidence of what a boss did, not code that William can immediately execute. The Engine checks source identities, adapts reviewed moves, interprets your controls and manages the resources needed while those moves run.

Start with `runtime/engine_config.py` for selectable moves and settings, then `runtime/prepare_session.py` for the checks required before enabling them. `build_product.py` decides what reaches each EXE. Comments explain ordering, ownership and byte-layout constraints where the code alone is insufficient.

Prefer small functions and concise comments for non-obvious mechanisms. Do not repeat the implementation in comments or guess meanings for unknown game fields.

## Vocabulary used in the comments

| Code word | Meaning in a fight | Why the implementation distinguishes it |
|---|---|---|
| actor / owner | William or another character, and the object owning its behavior | Addresses can change after death or a mission load; the new object must be rediscovered. |
| action / motion / timing | The move's behavior, animation clip and timed events | A matching animation number alone does not identify the complete move. |
| bank / package | A character's collection of move records or game resources | The same action number can mean different moves in different banks. |
| descriptor / payload | The move's index card and its detailed behavior data | The Engine checks their identity before making private adapted copies. |
| transition / graph | A rule allowing one move phase to lead into another, and the connected phases | Recording two consecutive attacks does not prove that one has a native link to the other. |
| adapter | The rules that make a reviewed source move usable by William | Recovery, stance, effects, paired roles and voice routing can need different treatment. |
| hook / trampoline | A detour through our code, and a preserved route through the original game instructions | The original instructions must remain reachable while callbacks or suspended threads may still use them. |
| pointer / RVA / offset | A current memory address, a location relative to the executable, or a position inside a record | They are different kinds of number; an old address is not a permanent move identity. |
| mask / bit | Several yes/no buttons or stance flags stored in one integer | A saved DS4 bit can differ from the game's XInput bit for the same physical control. |
| ABI / struct | The exact binary form Python and native code agree to exchange | Field order, byte size, signedness and padding must match, even if readable names look right. |
| ownership / generation | Which session owns a resource, or which incarnation of a device/session produced an event | Stale input and resources must not cross a death, reload or remapping boundary. |
| hash / fingerprint | A comparison value for exact source or file identity | Matching identities support validation; they do not prove enjoyable or correct gameplay. |
| atomic write / snapshot | Publishing a complete replacement file, or examining one consistent copy of data | Readers must not combine half of an old configuration with half of a new one. |

Unknown source words and raw byte arrays are retained as opaque evidence unless their meaning is established. A comment must not turn a suspected interpretation into a game rule.

## Follow the control flow

1. `engine_config.py`, `engine_policy.py` and `move_imports.py` validate public presets, private policy and reviewed imports. Public speeds are bounded; Ki Pulse authoring, physics and Frost timing remain developer policy.
2. `prepare_session.py` finds the current player/source records and checks the exact supported game build, action signatures, transitions and resources. `runtime_session.py` writes the fixed binary session layout used by `native/boss_session_schema.h`.
3. `supervisor.py`, `native_loader.py` and `process_support.py` manage worker/process lifetime. Process ID plus creation time distinguishes the current game from a reused Windows PID. Remote-thread completion matters separately from closing its handle.
4. `controller_reader.py` reads supported OS controllers. `game_controller.py` reads the native observer's selected controller. `gestures.py` turns coherent observations into taps, holds and chords; `run_dispatch.py` publishes bounded requests. Neither a reconnect nor stale observation creates a fresh press.
5. `native/observer.cpp` connects native callbacks. `boss_support.h` owns imported action adaptation; related headers handle replacements, continuations, Frost Moon, tracking, launch policy and voices. The original source records and privately owned replacements have different lifetimes.
6. `load_resources.py`, `resource_assets.py`, `profile_resources.py`, `motion_resources.py` and `timing_resources.py` resolve the game's existing archive entries. `native/resource_loader.cpp` keeps the required action/motion/timing/camera resources alive. Shared package records cannot be pruned without proving their dependencies.
7. `trace_reader.py` reads bounded observations for diagnostics and controller interpretation. `nioh_memory.py`, `action_banks.py` and `boss_probe.py` provide read/discovery primitives. Recorder receives only these read-only capabilities plus `controller_reader.py`.

`nioh_sword.py` and `native/nioh_sword_definitions.h` retain researched identities and recipes for this specific backend. `catalogue.py` maintains readable move definitions and validation. `project_paths.py` separates Engine code from product-owned data and writable runtime state. These source families do not yet implement ten arbitrary weapons.

For the C/C++ details, continue with [the native walkthrough](runtime/native/NATIVE-WALKTHROUGH.md): hook entry/exit, private copies, shared layouts and thread/resource lifetime.

## Sword inputs and casting

`mwm/data/move-help.json` supplies source labels, input kinds, stance choices and skill/string roles to both validation and the Electron dropdowns. A press-through string replaces Quick or Strong attacks. A skill may contain automatic jump/strike/landing phases while still needing only one activation; Frost excludes press-through strings. Saved assignments outside the new menu filter remain visible for compatibility.

The compiler tags imported string phases with their Quick/Strong input family. One graph cannot borrow both continuation-button families: its privately copied exit rows have one input policy. Native finishers use the current phase's recovery frame, stance and a fresh opposite-button edge: after Strong, L1 + Square; after Quick, L1 + Triangle. They take priority over the corresponding neutral guard skill during that window. Native strings use the same rule. Controller packet rollback requires a new press; frame-generated finishers defer to ranged triggers, item shortcuts, other face buttons, Pulse and menu inputs. Death, changed ownership, stance changes and controller gaps invalidate pending input.

Casting needs two separate boundaries: the attack must permit a native item exit, and the cast must commit its effect before cancellation. Ordinary imported actions retain verified William shortcut exits where that complete row family is available. Downward slash has a longer developer-authored Pulse hold window; the percentage still applies to actual native Ki expenditure.

`runtime/native/cast_pulse.h` carries the preceding sword Pulse deadline across native Onmyo motions110/111 and throwing motion104, matching their payload signatures. A fresh R1 can wait for a player-owned sound callback after the loaded stream's effect-release row40; later cleanup row41 does not delay cancellation. The same policy handles fast casts, frame-zero releases and shurikens without editing cast events, Ki, item counts or effects. Expired windows, controller gaps, stance/epoch changes and unrelated casts remain ineligible. Pulse uses validated native action lookup in every preset.

A live failure exposed a DWORD action key being checked as eight bytes: adjacent descriptor metadata rejected every real Pulse. The regression uses that captured metadata. Successful native Pulse consumes the window; refusal preserves it. On 2026-10-02 the user confirmed working Guardian Spirit Talisman and shuriken cancellation with surviving effects and the normal Pulse. The trace independently records talisman262 → native PulseD61. Other individual Onmyo items have not yet been tested, and these observations do not measure a numerical Ki refund.

Default Type A controls reserve L2 for aiming, R2 for shortcut pages/shooting, and R1 for Pulse/stances. Nioh 2 moves shortcut-page switching to R1 + D-pad left/right and uses R2 for Yokai actions. Its trigger-based mod bindings cannot be copied into Nioh 1 as free controls. References: [Nioh 1 official PC manual](https://cdn.akamai.steamstatic.com/steam/apps/485510/manuals/Nioh_steam_EN.pdf), [Nioh 2 official controls](https://www.gamecity.ne.jp/manual/t2wNiSht/steam/bri/2000.html).

## Damage and cross-game imports

The current importer retains source combat rows; most damage fields remain opaque. Attaching an action to William does not prove that every boss contact coefficient scales correctly. There is no verified damage-coefficient setter yet.

The smallest useful damage abstraction is a relative power budget per move, distributed across its contacts, with separate physical, elemental and Ki channels. Apply those weights at the verified native contact-power field before target mitigation, while letting the game resolve William's weapon, stats, buffs and the target's defense/resistance/difficulty. Do not replace final HP loss with a fixed number, guess an armor formula, or apply difficulty twice. Equal total power does not guarantee equal final damage: armor may affect each hit separately.

Calibration requires matched native/imported sword hits against the same target and equipment, then checks across equipment levels, defenses and difficulties. Compare repeated observations rather than one damage number. A four-contact move gets an explicit total budget; four full-strength hits must not accidentally become four times the intended skill. Preserve contact/event identity so a phase transition cannot repeat damage or status buildup. Add configurable coefficients only after identifying their native fields and ownership.

`resource_assets.py` validates installed archive entries by name, extent and hash; the native loader decodes and retains the required action/motion/timing/camera packages. Imports identify a source game build, bank, action, motion and payload, not a persistent address. The existing adapters are Nioh 1 recipes, not a cross-game converter or animation editor. Cross-game import would require archive decoding, skeleton/bone compatibility or retargeting, event translation, combat contacts and native object-factory compatibility before reusing the current execution layer. Shared package headers or action IDs alone establish none of these.

## First character review: Maria

All 13 Maria sessions match the archived evidence hashes. Six notes now have selected same-actor phase evidence, with full payloads matched uniquely to action package124 and companion timing4286/motion4287. Nine source phases provide four attack strings and an isolated forward dodge slash. `sword-maria.json` assigns Mid Square to C80 → C81 → C82, High Triangle to C83 → C84, Low Square to C85 → C86, and Mid L1+Triangle to isolated C89. High Strong → L1+Square retains Jin's downward slash for the cast-Pulse test. Each string phase requires a fresh press of its assigned attack button; multiple hits inside one phase remain automatic.

`sword-maria-dash.json` replaces Mid Square with C8A → C81 → C82. The short and long dodge-combo notes both record this same chain, so they do not establish two distinct imports. The dash and quick strings share C81/C82 and cannot be assigned together in one preset. Maria's source Ki cost remains10; William supplies input, stance and recovery transitions. Recorded continuation windows protect the second horizontal slash and final aerial kick. Grabs, independent evasions, buff, teleport and beam effects remain unadapted; C89's automatic retreat is also excluded. These presets are gameplay trials, not live acceptance. Reproduce their resource definitions with `python mwm/dataset/compile_trial.py <Nioh archive directory> --boss maria`.

## Voice substitution

A move's timing table can request a boss vocal at a particular frame. Preparation verifies the configured event index, frame and sound hash. `native/voice_support.h` recognizes only reviewed events belonging to William's active private imported action. `observer.cpp` then calls the original sound handler with the retained William attack row (`AV_WILLIAM_ATTACK_MIDDLE`, hash `0x97933946`). The imported move supplies the cue moment; the native William row retains its playback probability/variation and owner routing. Other actors and unmatched sounds use the original handler unchanged. This reuses game audio, and still needs an audible gameplay check.

## Data, dependencies and tests

- `tests/support/*.py` supplies cases to the two entrypoints. `tests/native/*` uses owned memory, fake records and controlled native calls; it must never treat offline success as gameplay acceptance. `tests/native/fixtures/*.json` and the stub header are serialized fixtures, not live addresses to inject.
- Run only `Test-Offline.ps1` for the maintained validation workflow. Its resource suite also checks the supported game archives on disk. Runtime resource files and generated harnesses under ignored build folders are outputs, not source to annotate manually.
- `third_party/minhook` provides instruction detours; HDE64 decodes instruction lengths so patches do not split an instruction. Keep its upstream license/provenance and document local changes. Header byte tables are decoder data, not lists of Nioh moves.
- `requirements-build.txt` pins the packaging tool. `.gitignore` keeps generated native files and session state out of commits; `.gitattributes` controls text/binary treatment.
- JSON has no comment syntax. Fixture schemas, field names and the adjacent source validators explain those records; inserting comments into raw JSON/JSONL would change evidence or break parsing. MWM's product data and curated evidence live under `mwm/`; raw working captures remain outside the repository.
- Keep observations, reviewed move graphs, playable imports and saved presets as separate versioned JSON contracts. Their records are small and irregular; the runtime does no bulk tensor arithmetic. PyTorch and TensorDict would add a large native dependency to the portable EXE without simplifying these contracts.

## Product direction and releases

The combined repository keeps the runtime in `runtime/`, the weapon application in `mwm/`, and recording evidence separate from playable imports. Future weapons can share hooks, controller interpretation and resource ownership, but need reviewed adapters and equipped-weapon routing before they appear in the UI. Raw capture history stays out of EXEs.

Engine remains private, Recorder remains a separate read-only product, and MWM begins with the single katana. See `RELEASES.md` for version, test, checksum and immutable-tag rules. Source comments do not update an existing EXE; any new distributable build must receive an unused release version.
