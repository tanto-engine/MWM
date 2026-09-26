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

using TrackingYawFn = void (*)(void*,float);
using TrackingTargetFn = uint64_t (*)(const uint64_t*);
static TrackingYawFn native_set_yaw;
static TrackingTargetFn native_locked_target;
static uint64_t tracking_registry;

static bool resolve_tracking_helpers(uint64_t module) {
    // Pin the native yaw-only setter and exact-handle registry lookup for this executable.
    // Both helpers run synchronously on an existing player callback, without hooks or retained targets.
    // The resolver returns a borrowed entity; its identity is checked again before the yaw write.
    const uint8_t yaw[]={0x0f,0x2f,0x0d,0x8d,0x6c,0xe7,0,0x76,0x0e,0xf3,0x0f,0x5c,0x0d,0xbb,0x6c,0xe7};
    const uint8_t target[]={0x48,0x8b,0xd1,0x48,0x8b,0x0d,0xae,0xab,0x14,0x01,0xe9,0xc1,0xfd,0xff,0xff};
    const uint8_t lookup[]={0x8b,0x02,0x4c,0x8b,0xd1,0x44,0x0f,0xb7,0x4a,0x06,0x45,0x33,0xc0,0x48,0x8b,0x12};
    uint8_t bytes[16];native_set_yaw=nullptr;native_locked_target=nullptr;tracking_registry=0;
    if (!copy_bytes(module+0x711DD0,bytes,sizeof(yaw)) || memcmp(bytes,yaw,sizeof(yaw))
        || !copy_bytes(module+0x755890,bytes,sizeof(target)) || memcmp(bytes,target,sizeof(target))
        || !copy_bytes(module+0x755660,bytes,sizeof(lookup)) || memcmp(bytes,lookup,sizeof(lookup))) return false;
    native_set_yaw=reinterpret_cast<TrackingYawFn>(module+0x711DD0);
    native_locked_target=reinterpret_cast<TrackingTargetFn>(module+0x755890);
    tracking_registry=module+0x18A0448;return true;
}

static void track_locked_target(uint64_t player, unsigned slot, float delta, unsigned group) {
    // Follow the current lock target through each supported attack phase with bounded horizontal turning.
    // Native711DD0 writes yaw alone; rate times unaccelerated delta preserves per-second turn speed.
    // Recheck identities each callback and retain no target, position, camera or accumulated-turn state.
    uint32_t serial=0,human=1;uint16_t type=1;uint64_t controller=0,handle=0,registry=0,preferred=0,movement=0;
    uint64_t profile=0,component=0,target_actor=0,target_current=0,target_payload=0,flags=0;
    if (!native_set_yaw || !native_locked_target || !copy_field(player+0xDC,serial)
        || !copy_field(boss_private_payload_address(slot)+0x18,flags) || (flags&0x20000000ULL)
        || !copy_field(player+8,controller) || !copy_field(controller+0x40,handle) || !handle
        || !copy_field(tracking_registry,registry) || !registry || !copy_field(player+0x38,preferred)) return;
    movement=preferred;
    if (!movement && !copy_field(player+0x18,movement)) return;
    const uint64_t target=native_locked_target(&handle);
    if (!target || target==boss_session.player_owner || !same_field(target,0,handle)
        || !copy_field(target+4,type) || type || !copy_field(target+0xE90,profile)
        || !copy_field(profile+0x0C,human) || (!group && human) || !copy_field(target+0x230,component)
        || !copy_field(component+8,target_actor) || target_actor==player || !same_field(target_actor,0,boss_session.vtable)
        || !same_field(target_actor,0x50,target) || !copy_field(target_actor+0x58,target_current)
        || !copy_field(target_current+0x20,target_payload) || !copy_field(target_payload+0x18,flags)
        || (flags&0x20000000ULL)) return;
    float origin[3],position[3],yaw=0;
    if (!copy_bytes(boss_session.player_owner+0xF0,origin,sizeof(origin)) || !copy_bytes(target+0xF0,position,sizeof(position))
        || !copy_field(movement+0x54,yaw) || !std::isfinite(yaw)) return;
    const float dx=position[0]-origin[0],dy=position[1]-origin[1],dz=position[2]-origin[2];
    if (!(dx*dx+dz*dz>0.000001f && dx*dx+dz*dz<=(group ? 1440000 : 360000) && std::abs(dy)<=1200)) return;
    constexpr float pi=3.141592741f;
    const float aim=std::atan2(dx,dz),difference=std::remainder(aim-yaw,2*pi);
    const float step=boss_tracking_rates[group]*delta*pi/(60*180);
    if (std::abs(difference)<0.00001f || !windup_writable_float(movement+0x54)
        || !boss_player_valid() || !same_field(player,8,controller) || !same_field(controller,0x40,handle)
        || !same_field(player,0x58,boss_private_descriptor_address(slot)) || !same_field(player,0x38,preferred)
        || (!preferred && !same_field(player,0x18,movement)) || !same_field(target,0,handle)
        || !same_field(target,0x230,component) || !same_field(component,8,target_actor)
        || !same_field(target_actor,0x50,target) || !same_field(target_actor,0x58,target_current)) return;
    uint32_t after=0;if (!copy_field(player+0xDC,after) || after!=serial) return;
    native_set_yaw(reinterpret_cast<void*>(movement),std::remainder(yaw+(difference>step ? step : difference < -step ? -step : difference),2*pi));
}

static float boss_advance_clock(void* actor, float native_delta) {
    // Shorten configured startup through the shared animation clock.
    // Scale speed and delta together; stop at each explicit phase boundary.
    // Seeking frames would desynchronize timing events; native per-frame recomputation supplies recovery.
    const uint64_t player = reinterpret_cast<uint64_t>(actor);
    if (player!=boss_session.player) return native_delta;
    const unsigned slot=boss_active_slot;
    if (slot>=boss_import_count) return native_delta;
    const auto& move=boss_imports[slot];const auto timing=boss_move_timing(slot);
    const bool izuna=(move.key==0xC79 && move.motion==5014 && boss_native_successor(slot,0xC7A)>=0)
        || (move.key==0xC7A && move.motion==1050 && boss_native_successor(slot,0x3B2)>=0);
    const unsigned group=izuna ? 0 : airborne_sword(move,boss_adapters[slot]) && boss_adapters[slot].kind!=5
        ? (move.key>=0xC81 ? 1 : 2) : 3;
    if (!timing.startup_end && group==3) return native_delta;
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
        || !(frame >= 0.0f && speed > 0.0f && speed <= 8.0f
             && delta > 0.0f && delta <= 4.0f && delta == native_delta)) return native_delta;
    const float tracking_end=move.key==0xC79 ? 26 : move.key==0xC83 ? 29 : move.key==0xC74 ? 20 : 1000;
    if (group<3 && boss_tracking_rates[group]>0 && frame<tracking_end) {
        const DWORD error=GetLastError();track_locked_target(player,slot,native_delta,group);SetLastError(error);
    }
    const float boundary=timing.startup_end;
    if (frame>=boundary) return native_delta;
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
