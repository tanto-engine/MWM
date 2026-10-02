// Passive builds forward all game arguments and results unchanged. Repeat mode
// schedules gestures, shortens C64 windup, and adapts configured boss voices.
#include <windows.h>
#include <stdint.h>
#include <wchar.h>
#include <cmath>
#include "MinHook.h"
#include "trace_protocol.h"

using ActionFn = bool (*)(void*, uint32_t, void*);
static ActionFn original_action;
static void* hook_target;
static TraceMapping* trace;
static HANDLE mapping_handle;
static volatile LONG writer_lock, lifecycle_lock;
static bool hook_created, minhook_initialized;
#ifdef RESEARCH_REPEAT
// RVA719050 takes RCX=action node, XMM1=delta. XMM0 is the effective delta;
// preserve it except for the explicitly scoped C64 early-clock adjustment.
using FrameFn = float (*)(void*, float);
static FrameFn original_frame;
static void* frame_target;
static bool frame_hook_created;
using VoiceFn = void (*)(void*, void*, void*, int32_t);
static VoiceFn original_voice;
static void* voice_target;
static bool voice_hook_created;
#endif

template<class T> static bool copy_field(uint64_t address, T& value) {
    // Read one native field without directly dereferencing a transient address.
    // Use ReadProcessMemory and require the complete field width to be copied.
    // Lifecycle changes must become rejected reads rather than access violations.
    SIZE_T count = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address), &value, sizeof(value), &count) && count == sizeof(value);
}

#ifdef RESEARCH_DISPATCH
#include "dispatch_support.h"
#endif
#ifdef RESEARCH_REPEAT
#include "voice_support.h"
#include "windup_support.h"
#include "controller_input.h"
#include "replacement_support.h"
#include "frost_moon.h"
#include "cast_pulse.h"
#include "launcher_weight.h"
#endif

enum class ActionRequest { Native, Gesture, Chain, Heavy, Frost, Followup, CastPulse };
static bool observed_action_impl(void* actor, uint32_t key, void* context, ActionRequest request=ActionRequest::Native) {
    // Run the shared action hook with scoped gesture, chain and research policies.
    // Preserve native arguments and errors except for a fully validated imported substitution.
    // Trace evidence records both requested action and actual native result for later acceptance.
    const DWORD incoming_error = GetLastError();
    const bool frame_mode=request!=ActionRequest::Native;
#ifdef RESEARCH_REPEAT
    if (key==0xD3A && dispatch && !InterlockedCompareExchange(&dispatch->control.enabled,0,0)
        && reinterpret_cast<uint64_t>(actor)==boss_session.player && mid_light_active()) {
        SetLastError(incoming_error); return false;
    }
#endif
#ifdef RESEARCH_BOSS
    BossCallScope scope;
#endif
    TraceRecord record{};
    const bool record_this = trace && InterlockedCompareExchange(&trace->header.enabled, 0, 0);
    uint32_t forwarded_key = key;
    void* forwarded_context = context;
#ifdef RESEARCH_DISPATCH
    DispatchCommand command{};
    DispatchReason reason = Disabled;
#ifdef RESEARCH_REPEAT
    if (record_this && request==ActionRequest::Native && key>=0xD5F && key<=0xD78
        && reinterpret_cast<uint64_t>(actor)==boss_session.player)
        latch_native_frost();
    if (record_this && request==ActionRequest::Frost) reason=choose_frost_moon(command);
    else if (record_this && request==ActionRequest::CastPulse) reason=choose_cast_pulse(command);
    else if (record_this && request==ActionRequest::Followup) reason=choose_attack_followup(command);
    else if (record_this && request==ActionRequest::Heavy) reason=choose_heavy(command);
    else if (record_this && request==ActionRequest::Chain) reason = choose_chain(actor, command);
    else
#endif
    if (record_this) reason = choose_dispatch(actor, key, context, command, frame_mode);
    if (reason == Accepted || reason == NativeHeavyTap || reason == NativeCastPulse) forwarded_key = command.desired_key;
#else
    (void)frame_mode;
#endif
#ifdef RESEARCH_REPEAT
    if (frame_mode && reason != Accepted && reason != NativeHeavyTap && reason != NativeCastPulse) { SetLastError(incoming_error); return false; }
    uint64_t current = 0;
    const bool suppress_guard = !frame_mode && !context && reinterpret_cast<uint64_t>(actor)==boss_session.player
        && (custom_chord_blocks(key) || ((key == 24 || key == 25)
        && InterlockedCompareExchange(&boss_active, 0, 0)
        && reinterpret_cast<uint64_t>(actor) == boss_active_player && boss_player_valid()
        && copy_field(boss_active_player + 0x58, current) && boss_is_preview_descriptor(current)));
    if (suppress_guard) reason = BossGuardSuppressed;
#endif
    if (record_this) {
        record.actor = reinterpret_cast<uint64_t>(actor);
        record.context = reinterpret_cast<uint64_t>(context);
        record.input_key = key;
        record.thread_id = GetCurrentThreadId();
        LARGE_INTEGER now; QueryPerformanceCounter(&now); record.qpc = now.QuadPart;
        if (copy_field(record.actor + 0x50, record.owner)) record.valid_fields |= 1;
        if (copy_field(record.actor + 0x58, record.before) && copy_field(record.before, record.before_key))
            record.valid_fields |= 2;
    }
#ifdef RESEARCH_BOSS
    uint64_t private_banks[3]{};
#ifdef RESEARCH_REPEAT
    if (!suppress_guard)
#endif
    if (reason != NativeCastPulse && !boss_prepare_call(actor, key, reason, command, forwarded_key, forwarded_context, private_banks)) {
        SetLastError(incoming_error);
        return false;
    }
#ifdef RESEARCH_REPEAT
    // A failed frame preflight never turns into an unsolicited key-0 setter.
    if (frame_mode && reason != Accepted && reason != NativeHeavyTap && reason != NativeCastPulse) { SetLastError(incoming_error); return false; }
    if (request==ActionRequest::Frost && reason==Accepted) boss_frost_playback=true;
#endif
#endif
#ifdef RESEARCH_DISPATCH
    record.reserved = forwarded_key;
    record.valid_fields |= uint32_t(reason) << 8;
    if (reason == Accepted) record.valid_fields |= TRACE_SUBSTITUTED;
#ifdef RESEARCH_REPEAT
    if (frame_mode) {
        record.valid_fields |= 1u << 18;
        record.context = uint64_t(command.edge_qpc);
    }
#endif
#endif
    SetLastError(incoming_error);
#ifdef RESEARCH_REPEAT
    ReplacementScope replacement_scope(actor, command, reason);
    restore_launch_weights(reinterpret_cast<uint64_t>(actor),true);
    const auto launch_hit=suppress_guard ? LaunchHit{} : launcher_hit(actor);
    SetLastError(incoming_error);
    const bool result = suppress_guard ? false : original_action(actor, forwarded_key, forwarded_context);
#else
    const bool result = original_action(actor, forwarded_key, forwarded_context);
#endif
    const DWORD native_error = GetLastError();
#ifdef RESEARCH_REPEAT
    finish_launch_weight(actor,launch_hit,result);
    restore_launch_weights(reinterpret_cast<uint64_t>(actor),false);
    if (reason == Accepted && !frame_mode) {
        record.reserved = command.desired_key;
        record.valid_fields = (record.valid_fields & ~(255u << 8)) | (uint32_t(Accepted) << 8) | TRACE_SUBSTITUTED;
    }
#endif
#ifdef RESEARCH_BOSS
    boss_finish_call(actor);
#endif
    if (!record_this) { SetLastError(native_error); return result; }
    record.native_result = result;
    if (copy_field(record.actor + 0x58, record.after) && copy_field(record.after, record.after_key))
        record.valid_fields |= 4;
    if (copy_field(record.actor + 0x68, record.bank)) record.valid_fields |= 8;
    if ((record.valid_fields & 4) && copy_field(record.after + 0x20, record.payload)
        && copy_field(record.payload + 0x20, record.motion_key)
        && copy_field(record.payload + 0x34, record.timing_key)) record.valid_fields |= 16;
#ifdef RESEARCH_DISPATCH
#ifdef RESEARCH_REPEAT
    if ((request==ActionRequest::Native || reason==NativeCastPulse) && result && record.actor==boss_session.player
        && (record.valid_fields&4) && record.after_key>=0xD5F && record.after_key<=0xD78)
        cast_pulse_input.closes=cast_pulse_input.edge=0;
#endif
    if (reason == NativeCastPulse && result && record.after_key>=0xD5F && record.after_key<=0xD62) {
        record.valid_fields |= TRACE_CAST_PULSE;
        InterlockedIncrement64(&dispatch->control.dispatch_count);
    }
    if (reason == Accepted && (record.valid_fields & 20) == 20
        && record.after == command.expected_descriptor && record.after_key == command.desired_key
        && record.payload == command.expected_payload && record.motion_key == command.expected_motion)
        record.valid_fields |= TRACE_FINAL_MATCH;
#endif
    // Contention drops an observation instead of blocking a game thread.
    if (InterlockedCompareExchange(&writer_lock, 1, 0)) {
        InterlockedIncrement64(&trace->header.dropped);
        SetLastError(native_error);
        return result;
    }
    const LONG64 sequence = InterlockedCompareExchange64(&trace->header.written, 0, 0) + 1;
    TraceRecord* slot = &trace->records[(sequence - 1) % TRACE_CAPACITY];
    InterlockedExchange64(&slot->sequence_begin, 0);
    InterlockedExchange64(&slot->sequence_end, 0);
    // The sequence markers are written separately around the payload copy.
    CopyMemory(reinterpret_cast<char*>(slot) + 8, reinterpret_cast<char*>(&record) + 8, sizeof(record)-16);
    InterlockedExchange64(&slot->sequence_end, sequence);
    InterlockedExchange64(&slot->sequence_begin, sequence);
    InterlockedExchange64(&trace->header.written, sequence);
    InterlockedExchange(&writer_lock, 0);
    SetLastError(native_error);
    return result;
}

static bool observed_action(void* actor, uint32_t key, void* context) {
    // Expose the ordinary native action-setter hook with unchanged calling convention.
    // Delegate to the shared implementation without frame or chain dispatch permission.
    // Natural game traffic must not accidentally consume a pending controller gesture.
    return observed_action_impl(actor, key, context);
}

#ifdef RESEARCH_REPEAT
static bool publish_player_context(float native_delta) {
    // Publish native frame eligibility and detect every ready-state transition.
    // Pack ownership flags with a sixteen-bit epoch using one atomic update.
    // Short menu or loading interruptions must invalidate external pending gestures.
    uint32_t flags = 0;
    if (boss_player_valid()) flags |= ContextPlayer;
    DispatchCommand latest{};
    uint64_t banks[3]{};
    if (snapshot_command(latest) && latest.player == boss_session.player
        && latest.owner == boss_session.player_owner && latest.vtable == boss_session.vtable
        && copy_bytes(boss_session.player + 0x70, banks, sizeof(banks))
        && !memcmp(banks, latest.banks, sizeof(banks))) flags |= ContextBanks;
    bool original_slots = true;
    for (unsigned i = 0; i != 4; ++i)
        if (!same_field(boss_slot(i), 0, boss_session.originals[i])) original_slots = false;
    if (original_slots) flags |= ContextOriginalSlots;
    if (std::isfinite(native_delta) && native_delta > 0.0f) flags |= ContextAdvancing;
    if (InterlockedCompareExchange(&boss_active, 0, 0)) flags |= ContextImportedAction;
    uint64_t current = 0; uint32_t key = 0;
    if (copy_field(boss_session.player + 0x58, current) && copy_field(current, key)
        && repeat_current_allowed(current, key)) flags |= ContextNeutralAction;
    auto* shared = reinterpret_cast<volatile LONG*>(&dispatch->control.reserved0);
    uint32_t before = uint32_t(InterlockedCompareExchange(shared, 0, 0));
    for (;;) {
        uint32_t epoch = before >> 16;
        if (player_context_ready(before) != player_context_ready(flags)) epoch = (epoch + 1) & UINT16_MAX;
        const uint32_t after = (epoch << 16) | flags;
        const uint32_t actual = uint32_t(InterlockedCompareExchange(shared, LONG(after), LONG(before)));
        if (actual == before) return player_context_ready(after);
        before = actual;
    }
}

static float observed_frame(void* actor, float delta) {
    // Schedule imports and recover resources on the player's existing game-thread frame.
    // Run native work first, then restoration, shared-clock windup adjustment and context gating.
    // Recovery must continue through frozen frames while new input waits for valid gameplay.
    // TODO: verify shrine, menus, cutscenes, death/retry and mission changes in normal play.
    // Context banks show suspension, not its cause; owned-memory checks do not establish live lifecycle coverage.
    const DWORD incoming_error = GetLastError();
    BossCallScope scope; // Stop retains callbacks while one is in progress.
    const bool player_frame=reinterpret_cast<uint64_t>(actor)==boss_session.player;
    const bool restore_weights=InterlockedCompareExchange(&launch_weight_count,0,0)
        && (!dispatch || !InterlockedCompareExchange(&dispatch->control.enabled,0,0) || (player_frame && !boss_player_valid()));
    restore_launch_weights(reinterpret_cast<uint64_t>(actor),restore_weights,player_frame);
    if (trace && reinterpret_cast<uint64_t>(actor) == boss_session.player)
        observe_game_input(trace->header);
    if (player_frame) latch_cast_pulse_window();
    SetLastError(incoming_error);
    float result = original_frame(actor, delta);
    const float native_delta = result;
    const DWORD native_error = GetLastError();
    restore_launch_weights(reinterpret_cast<uint64_t>(actor),restore_weights,player_frame);
    // Reload/recovery paths can change the current descriptor without invoking
    // the setter hook. Restore on the player's ordinary game-thread frame.
    if (InterlockedCompareExchange(&boss_active, 0, 0)
        && reinterpret_cast<uint64_t>(actor) == boss_active_player) {
        uint64_t current = 0;
        if (copy_field(boss_active_player + 0x58, current) && !boss_is_preview_descriptor(current))
            boss_finish_call(actor);
    }
    if (player_frame) boss_update_weapon_visibility();
    result = boss_advance_clock(actor, result);
    // Recovery above must still run when the native clock is frozen or banks
    // are changing. Epochs also invalidate gestures across sub-poll interruptions.
    const bool ready = dispatch && reinterpret_cast<uint64_t>(actor) == boss_session.player
        && publish_player_context(native_delta);
    if (reinterpret_cast<uint64_t>(actor)==boss_session.player) {
        if (!ready) frost_input={};
        else if (boss_frost_variants[0] || boss_frost_variants[1] || boss_frost_variants[2]) {
            SetLastError(native_error);
            observed_action_impl(actor,0,nullptr,ActionRequest::Frost);
        }
    }
    if (reinterpret_cast<uint64_t>(actor)==boss_session.player && boss_hold_variant) {
        if (!ready) { triangle_input.pressed=0; triangle_input.neutral=false; }
        if (!ready && pending_heavy.active) { pending_heavy.active=false; pending_heavy.spent=true; }
        if (pending_heavy.spent) {
            unsigned controller=0; bool down=false, interrupted=false;
            if (heavy_button(controller,down,interrupted) && !down) pending_heavy.spent=false;
        }
        if (ready && pending_heavy.active) {
            SetLastError(native_error);
            observed_action_impl(actor,0,nullptr,ActionRequest::Heavy);
        }
    }
    if (player_frame) {
        if (!ready) cast_pulse_input={};
        else {
            SetLastError(native_error);
            observed_action_impl(actor,0,nullptr,ActionRequest::CastPulse);
        }
        if (!ready) attack_followup_input={};
        else {
            SetLastError(native_error);
            observed_action_impl(actor,0,nullptr,ActionRequest::Followup);
        }
    }
    if (InterlockedCompareExchange(&boss_active,0,0)
        && reinterpret_cast<uint64_t>(actor) == boss_active_player) {
        if (!ready) boss_chain_cancelled = true;
        else {
            SetLastError(native_error);
            observed_action_impl(actor,0,nullptr,ActionRequest::Chain);
        }
    }
    if (ready && trace && InterlockedCompareExchange(&trace->header.enabled, 0, 0)
        && InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)
        && reinterpret_cast<uint64_t>(actor) == boss_session.player
        && !InterlockedCompareExchange(&boss_active, 0, 0)) {
        DispatchCommand pending{};
        if (snapshot_command(pending) && pending.armed == 1
            && pending.chord_sequence > uint64_t(InterlockedCompareExchange64(&dispatch->control.consumed_sequence, 0, 0))) {
            SetLastError(native_error);
            observed_action_impl(actor, 0, nullptr, ActionRequest::Gesture);
        }
    }
    SetLastError(native_error);
    return result;
}

static void observed_voice(void* state, void* timing_record, void* event, int32_t override_bank) {
    // Replace only an imported player's verified boss-vocal timing request.
    // Forward the retained William row through the original native audio handler.
    // Other actors, combat effects, owner routing and native LastError remain untouched.
    const DWORD incoming_error = GetLastError();
    BossCallScope scope;
    observe_cast_pulse_cue(state,timing_record,event);
    const bool suppress = boss_suppress_voice(state, timing_record, event);
    if (suppress && dispatch)
        InterlockedIncrement(reinterpret_cast<volatile LONG*>(&dispatch->control.reserved1));
    SetLastError(incoming_error);
    if (suppress)
        original_voice(state, &william_attack_voice, william_attack_voice.event, override_bank);
    else
        original_voice(state, timing_record, event, override_bank);
    // Only void callers were found. The original handler's LastError passes
    // through; the scope's interlocked decrement does not change it.
}

static bool frame_prologue_matches(void* target) {
    // Confirm the supported native player-frame entrypoint before hooking.
    // Compare its exact observed instruction prefix using a guarded process read.
    // An executable revision mismatch must fail before patching an unrelated function.
    const uint8_t expected[] = {0x40,0x53,0x48,0x83,0xec,0x20,0xf3,0x0f,0x11,0x89,0xa4,0x06,0,0,
        0x48,0x8b,0xd9,0xe8,0x5a,0x8e,0x03,0,0x4c,0x8b,0x43,0x50,0xf3,0x0f,0x11,0x83,0xa8,0x06};
    uint8_t actual[sizeof(expected)]; SIZE_T read = 0;
    return ReadProcessMemory(GetCurrentProcess(), target, actual, sizeof(actual), &read)
        && read == sizeof(actual) && !memcmp(actual, expected, sizeof(actual));
}

static bool voice_prologue_matches(void* target) {
    // Confirm the supported native sound-event handler before hooking.
    // Compare the researched instruction prefix rather than trusting the RVA alone.
    // Audio adaptation must not install a callback on an incompatible game build.
    const uint8_t expected[] = {0x44,0x89,0x4c,0x24,0x20,0x55,0x53,0x57,0x41,0x57,
        0x48,0x8d,0xac,0x24,0x68,0xff,0xff,0xff,0x48,0x81,0xec,0x98,0x01,0,0,
        0x49,0x63,0x40,0x08,0x41,0x8b,0xd9};
    uint8_t actual[sizeof(expected)]; SIZE_T read = 0;
    return ReadProcessMemory(GetCurrentProcess(), target, actual, sizeof(actual), &read)
        && read == sizeof(actual) && !memcmp(actual, expected, sizeof(actual));
}

static MH_STATUS disable_repeat_hooks() {
    // Stop new voice, frame and action entries while retaining their trampolines.
    // Attempt every created hook and preserve any disable error for the caller.
    // One failed disable must not prevent cleanup attempts for the other callbacks.
    MH_STATUS result = MH_OK;
    void* targets[] = {lookup_hook_created ? lookup_target : nullptr,
                      voice_hook_created ? voice_target : nullptr,
                      frame_hook_created ? frame_target : nullptr,
                      hook_created ? hook_target : nullptr};
    for (void* target : targets) if (target) {
        MH_STATUS stopped = MH_DisableHook(target);
        if (stopped != MH_OK && stopped != MH_ERROR_DISABLED) result = stopped;
    }
    return result;
}

static MH_STATUS rollback_repeat_hooks(MH_STATUS error) {
    // Disarm a partially enabled runtime without freeing callback-owned state.
    // Disable created hooks after clearing trace and command enable flags.
    // Already-entered callbacks may still need immutable descriptors and mapping storage.
    stop_dispatch();
    if (trace) InterlockedExchange(&trace->header.enabled, 0);
    disable_repeat_hooks();
    // Retain all created trampolines/mappings for callbacks already entered.
    return error;
}

static MH_STATUS enable_repeat_hooks() {
    // Create missing frame and voice hooks and enable the complete callback set.
    // Roll back the whole set if any creation or enable step fails.
    // Partial gameplay adaptation cannot safely coexist with missing recovery or audio hooks.
    if (!frame_hook_created) {
        MH_STATUS created = MH_CreateHook(frame_target, reinterpret_cast<void*>(&observed_frame),
                                         reinterpret_cast<void**>(&original_frame));
        if (created != MH_OK) return rollback_repeat_hooks(created);
        frame_hook_created = true;
    }
    if (!voice_hook_created) {
        MH_STATUS created = MH_CreateHook(voice_target, reinterpret_cast<void*>(&observed_voice),
                                         reinterpret_cast<void**>(&original_voice));
        if (created != MH_OK) return rollback_repeat_hooks(created);
        voice_hook_created = true;
    }
    if (replacements_configured() && !lookup_hook_created) {
        MH_STATUS created = MH_CreateHook(lookup_target, reinterpret_cast<void*>(&observed_lookup),
                                         reinterpret_cast<void**>(&original_lookup));
        if (created != MH_OK) return rollback_repeat_hooks(created);
        lookup_hook_created = true;
    }
    MH_STATUS result = MH_EnableHook(hook_target);
    if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    result = MH_EnableHook(frame_target);
    if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    result = MH_EnableHook(voice_target);
    if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    if (lookup_hook_created) {
        result = MH_EnableHook(lookup_target);
        if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    }
    return MH_OK;
}
#endif

// Only called before a hook exists: no callback can be using these resources.
// Once created, even an enable failure retains the trampoline/mapping for retry.
static DWORD cleanup_before_hook(DWORD error) {
    // Release initialization state only before an action hook has existed.
    // Close mappings and uninitialize MinHook while preserving state after hook creation.
    // Once callbacks can enter, their trampolines and referenced data must remain allocated.
    if (hook_created) return error;
#ifdef RESEARCH_DISPATCH
    cleanup_dispatch();
#endif
    if (minhook_initialized) {
        MH_STATUS result = MH_Uninitialize();
        if (result == MH_OK || result == MH_ERROR_NOT_INITIALIZED)
            minhook_initialized = false;
    }
    if (trace) { UnmapViewOfFile(trace); trace = nullptr; }
    if (mapping_handle) { CloseHandle(mapping_handle); mapping_handle = nullptr; }
    original_action = nullptr;
#ifdef RESEARCH_REPEAT
    original_frame = nullptr;
    original_voice = nullptr;
#endif
    return error;
}

static DWORD start_observer() {
    // Attach the maintained or explicitly selected research hook configuration.
    // Verify executable identity and prologues before creating shared state and callbacks.
    // The launcher prepares runtime addresses, but native startup still rejects incompatible code.
    if (hook_created) {
        MH_STATUS result =
#ifdef RESEARCH_REPEAT
            enable_repeat_hooks();
#else
            MH_EnableHook(hook_target);
#endif
        if (result != MH_OK && result != MH_ERROR_ENABLED) {
            InterlockedExchange(&trace->header.status, -(100 + result));
            return 100 + result;
        }
#ifdef RESEARCH_DISPATCH
        begin_dispatch();
#endif
        InterlockedExchange(&trace->header.enabled, 1);
        InterlockedExchange(&trace->header.status, 1);
        return 0;
    }
    HMODULE main = GetModuleHandleW(nullptr);
    wchar_t path[32768];
    if (!GetModuleFileNameW(main, path, 32768)) return 1;
    wchar_t* name = wcsrchr(path, L'\\');
    if (!name) return 2;
    ++name;
#ifdef RESEARCH_HARNESS
    if (_wcsicmp(name, L"nioh_hook_harness.exe")) return 3;
    hook_target = reinterpret_cast<void*>(GetProcAddress(main, "HarnessAction"));
    if (!hook_target) return 4;
#ifdef RESEARCH_REPEAT
    frame_target = reinterpret_cast<void*>(GetProcAddress(main, "HarnessFrame"));
    if (!frame_target) return 4;
    voice_target = reinterpret_cast<void*>(GetProcAddress(main, "HarnessVoice"));
    if (!voice_target) return 4;
#endif
#else
    if (_wcsicmp(name, L"nioh.exe")) return 3;
    // Launcher also validates the exact executable SHA-256 and process birth time.
    hook_target = reinterpret_cast<char*>(main) + 0x70ece0;
    const uint8_t expected[] = {0x48,0x8b,0xc4,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,
        0x48,0x81,0xec,0x80,0,0,0,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff};
    uint8_t actual[sizeof(expected)]; SIZE_T read = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), hook_target, actual, sizeof(actual), &read)
        || read != sizeof(actual) || memcmp(actual, expected, sizeof(actual))) return 5;
#ifdef RESEARCH_REPEAT
    frame_target = reinterpret_cast<char*>(main) + 0x719050;
    if (!frame_prologue_matches(frame_target)) return 5;
    voice_target = reinterpret_cast<char*>(main) + 0x9670a0;
    if (!voice_prologue_matches(voice_target)) return 5;
    if (!resolve_weight_setter(reinterpret_cast<uint64_t>(main))
        || !resolve_tracking_helpers(reinterpret_cast<uint64_t>(main))) return 5;
    {
        lookup_target = reinterpret_cast<char*>(main) + 0x73fa40;
        const uint8_t prefix[] = {0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48,0x83,0xec,0x20};
        uint8_t bytes[sizeof(prefix)];
        if (!copy_bytes(reinterpret_cast<uint64_t>(lookup_target),bytes,sizeof(bytes))
            || memcmp(prefix,bytes,sizeof(prefix))) return 5;
    }
#endif
#endif
    wchar_t mapping_name[96];
#ifdef RESEARCH_REPEAT
    repeat_mapping_name(mapping_name, L"Trace", GetCurrentProcessId(), BOSS_CONFIG_TAG);
#elif defined(RESEARCH_BOSS)
    wsprintfW(mapping_name, L"Local\\NiohBossTrace_v1_%lu", GetCurrentProcessId());
#elif defined(RESEARCH_DISPATCH)
    wsprintfW(mapping_name, L"Local\\NiohDispatchTrace_v1_%lu", GetCurrentProcessId());
#else
    wsprintfW(mapping_name, L"Local\\NiohResearchTrace_v1_%lu", GetCurrentProcessId());
#endif
    mapping_handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
                                      sizeof(TraceMapping), mapping_name);
    if (!mapping_handle) return 6;
    const DWORD existed = GetLastError();
    if (existed == ERROR_ALREADY_EXISTS) { CloseHandle(mapping_handle); mapping_handle = nullptr; return 7; }
    trace = reinterpret_cast<TraceMapping*>(MapViewOfFile(mapping_handle, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(TraceMapping)));
    if (!trace) { CloseHandle(mapping_handle); mapping_handle = nullptr; return 8; }
    ZeroMemory(trace, sizeof(*trace));
    LARGE_INTEGER frequency; QueryPerformanceFrequency(&frequency);
    trace->header.magic = TRACE_MAGIC; trace->header.version = TRACE_VERSION;
    trace->header.capacity = TRACE_CAPACITY; trace->header.record_size = sizeof(TraceRecord);
    trace->header.qpc_frequency = frequency.QuadPart;
    trace->header.hook_address = reinterpret_cast<uint64_t>(hook_target);
    trace->header.module_base = reinterpret_cast<uint64_t>(main);
#ifdef RESEARCH_REPEAT
    resolve_game_input();
#endif
#ifdef RESEARCH_DISPATCH
    const DWORD command_error = open_dispatch(frequency.QuadPart);
    if (command_error) return cleanup_before_hook(command_error);
#endif
    MH_STATUS result = MH_OK;
    if (!minhook_initialized) {
        result = MH_Initialize();
        if (result != MH_OK) return cleanup_before_hook(100 + result);
        minhook_initialized = true;
    }
    result = MH_CreateHook(hook_target, reinterpret_cast<void*>(&observed_action), reinterpret_cast<void**>(&original_action));
    if (result != MH_OK) return cleanup_before_hook(100 + result);
    hook_created = true;
    result =
#ifdef RESEARCH_REPEAT
        enable_repeat_hooks();
#else
        MH_EnableHook(hook_target);
#endif
    if (result != MH_OK) { InterlockedExchange(&trace->header.status, -(100 + result)); return 100 + result; }
#ifdef RESEARCH_DISPATCH
    begin_dispatch();
#endif
    InterlockedExchange(&trace->header.enabled, 1);
    InterlockedExchange(&trace->header.status, 1);
    return 0;
}

extern "C" __declspec(dllexport) DWORD WINAPI NiohResearchStart(void* parameter) {
    // Serialize startup and bind this DLL to one validated runtime configuration.
    // Reject active callbacks or actors before installing or re-enabling hooks.
    // A refreshed session must not overwrite descriptors still retained by the game.
    if (InterlockedCompareExchange(&lifecycle_lock, 1, 0)) return 9;
#ifdef RESEARCH_BOSS
    if (InterlockedCompareExchange(&boss_active, 0, 0) || InterlockedCompareExchange(&boss_inflight, 0, 0)
#ifdef RESEARCH_REPEAT
        || InterlockedCompareExchange(&launch_weight_count,0,0)
#endif
        ) {
        InterlockedExchange(&lifecycle_lock, 0); return ERROR_BUSY;
    }
#endif
#ifdef RESEARCH_RUNTIME_SESSION
    const DWORD config_result = load_runtime_session(parameter);
    if (config_result) { InterlockedExchange(&lifecycle_lock, 0); return config_result; }
#else
    (void)parameter;
#endif
    DWORD result = start_observer();
    InterlockedExchange(&lifecycle_lock, 0);
    return result;
}

extern "C" __declspec(dllexport) DWORD WINAPI NiohResearchStop(void*) {
    // Disarm new imports and wait until native playback can release its resources.
    // Retire only positively replaced actors, then disable hooks after in-flight work finishes.
    // Busy status preserves recovery instead of unloading code through live native references.
    if (InterlockedCompareExchange(&lifecycle_lock, 1, 0)) return 9;
    if (!hook_created) { InterlockedExchange(&lifecycle_lock, 0); return 0; }
#ifdef RESEARCH_BOSS
    InterlockedExchange(&dispatch->control.enabled, 0);
    if (InterlockedCompareExchange(&boss_active, 0, 0)
        && !InterlockedCompareExchange(&boss_inflight, 0, 0)) boss_retire_destroyed_actor();
    if (InterlockedCompareExchange(&boss_active, 0, 0) || InterlockedCompareExchange(&boss_inflight, 0, 0)) {
        InterlockedExchange(&trace->header.status, 2);
        InterlockedExchange(&lifecycle_lock, 0);
        return ERROR_BUSY;
    }
#ifdef RESEARCH_REPEAT
    if (mid_light_active() || InterlockedCompareExchange(&launch_weight_count,0,0)) {
        InterlockedExchange(&trace->header.status,2); InterlockedExchange(&lifecycle_lock,0);
        return ERROR_BUSY;
    }
#endif
#endif
#ifdef RESEARCH_DISPATCH
    stop_dispatch();
#endif
    InterlockedExchange(&trace->header.enabled, 0);
#ifdef RESEARCH_REPEAT
    MH_STATUS result = disable_repeat_hooks();
#else
    MH_STATUS result = MH_DisableHook(hook_target);
#endif
    InterlockedExchange(&trace->header.status, result == MH_OK || result == MH_ERROR_DISABLED ? 0 : -(100+result));
    InterlockedExchange(&lifecycle_lock, 0);
    // Keep DLL/trampoline/mapping allocated until process exit. An already-entered
    // callback can still return through them after the entry patch is removed.
    return result == MH_OK || result == MH_ERROR_DISABLED ? 0 : 100+result;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, void*) {
    // Keep DLL loading limited to loader-lock-safe bookkeeping.
    // Disable thread attach notifications and defer all native work to explicit exports.
    // Constructing resources or installing hooks under the Windows loader lock is unsafe.
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(module);
    return TRUE;
}
