// Exercise native-selected replacements with owned William/Jin resources.
#define main inherited_frame_main
#include "frame_dispatch_cases.cpp"
#undef main
#include "low_heavy_fixture.h"

alignas(8) static std::array<uint8_t,0x478> jin_actions{}, jin_timing{};
alignas(8) static std::array<uint8_t,0x490> jin_motion{};
alignas(8) static std::array<uint8_t,0x138> jin_bank{};
static std::array<std::array<uint8_t,0xD0>,3> jin_descriptors{}, heavy_descriptors{};
static std::array<std::array<uint8_t,0xB0>,3> jin_payloads{}, heavy_payloads{};
static std::array<std::array<std::array<uint8_t,0x30>,46>,3> player_rows{};
static std::array<std::array<uint64_t,46>,3> player_pointers{};
static uint64_t jin_entries[3];
static bool setter_rejects;
static unsigned native_idle_fallbacks;
static unsigned pad_mask=1;
static unsigned pad_calls;
static WORD pad_buttons;
static bool publish_during_input;

static DWORD WINAPI replacement_input(DWORD slot, XINPUT_STATE* sample) {
    // Supply deterministic in-process controller samples without opening a real device.
    // Vary connected slots and button state while leaving stick position irrelevant.
    // Pending holds must reject disconnects and competing pads without synthesizing a release.
    ++pad_calls;
    if (!(pad_mask & (1u<<slot))) return ERROR_DEVICE_NOT_CONNECTED;
    if (publish_during_input) {
        // The real supervisor publishes concurrently while XInputGetState runs.
        // Its newer heartbeat must be compared against time sampled after the read.
        // Treating it as a future timestamp randomly cancels accepted holds.
        LARGE_INTEGER now; QueryPerformanceCounter(&now);
        dispatch->command.heartbeat_qpc=now.QuadPart;
    }
    *sample={}; sample->Gamepad.wButtons=pad_buttons;
    sample->Gamepad.sThumbLX=25000; sample->Gamepad.sThumbLY=-25000;
    return ERROR_SUCCESS;
}

static uint64_t native_lookup(void*, uint32_t key, uint32_t* index) {
    // Resolve researched low-heavy keys without involving actual native code.
    // Return their original William descriptors, with neutral standing in for other actions.
    // The replacement hook must decide from native resolution rather than controller masks.
    if (index) *index=0;
    SetLastError(ACTION_ERROR);
    if (key==0xCB7 || key==0xC7A) return address(heavy_descriptors[0].data());
    return key>=0xCF5 && key<=0xCF7 ? address(heavy_descriptors[key-0xCF5].data()) : address(neutral.data());
}

static bool replacement_action(void* actor, uint32_t key, void* context) {
    // Simulate native alias resolution and a setter that may reject its final action.
    // Generic strong resolves to CF5, while concrete follow-ups preserve their requested keys.
    // Failed commits must restore resources even after a lookup returned an imported descriptor.
    ++action_calls;
    uint32_t index=0;
    uint64_t selected=0;
    if (context) {
        assert(GetLastError()==FRAME_ERROR);
        const auto* banks=static_cast<uint64_t*>(context);
        assert(!banks[0] && !banks[2]);
        for (unsigned slot=0;slot<boss_import_count;++slot)
            if (banks[1]==address(&boss_private_actions[slot].bank)) {
                assert(key==boss_imports[slot].key); selected=boss_private_descriptor_address(slot);
            }
        assert(selected); bindings(true); SetLastError(ACTION_ERROR);
    } else {
        const uint32_t opener=boss_hold_variant ? boss_adapters[boss_hold_variant-1].player_key : 0xCF5;
        selected=observed_lookup(static_cast<uint8_t*>(actor)+0x70,key==0xBC0 ? opener : key,&index);
        // Native input resolution falls back to idle when the concrete lookup is absent.
        if (!selected) { ++native_idle_fallbacks; selected=address(neutral.data()); }
    }
    // Native711A75 treats motion-1 as a redirect; an empty table rejects without
    // committing an action. A successful711D29 commit resets its clock even
    // when the selected descriptor equals the current walking descriptor.
    uint64_t payload=0; int32_t motion=0; uint16_t rows=0;
    assert(copy_field(selected+0x20,payload) && copy_field(payload+0x20,motion));
    if (motion==-1) {
        assert(copy_field(selected+0x82,rows) && rows==0);
        SetLastError(ACTION_ERROR); return false;
    }
    if (!setter_rejects) { put(actor,0x58,selected); put(actor,0x28,0.0f); }
    assert(GetLastError()==ACTION_ERROR);
    return !setter_rejects;
}

static void replacement_reset() {
    // Add three Jin imports with separate owned resources to the baseline fixture.
    // Use recorded William transition bytes and the source recovery/count signatures.
    // Distinct banks reveal accidental reuse of Okatsu resources during replacement or exit.
    for (auto& adapter : boss_adapters) adapter={};
    reset(); boss_active_slot=0; pending_heavy={}; boss_hold_variant=0; boss_hold_milliseconds=0;
    game_input_state=replacement_input; pad_mask=1; pad_buttons=0; native_idle_fallbacks=0; publish_during_input=false;
    boss_import_count=5;
    const int16_t recovery[]={35,45,45}, player_recovery[]={38,29,33};
    const uint16_t counts[]={46,46,44};
    const auto module=address(GetModuleHandleW(nullptr));
    put(jin_actions.data(),0,module+0x13C7970); put(jin_actions.data(),0x468,address(jin_bank.data()));
    put(jin_timing.data(),0,module+0x12C5408); put(jin_timing.data(),0x468,uint64_t(0x90002));
    put(jin_motion.data(),0,module+0x13C8FA0);
    put(jin_bank.data(),0x128,address(jin_entries)); put(jin_bank.data(),0x130,uint32_t(3));
    for (unsigned i=0;i<3;++i) {
        const unsigned slot=i+2;
        auto& move=boss_imports[slot]; move={}; boss_private_actions[slot]={};
        move.descriptor=address(jin_descriptors[i].data()); move.payload=address(jin_payloads[i].data());
        move.clip=0x80000+i*0x100; move.timing_record=0xA0000+i*0x100;
        move.flags=0x194C0000; move.key=0xC6E + i; move.motion=2400+int(i)*10;
        move.recovery_frame=recovery[i]; move.transition_count=i==2 ? 74 : 75; move.next_variant=-1;
        auto& descriptor=jin_descriptors[i]; auto& body=jin_payloads[i];
        descriptor.fill(0); body.fill(0); descriptor[0x40]=1;
        put(descriptor.data(),0,move.key); put(descriptor.data(),0x20,move.payload);
        put(descriptor.data(),0x38,uint64_t(0x12340000+slot*0x100));
        put(descriptor.data(),0x82,move.transition_count); jin_entries[i]=move.descriptor;
        put(body.data(),0x18,move.flags); put(body.data(),0x20,move.motion);
        put(body.data(),0x24,move.recovery_frame); put(body.data(),0x16,int16_t(10));
        auto& player_descriptor=heavy_descriptors[i]; auto& player_payload=heavy_payloads[i];
        player_descriptor.fill(0); player_payload.fill(0); player_descriptor[0x40]=1;
        put(player_descriptor.data(),0,uint32_t(0xCF5+i));
        put(player_descriptor.data(),0x20,address(player_payload.data()));
        put(player_descriptor.data(),0x78,address(player_pointers[i].data()));
        put(player_descriptor.data(),0x82,counts[i]);
        put(player_payload.data(),0x20,int32_t(4300+i*10));
        put(player_payload.data(),0x24,player_recovery[i]);
        put(player_payload.data(),0x0B,uint8_t(i ? 4 : 2));
        for (unsigned row=0;row<counts[i];++row) {
            for (unsigned byte=0;byte<0x30;++byte) {
                unsigned value=0; assert(std::sscanf(heavy_rows[i][row]+byte*2,"%2x",&value)==1);
                player_rows[i][row][byte]=uint8_t(value);
            }
            player_pointers[i][row]=address(player_rows[i][row].data());
        }
        boss_adapters[slot]={address(jin_actions.data()),address(jin_timing.data()),address(jin_bank.data()),
            address(jin_motion.data()),0x90002,address(player_descriptor.data()),0xCF5+i,int32_t(4300+i*10),
            counts[i],player_recovery[i],1};
    }
    // Native heavy resolution must also work outside the optional gesture whitelist.
    state(9,10,3); put(player.data(),0x470,uint32_t(2));
    original_action=replacement_action; original_lookup=native_lookup; setter_rejects=false;
    command.armed=0; publish_player_context(.25f); publish();
    triangle_input={}; observe_game_input(trace->header);
}

static void hold_reset(unsigned stance=2) {
    // Isolate pending-input selection from the separately tested paired-action adapter.
    // Reuse the valid CF5 import at a distinct hold slot and keep the exact250ms deadline.
    // This fixture proves tap-versus-hold scheduling without claiming live Izuna contact acceptance.
    replacement_reset(); boss_import_count=6; boss_hold_variant=6; boss_hold_milliseconds=250;
    boss_imports[5]=boss_imports[2]; boss_adapters[5]=boss_adapters[2]; boss_private_actions[5]={};
    boss_adapters[5].kind=2;
    static uint8_t unused_row[0x30]; static uint64_t unused_rows[128];
    memset(unused_row,0xff,sizeof(unused_row));
    for (auto& row : unused_rows) row=address(unused_row);
    put(jin_descriptors[0].data(),0x78,address(unused_rows));
    if (stance!=2) {
        auto& adapter=boss_adapters[5];
        // Captured player payloads encode high=1, mid=0, low=2; motion thousands are not stance IDs.
        adapter.player_key=stance==0 ? 0xCB7 : 0xC7A; adapter.player_motion=stance==0 ? 3300 : 2300;
        adapter.transition_count=stance==0 ? 40 : 42; adapter.recovery_frame=stance==0 ? 58 : 46;
        put(heavy_descriptors[0].data(),0,adapter.player_key);
        put(heavy_descriptors[0].data(),0x82,adapter.transition_count);
        put(heavy_payloads[0].data(),0x20,adapter.player_motion);
        put(heavy_payloads[0].data(),0x24,adapter.recovery_frame);
        put(heavy_payloads[0].data(),0x0B,uint8_t(stance));
        put(player.data(),0x470,stance);
    }
    state(0,0,3); publish_player_context(.25f); publish(); pad_buttons=XINPUT_GAMEPAD_Y;
    observe_game_input(trace->header);
    SetLastError(INCOMING); assert(!observed_action(player.data(),0xBC0,nullptr));
    assert(GetLastError()==ACTION_ERROR && pending_heavy.active && !boss_active);
    assert(dispatch->control.dispatch_count==0 && same_field(address(player.data()),0x58,address(neutral.data())));
    assert(native_idle_fallbacks==0);
    bindings(false);
}

int main() {
    // Stress native input priority, resource isolation and recovery under rejected commits.
    // Run the three moves through ordinary setter calls with no armed controller gesture.
    // Moving entry, lock-on-independent selection and native running exclusions share this path.
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency=freq.QuadPart;
    hold_reset();
    observe_game_input(trace->header); pad_calls=0;
    LARGE_INTEGER begin,end; QueryPerformanceCounter(&begin);
    for (unsigned i=0;i<10000;++i) {
        unsigned controller=0; bool down=false, interrupted=false;
        assert(heavy_button(controller,down,interrupted));
    }
    QueryPerformanceCounter(&end);
    std::printf("10000 heavy reads: %u device calls, %.3f ms\n",pad_calls,
        1000.0*double(end.QuadPart-begin.QuadPart)/frequency); std::fflush(stdout);
    assert(pad_calls==0);
    auto& published_input=*reinterpret_cast<GameInput*>(trace->header.reserved);
    ++published_input.sequence;
    unsigned pad=0; bool down=false,interrupted=false;
    assert(!heavy_button(pad,down,interrupted) && pad_calls==0);
    ++published_input.sequence;
    published_input.qpc-=frequency;
    assert(!heavy_button(pad,down,interrupted) && pad_calls==0);
    // A release first observed beyond the deadline is still a hold.
    // Exercise the real scheduler with an elapsed press and a released sample.
    // A missed threshold frame must not dispatch the low-heavy tap instead.
    hold_reset(); pending_heavy.started-=frequency/4; pad_buttons=0; publish(); tick();
    assert(boss_active && boss_active_slot==5 && dispatch->control.dispatch_count==1);
    // A native request buffered behind another action retains the physical press age.
    // Move only the owned clock backwards, then ask native lookup to authorize it.
    // Recognition must not add another full250ms after the action becomes eligible.
    hold_reset(); pending_heavy={}; triangle_input.pressed-=frequency/4;
    assert(!observed_action(player.data(),0xBC0,nullptr));
    assert(pending_heavy.started==triangle_input.pressed);
    publish(); tick(); assert(boss_active_slot==5 && dispatch->control.dispatch_count==1);
    replacement_reset();
    assert(!repeat_current_allowed(address(neutral.data()),9));
    for (unsigned i=0;i<3;++i) {
        assert(observed_action(player.data(),i==0 ? 0xBC0 : 0xCF5+i,nullptr));
        assert(boss_active && boss_active_slot==i+2 && dispatch->control.dispatch_count==i+1);
        assert(same_field(address(player.data()),0x58,boss_private_descriptor_address(i+2)));
        bindings(true);
        const auto& record=trace->records[i];
        assert((record.valid_fields&TRACE_FINAL_MATCH) && record.reserved==0xC6E + i);
        const auto& clone=boss_private_actions[i+2];
        assert(clone.transition_count==boss_adapters[i+2].transition_count);
        assert(!memcmp(clone.transition_bodies[clone.transition_count-2],native_dodge_row,0x30));
        assert(clone.payload[0x0B]==4 && clone.payload[0x33]==40);
        // Input adaptation must never replace Jin's combat tables with William's tables.
        assert(!memcmp(clone.descriptor+0x28,jin_descriptors[i].data()+0x28,0x50));
        for (unsigned row=0;row<clone.transition_count;++row) {
            // Only timing-window fields may differ from the player's native input row.
            assert(!memcmp(clone.transition_bodies[row],player_rows[i][row].data(),0x20));
            assert(!memcmp(clone.transition_bodies[row]+0x24,player_rows[i][row].data()+0x24,12));
        }
        publish();
    }
    assert(observed_action(player.data(),0xCD5,nullptr));
    assert(!boss_active); bindings(false);
    assert(dispatch->control.dispatch_count==3 && !replacement_call.actor);

    // Native running/quick/other-stance actions and unscoped lookups retain their descriptors.
    for (uint32_t key : {0xCD5u,0xCD6u,0xD2Bu,0xCF0u,0xD34u}) {
        replacement_reset(); observed_action(player.data(),key,nullptr);
        assert(!boss_active && dispatch->control.dispatch_count==0); bindings(false);
    }
    replacement_reset(); uint32_t index=9;
    assert(observed_lookup(player.data()+0x70,0xCF5,&index)==address(heavy_descriptors[0].data()));
    assert(!boss_active && index==0);

    for (unsigned failure=0;failure<8;++failure) {
        replacement_reset();
        if (failure==0) put(player.data(),0x470,uint32_t(1));
        if (failure==1) dispatch->control.enabled=0;
        if (failure==2) dispatch->command.heartbeat_qpc-=frequency;
        if (failure==3) dispatch->command.generation+=1;
        if (failure==4) dispatch->control.reserved0=0;
        if (failure==5) put(heavy_payloads[0].data(),0x20,int32_t(999));
        if (failure==6) dispatch->command.banks[0]+=8;
        if (failure==7) put(jin_actions.data(),0x468,uint64_t(0xDEAD00));
        observed_action(player.data(),0xBC0,nullptr);
        assert(!boss_active && dispatch->control.dispatch_count==0); bindings(false);
    }
    replacement_reset(); setter_rejects=true;
    assert(!observed_action(player.data(),0xBC0,nullptr));
    assert(!boss_active); bindings(false);
    replacement_reset(); observed_action(player.data(),0xBC0,nullptr);
    stop_dispatch(); observed_action(player.data(),0xCD5,nullptr);
    assert(!boss_active && dispatch->control.dispatch_count==1); bindings(false);

    hold_reset(); tick();
    assert(pending_heavy.active && dispatch->control.dispatch_count==0);
    pad_buttons=0; publish(); tick();
    assert(!pending_heavy.active && !pending_heavy.spent && boss_active_slot==2);
    assert(dispatch->control.dispatch_count==1); bindings(true);

    hold_reset(); pending_heavy.started-=frequency/4; publish(); tick();
    assert(!pending_heavy.active && pending_heavy.spent && boss_active_slot==5);
    assert(dispatch->control.dispatch_count==1); bindings(true);
    hold_reset(); pending_heavy.started-=frequency/4; publish(); publish_during_input=true; tick();
    assert(boss_active && boss_active_slot==5 && dispatch->control.dispatch_count==1);
    publish_during_input=false;
    observed_action(player.data(),0xCD5,nullptr); publish(); tick();
    observed_action(player.data(),0xBC0,nullptr); publish(); tick();
    assert(!pending_heavy.active && dispatch->control.dispatch_count==1 && !boss_active);
    pad_buttons=0; publish(); tick(); assert(!pending_heavy.spent);
    pad_buttons=XINPUT_GAMEPAD_Y; observe_game_input(trace->header); observed_action(player.data(),0xBC0,nullptr);
    assert(pending_heavy.active && dispatch->control.dispatch_count==1);

    // Recorded forward movement resumes one frame after BC0 was deferred: 0C/20,
    // or the lock-on 3EB..3FD family. Both releases and holds must survive that change.
    // Damage, dodge and running attacks still cancel rather than buffering an import.
    const uint32_t movement[][2]={{0xC,20},{0xD,30},{0xC7,21},{0xCA,41},
        {0x3EB,20},{0x3EC,24},{0x3F7,26},{0x3F8,28},
        {0x3FA,30},{0x3FB,31},{0x3FC,32},{0x3FD,33}};
    for (const auto& action : movement) for (bool held : {false,true}) {
        hold_reset(); state(action[0],int32_t(action[1]),3); publish(); tick();
        assert(pending_heavy.active && !pending_heavy.spent);
        if (held) pending_heavy.started-=frequency/4;
        pad_buttons=held ? XINPUT_GAMEPAD_Y : 0;
        publish(); tick();
        assert(boss_active && boss_active_slot==(held ? 5u : 2u));
        assert(dispatch->control.dispatch_count==1); bindings(true);
    }
    // Deferral must preserve the walking clock, including repeated native requests.
    // Checking only descriptor equality missed an otherwise identical recommit.
    // The final held import still starts exactly once after the original deadline.
    hold_reset(); state(0xC,20,3); put(player.data(),0x28,17.0f); publish();
    const auto started=pending_heavy.started;
    for (unsigned i=0;i<3;++i) {
        observed_action(player.data(),0xBC0,nullptr);
        float frame=0; assert(copy_field(address(player.data())+0x28,frame) && frame==17.0f);
        assert(pending_heavy.started==started && native_idle_fallbacks==0);
    }
    pending_heavy.started-=frequency/4; publish(); tick();
    assert(boss_active_slot==5 && dispatch->control.dispatch_count==1);
    // Native selection can authorize the next heavy during an attack's recovery.
    // Preserve that exact origin while timing the gesture; changing to damage cancels it.
    // Buffering must neither reset the previous attack nor require a forced idle frame.
    for (bool interrupted : {false,true}) {
        hold_reset(); pending_heavy={}; state(0xCD5,4020,2);
        put(player.data(),0x28,32.0f); publish();
        assert(!observed_action(player.data(),0xBC0,nullptr));
        float frame=0; assert(copy_field(address(player.data())+0x28,frame) && frame==32.0f);
        assert(pending_heavy.active && native_idle_fallbacks==0);
        if (interrupted) state(0x3E8,30222,3);
        pending_heavy.started-=frequency/4; publish(); tick();
        assert(!pending_heavy.active && bool(boss_active)==!interrupted);
        assert(dispatch->control.dispatch_count==(interrupted ? 0 : 1));
    }
    // A hold buffered from an imported heavy must keep its borrowed resources.
    // The failed native redirect leaves the previous private descriptor alive.
    // Recovery reborrows that exact bank until the scheduled launcher commits.
    hold_reset(); pad_buttons=0; publish(); tick();
    assert(boss_active && boss_active_slot==2);
    put(player.data(),0x28,32.0f); pad_buttons=XINPUT_GAMEPAD_Y; publish();
    observe_game_input(trace->header);
    assert(!observed_action(player.data(),0xBC0,nullptr));
    assert(pending_heavy.active && boss_active_slot==2); bindings(true);
    pending_heavy.started-=frequency/4; publish(); tick();
    assert(boss_active_slot==5 && dispatch->control.dispatch_count==2); bindings(true);
    for (const auto& action : {std::array<int,3>{9,10,3},{0x3E8,30222,3},{0xCD5,4020,2},{0xC,999,3}}) {
        hold_reset(); state(uint32_t(action[0]),action[1],int8_t(action[2]));
        pending_heavy.started-=frequency/4; publish(); tick();
        assert(!pending_heavy.active && !boss_active && dispatch->control.dispatch_count==0);
        bindings(false);
    }

    for (uint32_t key : {0xCF6u,0xCF7u,0xCD5u}) {
        hold_reset(); pending_heavy={};
        observed_action(player.data(),key,nullptr);
        assert(!pending_heavy.active);
        assert(dispatch->control.dispatch_count==(key==0xCD5 ? 0 : 1));
        assert((key==0xCD5) == !boss_active);
    }

    for (unsigned failure=0;failure<8;++failure) {
        hold_reset(); pending_heavy.started-=frequency/4;
        if (failure==0) pad_mask=0;
        if (failure==1) pad_mask=2;
        if (failure==2) { pad_mask=3; input_rescan=0; }
        if (failure==3) dispatch->control.reserved0+=1u<<16;
        if (failure==4) dispatch->command.heartbeat_qpc-=frequency;
        if (failure==5) stop_dispatch();
        if (failure==6) pad_buttons|=XINPUT_GAMEPAD_A;
        if (failure==7) frame_delta=0;
        tick();
        assert(!pending_heavy.active && pending_heavy.spent && !boss_active);
        assert(dispatch->control.dispatch_count==0); bindings(false);
        pad_mask=1; pad_buttons=XINPUT_GAMEPAD_Y; frame_delta=.25f;
        publish(); tick();
        assert(!pending_heavy.active && dispatch->control.dispatch_count==0);
    }
    for (unsigned stance : {0u,1u}) {
        hold_reset(stance); pad_buttons=0; publish(); tick();
        assert(!boss_active && !pending_heavy.active && dispatch->control.dispatch_count==0);
        assert(same_field(address(player.data()),0x58,address(heavy_descriptors[0].data()))); bindings(false);
        hold_reset(stance); pending_heavy.started-=frequency/4; publish(); tick();
        assert(boss_active && boss_active_slot==5 && dispatch->control.dispatch_count==1); bindings(true);
        hold_reset(stance); put(player.data(),0x470,uint32_t(2)); pending_heavy.started-=frequency/4;
        publish(); tick(); assert(!boss_active && !pending_heavy.active);
    }
    hold_reset();
    auto& launcher=boss_imports[5];
    launcher.key=0xC79; launcher.motion=5014; launcher.recovery_frame=-1;
    put(jin_descriptors[0].data(),0,launcher.key);
    put(jin_payloads[0].data(),0x20,launcher.motion);
    put(jin_payloads[0].data(),0x24,int16_t(-1)); put(jin_payloads[0].data(),0x26,int16_t(-1));
    static uint8_t launcher_combat[0x80]; static uint64_t launcher_combat_pointer;
    const char* contact="80000000000000080e00ffff05000000b4005f000500060c0e00060c3c320500ffffff64ffffffff1600230000002d00000000000000ff0223000c0037000064000200000000020000ff000108ff0a01ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";
    for (unsigned byte=0;byte<sizeof(launcher_combat);++byte) {
        unsigned value=0; assert(std::sscanf(contact+byte*2,"%2x",&value)==1); launcher_combat[byte]=uint8_t(value);
    }
    launcher_combat_pointer=address(launcher_combat);
    put(jin_descriptors[0].data(),0x48,address(&launcher_combat_pointer));
    put(jin_descriptors[0].data(),0x50,uint16_t(0)); put(jin_descriptors[0].data(),0x52,uint16_t(1));
    pending_heavy.started-=frequency/4; publish(); tick();
    assert(boss_active_slot==5 && boss_active);
    // Native71A5EE reads the signed grounded vertical impulse only after contact.
    // Change that one byte in the private row while retaining Jin's source and airborne response.
    // A missed attack never reaches this native reaction consumer.
    uint64_t contact_table=0,contact_row=0; int8_t impulse=0;
    assert(copy_field(boss_private_descriptor_address(5)+0x48,contact_table));
    assert(copy_field(contact_table,contact_row) && copy_field(contact_row+0x17,impulse));
    assert(impulse==16 && launcher_combat[0x17]==12);
    for (unsigned byte=0;byte<sizeof(launcher_combat);++byte) if (byte!=0x17) {
        uint8_t actual=0; assert(copy_field(contact_row+byte,actual) && actual==launcher_combat[byte]);
    }
    assert(boss_prepare_private_action(5));
    launcher_combat[0x10]^=1; // A changed source cannot silently overwrite a published combat row.
    assert(!boss_prepare_private_action(5)); launcher_combat[0x10]^=1;
    assert(boss_prepare_private_action(5));
    for (unsigned failure=0;failure<4;++failure) {
        uint8_t descriptor[0xD0],body[0x80]{};
        memcpy(descriptor,jin_descriptors[0].data(),sizeof(descriptor));
        if (failure==0) put(descriptor,0x52,uint16_t(0));
        if (failure==1) put(descriptor,0x48,uint64_t(0));
        if (failure==2) launcher_combat[0x17]=13;
        if (failure==3) launcher_combat_pointer=0;
        assert(!boss_copy_launcher_contact(5,descriptor,body));
        launcher_combat[0x17]=12; launcher_combat_pointer=address(launcher_combat);
    }
    for (unsigned unrelated=0;unrelated<3;++unrelated) {
        uint8_t descriptor[0xD0],body[0x80]{};
        memcpy(descriptor,jin_descriptors[0].data(),sizeof(descriptor));
        if (unrelated==0) launcher.key=0xC6E;
        if (unrelated==1) launcher.motion=5010;
        if (unrelated==2) boss_adapters[5].kind=1;
        assert(boss_copy_launcher_contact(5,descriptor,body));
        assert(!memcmp(descriptor,jin_descriptors[0].data(),sizeof(descriptor)));
        launcher.key=0xC79; launcher.motion=5014; boss_adapters[5].kind=2;
    }
    // Match native recovery permission bits and Pulse timing to the adapted tail.
    // The source still has no recovery; only the private player copy changes.
    // Paired/colliding keys must not inherit the launcher tuning.
    int16_t combo=0,cancel=0,pulse=0,source_recovery=0;
    const auto private_payload=boss_private_payload_address(5);
    assert(copy_field(private_payload+0x24,combo) && combo==54);
    assert(copy_field(private_payload+0x26,cancel) && cancel==54);
    assert(copy_field(private_payload+0x38,pulse) && pulse==54);
    assert(copy_field(launcher.payload+0x24,source_recovery) && source_recovery==-1);
    unsigned pulses=0;
    for (unsigned i=0;i<boss_private_actions[5].transition_count;++i) {
        const auto* body=boss_private_actions[5].transition_bodies[i]; int16_t key=0,start=0;
        memcpy(&key,body+0x14,2); memcpy(&start,body+0x20,2);
        if (key==0xD5F) { assert(start==54); ++pulses; }
    }
    assert(pulses==3);
    original_frame=native_clock_frame; put(motion.data(),0x58,launcher.clip);
    for (const auto& sample : {std::array<float,2>{0,2},{6.5f,1.5f},{7,1},{8,1},{12,1},{60,1}}) {
        put(player.data(),0x28,sample[0]); SetLastError(INCOMING);
        assert(observed_frame(player.data(),1.0f)==sample[1]);
        float speed=0,delta=0,frame=0;
        assert(copy_field(address(player.data())+0x6A8,speed) && speed==sample[1]);
        assert(copy_field(address(player.data())+0x24,delta) && delta==sample[1]);
        assert(copy_field(address(player.data())+0x28,frame) && frame==sample[0]);
    }
    launcher.motion=5010; assert(boss_move_timing(5).recovery==-1);
    put(player.data(),0x28,0.0f); SetLastError(INCOMING);
    assert(observed_frame(player.data(),1.0f)==1.0f);
    std::puts("native replacement checks passed: three stance holds, native mid/high taps, three-link heavy, camera-independent input, cancellations and LastError");
}
