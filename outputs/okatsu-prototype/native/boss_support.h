#pragma once
#include "boss_session.h"

static volatile LONG boss_active;
static volatile LONG boss_inflight;
static uint64_t boss_active_player, boss_active_owner;
#ifdef RESEARCH_REPEAT
// Native pool/build evidence: descriptor slots0xD0, payload slots0xB0. These
// copies remain immutable and allocated for the DLL lifetime: previous-action
// references can outlive the visible preview.
struct BossLookupOnlyBank {
    uint8_t unused[0x128];
    uint64_t entries;
    uint32_t count, padding;
};
static_assert(sizeof(BossLookupOnlyBank) == 0x138, "Lookup-only header size");
struct BossPrivateAction {
    alignas(16) uint8_t descriptor[0xD0];
    alignas(16) uint8_t payload[0xB0];
    BossLookupOnlyBank bank;
    uint64_t entry;
    uint8_t transition_bodies[31][0x30];
    uint64_t transition_pointers[31];
    uint16_t transition_count;
    bool ready;
};
static BossPrivateAction boss_private_actions[2]{};
static uint64_t boss_private_descriptor_address(unsigned slot = 0) {
    return reinterpret_cast<uint64_t>(boss_private_actions[slot].descriptor);
}
static uint64_t boss_private_payload_address(unsigned slot = 0) {
    return reinterpret_cast<uint64_t>(boss_private_actions[slot].payload);
}

// Exact CF0 rows21..23. Stance selectors differ; all retain native conditionD5,
// R1 input23, targetD5F and transition flagbit1 used by native Ki Pulse handling.
static constexpr uint8_t boss_pulse_templates[3][0x30] = {
    {0x51,0,0xd5,0,0xff,0xff,0xff,0xff,0xff,0xff,0,0x17,1,0xff,0xff,0,0,0,0,0,0x5f,0x0d,0,3,0,0x80,0x64,0x64,2,0,0x20,0,0,0x80,0xff,0x7f,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff},
    {0x50,0,0xd5,0,0xff,0xff,0xff,0xff,0xff,0xff,0,0x17,1,0xff,0xff,0,0,0,0,0,0x5f,0x0d,0,3,0,0x80,0x64,0x64,2,0,0x20,0,0,0x80,0xff,0x7f,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff},
    {0x52,0,0xd5,0,0xff,0xff,0xff,0xff,0xff,0xff,0,0x17,1,0xff,0xff,0,0,0,0,0,0x5f,0x0d,0,3,0,0x80,0x64,0x64,2,0,0x20,0,0,0x80,0xff,0x7f,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff}
};

static bool boss_copy_pulse_transitions(unsigned slot, const uint8_t* descriptor,
        uint8_t (&bodies)[31][0x30], uint16_t& total) {
    uint64_t source_table = 0; uint16_t source_start = 0, source_count = 0;
    memcpy(&source_table, descriptor + 0x78, 8); memcpy(&source_start, descriptor + 0x80, 2);
    memcpy(&source_count, descriptor + 0x82, 2);
    if (source_count != (slot ? 22 : 28) || source_table < 0x10000 || source_table > UINT64_MAX - 0x100000)
        return false;
    uint64_t source_pointers[28]{}, source_check[28]{};
    const uint64_t source_slice = source_table + uint64_t(source_start) * 8;
    if (!copy_bytes(source_slice, source_pointers, source_count * 8)) return false;
    for (unsigned i = 0; i != source_count; ++i) {
        uint8_t check[0x30];
        if (!copy_bytes(source_pointers[i], bodies[i], 0x30) || !copy_bytes(source_pointers[i], check, 0x30)
            || memcmp(bodies[i], check, 0x30)) return false;
    }
    uint8_t player[0x88], player_check[0x88];
    if (!copy_bytes(boss_session.player_pulse_descriptor, player, sizeof(player))) return false;
    uint32_t key = 0; uint64_t table = 0; uint16_t start = 0, count = 0;
    memcpy(&key, player, 4); memcpy(&table, player + 0x78, 8);
    memcpy(&start, player + 0x80, 2); memcpy(&count, player + 0x82, 2);
    if (key != 0xCF0 || !player[0x40] || count < 24 || count > 4096
        || table < 0x10000 || table > UINT64_MAX - 0x100000) return false;
    uint64_t pulse_pointers[3]{}, pulse_check[3]{};
    if (!copy_bytes(table + (uint64_t(start) + 21) * 8, pulse_pointers, sizeof(pulse_pointers))) return false;
    for (unsigned i = 0; i != 3; ++i) {
        auto* body = bodies[source_count + i];
        if (!copy_bytes(pulse_pointers[i], body, 0x30) || memcmp(body, boss_pulse_templates[i], 0x30)) return false;
        const int16_t recovery_start = slot ? 90 : 65;
        memcpy(body + 0x20, &recovery_start, 2); // Never enable a pulse before attack recovery.
    }
    if (!copy_bytes(source_slice, source_check, source_count * 8)
        || memcmp(source_pointers, source_check, source_count * 8)
        || !copy_bytes(table + (uint64_t(start) + 21) * 8, pulse_check, sizeof(pulse_check))
        || memcmp(pulse_pointers, pulse_check, sizeof(pulse_check))
        || !copy_bytes(boss_session.player_pulse_descriptor, player_check, sizeof(player))
        || memcmp(player, player_check, sizeof(player))) return false;
    total = uint16_t(source_count + 3);
    return true;
}

static bool boss_prepare_private_action(unsigned slot = 0) {
    if (slot > 1) return false;
    auto& target = boss_private_actions[slot];
    const uint64_t expected_descriptor = slot ? boss_session.charge_descriptor : boss_session.source_descriptor;
    const uint64_t expected_payload = slot ? boss_session.charge_payload : boss_session.source_payload;
    const uint32_t expected_key = slot ? 0xC66 : 0xC64;
    const int32_t expected_motion = slot ? 1230 : 1220;
    uint8_t descriptor[0xD0], payload[0xB0], check_descriptor[0xD0], check_payload[0xB0];
    if (!copy_bytes(expected_descriptor, descriptor, sizeof(descriptor))
        || !copy_bytes(expected_payload, payload, sizeof(payload))
        || !copy_bytes(expected_descriptor, check_descriptor, sizeof(check_descriptor))
        || !copy_bytes(expected_payload, check_payload, sizeof(check_payload))
        || memcmp(descriptor, check_descriptor, sizeof(descriptor))
        || memcmp(payload, check_payload, sizeof(payload))) return false;
    uint32_t key = 0; uint64_t source_payload = 0, flags = 0; int32_t motion = -1;
    memcpy(&key, descriptor, sizeof(key));
    memcpy(&source_payload, descriptor + 0x20, sizeof(source_payload));
    memcpy(&flags, payload + 0x18, sizeof(flags));
    memcpy(&motion, payload + 0x20, sizeof(motion));
    // The private context deliberately contains only this direct action. Reject
    // redirects/pending-action modes that could require another context lookup.
    if (key != expected_key || !descriptor[0x40] || source_payload != expected_payload
        || motion != expected_motion || (flags & ((uint64_t(1) << 34) | (uint64_t(1) << 35)))) return false;
    payload[0x0B] = 4; // Native0x70F3A3: keep current+0x470, retain+0x47C=1 behavior.
    int16_t recovery_start = 0, base_ki_cost = 0;
    memcpy(&recovery_start, payload + 0x24, sizeof(recovery_start));
    memcpy(&base_ki_cost, payload + 0x16, sizeof(base_ki_cost));
    if (recovery_start != (slot ? 90 : 65) || base_ki_cost <= 0) return false;
    // Native71000A computes recoverable Ki from this percentage of the actual
    // game-adjusted cost. Native715118 opens its normal timed recovery when the
    // action crosses+0x38; 7B59F0 uses+0x3A/+0x3C as fill/hold durations.
    // Percentage and durations match player swordCF0. Keep the imported cost.
    payload[0x33] = 40;
    const int16_t fill_frames = 25, hold_frames = 24;
    memcpy(payload + 0x38, &recovery_start, sizeof(recovery_start));
    memcpy(payload + 0x3A, &fill_frames, sizeof(fill_frames));
    memcpy(payload + 0x3C, &hold_frames, sizeof(hold_frames));
    uint8_t transitions[31][0x30]{}; uint16_t transition_count = 0;
    if (!boss_copy_pulse_transitions(slot, descriptor, transitions, transition_count)) return false;
    const uint64_t private_transitions = reinterpret_cast<uint64_t>(target.transition_pointers);
    const uint16_t private_start = 0;
    memcpy(descriptor + 0x78, &private_transitions, 8);
    memcpy(descriptor + 0x80, &private_start, 2);
    memcpy(descriptor + 0x82, &transition_count, 2);
    const uint64_t private_payload = boss_private_payload_address(slot);
    memcpy(descriptor + 0x20, &private_payload, sizeof(private_payload));
    if (target.ready)
        return !memcmp(descriptor, target.descriptor, sizeof(descriptor))
            && !memcmp(payload, target.payload, sizeof(payload))
            && target.transition_count == transition_count
            && !memcmp(transitions, target.transition_bodies, sizeof(transitions));
    memcpy(target.transition_bodies, transitions, sizeof(transitions));
    target.transition_count = transition_count;
    for (unsigned i = 0; i != transition_count; ++i)
        target.transition_pointers[i] = reinterpret_cast<uint64_t>(target.transition_bodies[i]);
    memcpy(target.payload, payload, sizeof(payload));
    memcpy(target.descriptor, descriptor, sizeof(descriptor));
    // Descriptor+0x38 and other embedded tables retain the real source bank;
    // +0x78 alone owns the augmented transition pointer table. The lookup-only
    // 0x138 header is used ONLY by native0x73FA40 through R8.
    target.entry = boss_private_descriptor_address(slot);
    target.bank.entries = reinterpret_cast<uint64_t>(&target.entry);
    target.bank.count = 1;
    target.ready = true;
    return true;
}
#endif

static bool boss_is_preview_descriptor(uint64_t descriptor) {
#ifdef RESEARCH_REPEAT
    for (unsigned slot = 0; slot != 2; ++slot)
        if (boss_private_actions[slot].ready && descriptor == boss_private_descriptor_address(slot)) return true;
    if (descriptor && descriptor == boss_session.charge_descriptor) return true;
#endif
    return descriptor == boss_session.source_descriptor;
}
struct BossCallScope {
    BossCallScope() { InterlockedIncrement(&boss_inflight); }
    ~BossCallScope() { InterlockedDecrement(&boss_inflight); }
};

static uint64_t boss_slot(unsigned i) {
    const uint64_t slots[] = {boss_session.player_motion + 8, boss_session.player_motion + 0x28,
                              boss_session.player_timing + 0x10, boss_session.player_timing + 0x28};
    return slots[i];
}
static uint64_t boss_borrowed(unsigned i) {
    return i < 2 ? boss_session.source_motion_bank : boss_session.source_timing_wrapper;
}
static bool same_field(uint64_t base, unsigned offset, uint64_t expected) {
    uint64_t actual = 0;
    return copy_field(base + offset, actual) && actual == expected;
}
static bool boss_player_valid() {
    return same_field(boss_session.player, 0, boss_session.vtable)
        && same_field(boss_session.player, 0x50, boss_session.player_owner)
        && same_field(boss_session.player_owner, 0x38, boss_session.player_motion)
        && same_field(boss_session.player_owner, 0x68, boss_session.player_timing);
}
static bool writable_slot(uint64_t slot) {
    MEMORY_BASIC_INFORMATION region{};
    return !(slot & 7) && VirtualQuery(reinterpret_cast<void*>(slot), &region, sizeof(region))
        && region.State == MEM_COMMIT && !(region.Protect & (PAGE_GUARD | PAGE_NOACCESS))
        && (region.Protect & 0xff) == PAGE_READWRITE
        && slot + 8 <= reinterpret_cast<uint64_t>(region.BaseAddress) + region.RegionSize;
}

// Called only inside the player's existing setter callback. Never overwrite an
// unexpected third-party value. Preflight all four locations before the first write.
static bool boss_set_bindings(bool borrow) {
    if (!boss_player_valid()) return false;
    uint64_t before[4]{};
    for (unsigned i = 0; i != 4; ++i) {
        if (!writable_slot(boss_slot(i)) || !copy_field(boss_slot(i), before[i])) return false;
        if (before[i] != boss_session.originals[i] && before[i] != boss_borrowed(i)) return false;
    }
    unsigned written = 0;
    for (; written != 4; ++written) {
        const uint64_t value = borrow ? boss_borrowed(written) : boss_session.originals[written];
        auto* slot = reinterpret_cast<volatile LONG64*>(boss_slot(written));
        if (uint64_t(InterlockedCompareExchange64(slot, LONG64(value), LONG64(before[written]))) != before[written]) break;
    }
    if (written == 4) return true;
    // Roll back only values this call actually installed, still under ownership.
    while (written) {
        --written;
        const uint64_t value = borrow ? boss_borrowed(written) : boss_session.originals[written];
        InterlockedCompareExchange64(reinterpret_cast<volatile LONG64*>(boss_slot(written)),
                                      LONG64(before[written]), LONG64(value));
    }
    return false;
}

static DispatchReason validate_boss_source(const DispatchCommand& c) {
#ifdef RESEARCH_REPEAT
    if (c.reserved[1] > 1) return InvalidConfig;
    const bool charge = c.reserved[1] == 1;
#else
    const bool charge = false;
#endif
    const uint32_t key_requested = charge ? 0xC66 : 0xC64;
    const int32_t motion_requested = charge ? 1230 : 1220;
    const uint64_t descriptor_requested = charge ? boss_session.charge_descriptor : boss_session.source_descriptor;
    const uint64_t payload_requested = charge ? boss_session.charge_payload : boss_session.source_payload;
    if (c.player != boss_session.player || c.owner != boss_session.player_owner
        || c.vtable != boss_session.vtable || c.desired_key != key_requested || c.expected_motion != motion_requested
        || c.expected_descriptor != descriptor_requested
        || c.expected_payload != payload_requested) return BossSourceMismatch;
    if (!boss_player_valid()
        || !same_field(boss_session.source_actor, 0, boss_session.vtable)
        || !same_field(boss_session.source_actor, 0x50, boss_session.source_owner)
        || !same_field(boss_session.source_actor, 0x78, boss_session.source_bank)
        || !same_field(boss_session.source_owner, 0x38, boss_session.source_motion)
        || !same_field(boss_session.source_owner, 0x68, boss_session.source_timing)
        || !same_field(boss_session.source_motion, 8, boss_session.source_motion_bank)
        || !same_field(boss_session.source_timing, 0x10, boss_session.source_timing_wrapper))
        return BossSourceMismatch;
    for (unsigned i = 0; i != 4; ++i)
        if (!same_field(boss_slot(i), 0, boss_session.originals[i])) return BossBindingMismatch;

    uint64_t table = 0; uint32_t count = 0;
    if (!copy_field(boss_session.source_bank + 0x128, table)
        || !copy_field(boss_session.source_bank + 0x130, count) || !count || count > 4096)
        return DesiredInvalid;
    uint64_t entries[4096];
    if (!copy_bytes(table, entries, size_t(count) * 8)) return DesiredInvalid;
    for (uint32_t i = 0; i != count; ++i) {
        if (!entries[i]) continue;
        uint32_t key = 0; uint8_t enabled = 0;
        if (!copy_field(entries[i], key) || !copy_field(entries[i] + 0x40, enabled)) return DesiredInvalid;
        if (!enabled || key != c.desired_key) continue;
        uint64_t payload = 0; int32_t motion = -1;
        if (entries[i] != c.expected_descriptor || !copy_field(entries[i] + 0x20, payload)
            || payload != c.expected_payload || !copy_field(payload + 0x20, motion)
            || motion != c.expected_motion) return DesiredMismatch;
        return Accepted;
    }
    return DesiredMissing;
}

static void boss_prepare_call(void* actor, uint32_t key, DispatchReason& reason,
        DispatchCommand& command, uint32_t& forwarded, void*& context, uint64_t (&private_banks)[3]) {
    const uint64_t player = reinterpret_cast<uint64_t>(actor);
    if (InterlockedCompareExchange(&boss_active, 0, 0) && player == boss_active_player) {
        if (!boss_set_bindings(false)) {
            InterlockedExchange(&dispatch->control.status, -int(BossBindingMismatch));
            reason = BossBindingMismatch;
        }
        if (key == 0xC65 || key == 0xC66 || key == 0xC67 || key == 0xC68) {
            forwarded = 0; context = nullptr; reason = BossFollowupExit;
        }
        return;
    }
    if (reason != Accepted) return;
    reason = validate_boss_source(command);
#ifdef RESEARCH_REPEAT
    const unsigned private_slot = command.reserved[1] == 1 ? 1 : 0;
    if (reason == Accepted && !boss_prepare_private_action(private_slot)) reason = BossSourceMismatch;
#endif
    if (reason != Accepted || !boss_set_bindings(true)) {
        if (reason == Accepted) reason = BossBindingMismatch;
        forwarded = key;
        InterlockedExchange(&dispatch->control.last_reason, reason);
        return;
    }
    boss_active_player = player; boss_active_owner = command.owner;
    private_banks[0] = 0; private_banks[1] = boss_session.source_bank; private_banks[2] = 0;
#ifdef RESEARCH_REPEAT
    private_banks[1] = reinterpret_cast<uint64_t>(&boss_private_actions[private_slot].bank);
    command.expected_descriptor = boss_private_descriptor_address(private_slot);
    command.expected_payload = boss_private_payload_address(private_slot);
#endif
    context = private_banks;
    InterlockedExchange(&boss_active, 1);
    InterlockedExchange(&dispatch->control.status, 2);
}

static void boss_finish_call(void* actor) {
    if (!InterlockedCompareExchange(&boss_active, 0, 0)
        || reinterpret_cast<uint64_t>(actor) != boss_active_player) return;
    uint64_t current = 0;
    if (!same_field(boss_active_player, 0x50, boss_active_owner)
        || !copy_field(boss_active_player + 0x58, current)) {
        InterlockedExchange(&dispatch->control.status, -int(BossBindingMismatch));
        return;
    }
    const bool still_preview = boss_is_preview_descriptor(current);
    if (!boss_set_bindings(still_preview)) {
        InterlockedExchange(&dispatch->control.status, -int(BossBindingMismatch));
        return;
    }
    if (!still_preview) {
        InterlockedExchange(&boss_active, 0);
        InterlockedExchange(&dispatch->control.status, 3);
    } else InterlockedExchange(&dispatch->control.status, 2);
}
