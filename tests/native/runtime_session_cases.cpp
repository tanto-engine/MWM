// Runtime startup and retirement guards with owned memory; no game access.
#define RESEARCH_RUNTIME_SESSION
#define main inherited_frame_test_main
#include "frame_dispatch_cases.cpp"
#undef main
#include "airborne_fixture.h"

static RuntimeSessionConfig config() {
    // Build a complete seven-import runtime ABI fixture with this process's birth.
    // Use non-live pointer values and the real baseline/chain topology.
    // Startup validation can then reject malformed contracts without accessing a game.
    RuntimeSessionConfig result{};
    result.magic = RUNTIME_SESSION_MAGIC; result.version = RUNTIME_SESSION_VERSION;
    result.frost_milliseconds = 0;
    result.frost_speed = 8;
    memcpy(result.launch_profiles,boss_launch_profiles,sizeof(result.launch_profiles)); result.air_juggle_boost=2;
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
    auto shared_ordinary=incoming;
    shared_ordinary.frost_variants[1]=1; // Mid Frost, High native binding, one stance-neutral C64 import.
    shared_ordinary.skill_bindings[0]={1,4,1,0xCB7,3300,40,0x8000000594C0000ULL};
    assert(runtime_imports_valid(shared_ordinary));
    for (unsigned field=0;field<9;++field) {
        auto changed=incoming;changed.move_settings[0]={1.5f,65,18,35,0};
        if (field==0) {assert(runtime_imports_valid(changed));continue;}
        if (field==1) changed.move_settings[0].speed=std::numeric_limits<float>::quiet_NaN();
        if (field==2) changed.move_settings[0].speed=2.1f;
        if (field==3) changed.move_settings[0].pulse_percent=101;
        if (field==4) changed.move_settings[0].pulse_fill=0;
        if (field==5) changed.move_settings[0].pulse_hold=121;
        if (field==6) changed.move_settings[0].reserved=1;
        if (field==7) changed.move_settings[6]=changed.move_settings[0]; // Paired attacker keeps native timing.
        if (field==8) changed.controller_selection=5;
        assert(!runtime_imports_valid(changed));
    }
    auto aerial=incoming; aerial.import_count=20; aerial.hold_variant=20; aerial.hold_milliseconds=250;
    aerial.hold_camera_bank=0x960000; aerial.hold_stances=1; aerial.frost_variants[0]=13; aerial.frost_variants[1]=8;
    for (unsigned phase=0;phase<12;++phase) {
        const auto& source=airborne_sources[phase];const unsigned slot=phase+7;
        auto& move=aerial.imports[slot];move=incoming.imports[0];move.voice_count=0;memset(move.voices,0,sizeof(move.voices));
        move.descriptor=0x500000+source.key*0x100;move.payload=move.descriptor+0x20;move.clip=move.descriptor+0x40;move.timing_record=move.descriptor+0x60;
        move.key=source.key;move.motion=source.motion;move.flags=source.flags;
        move.recovery_frame=source.recovery;move.transition_count=uint16_t(source.count);move.next_variant=phase==1 ? 9 : -1;
        auto& adapter=aerial.adapters[slot];adapter={0x910000,0x920000,0x930000,0x940000,0x950000,0xA00000,0xC7A,2300,42,46,2};
        adapter.kind=phase==0 || phase==5 || phase==9 ? 2 : phase>=2 && phase<=4 ? 3 : 4;
        if (adapter.kind==3) {adapter.player_descriptor=0;adapter.player_key=0;adapter.player_motion=0;adapter.transition_count=0;adapter.recovery_frame=0;}
        if (phase>=5) {adapter.player_descriptor=0xA10000;adapter.player_key=0xCF5;adapter.player_motion=4300;adapter.transition_count=46;adapter.recovery_frame=38;}
        if (phase>=9) {adapter.player_descriptor=0xA20000;adapter.player_key=0xCB7;adapter.player_motion=3300;adapter.transition_count=40;adapter.recovery_frame=58;}
    }
    aerial.imports[19]=aerial.imports[7];aerial.adapters[19]=aerial.adapters[12];
    aerial.skill_bindings[0]={2,4,17,0,0,0,0};
    aerial.skill_bindings[1]={3,1,20,0,0,0,0};
    assert(runtime_imports_valid(aerial));
    for (unsigned field=0;field<2;++field) {
        auto changed=aerial;
        if (field==0) ++changed.adapters[12].transition_count;
        else ++changed.adapters[12].recovery_frame;
        assert(!runtime_imports_valid(changed));
    }
    auto isolated=aerial;isolated.import_count=21;
    isolated.imports[20]=isolated.imports[12];isolated.adapters[20]=isolated.adapters[12];
    auto& jump=isolated.adapters[20];jump.kind=5;jump.player_descriptor=0;jump.player_key=0;
    jump.player_motion=0;jump.transition_count=0;jump.recovery_frame=0;
    assert(runtime_imports_valid(isolated));
    isolated.adapters[20].player_key=0xCF5;assert(!runtime_imports_valid(isolated));
    auto native_window=aerial;native_window.frost_milliseconds=0;assert(runtime_imports_valid(native_window));
    for (unsigned band=0;band<2;++band) {
        auto invalid=aerial;invalid.launch_profiles[band].weight_scale=0;assert(!runtime_imports_valid(invalid));
        invalid=aerial;invalid.launch_profiles[band].vertical_impulse=21;assert(!runtime_imports_valid(invalid));
    }

    for (unsigned slot : {7u,8u,9u,12u,13u,14u,15u,16u,17u,18u,19u}) {
        auto invalid=aerial;invalid.imports[slot].flags^=1;
        assert(!runtime_imports_valid(invalid));
    }
    auto invalid_alias=aerial;invalid_alias.imports[19].descriptor+=8;
    assert(!runtime_imports_valid(invalid_alias));
    invalid_alias=aerial;invalid_alias.adapters[19]=aerial.adapters[7];
    assert(!runtime_imports_valid(invalid_alias));
    static_assert(RUNTIME_SESSION_VERSION==13 && sizeof(RuntimeSessionConfig)==12552
        && offsetof(RuntimeSessionConfig,imports)==328 && offsetof(RuntimeSessionConfig,adapters)==6472
        && offsetof(RuntimeSessionConfig,skill_bindings)==10568
        && offsetof(RuntimeSessionConfig,chord_reservations)==12416);
    auto chords=incoming;chords.chord_reservation_count=2;
    chords.chord_reservations[0]={0x8100,1,0}; // Low LB+Y.
    chords.chord_reservations[1]={0x2100,7,10}; // LB+B, then Y.
    assert(runtime_imports_valid(chords));
    chords.chord_reservations[1].mode=0;
    assert(runtime_imports_valid(chords));
    auto bad_chord=chords;bad_chord.chord_reservations[0].buttons=0x8000;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservations[0].buttons=0x8300;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservations[0].stances=8;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservations[1].mode=2;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservations[1].mode=12;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservations[1].buttons=0xC01;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservations[2].buttons=0x8100;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservation_count=33;assert(!runtime_imports_valid(bad_chord));
    bad_chord=chords;bad_chord.chord_reservation_reserved=1;assert(!runtime_imports_valid(bad_chord));
    auto moved=aerial;moved.frost_variants[1]=17;moved.frost_variants[2]=8;
    moved.skill_bindings[0]={2,2,17,0,0,0,0};
    for (unsigned slot : {7u,8u}) {
        auto& adapter=moved.adapters[slot];adapter.player_key=0xCB7;adapter.player_motion=3300;adapter.transition_count=40;adapter.recovery_frame=58;
    }
    for (unsigned slot : {16u,17u,18u}) {
        auto& adapter=moved.adapters[slot];adapter.player_key=0xC7A;adapter.player_motion=2300;adapter.transition_count=42;adapter.recovery_frame=46;
    }
    assert(runtime_imports_valid(moved));
    auto wrong_binding=moved;wrong_binding.skill_bindings[0].stances=4;
    assert(!runtime_imports_valid(wrong_binding));
    wrong_binding=moved;wrong_binding.skill_bindings[0].variant=18;
    assert(!runtime_imports_valid(wrong_binding));
    wrong_binding=moved;wrong_binding.skill_bindings[1].variant=17;
    assert(!runtime_imports_valid(wrong_binding));
    wrong_binding=moved;wrong_binding.skill_bindings[1].kind=0;
    assert(!runtime_imports_valid(wrong_binding));
    wrong_binding=moved;wrong_binding.hold_stances=0;
    assert(!runtime_imports_valid(wrong_binding));
    wrong_binding=moved;wrong_binding.skill_bindings[1].variant=1;
    assert(runtime_imports_valid(wrong_binding));
    auto frost=incoming;frost.import_count=10;frost.hold_variant=8;frost.hold_milliseconds=250;
    frost.frost_variants[2]=8;
    for (unsigned phase=0;phase<3;++phase) {
        frost.imports[phase+7]=aerial.imports[phase+16];frost.adapters[phase+7]=aerial.adapters[phase+16];
    }
    assert(runtime_imports_valid(frost));
    for (uint64_t slot : {9ULL,11ULL}) {
        auto wrong=frost;wrong.frost_variants[2]=slot;
        assert(!runtime_imports_valid(wrong));
    }
    auto wrong=frost;wrong.frost_variants[2]=0;wrong.frost_variants[0]=8;
    assert(!runtime_imports_valid(wrong));
    wrong=frost;wrong.hold_stances=8;
    assert(!runtime_imports_valid(wrong));
    for (uint64_t window : {99ULL,1501ULL}) {
        wrong=frost;wrong.frost_milliseconds=window;
        assert(!runtime_imports_valid(wrong));
    }
    for (uint64_t speed : {0ULL,9ULL}) {
        wrong=frost;wrong.frost_speed=speed;
        assert(!runtime_imports_valid(wrong));
    }
    wrong=frost;wrong.frost_speed=1;
    assert(!runtime_imports_valid(wrong));
    // Compile every slot, then exercise a successor chain crossing the former 32-bit mask.
    // A high-index cycle and a table beyond capacity must still be rejected.
    auto expanded=incoming;expanded.import_count=BOSS_IMPORT_LIMIT;
    for (unsigned i=7;i<BOSS_IMPORT_LIMIT;++i) {
        expanded.imports[i]=incoming.imports[0];auto& move=expanded.imports[i];
        move.key=0x100+i;move.motion=1500+i;
        move.next_variant=i+1<BOSS_IMPORT_LIMIT ? int(i+1) : -1;
        move.next_start=move.next_variant<0 ? 0 : 1;move.next_end=move.next_variant<0 ? 0 : 2;
    }
    assert(runtime_imports_valid(expanded));
    expanded.imports[BOSS_IMPORT_LIMIT-1].next_variant=33;
    expanded.imports[BOSS_IMPORT_LIMIT-1].next_end=2;
    assert(!runtime_imports_valid(expanded));
    expanded.import_count=BOSS_IMPORT_LIMIT+1;assert(!runtime_imports_valid(expanded));
    auto ordinary=incoming;ordinary.hold_variant=2;ordinary.hold_milliseconds=250;ordinary.hold_stances=7;
    for (unsigned i=0;i<3;++i) ordinary.skill_bindings[i]={3,1u<<i,2,0,0,0,0};
    assert(runtime_imports_valid(ordinary));
    auto binding=incoming;binding.skill_bindings[0]={1,7,1,0xFAA,5090,21,0x40017C00000ULL};
    assert(runtime_imports_valid(binding));
    for (unsigned failure=0;failure<11;++failure) {
        auto invalid_binding=binding;auto& row=invalid_binding.skill_bindings[0];
        if (failure==0) row.kind=4;
        if (failure==1) row.stances=0;
        if (failure==2) row.stances=8;
        if (failure==3) row.variant=0;
        if (failure==4) row.variant=8;
        if (failure==5) row.key=0xFAB;
        if (failure==6) row.motion=5091;
        if (failure==7) row.transition_count=22;
        if (failure==8) row.flags^=1;
        if (failure==9) invalid_binding.skill_bindings[1]=row;
        if (failure==10) row.kind=0;
        assert(!runtime_imports_valid(invalid_binding));
    }
    binding.skill_bindings[0]={2,7,2,0,0,0,0};assert(runtime_imports_valid(binding));
    binding.skill_bindings[0].key=0xFAA;assert(!runtime_imports_valid(binding));
    auto grapple_config=incoming; grapple_config.native_bindings=1;
    assert(runtime_imports_valid(grapple_config));
    grapple_config.imports[6].motion=1312;
    assert(!runtime_imports_valid(grapple_config));
    assert(load_runtime_session(nullptr) == ERROR_INVALID_DATA);
    auto invalid = incoming; invalid.pid += 1;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    invalid = incoming; invalid.creation_filetime += 1;
    assert(load_runtime_session(&invalid) == ERROR_INVALID_DATA && !runtime_session_configured);
    invalid = incoming; invalid.native_bindings = 8;
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
    invalid=incoming;invalid.skill_bindings[0]={1,7,1,0xFAA,5090,21,0x40017C00000ULL};
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.frost_milliseconds=751;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.hold_stances=1;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
    invalid=incoming;invalid.frost_speed=7;
    assert(load_runtime_session(&invalid)==ERROR_INVALID_DATA);
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
