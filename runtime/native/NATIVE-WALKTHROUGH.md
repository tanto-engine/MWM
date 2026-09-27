# Native runtime walkthrough

For a Nioh player, this layer lets William use a configured imported sword move while preserving the game's input, animation events, Ki Pulse and recovery decisions. An action key is not a move name: the same key can mean different attacks in different banks. The recorded key, motion, flags and transition layout must all match before adaptation applies. Baseline C64/motion 1220 tap and C66/motion 1230 charge remain separate from a configured held string.

## Follow one action

1. `resource_loader.cpp` constructs and retains native action, motion, timing and camera packages on the game's update thread. Motion decoding validates package bounds and allocation results before publishing clips.
2. `boss_session_schema.h` defines the launcher's fixed configuration ABI. `boss_session_config.h` validates the process identity, import graph, settings and bindings before callbacks consume it.
3. `observer.cpp` runs the frame/action/voice hooks. `controller_input.h` samples Nioh's loaded XInput API once per player frame, so Steam's controller translation and every gesture share one timestamped sample.
4. `dispatch_support.h`, `replacement_support.h`, `sword_bindings.h` and `frost_moon.h` decide whether a native input or gesture may select an import. A stance, owner, controller or context-epoch change invalidates pending input.
5. `boss_support.h` copies the selected descriptor, payload and transition rows into private storage, then temporarily borrows the matching motion/timing resources. This preserves shared source data and the boss's own moves. Native next-press, contact and recovery rules determine continuation.
6. `windup_support.h` changes bounded clock deltas rather than seeking frames. `voice_support.h` substitutes only matched source vocal events; unrelated sounds still reach the native handler. `launcher_weight.h` records ownership before temporarily adjusting a hit reaction.
7. Completion restores only resource slots still owned by this runtime. Stop disables hooks after the runtime's recovery checks, retaining the DLL, mappings and trampolines because already-entered callbacks or native previous-action references can outlive the visible move.

## Read the memory contracts

| Representation | Meaning |
| --- | --- |
| Actor `+0x50`, `+0x58` | Owner and current action descriptor; both are rechecked as identities, not assumed permanent. |
| Descriptor `+0x20` | Payload pointer; the payload supplies motion, timed events and recovery fields. |
| Private descriptor/payload | Module-lifetime `0xD0`/`0xB0` copies, not transient stack buffers. |
| `BossSession.originals[4]` | Saved motion `+8/+0x28` and timing `+0x10/+0x28` slot values used for conditional restoration. |
| QPC values | Performance-counter ticks; divide by the shared frequency for seconds. Animation frames and milliseconds use different units. |
| Trace/command markers | Matching positive begin/end sequence numbers commit a record. The controller snapshot instead uses odd/even publication sequencing. |
| Import selection | Internal slots and `next_variant` are zero-based; configured binding variants are one-based with zero meaning unset. |
| Sword definition tables | Exact signatures and ordered timing policy. Hex keys, decimal motion IDs and adapter kinds are distinct fields. |

Struct sizes, offsets and alignment assertions protect the external ABI; changing a struct requires matching producer changes, not merely rebuilding the DLL. Resource addresses belong to one process/session. Guarded reads reject stale pointers; a successful read alone does not prove ownership.

`runtime.cpp` includes `observer.cpp` with the production feature switches. Header definitions intentionally participate in that translation unit. `Build.ps1` compiles MinHook as C and links two DLLs; it does not launch Nioh. `Test-Offline.ps1` remains the single repository command for the two offline suites and their native support fixtures.

## Vendored hook mechanics

MinHook decodes whole prologue instructions, copies them into an executable trampoline, rewrites relative operands and patches the original entry with a jump. Its old/new instruction offsets also relocate suspended thread contexts when enabling or disabling a hook. The HDE tables classify instruction bytes; they contain no game data. Packed jump structs are literal machine-code layouts.

The local single-target disable correction selects `ACTION_DISABLE` during thread freezing. Previously that path selected `ACTION_ENABLE`, causing context translation to skip already-enabled hooks. The owned-memory regression fails at stage 5 before the correction and passes afterward; mocked thread APIs prevent real thread suspension. Engine Stop retains trampolines, so this regression establishes incorrect context translation, not a demonstrated gameplay crash. See `third_party/minhook/UPSTREAM.txt` for provenance.

Raw capture fixtures remain evidence, not configurable examples. Offline fixtures verify memory contracts and deterministic decisions; they do not establish audible voice playback, physical-controller latency or completed gameplay acceptance.
