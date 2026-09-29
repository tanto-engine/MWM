#pragma once
#include "dispatch_protocol.h"
#ifdef RESEARCH_REPEAT
#include "boss_session_config.h"
#include "repeat_namespace.h"
#endif

static DispatchMapping* dispatch;
static HANDLE dispatch_handle;

static void cleanup_dispatch() {
    // Release command mapping resources before the hook acquires them.
    // Unmap the view and close its process-owned mapping handle.
    // Later callbacks require retained mappings and must never call this cleanup path.
    if (dispatch) { UnmapViewOfFile(dispatch); dispatch = nullptr; }
    if (dispatch_handle) { CloseHandle(dispatch_handle); dispatch_handle = nullptr; }
}

static DWORD open_dispatch(int64_t frequency) {
    // Create a uniquely named command mapping for this runtime configuration.
    // Validate exclusive creation, map the fixed ABI and initialize its frequency and header.
    // Another session's command stream must not attach to these transient actor pointers.
    wchar_t name[96];
#ifdef RESEARCH_REPEAT
    repeat_mapping_name(name, L"Command", GetCurrentProcessId(), BOSS_CONFIG_TAG);
#elif defined(RESEARCH_BOSS)
    wsprintfW(name, L"Local\\NiohBossCommand_v1_%lu", GetCurrentProcessId());
#else
    wsprintfW(name, L"Local\\NiohDispatchCommand_v1_%lu", GetCurrentProcessId());
#endif
    dispatch_handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
                                       sizeof(DispatchMapping), name);
    if (!dispatch_handle) return 20;
    if (GetLastError() == ERROR_ALREADY_EXISTS) { cleanup_dispatch(); return 21; }
    dispatch = reinterpret_cast<DispatchMapping*>(MapViewOfFile(dispatch_handle, FILE_MAP_ALL_ACCESS,
                                                               0, 0, sizeof(DispatchMapping)));
    if (!dispatch) { cleanup_dispatch(); return 22; }
    ZeroMemory(dispatch, sizeof(*dispatch));
    dispatch->control.magic = DISPATCH_MAGIC;
    dispatch->control.version = DISPATCH_VERSION;
    dispatch->control.command_size = sizeof(DispatchCommand);
    dispatch->control.qpc_frequency = frequency;
    return 0;
}

static void begin_dispatch() {
    // Arm a fresh dispatch generation without replenishing an active session.
    // Reset shared counters and context only after confirming dispatch was disabled.
    // Duplicate Start calls must not replay consumed gestures or bypass one-shot research limits.
    // Duplicate Start while active cannot replenish the one-shot allowance.
    if (InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)) return;
    InterlockedIncrement64(&dispatch->control.generation);
    InterlockedExchange64(&dispatch->control.consumed_sequence, 0);
    InterlockedExchange64(&dispatch->control.dispatch_count, 0);
    InterlockedExchange(reinterpret_cast<volatile LONG*>(&dispatch->control.reserved0), 0);
    InterlockedExchange(reinterpret_cast<volatile LONG*>(&dispatch->control.reserved1), 0);
    InterlockedExchange(&dispatch->control.last_reason, Disabled);
    InterlockedExchange(&dispatch->control.status, 1);
    InterlockedExchange(&dispatch->control.enabled, 1);
}

static void stop_dispatch() {
    // Disarm gesture execution while leaving retained resources accessible.
    // Clear only the command control's enabled and status fields.
    // Entered callbacks still need those mappings to finish native recovery safely.
    if (!dispatch) return;
    InterlockedExchange(&dispatch->control.enabled, 0);
    InterlockedExchange(&dispatch->control.status, 0);
}

static bool snapshot_command(DispatchCommand& c) {
    // Read one committed external command without blocking the game thread.
    // Require matching positive sequence markers before and after the payload copy.
    // Torn publisher writes cannot become mixed actor identities or gesture timings.
    const LONG64 before = InterlockedCompareExchange64(&dispatch->command.sequence_begin, 0, 0);
    if (before <= 0) return false;
    CopyMemory(&c, &dispatch->command, sizeof(c));
    MemoryBarrier();
    const LONG64 after = InterlockedCompareExchange64(&dispatch->command.sequence_end, 0, 0);
    return before == after && c.sequence_begin == before && c.sequence_end == before
        && InterlockedCompareExchange64(&dispatch->command.sequence_begin, 0, 0) == before;
}

static bool copy_bytes(uint64_t address, void* target, SIZE_T size) {
    // Read a bounded native-memory span through the process API.
    // Require a user-space address and an exact-length copy into owned storage.
    // Unreadable or partially copied records must reject the command before pointer use.
    SIZE_T read = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address), target, size, &read) && read == size;
}

#ifdef RESEARCH_BOSS
#include "boss_support.h"
#endif

#ifdef RESEARCH_REPEAT
static bool repeat_current_allowed(uint64_t descriptor, uint32_t key) {
    // Limit new gesture entry to researched William sword control states.
    // Match exact action, motion and stance triples while excluding attacks and damage.
    // Unknown locomotion or aiming states need evidence before gaining entry eligibility.
    // Saved player-triangle-movement evidence permits free/lock-on movement during an approved Triangle hold.
    // Dodge9, damage3E8 and concrete running attacks stay excluded; pending holds remain interruptible.
    struct Neutral { uint32_t key; int32_t motion; int8_t stance; };
    static constexpr Neutral allowed[] = {
        {0,0,3}, {1,1,3}, {2,2,3}, {3,3,3}, {4,8,3},
        {0xC,20,3}, {0xD,30,3}, {0xC7,21,3}, {0xC9,40,3}, {0xCA,41,3},
        {0x3EB,20,3}, {0x3EC,24,3}, {0x3F7,26,3}, {0x3F8,28,3},
        {0x3FA,30,3}, {0x3FB,31,3}, {0x3FC,32,3}, {0x3FD,33,3},
        {3154,2000,1}, {3155,2001,1}, {3156,2002,4}, {3157,2003,4}, {3158,2005,3},
        {3159,2006,0}, {3160,2007,2}, {3161,2008,4}, {3162,2009,4},
        {3214,3000,0}, {3215,3001,0}, {3216,3002,4}, {3217,3003,4}, {3218,2005,3},
        {3219,3006,1}, {3220,3007,2}, {3221,3008,4}, {3222,3009,4},
        {3276,4000,2}, {3277,4001,2}, {3278,4002,4}, {3279,4003,4}, {3280,2005,3},
        {3281,4006,1}, {3282,4007,0}, {3283,4008,4}, {3284,4009,4},
        {3181,2061,1}, {3182,2061,1}, {3242,2061,4}, {3243,2061,4},
        {3303,2061,2}, {3304,2061,2},
        // Guard locomotion in all three sword stances. Payload stance4 preserves
        // the current stance; these exact keys share directional clips1160..1163.
        {3186,1160,4}, {3187,1161,4}, {3188,1162,4}, {3189,1163,4},
        {3247,1160,4}, {3248,1161,4}, {3249,1162,4}, {3250,1163,4},
        {3308,1160,4}, {3309,1161,4}, {3310,1162,4}, {3311,1163,4}
    };
    for (const auto& entry : allowed) if (entry.key == key) {
        uint64_t payload = 0; int32_t motion = -1; int8_t stance = -1; uint8_t enabled = 0;
        return copy_field(descriptor + 0x20, payload) && copy_field(descriptor + 0x40, enabled)
            && enabled && copy_field(payload + 0x20, motion) && copy_field(payload + 0x0b, stance)
            && motion == entry.motion && stance == entry.stance;
    }
    return false;
}
#endif

static DispatchReason validate_actor(const DispatchCommand& c, void* actor) {
    // Check the native actor and requested action immediately before dispatch.
    // Re-read ownership and bank identity while respecting native lookup priority.
    // Configuration prepared earlier cannot authorize a replaced actor or changed bank.
    const uint64_t address = reinterpret_cast<uint64_t>(actor);
    if (address != c.player) return WrongActor;
    uint64_t owner = 0, vtable = 0, banks[3]{}, current = 0;
    uint32_t current_key = 0;
    if (!copy_field(address, vtable) || !copy_field(address + 0x50, owner)
        || !copy_bytes(address + 0x70, banks, sizeof(banks))
        || !copy_field(address + 0x58, current) || !copy_field(current, current_key))
        return IdentityReadFailed;
    if (owner != c.owner) return OwnerMismatch;
    if (vtable != c.vtable) return VtableMismatch;
    if (memcmp(banks, c.banks, sizeof(banks))) return BankMismatch;
#ifdef RESEARCH_REPEAT
    if (!repeat_current_allowed(current, current_key)) return CurrentNotAllowed;
#else
    if (current_key != 0 && current_key != 3276 && current_key != 3303 && current_key != 3304)
        return CurrentNotAllowed;
#endif

#ifdef RESEARCH_BOSS
    return validate_boss_source(c);
#else
    // Match native bank priority, enabled-byte filtering, and full DWORD keys.
    // These conservative bounds turn unexpected layouts into a skipped command.
    constexpr uint32_t MAX_DESCRIPTORS = 4096;
    uint64_t pointers[MAX_DESCRIPTORS];
    for (unsigned bank = 0; bank != 3; ++bank) {
        if (!banks[bank]) continue;
        uint32_t count = 0; uint64_t array = 0;
        if (!copy_field(banks[bank] + 0x130, count) || count > MAX_DESCRIPTORS
            || !copy_field(banks[bank] + 0x128, array)) return DesiredInvalid;
        if (count && !copy_bytes(array, pointers, size_t(count) * 8)) return DesiredInvalid;
        for (uint32_t i = 0; i != count; ++i) {
            if (!pointers[i]) continue;
            uint32_t key = 0; uint8_t enabled = 0;
            if (!copy_field(pointers[i], key) || !copy_field(pointers[i] + 0x40, enabled))
                return DesiredInvalid;
            if (!enabled || key != c.desired_key) continue;
            uint64_t payload = 0; int32_t motion = -1;
            if (pointers[i] != c.expected_descriptor || !copy_field(pointers[i] + 0x20, payload)
                || payload != c.expected_payload || !copy_field(payload + 0x20, motion)
                || motion != c.expected_motion) return DesiredMismatch;
            // Recheck identity and bank headers immediately before permitting the call.
            uint64_t owner_after = 0, vtable_after = 0, banks_after[3]{}, array_after = 0;
            uint32_t count_after = 0;
            if (!copy_field(address + 0x50, owner_after) || owner_after != owner
                || !copy_field(address, vtable_after) || vtable_after != vtable
                || !copy_bytes(address + 0x70, banks_after, sizeof(banks_after))
                || memcmp(banks_after, banks, sizeof(banks))
                || !copy_field(banks[bank] + 0x128, array_after) || array_after != array
                || !copy_field(banks[bank] + 0x130, count_after) || count_after != count)
                return BankMismatch;
            return Accepted;
        }
    }
    return DesiredMissing;
#endif
}

static bool same_dispatch_intent(const DispatchCommand& latest, const DispatchCommand& before) {
    // Detect whether publisher intent changed during native preflight.
    // Compare gesture identity, actor fields, desired action and reserved policy fields.
    // Heartbeat refreshes may continue while release or move changes must invalidate the attempt.
    return latest.chord_sequence == before.chord_sequence && latest.generation == before.generation
        && !memcmp(reinterpret_cast<const char*>(&latest) + 48,
                   reinterpret_cast<const char*>(&before) + 48, 72)
        && !memcmp(latest.reserved, before.reserved, sizeof(before.reserved));
}

#ifdef RESEARCH_REPEAT
static DispatchReason player_context_status(const DispatchCommand& command) {
    // Match a published gesture to the currently valid player-context epoch.
    // Read the packed native flags atomically and compare the command's epoch.
    // Even a suspension shorter than the Python polling interval must invalidate pending input.
    const uint32_t context = uint32_t(InterlockedCompareExchange(
        reinterpret_cast<volatile LONG*>(&dispatch->control.reserved0), 0, 0));
    if (!player_context_ready(context)) return ContextSuspended;
    return command.reserved[2] == (context >> 16) ? Accepted : ContextChanged;
}
#endif

#ifdef RESEARCH_REPEAT
static DispatchReason choose_chain(void* actor, DispatchCommand& c) {
    // Select a configured follow-up while the original held gesture remains current.
    // Check heartbeat, epoch, ownership and the source transition's frame window.
    // Release or interruption cancels later links; native contact alone may select a paired finisher.
    if (!dispatch || reinterpret_cast<uint64_t>(actor) != boss_active_player
        || !InterlockedCompareExchange(&boss_active,0,0) || boss_chain_cancelled) return BossPreviewActive;
    DispatchCommand intent{};
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    const int64_t frequency = dispatch->control.qpc_frequency;
    if (!InterlockedCompareExchange(&dispatch->control.enabled,0,0) || !snapshot_command(intent)
        || intent.held != 1 || (intent.reserved[0]&1) || intent.chord_sequence != boss_chain_sequence
        || intent.reserved[2] != boss_chain_epoch || intent.reserved[1] != boss_string_variant
        || intent.generation != uint64_t(dispatch->control.generation)
        || frequency <= 0 || intent.heartbeat_qpc > now.QuadPart
        || now.QuadPart-intent.heartbeat_qpc > frequency/10 || player_context_status(intent) != Accepted) {
        boss_chain_cancelled = true;
        return Released;
    }
    const auto& current = boss_imports[boss_active_slot];
    if (current.next_variant < 0 || !current.next_start) return BossPreviewActive;
    float frame = 0;
    if (!boss_player_valid() || !same_field(boss_active_player,0x58,boss_private_descriptor_address(boss_active_slot))
        || !copy_field(boss_active_player+0x28,frame) || !std::isfinite(frame)) {
        boss_chain_cancelled = true;
        return BossSourceMismatch;
    }
    if (frame < current.next_start) return CurrentNotAllowed;
    if (frame > current.next_end) { boss_chain_cancelled = true; return Expired; }
    c = intent;
    const auto& next = boss_imports[current.next_variant];
    c.reserved[1] = current.next_variant;
    c.desired_key = next.key; c.expected_motion = next.motion;
    c.expected_descriptor = next.descriptor; c.expected_payload = next.payload;
    c.edge_qpc = now.QuadPart;
    uint64_t banks[3]{};
    if (!copy_bytes(c.player+0x70,banks,sizeof(banks)) || memcmp(banks,c.banks,sizeof(banks))) return BankMismatch;
    auto reason = validate_boss_source(c);
    DispatchCommand latest{};
    if (reason == Accepted && (!snapshot_command(latest) || !same_dispatch_intent(latest,intent)
        || !latest.held || player_context_status(latest) != Accepted)) {
        boss_chain_cancelled = true;
        return Released;
    }
    if (reason == Accepted) InterlockedIncrement64(&dispatch->control.dispatch_count);
    return reason;
}
#endif

static DispatchReason choose_dispatch(void* actor, uint32_t key, void* context, DispatchCommand& c,
                                     bool frame_mode = false) {
    // Consume one eligible gesture at the permitted native dispatch boundary.
    // Validate the committed command twice before atomically claiming its sequence.
    // A release, stale actor or competing callback must not manufacture a new attack.
#ifdef RESEARCH_REPEAT
    constexpr bool limit_one_dispatch = false;
#else
    constexpr bool limit_one_dispatch = true;
#endif
    DispatchReason reason = Disabled;
    if (!dispatch || !InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)) return reason;
#ifdef RESEARCH_REPEAT
    // Repeated gestures are consumed only at the action-node frame boundary.
    // Ordinary guard/aim setter traffic must never trigger a pending command.
    (void)key;
    if (!frame_mode) return IneligibleRequest; // Keep the latest frame gate reason.
#else
    (void)frame_mode;
    if (key != 24 && key != 25) reason = IneligibleRequest;
    else
#endif
    if (context) reason = NonNullContext;
#ifdef RESEARCH_REPEAT
    else if (InterlockedCompareExchange(&boss_active, 0, 0)) reason = BossPreviewActive;
#endif
    else if (!snapshot_command(c)) reason = UnstableCommand;
    else {
        LARGE_INTEGER now; QueryPerformanceCounter(&now);
        reason = command_status(c, now.QuadPart, dispatch->control.qpc_frequency,
            InterlockedCompareExchange64(&dispatch->control.generation, 0, 0),
            InterlockedCompareExchange64(&dispatch->control.consumed_sequence, 0, 0),
            limit_one_dispatch && InterlockedCompareExchange64(&dispatch->control.dispatch_count, 0, 0) != 0);
#ifdef RESEARCH_REPEAT
        if (reason == Accepted) reason = player_context_status(c);
#endif
        if (reason == Accepted) reason = validate_actor(c, actor);
#ifdef RESEARCH_REPEAT
        if (reason == Accepted && (c.reserved[0]>>16&0xffff)) {
            uint32_t stance=0;
            if (!copy_field(c.player+0x470,stance) || stance>2
                || !(c.reserved[0]&(uint64_t(1)<<(34-stance)))) reason=IneligibleRequest;
        }
        if (reason == Accepted && c.reserved[1]<boss_import_count) {
            const auto& adapter=boss_adapters[c.reserved[1]];
            uint32_t stance=0;
            uint32_t expected=adapter.kind==2 ? (adapter.player_key==0xCF5 ? 2 : adapter.player_key==0xC7A ? 1 : 0) : 3;
            for (unsigned i=0;i<3;++i) if (boss_frost_variants[i]==c.reserved[1]+1) expected=2-i;
            if (expected<3 && (!copy_field(c.player+0x470,stance) || stance!=expected)) reason=IneligibleRequest;
        }
#endif
        // Re-read the live command after preflight: releasing during the lookup cancels it.
        if (reason == Accepted) {
            DispatchCommand latest{};
            if (!snapshot_command(latest)) reason = UnstableCommand;
            else if (!same_dispatch_intent(latest, c)) reason = InvalidConfig;
            else {
                QueryPerformanceCounter(&now);
                reason = command_status(latest, now.QuadPart, dispatch->control.qpc_frequency,
                    InterlockedCompareExchange64(&dispatch->control.generation, 0, 0),
                    InterlockedCompareExchange64(&dispatch->control.consumed_sequence, 0, 0),
                    limit_one_dispatch && InterlockedCompareExchange64(&dispatch->control.dispatch_count, 0, 0) != 0);
            }
        }
#ifdef RESEARCH_REPEAT
        if (reason == Accepted) reason = player_context_status(c);
        if (reason == Accepted && (c.reserved[0]>>16&0xffff)) {
            uint32_t stance=0;
            if (!copy_field(c.player+0x470,stance) || stance>2
                || !(c.reserved[0]&(uint64_t(1)<<(34-stance)))) reason=IneligibleRequest;
        }
#endif
        if (reason == Accepted) {
            if (!InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)) reason = Disabled;
#ifdef RESEARCH_REPEAT
            else if (InterlockedCompareExchange(&boss_active, 0, 0)) reason = BossPreviewActive;
            else {
                const LONG64 previous = InterlockedCompareExchange64(&dispatch->control.consumed_sequence, 0, 0);
                if (c.chord_sequence <= uint64_t(previous)) reason = SequenceConsumed;
                else if (InterlockedCompareExchange64(&dispatch->control.consumed_sequence,
                             LONG64(c.chord_sequence), previous) != previous) reason = Contention;
                else InterlockedIncrement64(&dispatch->control.dispatch_count);
            }
#else
            else if (InterlockedCompareExchange64(&dispatch->control.dispatch_count, 1, 0)) reason = ShotUsed;
            else InterlockedExchange64(&dispatch->control.consumed_sequence, static_cast<LONG64>(c.chord_sequence));
#endif
        }
    }
    InterlockedExchange(&dispatch->control.last_reason, reason);
    return reason;
}
