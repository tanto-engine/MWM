#define RESEARCH_RUNTIME_SESSION
// Owned buffers and direct callbacks only. MinHook is stubbed; no code patches.
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <limits>
#define RESEARCH_REPEAT
#define RESEARCH_BOSS
#define RESEARCH_DISPATCH
#include "../../runtime/native/observer.cpp"
#include "import_fixture.h"

static unsigned enables, disables, creates;
static MH_STATUS create_result = MH_OK, frame_enable_result = MH_OK, voice_enable_result = MH_OK;
static bool fail_voice_creation;
extern "C" MH_STATUS WINAPI MH_Initialize() {
    // Stub hook-library startup inside the disposable test process.
    // Return the fixture's startup result without installing a hook manager.
    // Native callback guards can then be tested without patching game code.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_Uninitialize() {
    // Stub hook-library cleanup for direct callback tests.
    // Expose the fixture's cleanup behavior without releasing a real hook library.
    // Failure paths must preserve owned mappings once callbacks could retain them.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_CreateHook(void* target, void*, void**) {
    // Control hook creation outcomes without modifying executable instructions.
    // Return the fixture's requested success or failure from this link-time stub.
    // The harness exercises rollback and ownership independently of MinHook internals.
    ++creates; return target == voice_target && fail_voice_creation ? MH_ERROR_UNSUPPORTED_FUNCTION : create_result;
}
extern "C" MH_STATUS WINAPI MH_EnableHook(void* target) {
    // Control hook-enable outcomes within the owned-memory fixture.
    // Use the local stub instead of patching the supplied target address.
    // Partial startup must be testable without any running game or real trampoline.
    ++enables;
    return target == frame_target ? frame_enable_result : target == voice_target ? voice_enable_result : MH_OK;
}
extern "C" MH_STATUS WINAPI MH_DisableHook(void*) {
    // Model hook disabling while leaving this process's code unchanged.
    // Return the fixture result and preserve its local call accounting where needed.
    // Stop and rollback tests can inspect cleanup without racing an actual hook.
    ++disables; return MH_OK;
}

alignas(8) static std::array<uint8_t,0x800> player{};
alignas(8) static std::array<uint8_t,0x800> owner{};
alignas(8) static std::array<uint8_t,0x478> source{}, source_owner{};
alignas(8) static std::array<uint8_t,0x100> motion{}, timing{}, source_motion{}, source_timing{};
alignas(8) static std::array<uint8_t,0x138> bank{}, player_bank{};
alignas(8) static std::array<uint8_t,0xD0> neutral{}, desired{};
alignas(8) static std::array<uint8_t,0xB0> neutral_payload{}, payload{};
alignas(8) static std::array<uint8_t,0xD0> pulse_descriptor{};
static std::array<std::array<uint8_t,0x30>,28> source_rows{};
static std::array<std::array<uint8_t,0x30>,3> pulse_rows{};
static std::array<uint8_t,0x30> dodge_row{};
static std::array<uint64_t,28> source_pointers{};
static std::array<uint64_t,49> pulse_pointers{};
static uint64_t entries[1];
static DispatchMapping own_dispatch;
static TraceMapping own_trace;
static DispatchCommand command;
static int64_t frequency;
static unsigned action_calls, frame_calls, checks;
static bool stop_inside_frame;
static float frame_delta = 0.25f;
static unsigned voice_calls, william_calls;
static bool stop_inside_voice;
alignas(8) static std::array<uint8_t,0x100> voice_state{};
alignas(8) static std::array<uint8_t,0x1000> voice_record{};
static constexpr DWORD INCOMING = 0x10203040, FRAME_ERROR = 0x33445566, ACTION_ERROR = 0x77889900;

template<class T> static void put(void* base, size_t at, T value) {
    // Write captured native-layout fields into memory owned by the harness.
    // Use memcpy so byte offsets do not create unaligned typed accesses.
    // The fixture must exercise real ABI offsets without requiring live game memory.
    memcpy(static_cast<uint8_t*>(base) + at, &value, sizeof(value));
}
static uint64_t address(const void* value) {
    // Represent an owned fixture pointer in the runtime's integer-address ABI.
    // Preserve the pointer value without allocating or extending its lifetime.
    // Transient test addresses must never become permanent catalogue identities.
    return reinterpret_cast<uint64_t>(value);
}
static void bindings(bool borrowed) {
    // Verify every adapted motion and timing slot against its expected owner.
    // Read all four fields and compare with either original or borrowed resources.
    // A partial restore or mixed resource set must fail the test immediately.
    for (unsigned i = 0; i != 4; ++i) {
        uint64_t value = 0; assert(copy_field(boss_slot(i),value));
        assert(value == (borrowed ? boss_borrowed(i) : boss_session.originals[i]));
    }
}
static bool fake_action(void* actor, uint32_t key, void* context) {
    // Simulate the frame-generated setter and ordinary native exit.
    // Check the private context, resource bindings and incoming native error.
    // Frame scheduling must not accidentally forward a key-zero call after rejection.
    ++action_calls; assert(actor == player.data());
    if (key == 0xC64) {
        assert(GetLastError() == FRAME_ERROR && context);
        auto* banks = static_cast<uint64_t*>(context);
        assert(!banks[0] && !banks[2] && banks[1] == address(&boss_private_actions[0].bank));
        assert(boss_private_actions[0].payload[0x0b] == 4);
        bindings(true); put(actor,0x58,boss_private_descriptor_address());
    } else {
        assert(context == nullptr); bindings(false); put(actor,0x58,address(neutral.data()));
    }
    SetLastError(ACTION_ERROR); return true;
}
static float fake_frame(void* actor, float delta) {
    // Provide an owned native-frame callback with controllable time advancement.
    // Return the configured delta and exercise Stop while a callback is entered.
    // Lifecycle tests need frozen frames without suspending recovery or accessing the game.
    ++frame_calls; assert(actor && delta == 0.25f && GetLastError() == INCOMING);
    if (stop_inside_frame) assert(NiohResearchStop(nullptr) == ERROR_BUSY);
    SetLastError(FRAME_ERROR); return frame_delta;
}
static float native_clock_frame(void* actor, float delta) {
    // Reproduce the native clock fields consumed by startup acceleration.
    // Set the speed and delta in the owned actor before returning its native interval.
    // Windup checks must verify shared motion/timing clock behavior without seeking frames.
    assert(actor == player.data() && GetLastError() == INCOMING);
    put(actor,0x6a8,1.0f); put(actor,0x24,delta);
    SetLastError(FRAME_ERROR); return delta;
}
static void fake_voice(void* state, void* record, void* event, int32_t bank_override) {
    // Inspect the original audio handler arguments after scoped voice adaptation.
    // Distinguish the retained William row from untouched native timing records.
    // Replacing a voice must preserve ownership, LastError and callback lifetime guards.
    ++voice_calls;
    assert(state==voice_state.data());
    if (record==&william_attack_voice) {
        ++william_calls;
        assert(event==william_attack_voice.event);
        assert(william_attack_voice.header[1]==1 && william_attack_voice.header[2]==0x24
            && william_attack_voice.header[4]==0x30 && william_attack_voice.event[1]==10
            && william_attack_voice.event[2]==0 && william_attack_voice.sound[7]==0x97933946
            && william_attack_voice.sound[12]==80);
    } else {
        assert(record==voice_record.data() && event==voice_record.data()+0x24);
    }
    assert(bank_override==-1234 && GetLastError()==INCOMING && boss_inflight==1);
    if (stop_inside_voice) assert(NiohResearchStop(nullptr)==ERROR_BUSY);
    SetLastError(ACTION_ERROR);
}
static void publish(uint64_t sequence = 1) {
    // Commit a prepared command into the harness's shared mapping.
    // Publish the fixture's sequence markers and actor/action fields together.
    // Each failure case must mutate the intended guard without inheriting a torn command.
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    command.edge_qpc = command.heartbeat_qpc = now.QuadPart;
    command.expires_qpc = now.QuadPart + frequency;
    command.chord_sequence = sequence;
    command.reserved[2] = dispatch->control.reserved0 >> 16;
    command.sequence_begin = command.sequence_end = 1;
    memcpy(&dispatch->command,&command,sizeof(command));
}
static void state(uint32_t key, int32_t motion_key, int8_t stance) {
    // Build an owned current-action descriptor for eligibility tests.
    // Set its exact key, motion and stance in the native-shaped payload.
    // Key collisions must not make an unrelated state appear eligible for dispatch.
    put(neutral.data(),0,key); neutral[0x40]=1;
    put(neutral.data(),0x20,address(neutral_payload.data()));
    put(neutral_payload.data(),0x20,motion_key); put(neutral_payload.data(),0x0b,stance);
}
static void reset() {
    // Rebuild valid owned actor, resource and command state between cases.
    // Populate the researched native offsets and reset the callback control fields.
    // Prior failures must not leak consumed gestures or borrowed slots into later checks.
    own_dispatch = {}; own_trace = {}; dispatch=&own_dispatch; trace=&own_trace;
    player.fill(0); owner.fill(0); source.fill(0); source_owner.fill(0);
    motion.fill(0); timing.fill(0); source_motion.fill(0); source_timing.fill(0);
    bank.fill(0); player_bank.fill(0); neutral.fill(0); desired.fill(0); payload.fill(0);
    boss_session = {}; boss_private_actions[0] = {}; boss_private_actions[1] = {}; boss_active = boss_inflight = 0;
    boss_adapters[0]={};boss_adapters[1]={};
    for (auto& part : boss_hidden_weapons) part={};
    boss_session.player=address(player.data()); boss_session.player_owner=address(owner.data());
    boss_session.source_action_resource=address(source.data()); boss_session.source_timing_resource=address(source_owner.data());
    boss_session.vtable=0xabcdef; boss_session.source_bank=address(bank.data());
    boss_session.source_descriptor=address(desired.data()); boss_session.source_payload=address(payload.data());
    boss_session.player_motion=address(motion.data()); boss_session.player_timing=address(timing.data());
    const auto module=address(GetModuleHandleW(nullptr));
    put(source.data(),0,module+0x13C7970); put(source.data(),0x468,boss_session.source_bank);
    put(source_owner.data(),0,module+0x12C5408); put(source_owner.data(),0x468,uint64_t(0x20002));
    put(source_motion.data(),0,module+0x13C8FA0);

    boss_session.source_motion_bank=address(source_motion.data()); boss_session.source_timing_wrapper=0x20002;
    for (unsigned i=0;i!=4;++i) {
        boss_session.originals[i]=0x10001+i;
        put(reinterpret_cast<void*>(boss_slot(i)),0,boss_session.originals[i]);
    }
    put(player.data(),0,boss_session.vtable);
    put(player.data(),0x50,boss_session.player_owner);
    put(player.data(),0x58,address(neutral.data())); put(player.data(),0x70,address(player_bank.data()));
    put(owner.data(),0x38,boss_session.player_motion); put(owner.data(),0x68,boss_session.player_timing);



    put(desired.data(),0,uint32_t(0xC64)); desired[0x40]=1; put(desired.data(),0x20,address(payload.data()));
    put(payload.data(),0x20,int32_t(1220)); put(payload.data(),0x34,int32_t(-1)); payload[0x0b]=1;
    put(payload.data(),0x18,uint64_t(0x184C0000));
    put(payload.data(),0x16,int16_t(15)); put(payload.data(),0x24,int16_t(65));
    for (unsigned i=0;i!=28;++i) {
        source_rows[i].fill(uint8_t(i)); source_pointers[i]=address(source_rows[i].data());
    }
    put(desired.data(),0x78,address(source_pointers.data()));
    put(desired.data(),0x80,uint16_t(0)); put(desired.data(),0x82,uint16_t(28));
    pulse_descriptor.fill(0); pulse_pointers.fill(0);
    memcpy(dodge_row.data(),native_dodge_row,0x30);
    pulse_pointers[48]=address(dodge_row.data());
    fixture_shortcut_exits(pulse_pointers.data());
    for (unsigned i=0;i!=3;++i) {
        memcpy(pulse_rows[i].data(),boss_pulse_templates[i],0x30);
        pulse_pointers[21+i]=address(pulse_rows[i].data());
    }
    put(pulse_descriptor.data(),0,uint32_t(0xCF0)); pulse_descriptor[0x40]=1;
    put(pulse_descriptor.data(),0x78,address(pulse_pointers.data()));
    put(pulse_descriptor.data(),0x82,uint16_t(49));
    boss_session.player_pulse_descriptor=address(pulse_descriptor.data());
    entries[0]=address(desired.data()); put(bank.data(),0x128,address(entries)); put(bank.data(),0x130,uint32_t(1));
    fixture_imports();
    for (auto& chord : boss_chord_reservations) chord={};
    boss_chord_reservation_count=0;
    state(0,0,3);
    dispatch->control.qpc_frequency=frequency; trace->header.qpc_frequency=frequency;
    input_rescan=0; begin_dispatch(); trace->header.enabled=1;
    command={}; command.player=boss_session.player; command.owner=boss_session.player_owner;
    command.vtable=boss_session.vtable; command.banks[0]=address(player_bank.data());
    command.expected_descriptor=boss_session.source_descriptor; command.expected_payload=boss_session.source_payload;
    command.desired_key=0xC64; command.expected_motion=1220; command.generation=dispatch->control.generation;
    command.held=1; publish();
    publish_player_context(0.25f);
    command.armed=1; publish();
    original_action=fake_action; original_frame=fake_frame; original_voice=fake_voice;
    hook_created=frame_hook_created=voice_hook_created=true; hook_target=reinterpret_cast<void*>(0x12340000);
    frame_target=reinterpret_cast<void*>(0x12350000);
    voice_target=reinterpret_cast<void*>(0x12360000);
    action_calls=frame_calls=0; stop_inside_frame=false; frame_delta=0.25f;
    voice_calls=william_calls=0; stop_inside_voice=false;
}
static void tick(void* actor=player.data()) {
    // Run one player-frame wrapper against controlled owned state.
    // Assert effective delta, native LastError and complete callback-scope release.
    // Every lifecycle scenario must preserve the native frame contract.
    SetLastError(INCOMING); float result=observed_frame(actor,0.25f);
    uint32_t bits, expected; memcpy(&bits,&result,sizeof(bits)); memcpy(&expected,&frame_delta,sizeof(expected));
    assert(bits==expected && GetLastError()==FRAME_ERROR && boss_inflight==0); ++checks;
}
static void exit_move() {
    // Drive an ordinary native transition away from the imported fixture.
    // Assert the action exits and all borrowed resource fields return to originals.
    // Later gestures must start only after actual native recovery has completed.
    SetLastError(INCOMING); assert(observed_action(player.data(),3000,nullptr));
    assert(!boss_active && GetLastError()==ACTION_ERROR); bindings(false);
}

static void handgun_visibility_cases() {
    // Reproduce the visible sword through owned weapon/model buffers, including nonzero adjacent bytes.
    // Verify the same restoration path used before native exits, disabling, and equipment changes.
    // A pre-hidden model or a replaced actor must never be unhidden by this action's cleanup.
    reset();
    alignas(8) std::array<uint8_t,0xA00> equipment{};
    alignas(8) std::array<uint8_t,0x30> weapon{}, sheath{}, model{}, sheath_model{};
    put(owner.data(),0x240,address(equipment.data())); equipment[0x9CC]=1;
    put(owner.data(),0x500,address(weapon.data())); put(owner.data(),0x560,address(sheath.data()));
    put(weapon.data(),4,uint16_t(3)); put(weapon.data(),6,uint16_t(1));
    put(sheath.data(),4,uint16_t(3)); put(sheath.data(),6,uint16_t(1));
    put(weapon.data(),0x18,address(model.data())); put(sheath.data(),0x18,address(sheath_model.data()));
    put(model.data(),0,address(weapon.data())); put(sheath_model.data(),0,address(sheath.data()));
    model[0x18]=sheath_model[0x18]=0xA5; sheath_model[0x0A]=1;
    boss_active=1;boss_active_player=address(player.data());boss_active_owner=address(owner.data());boss_active_slot=0;
    boss_imports[0].key=0xC6A;boss_imports[0].motion=1130;boss_imports[0].flags=0x40019480000ULL;
    boss_imports[0].transition_count=9;boss_imports[0].recovery_frame=-1;boss_adapters[0].kind=2;
    put(player.data(),0x58,boss_private_descriptor_address(0));
    boss_update_weapon_visibility();assert(model[0x0A]==1 && sheath_model[0x0A]==1);
    assert(equipment[0x9CC]==1); // Hiding must not change which weapon is equipped.
    assert(boss_set_bindings(false));assert(model[0x0A]==0 && sheath_model[0x0A]==1);
    boss_update_weapon_visibility();assert(model[0x0A]==1);
    // Moving the weapon to the second equipment slot retains ownership for restoration.
    put(owner.data(),0x500,uint64_t(0));put(owner.data(),0x680,address(weapon.data()));
    dispatch->control.enabled=0;boss_update_weapon_visibility();assert(model[0x0A]==0);
    dispatch->control.enabled=1;equipment[0x9CC]=0;boss_update_weapon_visibility();assert(model[0x0A]==1);
    put(player.data(),0x50,uint64_t(0));boss_update_weapon_visibility();assert(model[0x0A]==1);
    for (const auto& part : boss_hidden_weapons) assert(!part.model);
    ++checks;
}

int main() {
    // Exercise frame scheduling, lifecycle suspension, windup and voice adaptation.
    // Drive real wrappers using owned memory and configurable native callback outcomes.
    // Gameplay acceptance still requires live evidence beyond these deterministic invariants.
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); frequency=f.QuadPart;
    handgun_visibility_cases();
    reset(); boss_frost_variants[1]=1; // Mid Frost shares ordinary C64 with a High custom input.
    put(player.data(),0x470,uint32_t(0)); publish(); tick();
    assert(boss_active && boss_private_actions[0].payload[0x0B]==4); ++checks;
    boss_frost_variants[1]=0;
    reset();
    dispatch->control.last_reason=CurrentNotAllowed;
    SetLastError(INCOMING); assert(observed_action(player.data(),25,nullptr));
    assert(dispatch->control.dispatch_count==0 && action_calls==1); ++checks;
    assert(dispatch->control.last_reason==CurrentNotAllowed);
    assert((trace->records[0].valid_fields>>8 & 255)==IneligibleRequest); ++checks;
    assert(trace->records[0].context==0 && !(trace->records[0].valid_fields & (1u<<18))); ++checks;
    tick(); assert(frame_calls==1 && action_calls==2 && boss_active && dispatch->control.dispatch_count==1);
    assert(boss_private_actions[0].transition_count==36);
    for (unsigned i=0;i!=3;++i) {
        auto expected=pulse_rows[i]; put(expected.data(),0x20,int16_t(54));
        assert(!memcmp(boss_private_actions[0].transition_bodies[28+i],expected.data(),0x30));
        assert(!memcmp(pulse_rows[i].data(),boss_pulse_templates[i],0x30));
    }
    auto expected_dodge=dodge_row; put(expected_dodge.data(),0x20,int16_t(54));
    assert(!memcmp(boss_private_actions[0].transition_bodies[31],expected_dodge.data(),0x30));
    ++checks;
    assert((trace->records[1].valid_fields & ((1u<<18)|TRACE_FINAL_MATCH)) == ((1u<<18)|TRACE_FINAL_MATCH)); ++checks;
    assert(trace->records[1].context==uint64_t(command.edge_qpc)
        && trace->records[1].qpc>=command.edge_qpc); ++checks;
    auto calls=action_calls;
    for (uint32_t key : {24u,25u}) {
        SetLastError(INCOMING); assert(!observed_action(player.data(),key,nullptr));
        assert(GetLastError()==INCOMING && action_calls==calls && boss_active); bindings(true); ++checks;
    }
    tick(); assert(action_calls==calls); exit_move(); tick(); assert(dispatch->control.dispatch_count==1); ++checks;
    publish(2); tick(); assert(dispatch->control.dispatch_count==2 && boss_active); exit_move(); ++checks;

    // Sequence policy checks stance without reserving either original button.
    reset(); command.reserved[0]=1|(1ULL<<35)|(1ULL<<34); publish(); tick();
    assert(boss_active && dispatch->control.dispatch_count==1); exit_move(); ++checks;
    reset(); command.reserved[0]=1|(1ULL<<35)|(1ULL<<32); publish(); tick();
    assert(!boss_active && dispatch->control.last_reason==IneligibleRequest); ++checks;
    reset(); command.reserved[0]=1|(1ULL<<35)|(1ULL<<34)|(0x100ULL<<16); publish(); tick();
    assert(!boss_active && dispatch->control.last_reason==InvalidConfig); ++checks;

    // Attack-context intents use one exact native sword opener and its recovery edge.
    for (const auto& attack : {std::array<int,5>{0xCF5,4300,2,36,2},
                               {0xC7A,2300,1,36,1}, {0xCF0,4100,2,37,2},
                               {0xCB3,3100,0,37,0}}) {
        reset(); state(attack[0],attack[1],int8_t(attack[2]));
        put(neutral_payload.data(),0x18,uint64_t(0x8000000594C0000ULL));
        put(neutral_payload.data(),0x24,int16_t(30)); put(player.data(),0x28,30.0f);
        put(player.data(),0x470,uint32_t(attack[4]));
        command.reserved[0]=1ULL|(1ULL<<attack[3])|(1ULL<<(34-attack[4]));
        assert(valid_chord_policy(command.reserved[0]));
        assert(validate_actor(command,player.data())==Accepted);
        put(player.data(),0x28,29.0f);
        assert(validate_actor(command,player.data())==CurrentNotAllowed);
        put(player.data(),0x28,30.0f);put(neutral_payload.data(),0x18,uint64_t(0));
        assert(validate_actor(command,player.data())==CurrentNotAllowed);
        put(neutral_payload.data(),0x18,uint64_t(0x8000000594C0000ULL));
        command.held=0; publish();
        boss_active=1;DispatchCommand blocked{};
        assert(choose_dispatch(player.data(),0,nullptr,blocked,true)==BossPreviewActive);
        boss_active=0;tick();
        assert(boss_active && dispatch->control.dispatch_count==1); exit_move(); ++checks;
    }
    assert(!valid_chord_policy(1ULL|(1ULL<<36)|(1ULL<<37)|(1ULL<<32)));
    assert(valid_chord_policy(1ULL|(1ULL<<35)|(1ULL<<32)|(0xA100ULL<<16)));
    assert(valid_chord_policy(1ULL|(1ULL<<35)|(1ULL<<32)|(0x8100ULL<<16)));
    assert(!valid_chord_policy(1ULL|(1ULL<<35)|(1ULL<<32)|(0x100ULL<<16)));

    reset(); command.held=0; publish(); tick(); assert(!action_calls && dispatch->control.last_reason==Released); ++checks;
    command.reserved[0]=1; publish(); tick(); assert(action_calls==1 && boss_active); exit_move(); ++checks;
    reset(); command.armed=0; publish(); tick(); assert(!action_calls); ++checks;
    reset(); command.heartbeat_qpc-=frequency; memcpy(&dispatch->command,&command,sizeof(command));
    tick(); assert(!action_calls); ++checks;
    reset(); command.expires_qpc=command.heartbeat_qpc-1; memcpy(&dispatch->command,&command,sizeof(command));
    tick(); assert(!action_calls); ++checks;
    reset(); tick(source.data()); assert(!action_calls && frame_calls==1); ++checks;

    // Startup needs an acknowledged native epoch, even with matching banks.
    reset(); dispatch->control.reserved0=0; publish(); tick();
    assert(!action_calls && dispatch->control.last_reason==ContextChanged
        && dispatch->control.reserved0==((1u<<16)|47)); ++checks;
    tick(); assert(!action_calls && dispatch->control.reserved0==((1u<<16)|47)); ++checks;
    publish(); tick(); assert(boss_active); exit_move(); ++checks;

    // A frozen/invalid native clock cannot dispatch or retain a pre-freeze edge.
    for (float stopped_delta : {0.0f,-0.0f,-0.25f,std::numeric_limits<float>::infinity(),
                               std::numeric_limits<float>::quiet_NaN()}) {
        reset(); frame_delta=stopped_delta; tick();
        assert(!action_calls && !player_context_ready(dispatch->control.reserved0)
            && !(dispatch->control.reserved0 & ContextAdvancing)
            && (dispatch->control.reserved0>>16)==2); ++checks;
        frame_delta=0.25f; tick();
        assert(!action_calls && dispatch->control.last_reason==ContextChanged
            && (dispatch->control.reserved0>>16)==3); ++checks;
        publish(); tick(); assert(boss_active); exit_move(); ++checks;
    }

    // Both bank transitions happen before the publisher runs again.
    reset(); const auto before_bank_suspend=dispatch->command;
    put(player.data(),0x70,address(bank.data())); tick();
    assert(!action_calls && !(dispatch->control.reserved0 & ContextBanks)
        && (dispatch->control.reserved0>>16)==2); ++checks;
    tick(); assert((dispatch->control.reserved0>>16)==2); ++checks;
    put(player.data(),0x70,address(player_bank.data())); tick();
    assert(!action_calls && dispatch->control.last_reason==ContextChanged
        && !memcmp(&before_bank_suspend,&dispatch->command,sizeof(before_bank_suspend))
        && dispatch->control.enabled && trace->header.enabled); ++checks;
    publish(); tick(); assert(boss_active); exit_move(); ++checks;

    reset(); put(owner.data(),0x38,boss_session.player_motion+8); tick();
    assert(!action_calls && !(dispatch->control.reserved0 & ContextPlayer)); ++checks;
    put(owner.data(),0x38,boss_session.player_motion); tick();
    assert(!action_calls && dispatch->control.last_reason==ContextChanged); ++checks;

    // An unfamiliar resource slot remains untouched throughout suspension.
    reset(); put(reinterpret_cast<void*>(boss_slot(2)),0,uint64_t(0x90000)); tick();
    uint64_t untouched=0; assert(copy_field(boss_slot(2),untouched) && untouched==0x90000
        && !action_calls && !(dispatch->control.reserved0 & ContextOriginalSlots)); ++checks;
    put(reinterpret_cast<void*>(boss_slot(2)),0,boss_session.originals[2]); tick();
    assert(!action_calls && dispatch->control.last_reason==ContextChanged); ++checks;

    // Recovery is independent of the native clock and command suspension.
    reset(); tick(); publish(2); const auto calls_before_recovery=action_calls;
    put(player.data(),0x58,address(neutral.data())); frame_delta=0.0f; tick();
    bindings(false);
    assert(!boss_active && action_calls==calls_before_recovery && dispatch->control.enabled
        && trace->header.enabled && !player_context_ready(dispatch->control.reserved0)); ++checks;
    frame_delta=0.25f; tick(); assert(action_calls==calls_before_recovery); ++checks;
    publish(2); tick(); assert(boss_active && dispatch->control.dispatch_count==2); exit_move(); ++checks;

    // Ordinary attacks change eligibility, not lifecycle readiness or its epoch.
    reset(); state(3172,2033,4); tick();
    assert(!action_calls && !(dispatch->control.reserved0 & ContextNeutralAction)
        && player_context_ready(dispatch->control.reserved0) && (dispatch->control.reserved0>>16)==1); ++checks;
    state(0,0,3); tick(); assert(boss_active && (dispatch->control.reserved0>>16)==1); exit_move(); ++checks;

    reset(); dispatch->control.reserved0=(UINT16_MAX<<16)|47;
    frame_delta=0.0f; tick(); assert((dispatch->control.reserved0>>16)==0); ++checks;
    const auto suspended_context=dispatch->control.reserved0;
    tick(source.data()); assert(dispatch->control.reserved0==suspended_context); ++checks;

    for (auto row : {std::array<int,3>{3154,2000,1}, {3214,3000,0}, {3276,4000,2},
                     {3158,2005,3}, {3160,2007,2}, {3161,2008,4}, {3181,2061,1}, {3242,2061,4}, {3303,2061,2}}) {
        reset(); state(row[0],row[1],row[2]); tick(); assert(boss_active); exit_move(); ++checks;
    }
    for (int first_key : {3186,3247,3308}) for (int direction=0;direction!=4;++direction) {
        reset(); state(first_key+direction,1160+direction,4);
        tick(); assert(boss_active && dispatch->control.dispatch_count==1); exit_move(); ++checks;
    }
    for (auto row : {std::array<int,3>{3154,2001,1}, {3154,2000,2}, {3172,2033,4},
                     {3312,4100,2}, {16,50,-1}, {24,-1,4}, {3308,1161,4}, {3308,1160,2}}) {
        reset(); state(row[0],row[1],row[2]); tick(); assert(!action_calls && !boss_active); ++checks;
    }
    reset(); DispatchCommand latest=command;
    assert(same_dispatch_intent(latest,command));
    for (unsigned field=0;field!=3;++field) {
        latest=command; latest.reserved[field]^=1;
        assert(!same_dispatch_intent(latest,command)); ++checks;
    }
    latest=command; latest.heartbeat_qpc+=1; latest.held=0; latest.armed=0;
    assert(same_dispatch_intent(latest,command));
    assert(command_status(latest,latest.heartbeat_qpc,frequency,latest.generation,0,false)==NotArmed); ++checks;

    reset(); stop_inside_frame=true; auto stopped=disables; tick();
    assert(!action_calls && !dispatch->control.enabled && disables==stopped); ++checks;
    stop_inside_frame=false; assert(NiohResearchStop(nullptr)==0 && disables==stopped+3);
    assert(original_frame==fake_frame && original_voice==fake_voice && original_action==fake_action && trace==&own_trace); ++checks;
    reset(); frame_hook_created=false; create_result=MH_ERROR_UNSUPPORTED_FUNCTION;
    assert(enable_repeat_hooks()==MH_ERROR_UNSUPPORTED_FUNCTION && !frame_hook_created); ++checks;
    create_result=MH_OK; frame_enable_result=MH_ERROR_MEMORY_PROTECT; stopped=disables;
    assert(enable_repeat_hooks()==MH_ERROR_MEMORY_PROTECT && frame_hook_created && disables==stopped+3); ++checks;
    frame_enable_result=MH_OK; auto previous_creates=creates;
    assert(enable_repeat_hooks()==MH_OK && creates==previous_creates); ++checks;
    voice_enable_result=MH_ERROR_MEMORY_PROTECT; stopped=disables;
    assert(enable_repeat_hooks()==MH_ERROR_MEMORY_PROTECT && disables==stopped+3);
    assert(!dispatch->control.enabled && !trace->header.enabled); ++checks;
    voice_enable_result=MH_OK; voice_hook_created=false; fail_voice_creation=true; stopped=disables;
    assert(enable_repeat_hooks()==MH_ERROR_UNSUPPORTED_FUNCTION && disables==stopped+2 && !voice_hook_created); ++checks;
    fail_voice_creation=false; assert(enable_repeat_hooks()==MH_OK && voice_hook_created); ++checks;

    uint8_t prologue[]={0x40,0x53,0x48,0x83,0xec,0x20,0xf3,0x0f,0x11,0x89,0xa4,0x06,0,0,
        0x48,0x8b,0xd9,0xe8,0x5a,0x8e,0x03,0,0x4c,0x8b,0x43,0x50,0xf3,0x0f,0x11,0x83,0xa8,0x06};
    assert(frame_prologue_matches(prologue)); prologue[6]^=1;
    assert(!frame_prologue_matches(prologue) && !frame_prologue_matches(reinterpret_cast<void*>(1))); ++checks;
    uint8_t audio_prologue[]={0x44,0x89,0x4c,0x24,0x20,0x55,0x53,0x57,0x41,0x57,
        0x48,0x8d,0xac,0x24,0x68,0xff,0xff,0xff,0x48,0x81,0xec,0x98,0x01,0,0,
        0x49,0x63,0x40,0x08,0x41,0x8b,0xd9};
    assert(voice_prologue_matches(audio_prologue)); audio_prologue[0]^=1;
    assert(!voice_prologue_matches(audio_prologue) && !voice_prologue_matches(reinterpret_cast<void*>(1))); ++checks;

    reset(); tick(); voice_state.fill(0); voice_record.fill(0);
    boss_session.source_timing_record=address(voice_record.data()); fixture_imports();
    put(voice_state.data(),8,boss_session.player_owner); put(voice_state.data(),0x20,boss_session.source_timing_record);
    put(voice_record.data(),4,uint32_t(1)); put(voice_record.data(),8,uint32_t(0x24));
    put(voice_record.data(),0x10,uint32_t(0x80)); put(voice_record.data(),0x24,uint32_t(30));
    put(voice_record.data(),0x28,uint32_t(10)); put(voice_record.data(),0x2c,uint32_t(11));
    put(voice_record.data(),0x80+11*0x4c+0x1c,uint32_t(0x0E077D36));
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(voice_calls==1 && william_calls==1 && GetLastError()==ACTION_ERROR
        && dispatch->control.reserved1==1 && boss_inflight==0); ++checks;
    put(voice_record.data(),0x80+11*0x4c+0x1c,uint32_t(0x12345678));
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(voice_calls==2 && william_calls==1 && GetLastError()==ACTION_ERROR
        && dispatch->control.reserved1==1 && boss_inflight==0); ++checks;
    boss_private_actions[1].ready=true;
    boss_session.charge_timing_record=address(voice_record.data()); fixture_imports();
    put(player.data(),0x58,boss_private_descriptor_address(1));
    put(voice_record.data(),0x24,uint32_t(46)); put(voice_record.data(),0x2c,uint32_t(16));
    put(voice_record.data(),0x80+16*0x4c+0x1c,uint32_t(0xF519B456));
    const auto imported_voice=voice_record;
    const auto player_voice_state=voice_state;
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(voice_calls==3 && william_calls==2 && dispatch->control.reserved1==2 && boss_inflight==0);
    assert(voice_record==imported_voice && voice_state==player_voice_state); ++checks;
    put(voice_state.data(),8,boss_session.player_owner+8);
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(voice_calls==4 && william_calls==2 && dispatch->control.reserved1==2); ++checks;
    put(voice_state.data(),8,boss_session.player_owner);
    put(player.data(),0x58,boss_private_descriptor_address(0));
    exit_move(); stop_inside_voice=true; stopped=disables;
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(GetLastError()==ACTION_ERROR && disables==stopped && !dispatch->control.enabled && boss_inflight==0); ++checks;

    reset(); tick(); original_frame=native_clock_frame;
    boss_session.source_clip=0x23450000; boss_imports[0].clip=boss_session.source_clip;
    put(motion.data(),0x58,boss_session.source_clip);
    auto rush_tick = [](float frame, float expected) {
        // Probe the startup clock at a specific animation boundary.
        // Run the real frame wrapper and compare both native clock fields.
        // Faster startup must preserve shared timing rather than seek past events.
        put(player.data(),0x28,frame); SetLastError(INCOMING);
        assert(observed_frame(player.data(),1.0f)==expected);
        float speed=0,delta=0;
        assert(copy_field(address(player.data())+0x6a8,speed) && copy_field(address(player.data())+0x24,delta));
        assert(speed==expected && delta==expected && GetLastError()==FRAME_ERROR && !boss_inflight); ++checks;
    };
    rush_tick(0.0f,2.0f); rush_tick(5.0f,2.0f); rush_tick(29.0f,1.0f);
    rush_tick(28.5f,1.5f); rush_tick(30.0f,1.0f); rush_tick(65.0f,1.0f);
    // C66 and an unbound/stale clip never receive the C64 boost.
    put(player.data(),0x58,boss_private_descriptor_address(1)); rush_tick(5.0f,1.0f);
    put(player.data(),0x58,boss_private_descriptor_address(0));
    put(motion.data(),0x58,uint64_t(0)); rush_tick(5.0f,1.0f);
    put(motion.data(),0x58,boss_session.source_clip);
    dispatch->control.enabled=0; rush_tick(5.0f,1.0f);
    dispatch->control.enabled=1;
    put(player.data(),0x28,5.0f); SetLastError(INCOMING);
    assert(observed_frame(player.data(),0.0f)==0.0f && GetLastError()==FRAME_ERROR); ++checks;
    put(player.data(),0x28,5.0f); SetLastError(INCOMING);
    assert(observed_frame(player.data(),8.0f)==8.0f && GetLastError()==FRAME_ERROR); ++checks;
    std::printf("frame dispatcher offline checks passed: %u\n",checks);
    return 0;
}
