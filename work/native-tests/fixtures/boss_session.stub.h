#pragma once
// Session-bound preview only. Regenerate after any process/actor reload.
#include <stdint.h>
static constexpr uint64_t BOSS_CONFIG_TAG = 0ULL;
struct BossSession {
    uint64_t player;
    uint64_t player_owner;
    uint64_t source_actor;
    uint64_t source_owner;
    uint64_t vtable;
    uint64_t source_bank;
    uint64_t source_descriptor;
    uint64_t source_payload;
    uint64_t source_motion;
    uint64_t source_timing;
    uint64_t source_motion_bank;
    uint64_t source_timing_wrapper;
    uint64_t source_clip;
    uint64_t source_timing_record;
    uint64_t player_motion;
    uint64_t player_timing;
    uint64_t charge_descriptor;
    uint64_t charge_payload;
    uint64_t charge_clip;
    uint64_t charge_timing_record;
    uint64_t player_pulse_descriptor;
    uint64_t originals[4];
};
static BossSession boss_session = {};
