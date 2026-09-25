#pragma once
#include "dispatch_protocol.h"
#ifdef RESEARCH_REPEAT
#include "boss_session.h"
#include "repeat_namespace.h"
#endif

static DispatchMapping* dispatch;
static HANDLE dispatch_handle;

static void cleanup_dispatch() {
    if (dispatch) { UnmapViewOfFile(dispatch); dispatch = nullptr; }
    if (dispatch_handle) { CloseHandle(dispatch_handle); dispatch_handle = nullptr; }
}

static DWORD open_dispatch(int64_t frequency) {
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
    // Duplicate Start while active cannot replenish the one-shot allowance.
    if (InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)) return;
    InterlockedIncrement64(&dispatch->control.generation);
    InterlockedExchange64(&dispatch->control.consumed_sequence, 0);
    InterlockedExchange64(&dispatch->control.dispatch_count, 0);
    InterlockedExchange(reinterpret_cast<volatile LONG*>(&dispatch->control.reserved1), 0);
    InterlockedExchange(&dispatch->control.last_reason, Disabled);
    InterlockedExchange(&dispatch->control.status, 1);
    InterlockedExchange(&dispatch->control.enabled, 1);
}

static void stop_dispatch() {
    if (!dispatch) return;
    InterlockedExchange(&dispatch->control.enabled, 0);
    InterlockedExchange(&dispatch->control.status, 0);
}

static bool snapshot_command(DispatchCommand& c) {
    const LONG64 before = InterlockedCompareExchange64(&dispatch->command.sequence_begin, 0, 0);
    if (before <= 0) return false;
    CopyMemory(&c, &dispatch->command, sizeof(c));
    MemoryBarrier();
    const LONG64 after = InterlockedCompareExchange64(&dispatch->command.sequence_end, 0, 0);
    return before == after && c.sequence_begin == before && c.sequence_end == before
        && InterlockedCompareExchange64(&dispatch->command.sequence_begin, 0, 0) == before;
}

static bool copy_bytes(uint64_t address, void* target, SIZE_T size) {
    SIZE_T read = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address), target, size, &read) && read == size;
}

#ifdef RESEARCH_BOSS
#include "boss_support.h"
#endif

#ifdef RESEARCH_REPEAT
static bool repeat_current_allowed(uint64_t descriptor, uint32_t key) {
    // Exact key/motion/stance triples from the validated sword bank; deliberately
    // exclude attacks, damage, death and unresolved command-only descriptors.
    struct Neutral { uint32_t key; int32_t motion; int8_t stance; };
    static constexpr Neutral allowed[] = {
        {0,0,3}, {1,1,3}, {2,2,3}, {3,3,3}, {4,8,3},
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
    return latest.chord_sequence == before.chord_sequence && latest.generation == before.generation
        && !memcmp(reinterpret_cast<const char*>(&latest) + 48,
                   reinterpret_cast<const char*>(&before) + 48, 72)
        && !memcmp(latest.reserved, before.reserved, sizeof(before.reserved));
}

static DispatchReason choose_dispatch(void* actor, uint32_t key, void* context, DispatchCommand& c,
                                     bool frame_mode = false) {
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
        if (reason == Accepted) reason = validate_actor(c, actor);
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
