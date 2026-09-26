#pragma once
#include "boss_session_schema.h"
static uint64_t BOSS_CONFIG_TAG;
static BossSession boss_session{};
static MoveImport boss_imports[24]{};
static MoveAdapter boss_adapters[24]{};
static uint32_t boss_import_count, boss_string_variant;
static uint64_t boss_hold_variant, boss_hold_milliseconds, boss_hold_camera_bank;
static uint64_t boss_native_grapple;
static uint64_t boss_native_bindings;
static SkillBinding boss_skill_bindings[8]{};
static uint64_t boss_hold_stances=7, boss_frost_variants[3]{}, boss_frost_milliseconds=750, boss_frost_speed=8;
static bool runtime_session_configured;

static bool airborne_sword(const MoveImport& move, const MoveAdapter& adapter) {
    // Recognize recorded airborne phases with their exact stance owners.
    // Only the two jumps are entries; the remaining phases require native continuation.
    // Other zero-flag actions cannot acquire the airborne policy.
    const bool swallow=move.key>=0xC71 && move.key<=0xC74;
    const bool somersault=move.key>=0xC81 && move.key<=0xC83;
    if (!swallow && !somersault) return false;
    const unsigned phase=swallow ? move.key-0xC71 : move.key-0xC81+4;
    constexpr int motions[]={1050,5000,5001,5002,1050,5050,5051}, counts[]={18,17,18,75,18,18,75};
    return move.motion==motions[phase] && move.transition_count==counts[phase]
        && move.flags==((phase==3 || phase==6) ? 0x1BCE0000ULL : 0)
        && adapter.kind==((phase==0 || phase==4) ? 2u : 4u)
        && move.recovery_frame==(phase==3 ? 20 : -1) && move.next_variant==-1;
}

static bool runtime_imports_valid(const RuntimeSessionConfig& config) {
    // Validate the configuration-only import table before native callbacks can use it.
    // Check pointer bounds, supported action families, voice rows and acyclic combo topology.
    // Paired actions and legacy baseline aliases must not gain unsupported dispatch paths.
    if (config.import_count < 2 || config.import_count > 24 || config.string_variant >= config.import_count || (config.native_bindings&~5ULL)
        || config.hold_stances>7 || config.frost_milliseconds<100 || config.frost_milliseconds>1500
        || config.frost_speed<1 || config.frost_speed>8)
        return false;
    constexpr uint32_t openers[]={0xCF5,0xC7A,0xCB7};
    for (unsigned stance=0;stance<3;++stance) {
        const auto slot=config.frost_variants[stance];
        if (slot && (slot>config.import_count || config.adapters[slot-1].kind!=2
            || config.adapters[slot-1].player_key!=openers[stance])) return false;
    }
    uint32_t held_stances=0;
    for (unsigned index=0;index<8;++index) {
        const auto& binding=config.skill_bindings[index];const SkillBinding empty{};
        if (!binding.kind) { if (memcmp(&binding,&empty,sizeof(empty))) return false; continue; }
        if (binding.kind>3 || !binding.stances || binding.stances>7 || !binding.variant || binding.variant>config.import_count) return false;
        const auto& adapter=config.adapters[binding.variant-1];
        if (binding.kind==3) {
            if (adapter.kind!=2) return false;
            held_stances|=binding.stances;
        }
        if (!adapter.kind && config.imports[binding.variant-1].flags!=0x184C0000ULL) return false;
        if (adapter.kind) {
            bool owner=false;
            for (unsigned stance=0;stance<3;++stance)
                owner=owner || (adapter.kind==2 && binding.stances==(1u<<stance) && adapter.player_key==openers[stance]);
            if (!owner) return false;
        }
        if (binding.kind==1 ? (binding.key!=0xFAA || binding.motion!=5090 || binding.transition_count!=21 || binding.flags!=0x40017C00000ULL)
            : (binding.key || binding.motion || binding.transition_count || binding.flags)) return false;
        for (unsigned prior=0;prior<index;++prior) {
            const auto& earlier=config.skill_bindings[prior];
            if (earlier.kind==binding.kind && earlier.key==binding.key && (earlier.stances&binding.stances)) return false;
        }
    }
    if (held_stances!=config.hold_stances || (held_stances && !config.hold_variant)) return false;
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
        const bool izuna_bridge = adapter.kind==4 && move.key==0xC7A && move.motion==1050 && !move.flags;
        const bool airborne=airborne_sword(move,adapter);
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
                || adapter.recovery_frame <= 0 || (!izuna_bridge && !airborne && move.flags != 0x194C0000)
                || (adapter.kind == 1 && move.next_variant != -1)) return false;
            if (adapter.kind == 1) for (unsigned prior=0; prior<i; ++prior)
                if (config.adapters[prior].kind == 1 && config.adapters[prior].player_key == adapter.player_key) return false;
            } else if (adapter.player_descriptor || adapter.player_key || adapter.player_motion
                || adapter.transition_count || adapter.recovery_frame || move.flags != 0x8038000000ULL) return false;
        } else if (memcmp(&adapter, &no_adapter, sizeof(adapter))) return false;
        const bool simple = move.flags == 0x184C0000 || replacement;
        const bool attempt = move.flags == 0x594C0000 || ((adapter.kind == 2 || izuna_bridge) && move.next_variant>=0);
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
        for (unsigned prior = 0; prior != i; ++prior) if (move.key == config.imports[prior].key) {
            const auto& earlier=config.imports[prior]; const auto& owner=config.adapters[prior];
            if (move.key!=0xC79 || move.motion!=5014 || move.flags!=0x194C0000 || adapter.kind!=2 || owner.kind!=2
                || adapter.player_key==owner.player_key || earlier.motion!=move.motion || earlier.flags!=move.flags
                || earlier.descriptor!=move.descriptor || earlier.payload!=move.payload || earlier.clip!=move.clip
                || earlier.timing_record!=move.timing_record || earlier.transition_count!=move.transition_count
                || earlier.recovery_frame!=move.recovery_frame) return false;
        }
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
    return (!(config.native_bindings&1) || grapple_target) && first.flags == 0x184C0000 && second.flags == 0x184C0000
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
    if (incoming.native_bindings&~5ULL) return ERROR_INVALID_DATA;
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
            && incoming.native_bindings == boss_native_bindings
            && incoming.hold_stances==boss_hold_stances && incoming.frost_milliseconds==boss_frost_milliseconds
            && incoming.frost_speed==boss_frost_speed
            && !memcmp(incoming.frost_variants,boss_frost_variants,sizeof(boss_frost_variants))
            && !memcmp(incoming.skill_bindings,boss_skill_bindings,sizeof(boss_skill_bindings))
            && !memcmp(incoming.adapters, boss_adapters, sizeof(boss_adapters))
            && !memcmp(incoming.imports, boss_imports, sizeof(boss_imports)) ? 0 : ERROR_INVALID_DATA;
    }
    boss_session = incoming.session;
    memcpy(boss_skill_bindings,incoming.skill_bindings,sizeof(boss_skill_bindings));
    memcpy(boss_imports, incoming.imports, sizeof(boss_imports));
    memcpy(boss_adapters, incoming.adapters, sizeof(boss_adapters));
    boss_import_count = incoming.import_count;
    boss_string_variant = incoming.string_variant;
    boss_hold_variant = incoming.hold_variant;
    boss_hold_milliseconds = incoming.hold_milliseconds;
    boss_hold_camera_bank = incoming.hold_camera_bank;
    boss_native_bindings = incoming.native_bindings; boss_native_grapple=boss_native_bindings&1;
    boss_hold_stances=incoming.hold_stances; boss_frost_milliseconds=incoming.frost_milliseconds; boss_frost_speed=incoming.frost_speed;
    memcpy(boss_frost_variants,incoming.frost_variants,sizeof(boss_frost_variants));
    BOSS_CONFIG_TAG = incoming.config_tag;
    runtime_session_configured = true;
    return 0;
}
