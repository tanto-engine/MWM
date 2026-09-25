#pragma once

// Native9670A0 handles timing type10 sound entries. The two hashes resolve to
// AV_OKATSU_SKILL_SHORT and AV_OKATSU_ATTACK_STRONG in the loaded audio name tree.
// This predicate changes no metadata and leaves every other sound request alone.
static bool boss_suppress_voice(void* state, void* timing_record, void* event) {
    if (!InterlockedCompareExchange(&boss_active, 0, 0)
        || boss_active_player != boss_session.player
        || boss_active_owner != boss_session.player_owner || !boss_player_valid()) return false;
    uint64_t current = 0;
    if (!copy_field(boss_session.player + 0x58, current)) return false;
    unsigned slot = 2;
    for (unsigned i = 0; i != 2; ++i)
        if (boss_private_actions[i].ready && current == boss_private_descriptor_address(i)) slot = i;
    if (slot == 2) return false;
    const uint64_t record = reinterpret_cast<uint64_t>(timing_record);
    const uint64_t expected_record = slot ? boss_session.charge_timing_record : boss_session.source_timing_record;
    const uint64_t state_address = reinterpret_cast<uint64_t>(state);
    if (record != expected_record || record < 0x10000 || record > UINT64_MAX - 0x20000
        || !same_field(state_address, 8, boss_session.player_owner)
        || !same_field(state_address, 0x20, record)) return false;
    uint32_t count = 0, event_offset = 0, sound_offset = 0;
    if (!copy_field(record + 4, count) || !copy_field(record + 8, event_offset)
        || !copy_field(record + 0x10, sound_offset)
        || !count || count > 512 || event_offset < 0x24 || event_offset > 0x10000
        || sound_offset < event_offset + count * 12 || sound_offset > 0x10000) return false;
    const uint64_t address = reinterpret_cast<uint64_t>(event);
    const uint64_t start = record + event_offset;
    if (address < start || address - start >= uint64_t(count) * 12 || (address - start) % 12) return false;
    uint32_t fields[3]{};
    if (!copy_bytes(address, fields, sizeof(fields)) || fields[1] != 10
        || fields[0] != (slot ? 46u : 30u) || fields[2] != (slot ? 16u : 11u)) return false;
    uint32_t sound_hash = 0;
    return copy_field(record + sound_offset + uint64_t(fields[2]) * 0x4c + 0x1c, sound_hash)
        && sound_hash == (slot ? 0xF519B456u : 0x0E077D36u);
}
