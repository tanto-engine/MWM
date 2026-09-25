// Owned buffers and direct callbacks only. MinHook is stubbed; no code patches.
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#define RESEARCH_REPEAT
#define RESEARCH_BOSS
#define RESEARCH_DISPATCH
#include "../../outputs/okatsu-prototype/native/observer.cpp"

static unsigned enables, disables, creates;
static MH_STATUS create_result = MH_OK, frame_enable_result = MH_OK, voice_enable_result = MH_OK;
static bool fail_voice_creation;
extern "C" MH_STATUS WINAPI MH_Initialize() { return MH_OK; }
extern "C" MH_STATUS WINAPI MH_Uninitialize() { return MH_OK; }
extern "C" MH_STATUS WINAPI MH_CreateHook(void* target, void*, void**) {
    ++creates; return target == voice_target && fail_voice_creation ? MH_ERROR_UNSUPPORTED_FUNCTION : create_result;
}
extern "C" MH_STATUS WINAPI MH_EnableHook(void* target) {
    ++enables;
    return target == frame_target ? frame_enable_result : target == voice_target ? voice_enable_result : MH_OK;
}
extern "C" MH_STATUS WINAPI MH_DisableHook(void*) { ++disables; return MH_OK; }

alignas(8) static std::array<uint8_t,0x800> player{};
alignas(8) static std::array<uint8_t,0x100> owner{}, source{}, source_owner{};
alignas(8) static std::array<uint8_t,0x100> motion{}, timing{}, source_motion{}, source_timing{};
alignas(8) static std::array<uint8_t,0x138> bank{}, player_bank{};
alignas(8) static std::array<uint8_t,0xD0> neutral{}, desired{};
alignas(8) static std::array<uint8_t,0xB0> neutral_payload{}, payload{};
alignas(8) static std::array<uint8_t,0xD0> pulse_descriptor{};
static std::array<std::array<uint8_t,0x30>,28> source_rows{};
static std::array<std::array<uint8_t,0x30>,3> pulse_rows{};
static std::array<uint64_t,28> source_pointers{};
static std::array<uint64_t,24> pulse_pointers{};
static uint64_t entries[1];
static DispatchMapping own_dispatch;
static TraceMapping own_trace;
static DispatchCommand command;
static int64_t frequency;
static unsigned action_calls, frame_calls, checks;
static bool stop_inside_frame;
static unsigned voice_calls;
static bool stop_inside_voice;
alignas(8) static std::array<uint8_t,0x100> voice_state{};
alignas(8) static std::array<uint8_t,0x1000> voice_record{};
static constexpr DWORD INCOMING = 0x10203040, FRAME_ERROR = 0x33445566, ACTION_ERROR = 0x77889900;

template<class T> static void put(void* base, size_t at, T value) {
    memcpy(static_cast<uint8_t*>(base) + at, &value, sizeof(value));
}
static uint64_t address(const void* value) { return reinterpret_cast<uint64_t>(value); }
static void bindings(bool borrowed) {
    for (unsigned i = 0; i != 4; ++i) {
        uint64_t value = 0; assert(copy_field(boss_slot(i),value));
        assert(value == (borrowed ? boss_borrowed(i) : boss_session.originals[i]));
    }
}
static bool fake_action(void* actor, uint32_t key, void* context) {
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
    ++frame_calls; assert(actor && delta == 0.25f && GetLastError() == INCOMING);
    if (stop_inside_frame) assert(NiohResearchStop(nullptr) == ERROR_BUSY);
    SetLastError(FRAME_ERROR); return -0.0f;
}
static float native_clock_frame(void* actor, float delta) {
    assert(actor == player.data() && GetLastError() == INCOMING);
    put(actor,0x6a8,1.0f); put(actor,0x24,delta);
    SetLastError(FRAME_ERROR); return delta;
}
static void fake_voice(void* state, void* record, void* event, int32_t bank_override) {
    ++voice_calls;
    assert(state==voice_state.data() && record==voice_record.data() && event==voice_record.data()+0x24);
    assert(bank_override==-1234 && GetLastError()==INCOMING && boss_inflight==1);
    if (stop_inside_voice) assert(NiohResearchStop(nullptr)==ERROR_BUSY);
    SetLastError(ACTION_ERROR);
}
static void publish(uint64_t sequence = 1) {
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    command.edge_qpc = command.heartbeat_qpc = now.QuadPart;
    command.expires_qpc = now.QuadPart + frequency;
    command.chord_sequence = sequence;
    command.sequence_begin = command.sequence_end = 1;
    memcpy(&dispatch->command,&command,sizeof(command));
}
static void state(uint32_t key, int32_t motion_key, int8_t stance) {
    put(neutral.data(),0,key); neutral[0x40]=1;
    put(neutral.data(),0x20,address(neutral_payload.data()));
    put(neutral_payload.data(),0x20,motion_key); put(neutral_payload.data(),0x0b,stance);
}
static void reset() {
    own_dispatch = {}; own_trace = {}; dispatch=&own_dispatch; trace=&own_trace;
    player.fill(0); owner.fill(0); source.fill(0); source_owner.fill(0);
    motion.fill(0); timing.fill(0); source_motion.fill(0); source_timing.fill(0);
    bank.fill(0); player_bank.fill(0); neutral.fill(0); desired.fill(0); payload.fill(0);
    boss_session = {}; boss_private_actions[0] = {}; boss_private_actions[1] = {}; boss_active = boss_inflight = 0;
    boss_session.player=address(player.data()); boss_session.player_owner=address(owner.data());
    boss_session.source_actor=address(source.data()); boss_session.source_owner=address(source_owner.data());
    boss_session.vtable=0xabcdef; boss_session.source_bank=address(bank.data());
    boss_session.source_descriptor=address(desired.data()); boss_session.source_payload=address(payload.data());
    boss_session.player_motion=address(motion.data()); boss_session.player_timing=address(timing.data());
    boss_session.source_motion=address(source_motion.data()); boss_session.source_timing=address(source_timing.data());
    boss_session.source_motion_bank=0x20001; boss_session.source_timing_wrapper=0x20002;
    for (unsigned i=0;i!=4;++i) {
        boss_session.originals[i]=0x10001+i;
        put(reinterpret_cast<void*>(boss_slot(i)),0,boss_session.originals[i]);
    }
    put(player.data(),0,boss_session.vtable); put(source.data(),0,boss_session.vtable);
    put(player.data(),0x50,boss_session.player_owner); put(source.data(),0x50,boss_session.source_owner);
    put(player.data(),0x58,address(neutral.data())); put(player.data(),0x70,address(player_bank.data()));
    put(owner.data(),0x38,boss_session.player_motion); put(owner.data(),0x68,boss_session.player_timing);
    put(source_owner.data(),0x38,boss_session.source_motion); put(source_owner.data(),0x68,boss_session.source_timing);
    put(source.data(),0x78,boss_session.source_bank);
    put(source_motion.data(),8,boss_session.source_motion_bank); put(source_timing.data(),0x10,boss_session.source_timing_wrapper);
    put(desired.data(),0,uint32_t(0xC64)); desired[0x40]=1; put(desired.data(),0x20,address(payload.data()));
    put(payload.data(),0x20,int32_t(1220)); put(payload.data(),0x34,int32_t(-1)); payload[0x0b]=1;
    put(payload.data(),0x16,int16_t(15)); put(payload.data(),0x24,int16_t(65));
    for (unsigned i=0;i!=28;++i) {
        source_rows[i].fill(uint8_t(i)); source_pointers[i]=address(source_rows[i].data());
    }
    put(desired.data(),0x78,address(source_pointers.data()));
    put(desired.data(),0x80,uint16_t(0)); put(desired.data(),0x82,uint16_t(28));
    pulse_descriptor.fill(0); pulse_pointers.fill(0);
    for (unsigned i=0;i!=3;++i) {
        memcpy(pulse_rows[i].data(),boss_pulse_templates[i],0x30);
        pulse_pointers[21+i]=address(pulse_rows[i].data());
    }
    put(pulse_descriptor.data(),0,uint32_t(0xCF0)); pulse_descriptor[0x40]=1;
    put(pulse_descriptor.data(),0x78,address(pulse_pointers.data()));
    put(pulse_descriptor.data(),0x82,uint16_t(24));
    boss_session.player_pulse_descriptor=address(pulse_descriptor.data());
    entries[0]=address(desired.data()); put(bank.data(),0x128,address(entries)); put(bank.data(),0x130,uint32_t(1));
    state(0,0,3);
    dispatch->control.qpc_frequency=frequency; begin_dispatch(); trace->header.enabled=1;
    command={}; command.player=boss_session.player; command.owner=boss_session.player_owner;
    command.vtable=boss_session.vtable; command.banks[0]=address(player_bank.data());
    command.expected_descriptor=boss_session.source_descriptor; command.expected_payload=boss_session.source_payload;
    command.desired_key=0xC64; command.expected_motion=1220; command.generation=dispatch->control.generation;
    command.armed=command.held=1; publish();
    original_action=fake_action; original_frame=fake_frame; original_voice=fake_voice;
    hook_created=frame_hook_created=voice_hook_created=true; hook_target=reinterpret_cast<void*>(0x12340000);
    frame_target=reinterpret_cast<void*>(0x12350000);
    voice_target=reinterpret_cast<void*>(0x12360000);
    action_calls=frame_calls=0; stop_inside_frame=false;
    voice_calls=0; stop_inside_voice=false;
}
static void tick(void* actor=player.data()) {
    SetLastError(INCOMING); float result=observed_frame(actor,0.25f);
    uint32_t bits; memcpy(&bits,&result,sizeof(bits));
    assert(bits==0x80000000 && GetLastError()==FRAME_ERROR && boss_inflight==0); ++checks;
}
static void exit_move() {
    SetLastError(INCOMING); assert(observed_action(player.data(),3000,nullptr));
    assert(!boss_active && GetLastError()==ACTION_ERROR); bindings(false);
}

int main() {
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); frequency=f.QuadPart;
    reset();
    dispatch->control.last_reason=CurrentNotAllowed;
    SetLastError(INCOMING); assert(observed_action(player.data(),25,nullptr));
    assert(dispatch->control.dispatch_count==0 && action_calls==1); ++checks;
    assert(dispatch->control.last_reason==CurrentNotAllowed);
    assert((trace->records[0].valid_fields>>8 & 255)==IneligibleRequest); ++checks;
    tick(); assert(frame_calls==1 && action_calls==2 && boss_active && dispatch->control.dispatch_count==1);
    assert(boss_private_actions[0].transition_count==31);
    for (unsigned i=0;i!=3;++i) {
        auto expected=pulse_rows[i]; put(expected.data(),0x20,int16_t(65));
        assert(!memcmp(boss_private_actions[0].transition_bodies[28+i],expected.data(),0x30));
        assert(!memcmp(pulse_rows[i].data(),boss_pulse_templates[i],0x30));
    }
    ++checks;
    assert((trace->records[1].valid_fields & ((1u<<18)|TRACE_FINAL_MATCH)) == ((1u<<18)|TRACE_FINAL_MATCH)); ++checks;
    auto calls=action_calls;
    for (uint32_t key : {24u,25u}) {
        SetLastError(INCOMING); assert(!observed_action(player.data(),key,nullptr));
        assert(GetLastError()==INCOMING && action_calls==calls && boss_active); bindings(true); ++checks;
    }
    tick(); assert(action_calls==calls); exit_move(); tick(); assert(dispatch->control.dispatch_count==1); ++checks;
    publish(2); tick(); assert(dispatch->control.dispatch_count==2 && boss_active); exit_move(); ++checks;

    reset(); command.held=0; publish(); tick(); assert(!action_calls && dispatch->control.last_reason==Released); ++checks;
    command.reserved[0]=1; publish(); tick(); assert(action_calls==1 && boss_active); exit_move(); ++checks;
    reset(); command.armed=0; publish(); tick(); assert(!action_calls); ++checks;
    reset(); command.heartbeat_qpc-=frequency; memcpy(&dispatch->command,&command,sizeof(command));
    tick(); assert(!action_calls); ++checks;
    reset(); command.expires_qpc=command.heartbeat_qpc-1; memcpy(&dispatch->command,&command,sizeof(command));
    tick(); assert(!action_calls); ++checks;
    reset(); tick(source.data()); assert(!action_calls && frame_calls==1); ++checks;

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
        latest=command; latest.reserved[field]=1;
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
    boss_session.source_timing_record=address(voice_record.data());
    put(voice_state.data(),8,boss_session.player_owner); put(voice_state.data(),0x20,boss_session.source_timing_record);
    put(voice_record.data(),4,uint32_t(1)); put(voice_record.data(),8,uint32_t(0x24));
    put(voice_record.data(),0x10,uint32_t(0x80)); put(voice_record.data(),0x24,uint32_t(30));
    put(voice_record.data(),0x28,uint32_t(10)); put(voice_record.data(),0x2c,uint32_t(11));
    put(voice_record.data(),0x80+11*0x4c+0x1c,uint32_t(0x0E077D36));
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(!voice_calls && GetLastError()==INCOMING && dispatch->control.reserved1==1 && boss_inflight==0); ++checks;
    put(voice_record.data(),0x80+11*0x4c+0x1c,uint32_t(0x12345678));
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(voice_calls==1 && GetLastError()==ACTION_ERROR && dispatch->control.reserved1==1 && boss_inflight==0); ++checks;
    exit_move(); stop_inside_voice=true; stopped=disables;
    SetLastError(INCOMING); observed_voice(voice_state.data(),voice_record.data(),voice_record.data()+0x24,-1234);
    assert(GetLastError()==ACTION_ERROR && disables==stopped && !dispatch->control.enabled && boss_inflight==0); ++checks;

    reset(); tick(); original_frame=native_clock_frame;
    boss_session.source_clip=0x23450000; put(motion.data(),0x58,boss_session.source_clip);
    auto rush_tick = [](float frame, float expected) {
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
