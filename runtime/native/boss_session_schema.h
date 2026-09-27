#pragma once
#include <stdint.h>
#include <stddef.h>

// Runtime addresses are session data, never compiled move identities.
// These uint64_t values are addresses inside this Nioh process, not portable asset IDs.
// The loader retains source packages; this record identifies player components that must be revalidated after reload.
struct BossSession {
    uint64_t player;
    uint64_t player_owner;
    uint64_t source_action_resource;
    uint64_t source_timing_resource;
    uint64_t vtable;
    uint64_t source_bank;
    uint64_t source_descriptor;
    uint64_t source_payload;
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
    uint64_t source_camera_bank;
    uint64_t player_camera_slot;
    uint64_t camera_original;
    // Saved values correspond to motion +8/+0x28, then timing +0x10/+0x28 (see boss_slot).
    // Restoration requires the slot still to contain either its saved value or this runtime's borrowed value.
    uint64_t originals[4];
};
static_assert(sizeof(BossSession) == 208, "Session ABI size");

// Voice entries identify a source timing event by frame, sound-row index and exact sound hash.
struct MoveVoice { uint32_t frame, index, hash; };
// One import joins an action descriptor/payload to its motion clip and timed-event record.
// next_variant uses a zero-based import index or -1; it describes an allowed follow-up, not a forced input.
struct MoveImport {
    uint64_t descriptor, payload, clip, timing_record, flags;
    uint32_t key;
    int32_t motion;
    int16_t recovery_frame;
    uint16_t transition_count;
    int16_t next_variant;
    uint16_t next_start, next_end, voice_count;
    MoveVoice voices[3];
};
static_assert(sizeof(MoveVoice) == 12 && sizeof(MoveImport) == 96, "Import ABI size");

// Zero rows use the baseline resource set. Replacements carry their own source
// resources and an exact William descriptor whose input/recovery rules are kept.
struct MoveAdapter {
    uint64_t action_resource, timing_resource, bank, motion_bank, timing_wrapper, player_descriptor;
    uint32_t player_key;
    int32_t player_motion;
    uint16_t transition_count;
    int16_t recovery_frame;
    uint32_t kind; // 0 baseline, 1 native replacement, 2 skill entry, 3 paired, 4 ordinary continuation, 5 isolated jump.
};
static_assert(sizeof(MoveAdapter) == 64, "Adapter ABI size");

// Binding variants are 1-based (zero means unset); stance bits use the runtime's low/mid/high order.
// Native-signature bindings also retain key/motion/flags to avoid replacing an unrelated attack.
struct SkillBinding {
    uint32_t kind, stances, variant, key;
    int32_t motion;
    uint32_t transition_count;
    uint64_t flags;
};
static_assert(sizeof(SkillBinding)==32,"Skill binding ABI size");

// Thresholds choose a launch policy by resistance; weight_scale and vertical_impulse affect separate native fields.
struct LaunchProfile { uint32_t resistance_below; float weight_scale, vertical_impulse; uint32_t reserved; };
// Playback speed is a multiplier; pulse_percent controls recoverable Ki and fill/hold use native frame units.
struct MoveSettings { float speed; uint16_t pulse_percent, pulse_fill, pulse_hold, reserved; };
static_assert(sizeof(MoveSettings)==12,"Move settings ABI size");

// This fixed Windows x64 layout is copied from the launcher, not read as a C++ object from another process.
// PID plus creation_filetime rejects a reused PID; config_tag separates sessions sharing the same process.
// Keep reserved fields zero and update both producers and consumers when changing version, size or offsets.
struct RuntimeSessionConfig {
    uint32_t magic, version, size, pid;
    uint64_t creation_filetime, config_tag;
    uint64_t hold_variant, hold_milliseconds, hold_camera_bank, native_bindings; // native grapple1, mid-light ender4; skill_bindings owns input mappings
    uint64_t hold_stances, frost_variants[3], frost_milliseconds, frost_speed;
    BossSession session;
    uint32_t import_count, string_variant;
    MoveImport imports[32];
    MoveAdapter adapters[32];
    SkillBinding skill_bindings[8];
    LaunchProfile launch_profiles[2];
    float air_juggle_boost, tracking_rates[3];
    MoveSettings move_settings[32];
    uint32_t controller_selection, reserved;
};
static_assert(sizeof(RuntimeSessionConfig) == 6144 && offsetof(RuntimeSessionConfig, imports) == 328,
              "Runtime configuration ABI size");
static constexpr uint32_t RUNTIME_SESSION_MAGIC = 0x3153454e; // NES1
static constexpr uint32_t RUNTIME_SESSION_VERSION = 11;
