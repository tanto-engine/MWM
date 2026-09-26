# Tanto Engine

Private developer tooling and native runtime implementation for building game mods. This repository has no user-facing GUI. Products select a backend, data and capabilities, then build independent executables. Users never need the development checkout.

| Repository | Owns | Consumer distribution |
|---|---|---|
| neuriv/tanto-engine | Native integration, ownership/lifecycle, private policy, validation, builds and tests | None |
| neuriv/tanto-recorder | Read-only recording, boss signatures, annotations, export and capture archive | TantoRecorder.exe |
| neuriv/tanto-sword-mod | Sword definitions, import/resource profiles, default bindings and product UI | TantoSword.exe with selected micro-runtime |

The first backend is the existing exact-build Nioh 1 sword implementation. The framework does not yet implement arbitrary weapons or asset formats. Additional mods need validated adapters and content definitions; putting an unknown move ID in JSON is insufficient. Engine-owned policies such as enemy weight/impulse and tracking are compiled/configured by developers, not exposed as unrestricted GUI fields.

## Developer workflow

Keep the three repositories as sibling checkouts. Use Python 3.10+ and Windows x64 GCC/G++ for native development. Build-only dependencies are pinned in requirements-build.txt. Product Build.ps1 scripts verify their engine commit before building. build_product.py stages an explicit capability subset and emits a SHA-256 file manifest. Recorder includes only read-only process/bank/controller readers. Sword includes its required runtime and native DLLs; recording/report CLI and catalogue editing are cut from the staged runtime.

```powershell
.\runtime\native\Build.ps1
.\Test-Offline.ps1
python -B build_product.py ..\tanto-recorder --stage-only
python -B build_product.py ..\tanto-sword-mod --onedir
python -B build_product.py ..\tanto-sword-mod
```

The two maintained test entrypoints remain tests/test_move_readiness.py and tests/test_resource_crashes.py. They exercise source logic, native owned-memory fixtures, cross-repository integration, contributor export and package boundaries. Clone both product repositories alongside this checkout for integration tests. The resource crash test also reads the supported local game archives. Passing tests does not certify live gameplay.

`runtime/` holds the backend and reusable development interfaces. `tests/` holds fixtures and checks. `third_party/minhook/` is required by current native detours and is built into Sword runtime libraries. Recorder does not receive it. Removing MinHook without replacing those detours breaks the backend. Resource profiles belong to the mod because they specify the actual assets that product loads.

Recorded Python signatures live in `runtime/nioh_sword.py`; native airborne signatures, player templates and timing recipes live in `runtime/native/nioh_sword_definitions.h`. `move_timing.h` evaluates bounded startup phases without source identities or process writes. The ownership layer selects a recipe only when its full recorded signature and binding/continuation requirements match. Native template validation now checks transition count and recovery as strictly as Python preparation. Other Nioh-specific transition, effect and hook definitions still live beside their backend helpers; this is a bounded extraction, not a completed general mod framework.

There is no outputs/, research/ or capture catalogue in this engine checkout. Old investigations and the workbook remain recoverable from history; local archival copies also exist outside the repositories. The Downloads workbook is historical, not an engine dependency. Retained source captures and labels live in Tanto Recorder.

Compilation and selective packaging reduce what is distributed; they cannot make local code unextractable. No engine development GUI, general plugin loader, DRM framework or automatic data upload is introduced. The products are privately published prereleases; gameplay verification remains deferred.

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

The following are policy values, not inferred universal Nioh rules. The archived Downloads workbook contains the historical human-readable Tuning ledger; `../tanto-sword-mod/data/imports/` contains source requirements and graph recipes. Source bytes and current implementation remain authoritative when revising a policy. Do not conflate source recovery values with adapted cancellation frames.

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

Startup/recovery recipes are checked at compile time for finite bounded rates, phase ends and compatible recovery. `boss_move_timing` resolves binding-dependent recipes, and `move_timing_delta` caps acceleration at their startup boundary while preserving a native tick that already crosses it. Recovery enables cancellation; it does not truncate the native tail. General speed sliders, arbitrary start/end frames and frame skipping remain unimplemented because the required event boundaries are not established.

These modifications change collision weight and upward impulse, **not a general enemy gravity constant**. Weight is applied around the single validated standalone-launcher damage reaction through native `Character::SetWeight`; the engine tracks up to eight owned overrides and restores only its exact applied value when ownership ends. Restoration checks actor, owner, collider and descriptor identity so a later writer is not overwritten. Rejected or paired reactions release provisional ownership.

The observed footsoldier and armored rogue both had native weight 100. Resistance separated these two observations; the rogue was cursed. Therefore the thresholds are provisional resistance bands, not stable enemy species IDs or proof that all light/medium humans share those values. A better future enemy policy should key verified archetype plus relevant status modifiers, with a fallback band. Record unmodified archetype/status data before changing that classification.

Tracking reads the actual player lock target at controller `+0x90`, falling back to the optional attack handle at `+0x40`. It resolves and rechecks the target on each callback and calls the native yaw-only setter for movement `+0x54`. It does not teleport the actor, translate its hitbox or force a victim into a paired animation. Turn increments use unaccelerated delta, so faster startup does not multiply degrees per second. This corrects a traced failure to find the lock target, but hit confirmation and airborne Izuna pairing remain gameplay questions.

Paired Izuna preserves native contact gates, attacker/victim roles and camera lifecycle. The engine borrows validated camera resources only for the owned paired action and restores them on exit. Paired playback stays native speed. It does not forcibly pair an airborne enemy just because it is locked on. If the native catch still misses, capture contact/reaction data before loosening unknown paired-state constraints.

## What must be logged when changing an import

Every change needs the boss/source-bank identity, full action key, motion and timing IDs, source hash, native transition/combat evidence and the adapted result. Record timing phase boundaries and speed separately from recovery/cancel/Pulse thresholds. Record input binding and native assignment checks separately from source graph edges. The Tuning ledger should identify an engine rule versus a public preset value and whether validation was offline or observed in game.

The less visible hardcoded adaptations also need that ledger: source flags and exact signature checks; private descriptor/payload offsets; transition pruning and replacement; completion stance/sheath behavior; weapon effect filtering; native input debounce/suppression; recovery, Living Water and running-priority rows; source resource lifetime; camera borrowing; voice cue substitution; launch classification, weight ownership, impulse changes and air-hit exclusions; tracking target resolution, rate and phase/range limits. These are not exposed as arbitrary user-editable bytes.

Build-specific ABI constants are contracts rather than sliders. `boss_probe.py` and `action_banks.py` describe read layouts; `boss_session_schema.h`, `dispatch_protocol.h` and `trace_protocol.h` define process interfaces; `boss_session_config.h` validates them. Exact expected byte signatures and RVAs live beside the native helper that uses them. Preserving those source locations avoids a second unsynchronized offset dictionary. Shared action/motion/timing packages cannot safely be pruned record-by-record without proving internal reference closure; the playable catalogue is sword-only while shared packages may contain unused source records.

## Outstanding checks

Offline validation covers signature rejection, timing boundaries, retained private resources, actor identity changes and Recorder evidence handling. It does not complete these checks:

| Area | Required evidence or implementation |
|---|---|
| Enemy classification | Record the same uncursed archetypes with and without relevant status effects; preserve native weight, resistance and reaction identity before replacing provisional bands. |
| Lifecycle | Record shrine/menu/cutscene entry and exit, equipment changes, death/retry and mission changes; check retained action/motion/timing/effect/camera ownership and restored weapon state. |
| Resource coverage | Inventory dependencies and exercise effects beyond the four retained packages before admitting additional imports. |
| Controllers | Implement explicit XInput slot selection consistently for Python and native gestures; verify DS4, DualSense, Xbox and SCUF reconnects. DirectInput-only support and unmapped paddles remain unresolved. |
| Latency | Correlate input sample, recognized gesture, dispatch and first changed animation frame on one clock; record sampling uncertainty before altering polling or startup. |
| Native semantics | Capture damage, Ki damage, hitbox/contact and unknown record fields against controlled baselines; matching bytes alone do not establish their meaning. |

Further executable builds/releases and live gameplay verification are deferred. No readiness receipt is implied by the offline checks.
