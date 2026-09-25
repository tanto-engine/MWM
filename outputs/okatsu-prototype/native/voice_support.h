#pragma once

// Copied from William's sword timing4210/frame27. The native sound-name tree
// resolves 97933946 to AV_WILLIAM_ATTACK_MIDDLE. Keep its native probability,
// owner routing and variation; the imported timing only supplies the cue time.
// Static storage also covers any deferred native use of the sound row.
struct PlayerVoiceTiming {
    uint32_t header[9], event[3], sound[19];
};
static PlayerVoiceTiming william_attack_voice = {
    {0, 1, 0x24, 0, 0x30, 0, 0, 0, 0}, {0, 10, 0},
    {0, 0, 0, 0, 0, 1, 2, 0x97933946, 0, 0, 0, 0xffffffff, 80,
     0xffffffff, 0xffffffff, 0, 12, 0, 0}
};
static_assert(offsetof(PlayerVoiceTiming, sound) == 0x30, "Native sound row offset");

// Native9670A0 handles timing type10 sound entries. Configured rows include
// AV_OKATSU_SKILL_SHORT and AV_OKATSU_ATTACK_STRONG from the native name tree.
// This predicate leaves every other actor and sound request alone.
static bool boss_suppress_voice(void* state, void* timing_record, void* event) {
    // Recognize only configured boss-vocal events belonging to the imported player.
    // Check action ownership, timing record, event bounds and the exact source sound hash.
    // The boss's own audio and unrelated combat sounds must retain their original handler path.
    // TODO: verify the replacement William attack vocal audibly during play.
    // Exact event routing and retained native probability are covered offline;
    // those checks cannot establish that a particular playback was heard.
    if (!InterlockedCompareExchange(&boss_active, 0, 0)
        || boss_active_player != boss_session.player
        || boss_active_owner != boss_session.player_owner || !boss_player_valid()) return false;
    uint64_t current = 0;
    if (!copy_field(boss_session.player + 0x58, current)) return false;
    unsigned slot = boss_import_count;
    for (unsigned i = 0; i != boss_import_count; ++i)
        if (boss_private_actions[i].ready && current == boss_private_descriptor_address(i)) slot = i;
    if (slot == boss_import_count) return false;
    const uint64_t record = reinterpret_cast<uint64_t>(timing_record);
    const uint64_t expected_record = boss_imports[slot].timing_record;
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
    if (!copy_bytes(address,fields,sizeof(fields)) || fields[1] != 10) return false;
    for (unsigned i = 0; i != boss_imports[slot].voice_count; ++i) {
        const auto& voice = boss_imports[slot].voices[i];
        if (fields[0] != voice.frame || fields[2] != voice.index) continue;
        uint32_t hash = 0;
        return copy_field(record+sound_offset+uint64_t(fields[2])*0x4c+0x1c,hash) && hash == voice.hash;
    }
    return false;
}
