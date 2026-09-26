# Nioh 1 Sword Skills Expanded

This private repository contains the sword configuration app, an exact-build native adaptation engine, and a curated source-action catalogue. It imports selected boss sword actions into William's moveset. It does not implement a general animation editor. Gameplay verification of the latest tracking, airborne Izuna contact, weapon preservation and dodge continuations is **pending**. Offline verification cannot establish hit contact or animation quality.

The active `runtime/controller-binding.json` is intentionally empty for the next Jin recording session. The revised gameplay configuration is preserved in `app/sword-expanded.json`. The engine is stopped; recording is user-started. William's full moveset capture and EXE packaging remain deferred.

## Running and maintaining the source build

Use Windows x64, Python 3.10+ and MinGW GCC/G++. Run these commands from the repository in PowerShell. Enable waits for a supported game process; Disable requests cooperative recovery rather than tearing an imported action out of the game mid-frame.

```powershell
.\Trainer.ps1                         # Configuration and recording app
.\Trainer.ps1 -Enable                 # Explicitly attach the selected preset
.\Trainer.ps1 -Disable                # Restore owned state, then stop
.\runtime\native\Build.ps1            # Build native libraries, no game access
.\Test-Offline.ps1                    # Both maintained test entrypoints
.\Sync-Catalogue.ps1                  # Reconcile the Downloads workbook
python -B -m catalogue.recordings     # Rebuild occurrence report from indexed evidence
```

To restore the gameplay configuration, import `app/sword-expanded.json` in the app and apply it. The app's baseline button also loads that preset into the form. Applying a preset saves the active configuration; an enabled supervisor restarts its session after native recovery. Merely editing a file is not a successful gameplay test.

The supported executable SHA-256 is `0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389`. Addresses and structure layouts below belong to that build. A mismatch must fail validation, not fall back to guessed offsets.

## Ownership boundaries

`app/` owns the user interface and the shipped Sword Skills Expanded preset. `runtime/engine_config.py` validates its public schema. `runtime/engine_policy.py`, the native engine and `catalogue/imports/` own implementation policy: supported native signatures, resource identity, contact rules, weight/impulse tuning and tracking. `catalogue/` owns the curated sword identities and indexed source evidence. `research/` retains mechanical findings; it is not loaded as gameplay configuration. `tests/native/` contains fixtures exercised by the two existing test entrypoints.

This is a source-level separation, not yet a separately packaged public SDK. The Python app still launches private engine workers. A future public distribution should expose a narrow validated settings interface to a compiled engine. Do not publish this repository, its technical research, import recipes or this engine README as the public app repository. A private source repository keeps source private only until someone is given it.

No locally distributed EXE can guarantee that an experienced owner cannot extract, inspect or modify its engine. Compilation, signing and obfuscation can raise the cost and establish publisher identity; they cannot make local code inaccessible. OWASP explicitly treats obfuscation as increased reverse-engineering effort, not prevention: [binary obfuscation guidance](https://mas.owasp.org/MASWE/MASVS-RESILIENCE/MASWE-0059/). Keeping code off the client is the stronger confidentiality boundary, but remote execution is unsuitable for these latency-sensitive local game callbacks. No DRM or anti-debug framework is introduced here.

### Public configuration

Schema 7 accepts stable move IDs, stance selection, supported skill replacements, custom chord selection, a hold threshold and bounded Frost Moon timing. It rejects unknown fields. Schema 4–6 presets migrate their bindings but discard historical `launch_profiles`, `air_juggle_boost`, `tracking_rates` and `izuna_tracking_degrees`; these are now private engine policy. The input document is not mutated during migration.

```json
{
  "source": "tiger_sprint",
  "stance": "any",
  "move": "okatsu.charged_rush"
}
```

This is an entry in `skill_bindings`, not a complete preset. Tiger Sprint is a **native skill override**: native eligibility and assignment determine where it can run. In Mid stance its validated entry can redirect immediately, avoiding the sheath preparation. Other stances retain their native trigger path. Removing Tiger Sprint from a stance does not independently enable this replacement there. This is the abstraction to extend when more native skill signatures have been recorded.

`guard_light` is a **custom input override**, not an identified native skill. High `guard_light` currently means LB + Square and can replace whichever guard-light skill would otherwise run. `heavy_attack` and `dodge_attack` are validated action adapters. Their source IDs, motion, transition count and flags are checked. Arbitrary native skills or arbitrary captured boss records cannot be enabled by inventing a JSON identifier.

Public custom chords currently provide one modifier and trigger bit, tap/hold choices from implemented adapters, and `hold_seconds` in 0.08–2 seconds (baseline 0.25). Stance holds and Frost Moon each use explicit low/mid/high maps. At most eight native/chord bindings are supported, with overlap validation. One imported Jin graph must have one stance across its bindings. These are current adapter limitations, not promises about a future GUI.

```python
from engine_config import validate_preset
public_preset = validate_preset(document)   # unknown fields and unsafe policy rejected
# prepare_session injects private LAUNCH_PROFILES/TRACKING_RATES itself.
```

### Speed sliders and frame controls

The current implementation already has a small timing abstraction: `MoveTiming { recovery, startup_end, startup_speed }` in `boss_support.h`. `boss_advance_clock` applies it on the player's native callback. It scales both player speed at `+0x6A8` and delta at `+0x24`, then stops acceleration at the startup boundary. Animation and timing events advance through their shared native clock. The original native tick recomputes these fields; there is no persistent global speed patch.

```cpp
const float remaining = boundary - frame;
float accelerated = delta * timing.startup_speed;
if (accelerated > remaining) accelerated = remaining;
// Apply only when accelerated > delta; do not seek either event cursor.
```

We are **not** arbitrarily deleting animation frames or changing a byte string for each speed slider value. Recovery editing changes when native cancellation/Pulse becomes available; an uncancelled tail can finish normally. Some adaptations also change private transition and payload bytes, so the structural edits must remain documented independently of speed policy.

The current public speed control is the shared integer `frost_startup_speed` in 1–8. It also accelerates the Izuna opener. It is not a generic per-move speed slider and does not implement slow motion or arbitrary start-frame seeking. For a future per-move slider, expose a stable move ID and a multiplier bounded by an engine-owned phase policy. A future start/end-frame option must be restricted to validated event-safe boundaries: jumping over hit registration, root motion or paired-action setup can break gameplay. The private engine should own allowed ranges and paired-camera exclusions; public configuration should never supply offsets or raw bytes.

## Runtime lifecycle and resource ownership

`prepare_session.py` discovers William and resolves enabled native source banks. Exact build, action key, motion, flags, transition counts and resource identity are checked before producing a runtime session. Source actors and process addresses are temporary discoveries, not move IDs. The resource loader owns the imported action/motion/timing/camera packages across mission changes; the supervisor reacquires session objects. Native code is built once per source revision, not per mission.

`runtime_session.py` and `boss_session_schema.h` define the same ABI: magic `0x3153454E`, version 10, size 5752 bytes, 32 imports, 32 adapters, eight skill bindings, two launch profiles and three tracking rates. A `MoveImport` is 96 bytes, `MoveAdapter` 64 and `SkillBinding` 32. Process ID, process birth time and configuration tag reject stale sessions. Double-copy validation rejects concurrent mutation; session configuration is immutable after acceptance.

The engine uses existing native callbacks for action setting, frame advancement, action lookup, voice and resource integration. MinHook supplies the required detours and remains an active dependency, not unused scaffolding. Removing it requires replacing those hooks. `third_party/minhook` and its license are retained. Dispatch and observation protocols are bounded shared-memory structures; the trace ring has 512 entries. Stale publisher/device/session generations invalidate pending input instead of replaying it.

### Private action adaptation

Native action lookup uses a full DWORD key within the actor's enabled source banks. A low 16-bit value is insufficient. Jin C64/C66 and Okatsu C64/C66 are different records. The import namespace keeps source-bank identity, motion/timing and adapter ownership; numerical equality does not authorize cross-bank redirection.

The engine copies the selected descriptor, payload, transition rows and relevant combat data into private storage. Native sources are checked before and after dependent reads. Transition rows are 48 bytes; combat rows are 128. The descriptor prefix is `0xD0` bytes. The copies keep source resource references while replacing selected input, recovery and continuation paths. Lookup interception is scoped to the current owned imported action; it does not globally replace every equal key.

Adapter kinds are 0 baseline, 1 native replacement, 2 skill entry, 3 paired action, 4 ordinary continuation and 5 isolated jump. `repeat_namespace.h` retains native graph edges within the imported source namespace. Automatic animation-end continuation, native input continuation and paired contact are distinct relationships. In particular, temporal adjacency in a recording cannot be used as an automatic graph edge without native evidence.

Native recovery retains William's stance and ordinary movement rules. Boss completion paths are adapted to weapon-drawn recovery rather than a boss's sheath/idle state. Jin source effects 46 and 47 can swap weapon slots: effect byte `+0x2B` selects a slot, with exact native signature validation. `boss_preserve_weapon` removes only matching 128-byte source effect identities from the private payload's sixteen six-byte schedules at `+0x40..+0x9F`. It does not disable all effects or alter the source resource. The latest weapon/sheath preservation still needs gameplay acceptance.

## Controller, Frost Moon and native skill behavior

Controller state is sampled coherently on the native frame path. Saved calibration maps device bits; XInput face names are API names, not PlayStation labels. Holds use one threshold and explicit tap/hold ownership so holding Low Triangle can supersede an empty-Ki grapple while a tap remains available. Device/epoch changes or a sampling gap of 100 ms reset gesture history; reconnect discovery is bounded. The code does not write right-stick axes or camera position.

Frost Moon is RB plus two edges of the same *other* stance face button: XInput A/PS Cross selects Low, X/Square Mid, Y/Triangle High. The origin stance is retained across native Pulse/Flux transitions so both other destinations stay available. Releasing and repressing RB can supply another chord edge. A recognized request owns the accidental light/heavy/dodge input generated by spamming the chord. Movement alone does not invalidate the opportunity; damage, paired animations and unrelated actions can.

The window opens at earliest native Ki availability, not perfect Ki Pulse. `frost_window_seconds=0` follows remaining native availability. A nonzero setting clamps the configurable fixed window to 0.1–1.5 seconds. The older 0.75-second request is preserved by selecting 0.75, but the revised baseline uses the full native window for repositioning. Pulse state is latched before native action selection consumes it; Flux does not mint a fresh unlimited deadline.

The saved gameplay preset uses Low full Flying Swallow, Mid somersault and High the recorded downward sword slash. High slash stays at native speed. High LB + Square selects the launcher/contact/Izuna graph. Mid heavy and Mid dodge Triangle enter Jin's five-hit A (`BBF → C63 → C64 → C65 → C66`). Low heavy uses D (`C6E → C6F → C70`), and Low dodge Triangle enters its second hit. The four-hit B remains recorded data, not a bound replacement. Running and Square dodge paths retain native priority. The isolated jump is available as an adapter but unbound; the LB + RB + Circle chord has no custom move.

## Engine-owned tuning inventory

The following are policy values, not inferred universal Nioh rules. `outputs/Nioh1-Sword-Move-Observations.xlsx` contains the human-readable Tuning ledger; `catalogue/imports/` contains source requirements and graph recipes. Source bytes and current implementation remain authoritative when revising a policy. Do not conflate source recovery values with adapted cancellation frames.

| Policy | Current value and scope | Implementation |
|---|---|---|
| Okatsu dash | Startup through frame 30 at 2x; recovery/Pulse 54 | `boss_move_timing` |
| Okatsu leap | Native speed; recovery/Pulse 78 | `boss_move_timing` |
| Low standalone launcher | First 8 frames at 2x; cancellation/Pulse 21; full tail retained | `boss_move_timing` |
| Izuna opener | First 12 frames at configured startup speed (baseline 8x); recovery 54 | `boss_move_timing` |
| Flying Swallow/somersault entry | First 19 frames at configured startup speed when Frost-bound | `boss_move_timing` |
| Somersault landing | Cancellation/Pulse 30 | `boss_move_timing` |
| Downward sword slash | Native speed throughout; final strike cancellation/Pulse 29 | `boss_move_timing` |
| Imported per-hit recovery | A: 20/25/35/30/30; D: 35/45/45; other records use their validated import recovery | Import recipes and timing policy |
| Ki Pulse adaptation | 40 percent; fill 25 frames; hold 24 frames; start equals adapted recovery | Private payload `+0x33/+0x38/+0x3A/+0x3C` |
| Native cancellation | Recovery/cancel thresholds at payload `+0x24/+0x26` aligned to recovery | `boss_support.h` |
| Light human launcher | Resistance below 75: weight ×0.75, upward impulse 14 | `engine_policy.py` |
| Medium human launcher | Resistance below 200: weight ×0.45, upward impulse 17 | `engine_policy.py` |
| Unmatched launcher baseline | Weight ×0.5, impulse 16; source combat vertical fields 12 become 16 | `launcher_weight.h`, private combat row |
| Airborne sword follow-up | Extra upward impulse 2, final upward impulse capped at 20; paired actions and Izuna opener excluded | `launcher_weight.h` |
| Horizontal tracking | Izuna 720, somersault 720, Flying Swallow 540 degrees/second | Private `TRACKING_RATES` |
| Tracking envelope | Izuna horizontal radius 600, aerial radius 1200; vertical difference ≤1200 native units | `windup_support.h` |
| Tracking phase end | C79 frame 26, C83 frame 29, C74 frame 20; other supported phases bounded by action lifetime | `windup_support.h` |
| Voice substitution | William cue hash `0x97933946`; only validated imported voice events | `voice_support.h`, import voices |

These modifications change collision weight and upward impulse, **not a general enemy gravity constant**. Weight is applied around the single validated standalone-launcher damage reaction through native `Character::SetWeight`; the engine tracks up to eight owned overrides and restores only its exact applied value when ownership ends. Restoration checks actor, owner, collider and descriptor identity so a later writer is not overwritten. Rejected or paired reactions release provisional ownership.

The observed footsoldier and armored rogue both had native weight 100. Resistance separated these two observations; the rogue was cursed. Therefore the thresholds are provisional resistance bands, not stable enemy species IDs or proof that all light/medium humans share those values. A better future enemy policy should key verified archetype plus relevant status modifiers, with a fallback band. Record unmodified archetype/status data before changing that classification.

Tracking reads the actual player lock target at controller `+0x90`, falling back to the optional attack handle at `+0x40`. It resolves and rechecks the target on each callback and calls the native yaw-only setter for movement `+0x54`. It does not teleport the actor, translate its hitbox or force a victim into a paired animation. Turn increments use unaccelerated delta, so faster startup does not multiply degrees per second. This corrects a traced failure to find the lock target, but hit confirmation and airborne Izuna pairing remain gameplay questions.

Paired Izuna preserves native contact gates, attacker/victim roles and camera lifecycle. The engine borrows validated camera resources only for the owned paired action and restores them on exit. Paired playback stays native speed. It does not forcibly pair an airborne enemy just because it is locked on. If the native catch still misses, capture contact/reaction data before loosening unknown paired-state constraints.

## What must be logged when changing an import

Every change needs the boss/source-bank identity, full action key, motion and timing IDs, source hash, native transition/combat evidence and the adapted result. Record timing phase boundaries and speed separately from recovery/cancel/Pulse thresholds. Record input binding and native assignment checks separately from source graph edges. The Tuning ledger should identify an engine rule versus a public preset value and whether validation was offline or observed in game.

The less visible hardcoded adaptations also need that ledger: source flags and exact signature checks; private descriptor/payload offsets; transition pruning and replacement; completion stance/sheath behavior; weapon effect filtering; native input debounce/suppression; recovery, Living Water and running-priority rows; source resource lifetime; camera borrowing; voice cue substitution; launch classification, weight ownership, impulse changes and air-hit exclusions; tracking target resolution, rate and phase/range limits. These are not exposed as arbitrary user-editable bytes.

Build-specific ABI constants are contracts rather than sliders. `boss_probe.py` and `action_banks.py` describe read layouts; `boss_session_schema.h`, `dispatch_protocol.h` and `trace_protocol.h` define process interfaces; `boss_session_config.h` validates them. Exact expected byte signatures and RVAs live beside the native helper that uses them. Preserving those source locations avoids a second unsynchronized offset dictionary. Shared action/motion/timing packages cannot safely be pruned record-by-record without proving internal reference closure; the playable catalogue is sword-only while shared packages may contain unused source records.

## Recording, inference and contributor workflow

`boss_probe.py` opens the exact supported process for read-only observation. It samples action state changes every 10 ms and captures bounded metadata (up to 128 transition rows and 16 combat rows in the encounter path). Metadata must match its preceding owner-validated descriptor/payload state. Reads are non-atomic; races, missing objects and gaps are recorded. A process address is never a permanent identity.

`encounter_recording.py` wraps this in continuous takes. It finds source actors by the workbook's action/motion fingerprints, reacquires after actor loss or reload, and preserves existing takes. A recognized boss take can run for 86400 seconds; an unassigned scout take refreshes after 30 seconds. Selecting a boss name does not prove the observed actor is that boss. Cooperative stop flushes the take and reconstructs it. A runtime trace can seed discovery, but process birth and ownership must be revalidated.

```powershell
python -B runtime\encounter_recording.py --boss-id jin_hayabusa --outdir runtime\recordings\jin-session
# Wait for status.json state=recording before starting a described attempt.
New-Item runtime\recordings\jin-session\STOP -ItemType File
python -B runtime\encounter_recording.py --boss-id jin_hayabusa --outdir runtime\recordings\report --reconstruct runtime\recordings\jin-session\take-0001\events.jsonl
```

The app already provides Record, Stop and Import. **Describe recent string** now appends a description to the active recording after the user pauses the game. Capture continues; the app neither pauses nor controls Nioh. The label includes boss, take, latest complete persisted timestamp and notice wall time. It explicitly does not claim that the timestamp is the exact last frame of the described move. Mention an intervening attack or death in the description.

Reconstruction binds full action/motion/timing identities in two passes, keeps unknown low-word records uncertain and splits actor sequences at gaps, corruption, identity changes and timestamp regressions. Sequences are bounded to 64 actions. Repeated state samples increment `observations`; only a changed descriptor/action counter increments `observed_entries`. The first observation after a gap is `censored_observations`, because its start was not seen. A same-action recommit remains visible instead of being merged away.

`catalogue/recordings/index.json` is the common source index for old Okatsu, Jin and Maria captures and retained human descriptions. Raw captures and labels are hash-checked and remain unchanged. `catalogue/recordings/summary.json` is regenerated by `python -B -m catalogue.recordings`. The workbook remains the single curated move/label authority; the report joins those labels instead of inventing another maintained catalogue. Duplicate raw hashes are counted once. Aliases such as the standalone launcher and Izuna opener share a source identity and are not double-counted.

The report ranks only known sword identities observed on an attributed boss. The workbook occurrence sheet is a snapshot of that report; rebuilding the JSON report alone does not rewrite the workbook. Maria's sampled trace lacks proven boss attribution and its native trace uses a different event format with potential overlap, so it is retained but excluded from common occurrence ranking. Counts describe these targeted captures, not natural boss move probabilities. State-sample counts, observed starts and uncertain first sightings remain distinct. Ranking a string should use its verified opener, not add all hit counts and call that string frequency.

The next useful inference step is to combine three evidence types: repeated observed sequences, decoded native transition conditions/windows, and user annotations. Repeated adjacency alone is a candidate; a decoded gated edge supports a possible native continuation; a clean labeled isolated recording supports the intended move name. Preserve alternative branches and uncertainty instead of collapsing them into one guessed combo. Compare motion/timing, conditions and resource identity to identify new variants; do not merge them just because their low-word IDs match.

For a contributor-facing app, use the same flow: select boss, wait for verified recording, fight, manually pause, describe the recent sequence, resume, then stop/export. A timeline should let the contributor adjust the proposed label range and mark uncertainty. The current description button is the first part of this flow; editable segmentation and a polished export wizard are not implemented yet.

The proposed standalone recorder should have its own repository and portable Windows package, used by contributors and maintainers alike. Extract one maintained read-only backend from the existing probe/reconstruction code. Replace its workbook/trainer dependencies with a small versioned boss-signature manifest. Keep the private gameplay engine, physics policy and native hooks out of that package. The mod should consume the recorder's versioned output instead of maintaining a second recorder implementation.

Its UI should need no terminal, Python installation, controller calibration or hexadecimal IDs. Start recording finds Nioh and displays Waiting for game, Finding boss, Recording, Recovering after reload or Stopped. Show Ready to fight only after validated boss sampling begins. Continuous capture lets the user pause after a move rather than predict it. Describe last move accepts ordinary language plus New, Repeat, Unsure or Interrupted. Proposed time ranges remain editable because a pause is not an exact animation boundary.

Stop and Export should produce one shareable file in Downloads and open its folder. No account or automatic upload is needed for the first release. Our importer should validate schemas and hashes, deduplicate captures and preserve uncertain labels before any catalogue promotion. Repeated sequences and native transition gates can suggest strings; they cannot reliably supply every move name or prove every observed sequence is a combo. Human descriptions remain review evidence, never gameplay configuration.

The portable package must be checked on a clean Windows machine without developer tools, including death/retry, mission reload, interrupted capture and unsupported game builds. Its backend needs process query/read access; it does not need gameplay modification capabilities. See Microsoft's [ReadProcessMemory contract](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-readprocessmemory). Packaging and the separate recorder repository are proposed next work, not implemented by this cleanup.

Export should produce a local ZIP in Downloads containing a versioned manifest, raw JSONL takes, labels and a readable spreadsheet summary. The manifest should include build/schema version, capture hashes, boss attribution and sampling gaps. Spreadsheet columns should show move IDs, motion/timing, description, take/time range, observed entries and confidence/evidence. Keep raw structural evidence in JSONL, not thousands of opaque byte cells. Contributors can send the bundle manually; automatic uploads are not implemented or required. Do not include unrelated process logs or absolute personal paths in a public export.

## Validation and unresolved work

`tests/test_move_readiness.py --offline` and `tests/test_resource_crashes.py` are the only maintained test entrypoints. They exercise Python validation, lifecycle/reconstruction behavior and native harnesses. Native cases live under `tests/native/`; moving them does not add a third test runner. `Test-Offline.ps1` runs both. Build and fixture success are implementation checks, not gameplay approval.

The player previously accepted all Frost routes, High slash speed, Flying Swallow speed and immediate Mid Tiger Sprint. Subsequent Mid five-hit/dodge, tracking, airborne catch and weapon/sheath preservation changes require another gameplay pass. The next requested data task is fresh continuous Jin recording with pause-time descriptions; William recording is deferred. No recording should be announced ready merely because discovery has started.

Cleanup removes obsolete packaging, duplicate captures, generated reports, old build/test logs and one-off research scripts. Unique capture evidence, human descriptions, mechanical findings, active engine modules, native fixtures and required MinHook code remain. Git history retains removed historical tools. Runtime output stays under ignored `runtime/` state directories; maintained evidence belongs under `catalogue/recordings/` or `research/`, not a growing scratch folder.

The second cleanup removes unreferenced historical investigations, capture-side discovery dumps, unused extracted assets and the duplicate MinHook license. The engine and crash tests read assets from the installed game archives. The small Jin action package remains because curated evidence references it. Indexed raw captures, labels, evidence dependencies and active code remain. Removed material is recoverable from commit `c91aded`, with local copies retained outside the repository. History has not been rewritten: this trims checkout contents, not historical Git objects.
