#pragma once

// Native clock chain:719101/719114 computes speed(+6A8) and delta(+24).
// 6FF8F1..6FF920 copies speed to motion+F4;955A67 and969512/96952B
// use that SAME speed for motion and timing. Never seek either event cursor.
static bool windup_writable_float(uint64_t address) {
    // Validate the two native clock fields before scoped speed adjustment.
    // Require aligned committed writable storage containing the entire float.
    // A changed allocation must reject acceleration before either clock field is written.
    MEMORY_BASIC_INFORMATION region{};
    return !(address & 3) && VirtualQuery(reinterpret_cast<void*>(address), &region, sizeof(region))
        && region.State == MEM_COMMIT && !(region.Protect & (PAGE_GUARD | PAGE_NOACCESS))
        && (region.Protect & 0xff) == PAGE_READWRITE
        && address + sizeof(float) <= reinterpret_cast<uint64_t>(region.BaseAddress) + region.RegionSize;
}

static float boss_advance_clock(void* actor, float native_delta) {
    // Shorten configured startup through the shared native animation clock.
    // Scale speed and delta together before C64 frame30 or the identified C79 launcher frame8.
    // Seeking frames would desynchronize timing events; native per-frame recomputation supplies recovery.
    const uint64_t player = reinterpret_cast<uint64_t>(actor);
    const unsigned slot=boss_active_slot;
    if (slot>=boss_import_count) return native_delta;
    const auto& move=boss_imports[slot];
    const auto timing=boss_move_timing(slot);
    const float boundary=timing.startup_end;
    if (!boundary) return native_delta;
    if (!trace || !dispatch || !InterlockedCompareExchange(&trace->header.enabled, 0, 0)
        || !InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)
        || !InterlockedCompareExchange(&boss_active, 0, 0)
        || player != boss_session.player || player != boss_active_player
        || !boss_private_actions[slot].ready || !boss_player_valid()
        || !same_field(player, 0x58, boss_private_descriptor_address(slot))
        || !move.clip || !same_field(boss_session.player_motion, 0x58, move.clip))
        return native_delta;
    float frame = 0, speed = 0, delta = 0;
    if (!copy_field(player + 0x28, frame) || !copy_field(player + 0x6A8, speed)
        || !copy_field(player + 0x24, delta)
        || !(frame >= 0.0f && frame < boundary && speed > 0.0f && speed <= 8.0f
             && delta > 0.0f && delta <= 4.0f && delta == native_delta)) return native_delta;
    const float remaining = boundary - frame;
    float accelerated = delta * timing.startup_speed;
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
