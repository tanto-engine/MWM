#pragma once
#ifdef RESEARCH_RUNTIME_SESSION
#include "boss_session_schema.h"
static uint64_t BOSS_CONFIG_TAG;
static BossSession boss_session{};
static MoveImport boss_imports[24]{};
static MoveAdapter boss_adapters[24]{};
static uint32_t boss_import_count, boss_string_variant;
static uint64_t boss_hold_variant, boss_hold_milliseconds, boss_hold_camera_bank;
static uint64_t boss_native_grapple;
static bool runtime_session_configured;

static bool runtime_imports_valid(const RuntimeSessionConfig& config) {
    // Validate the configuration-only import table before native callbacks can use it.
    // Check pointer bounds, supported action families, voice rows and acyclic combo topology.
    // Paired actions and legacy baseline aliases must not gain unsupported dispatch paths.
    if (config.import_count < 2 || config.import_count > 24 || config.string_variant >= config.import_count || config.native_grapple>1)
        return false;
    if (config.imports[config.string_variant].flags == 0x8078000000ULL) return false;
    if (config.hold_variant) {
        if (config.hold_variant > config.import_count || config.adapters[config.hold_variant-1].kind != 2
            || config.hold_milliseconds < 80 || config.hold_milliseconds > 2000
            || (config.hold_camera_bank && (config.hold_camera_bank < 0x10000 || config.hold_camera_bank > 0x7fffffffffffULL))) return false;
    } else if (config.hold_milliseconds || config.hold_camera_bank) return false;
    const MoveImport empty{};
    const MoveAdapter no_adapter{};
    bool grapple_target=false;
    for (unsigned i = config.import_count; i != 24; ++i)
        if (memcmp(&config.imports[i], &empty, sizeof(empty))
            || memcmp(&config.adapters[i], &no_adapter, sizeof(no_adapter))) return false;
    for (unsigned i = 0; i != config.import_count; ++i) {
        const auto& move = config.imports[i];
        const uint64_t pointers[] = {move.descriptor, move.payload, move.clip, move.timing_record};
        for (uint64_t pointer : pointers)
            if (pointer < 0x10000 || pointer > 0x00007fffffffffffULL) return false;
        const auto& adapter = config.adapters[i];
        if (adapter.kind==3 && !config.hold_camera_bank) return false;
        if (move.key==0x361 && move.motion==1311 && move.flags==0x8078000000ULL && !adapter.kind) grapple_target=true;
        const bool replacement = adapter.kind == 1 || adapter.kind == 2 || adapter.kind == 4;
        if (adapter.kind) {
            if (adapter.kind > 4) return false;
            const uint64_t dependencies[] = {adapter.action_resource,adapter.timing_resource,adapter.bank,
                adapter.motion_bank,adapter.timing_wrapper};
            for (uint64_t pointer : dependencies)
                if (pointer < 0x10000 || pointer > 0x00007fffffffffffULL) return false;
            if (replacement) {
            // These three researched sword entries exclude dash/running attacks.
            if (adapter.player_descriptor < 0x10000 || adapter.player_descriptor > 0x7fffffffffffULL
                || !((adapter.player_key >= 0xCF5 && adapter.player_key <= 0xCF7
                    && adapter.player_motion == 4300 + int(adapter.player_key - 0xCF5)*10)
                    || (adapter.kind != 1 && ((adapter.player_key==0xCB7 && adapter.player_motion==3300
                        && adapter.transition_count==40 && adapter.recovery_frame==58)
                        || (adapter.player_key==0xC7A && adapter.player_motion==2300
                        && adapter.transition_count==42 && adapter.recovery_frame==46))))
                || !adapter.transition_count || adapter.transition_count > 63
                || adapter.recovery_frame <= 0 || (move.flags != 0x194C0000 && (adapter.kind == 1 || move.flags != 0x200194C0000ULL))
                || (adapter.kind == 1 && move.next_variant != -1)) return false;
            if (adapter.kind == 1) for (unsigned prior=0; prior<i; ++prior)
                if (config.adapters[prior].kind == 1 && config.adapters[prior].player_key == adapter.player_key) return false;
            } else if (adapter.player_descriptor || adapter.player_key || adapter.player_motion
                || adapter.transition_count || adapter.recovery_frame || move.flags != 0x8038000000ULL) return false;
        } else if (memcmp(&adapter, &no_adapter, sizeof(adapter))) return false;
        const bool simple = move.flags == 0x184C0000 || replacement;
        const bool attempt = move.flags == 0x594C0000 || (adapter.kind == 2 && move.next_variant>=0);
        const bool paired = move.flags == 0x8078000000ULL || move.flags == 0x8038000000ULL;
        if ((!simple && !attempt && !paired) || (replacement ? (move.recovery_frame == 0 || move.recovery_frame < -1 || (adapter.kind==1 && move.recovery_frame<0)) : (simple ? move.recovery_frame <= 0 : move.recovery_frame != -1)))
            return false;
        if (!move.key || move.key > 0xfffe || move.motion < 0
            || !move.transition_count || move.transition_count > (replacement ? 128 : 28) || move.voice_count > 3
            || move.next_variant < -1 || move.next_variant >= int(config.import_count)
            || move.next_start > 0x7fff || move.next_end > 0x7fff) return false;
        if (move.next_variant == -1) {
            if (move.next_start || move.next_end) return false;
        } else {
            const auto& target = config.imports[move.next_variant];
            if (attempt != (target.flags == 0x8078000000ULL || target.flags == 0x8038000000ULL)) return false;
            if (attempt ? (move.next_start || move.next_end) :
                (paired || move.next_start > move.next_end || !move.next_end)) return false;
        }
        for (unsigned prior = 0; prior != i; ++prior)
            if (move.key == config.imports[prior].key) return false;
        const MoveVoice no_voice{};
        for (unsigned voice = 0; voice != 3; ++voice) {
            const auto& event = move.voices[voice];
            if (voice >= move.voice_count) {
                if (memcmp(&event, &no_voice, sizeof(event))) return false;
            } else {
                if (event.frame > 0xffff || event.index >= 512 || !event.hash) return false;
                for (unsigned prior = 0; prior != voice; ++prior)
                    if (event.frame == move.voices[prior].frame && event.index == move.voices[prior].index) return false;
            }
        }
        uint32_t visited = 0;
        int current = int(i);
        while (current != -1) {
            if (visited & (1u << current)) return false;
            visited |= 1u << current;
            current = config.imports[current].next_variant;
            if (current < -1 || current >= int(config.import_count)) return false;
        }
    }
    const auto& first = config.imports[0];
    const auto& second = config.imports[1];
    const auto& legacy = config.session;
    return (!config.native_grapple || grapple_target) && first.flags == 0x184C0000 && second.flags == 0x184C0000
        && first.key == 0xC64 && first.motion == 1220 && second.key == 0xC66 && second.motion == 1230
        && first.descriptor == legacy.source_descriptor && first.payload == legacy.source_payload
        && first.clip == legacy.source_clip && first.timing_record == legacy.source_timing_record
        && second.descriptor == legacy.charge_descriptor && second.payload == legacy.charge_payload
        && second.clip == legacy.charge_clip && second.timing_record == legacy.charge_timing_record;
}

static DWORD load_runtime_session(const void* parameter) {
    // Accept a stable configuration for this exact process and module lifetime.
    // Double-copy the ABI, verify process birth and reject later attempts to mutate it.
    // Private descriptors may remain referenced after an actor changes, requiring a new DLL instance.
    RuntimeSessionConfig incoming{}, check{};
    SIZE_T read = 0;
    if (!parameter || !ReadProcessMemory(GetCurrentProcess(), parameter, &incoming, sizeof(incoming), &read)
        || read != sizeof(incoming)
        || !ReadProcessMemory(GetCurrentProcess(), parameter, &check, sizeof(check), &read)
        || read != sizeof(check) || memcmp(&incoming, &check, sizeof(incoming))) return ERROR_INVALID_DATA;
    if (incoming.magic != RUNTIME_SESSION_MAGIC || incoming.version != RUNTIME_SESSION_VERSION
        || incoming.size != sizeof(incoming) || incoming.pid != GetCurrentProcessId()
        || !incoming.config_tag) return ERROR_INVALID_DATA;
    if (incoming.native_grapple > 1) return ERROR_INVALID_DATA;
    FILETIME born{}, exited{}, kernel_time{}, user_time{};
    if (!GetProcessTimes(GetCurrentProcess(), &born, &exited, &kernel_time, &user_time)) return GetLastError();
    const uint64_t creation = (uint64_t(born.dwHighDateTime) << 32) | born.dwLowDateTime;
    if (creation != incoming.creation_filetime) return ERROR_INVALID_DATA;
    // Reject absent/non-user pointers before any callback can access the config.
    // Actual ownership, keys, resources and hook prologues receive further guards.
    uint64_t pointers[26]{};
    memcpy(pointers, &incoming.session, sizeof(pointers));
    for (unsigned i = 0; i != 26; ++i) {
        const uint64_t value = pointers[i];
        // Imported actions use camera slot0, normally empty on William.
        if (i == offsetof(BossSession,camera_original)/8 && !value) continue;
        if (value < 0x10000 || value > 0x00007fffffffffffULL) return ERROR_INVALID_DATA;
    }
    if (!runtime_imports_valid(incoming)) return ERROR_INVALID_DATA;
    if (runtime_session_configured) {
        // Private descriptors may be retained as previous actions by the game.
        // Each refreshed session gets its own copy of this same prebuilt DLL.
        return incoming.config_tag == BOSS_CONFIG_TAG
            && !memcmp(&incoming.session, &boss_session, sizeof(boss_session))
            && incoming.import_count == boss_import_count && incoming.string_variant == boss_string_variant
            && incoming.hold_variant == boss_hold_variant && incoming.hold_milliseconds == boss_hold_milliseconds
            && incoming.hold_camera_bank == boss_hold_camera_bank
            && incoming.native_grapple == boss_native_grapple
            && !memcmp(incoming.adapters, boss_adapters, sizeof(boss_adapters))
            && !memcmp(incoming.imports, boss_imports, sizeof(boss_imports)) ? 0 : ERROR_INVALID_DATA;
    }
    boss_session = incoming.session;
    memcpy(boss_imports, incoming.imports, sizeof(boss_imports));
    memcpy(boss_adapters, incoming.adapters, sizeof(boss_adapters));
    boss_import_count = incoming.import_count;
    boss_string_variant = incoming.string_variant;
    boss_hold_variant = incoming.hold_variant;
    boss_hold_milliseconds = incoming.hold_milliseconds;
    boss_hold_camera_bank = incoming.hold_camera_bank;
    boss_native_grapple = incoming.native_grapple;
    BOSS_CONFIG_TAG = incoming.config_tag;
    runtime_session_configured = true;
    return 0;
}
#else
// Only research preview/test builds use a generated or owned-buffer header.
#include "boss_session.h"
static constexpr uint64_t boss_native_grapple = 0;
#endif
