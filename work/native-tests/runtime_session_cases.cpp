// Runtime startup and retirement guards with owned memory; no game access.
#define RESEARCH_RUNTIME_SESSION
#define main inherited_frame_test_main
#include "frame_dispatch_cases.cpp"
#undef main

static RuntimeSessionConfig config() {
    // Build a complete seven-import runtime ABI fixture with this process's birth.
    // Use non-live pointer values and the real baseline/chain topology.
    // Startup validation can then reject malformed contracts without accessing a game.
    RuntimeSessionConfig result{};
    result.magic = RUNTIME_SESSION_MAGIC; result.version = RUNTIME_SESSION_VERSION;
    result.size = sizeof(result); result.pid = GetCurrentProcessId(); result.config_tag = 0x123456789abcdef0ULL;
    FILETIME born{}, ended{}, kernel{}, user{};
    assert(GetProcessTimes(GetCurrentProcess(), &born, &ended, &kernel, &user));
    result.creation_filetime = (uint64_t(born.dwHighDateTime) << 32) | born.dwLowDateTime;
    uint64_t values[26];
    for (unsigned i = 0; i != 26; ++i) values[i] = 0x10000 + i * 0x100;
    memcpy(&result.session, values, sizeof(values));
    result.session.camera_original=0;
    result.import_count=7; result.string_variant=2;
    const uint32_t keys[]={0xC64,0xC66,0xC61,0xC62,0xC63,0xC69,0x361};
    const int32_t motions[]={1220,1230,1210,1211,1212,1310,1311};
    const int16_t recovery[]={65,90,52,37,67,-1,-1};
    const uint16_t rows[]={28,22,14,14,16,13,7};
    for (unsigned i=0;i!=7;++i) {
        auto& move=result.imports[i];
        move.descriptor=0x20000+i*0x1000;move.payload=move.descriptor+0x100;
        move.clip=move.descriptor+0x200;move.timing_record=move.descriptor+0x300;
        move.key=keys[i];move.motion=motions[i];move.recovery_frame=recovery[i];move.transition_count=rows[i];
        move.flags=i==6 ? 0x8078000000ULL : i==5 ? 0x594C0000 : 0x184C0000;
        move.next_variant=-1;move.voice_count=1;move.voices[0]={22,12,0x297D2215};
    }
    auto& first=result.imports[0];auto& second=result.imports[1];
    first.descriptor=result.session.source_descriptor;first.payload=result.session.source_payload;
    first.clip=result.session.source_clip;first.timing_record=result.session.source_timing_record;
    second.descriptor=result.session.charge_descriptor;second.payload=result.session.charge_payload;
    second.clip=result.session.charge_clip;second.timing_record=result.session.charge_timing_record;
    result.imports[2].next_variant=3;result.imports[2].next_start=30;result.imports[2].next_end=45;
    result.imports[3].next_variant=4;result.imports[3].next_start=25;result.imports[3].next_end=40;
    result.imports[4].next_variant=5;result.imports[4].next_start=75;result.imports[4].next_end=99;
    result.imports[5].next_variant=6;
    return result;
}

int main() {
    // Exercise immutable runtime configuration and positive actor retirement.
    // Mutate the seven-import ABI and drive owned frame recovery scenarios.
    // Stale process identities and reused actor pointers must not authorize native writes.
    auto incoming = config();
    auto grapple_config=incoming; grapple_config.native_grapple=1;
    assert(runtime_imports_valid(grapple_config));
    grapple_config.imports[6].motion=1312;
    assert(!runtime_imports_valid(grapple_config));
    assert(load_runtime_session(nullptr) == ERROR_INVALID_DATA);
    auto invalid = incoming; invalid.pid += 1;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    invalid = incoming; invalid.creation_filetime += 1;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    invalid = incoming; invalid.native_grapple = 2;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    invalid = incoming; invalid.session.player = 1;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    invalid = incoming; invalid.session.source_bank = 0xffffffffffffffffULL;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    for (unsigned i=0;i<26;++i) {
        if (i==offsetof(BossSession,camera_original)/8) continue;
        invalid=incoming;
        const uint64_t null_pointer=0;
        memcpy(reinterpret_cast<uint8_t*>(&invalid.session)+i*8,&null_pointer,8);
        assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA && !runtime_session_configured);
    }
    for (uint32_t count : {0u,1u,17u}) {
        invalid=incoming;invalid.import_count=count;
        assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA && !runtime_session_configured);
    }
    invalid=incoming;invalid.string_variant=7;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[7].key=1;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].next_variant=16;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].next_variant=2;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[4].next_variant=2;invalid.imports[4].next_start=1;invalid.imports[4].next_end=2;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[4].next_end=4;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].next_start=46;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].key=0xC64;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].descriptor=0xffffffffffffffffULL;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].transition_count=29;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].recovery_frame=-1;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].voice_count=4;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].voices[0].index=512;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].voices[0].frame=65536;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].voices[0].hash=0;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].voices[1].hash=1;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[0].clip+=8;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.string_variant=6;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[4].next_variant=6;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[5].next_end=1;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.imports[2].flags=0xffffffff;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    assert(load_runtime_session(&incoming) == 0 && runtime_session_configured);
    assert(BOSS_CONFIG_TAG == incoming.config_tag && !memcmp(&boss_session, &incoming.session, sizeof(boss_session)));
    assert(boss_import_count==7 && boss_string_variant==2 && !memcmp(boss_imports,incoming.imports,sizeof(boss_imports)));
    assert(load_runtime_session(&incoming) == 0);
    invalid = incoming; invalid.session.player += 0x100;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA);
    assert(!memcmp(&boss_session, &incoming.session, sizeof(boss_session)));
    invalid=incoming;invalid.imports[2].recovery_frame+=1;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    assert(!memcmp(boss_imports,incoming.imports,sizeof(boss_imports)));

    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency = freq.QuadPart;
    reset(); tick();
    // A descriptor-only recovery restores all slots at a native frame boundary.
    put(player.data(), 0x58, address(neutral.data())); tick();
    assert(!boss_active); bindings(false);

    reset(); tick();
    // Stop must not abandon a still-live private action.
    assert(!boss_retire_destroyed_actor() && boss_active);
    assert(NiohResearchStop(nullptr) == ERROR_BUSY);
    // A replaced actor is retired without touching its former resource slots.
    put(player.data(), 0x50, boss_session.player_owner + 8);
    assert(NiohResearchStop(nullptr) == 0 && !boss_active);
    bindings(true);
    reset(); tick(); boss_inflight = 1;
    put(player.data(), 0x50, boss_session.player_owner + 8);
    assert(!boss_retire_destroyed_actor() && boss_active);
    boss_inflight = 0;
    assert(boss_retire_destroyed_actor() && !boss_active);
    std::puts("runtime session and recovery checks passed");
}
