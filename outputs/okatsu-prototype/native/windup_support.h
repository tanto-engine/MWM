#pragma once

// Native clock chain:719101/719114 computes speed(+6A8) and delta(+24).
// 6FF8F1..6FF920 copies speed to motion+F4;955A67 and969512/96952B
// use that SAME speed for motion and timing. Never seek either event cursor.
static bool windup_writable_float(uint64_t address) {
    MEMORY_BASIC_INFORMATION region{};
    return !(address & 3) && VirtualQuery(reinterpret_cast<void*>(address), &region, sizeof(region))
        && region.State == MEM_COMMIT && !(region.Protect & (PAGE_GUARD | PAGE_NOACCESS))
        && (region.Protect & 0xff) == PAGE_READWRITE
        && address + sizeof(float) <= reinterpret_cast<uint64_t>(region.BaseAddress) + region.RegionSize;
}

static float boss_shorten_rush_windup(void* actor, float native_delta) {
    const uint64_t player = reinterpret_cast<uint64_t>(actor);
    if (!trace || !dispatch || !InterlockedCompareExchange(&trace->header.enabled, 0, 0)
        || !InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)
        || !InterlockedCompareExchange(&boss_active, 0, 0)
        || player != boss_session.player || player != boss_active_player
        || !boss_private_actions[0].ready || !boss_player_valid()
        || !same_field(player, 0x58, boss_private_descriptor_address(0))
        || !boss_session.source_clip || !same_field(boss_session.player_motion, 0x58, boss_session.source_clip))
        return native_delta;
    float frame = 0, speed = 0, delta = 0;
    if (!copy_field(player + 0x28, frame) || !copy_field(player + 0x6A8, speed)
        || !copy_field(player + 0x24, delta)
        || !(frame >= 0.0f && frame < 30.0f && speed > 0.0f && speed <= 8.0f
             && delta > 0.0f && delta <= 4.0f && delta == native_delta)) return native_delta;
    const float remaining = 30.0f - frame;
    float accelerated = delta * 2.0f;
    if (accelerated > remaining) accelerated = remaining;
    // Never slow an ordinary update when it already crosses the boundary.
    if (!(accelerated > delta) || !windup_writable_float(player + 0x24)
        || !windup_writable_float(player + 0x6A8)) return native_delta;
    const float accelerated_speed = speed * (accelerated / delta);
    // Both native-owned fields are updated on the existing player game thread,
    // before the motion-binding/update phase. Original719050 recomputes them
    // on every tick, so no persistent speed patch or cleanup is required.
    memcpy(reinterpret_cast<void*>(player + 0x6A8), &accelerated_speed, sizeof(float));
    memcpy(reinterpret_cast<void*>(player + 0x24), &accelerated, sizeof(float));
    return accelerated;
}
