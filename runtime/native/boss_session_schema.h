#pragma once
#include <stdint.h>
#include <stddef.h>

// Runtime addresses are session data, never compiled move identities.
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
    uint64_t originals[4];
};
static_assert(sizeof(BossSession) == 208, "Session ABI size");

struct MoveVoice { uint32_t frame, index, hash; };
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
    uint32_t kind; // 0 baseline, 1 native replacement, 2 held entry, 3 native paired continuation.
};
static_assert(sizeof(MoveAdapter) == 64, "Adapter ABI size");

struct RuntimeSessionConfig {
    uint32_t magic, version, size, pid;
    uint64_t creation_filetime, config_tag;
    uint64_t hold_variant, hold_milliseconds, hold_camera_bank, native_bindings; // grapple1, Tiger Sprint2, mid ender4
    uint64_t hold_stances, frost_variants[3], frost_milliseconds, frost_speed;
    BossSession session;
    uint32_t import_count, string_variant;
    MoveImport imports[24];
    MoveAdapter adapters[24];
};
static_assert(sizeof(RuntimeSessionConfig) == 4168 && offsetof(RuntimeSessionConfig, imports) == 328,
              "Runtime configuration ABI size");
static constexpr uint32_t RUNTIME_SESSION_MAGIC = 0x3153454e; // NES1
static constexpr uint32_t RUNTIME_SESSION_VERSION = 7;
