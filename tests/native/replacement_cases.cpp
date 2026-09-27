// Exercise native-selected replacements with owned William/Jin resources.
#define main inherited_frame_main
#include "frame_dispatch_cases.cpp"
#undef main
#include "low_heavy_fixture.h"
#include "airborne_fixture.h"

alignas(8) static std::array<uint8_t,0x478> jin_actions{}, jin_timing{};
alignas(8) static std::array<uint8_t,0x490> jin_motion{};
alignas(8) static std::array<uint8_t,0x138> jin_bank{};
static std::array<std::array<uint8_t,0xD0>,3> jin_descriptors{}, heavy_descriptors{};
static std::array<std::array<uint8_t,0xB0>,3> jin_payloads{}, heavy_payloads{};
static std::array<uint8_t,0xD0> grapple_descriptor{};
static std::array<uint8_t,0xB0> grapple_payload{};
static std::array<std::array<std::array<uint8_t,0x30>,46>,3> player_rows{};
static std::array<std::array<uint64_t,46>,3> player_pointers{};
static uint64_t jin_entries[3];
static bool setter_rejects;
static unsigned native_idle_fallbacks;
static unsigned pad_mask=1;
static unsigned pad_calls;
static WORD pad_buttons;
static bool publish_during_input;
static unsigned weight_calls;
static uint64_t weight_reaction;
static bool weight_accept=true;
static float weight_native_impulse=16;
static uint64_t weight_component_after;

static void owned_weight(void* actor, float weight) {
    // Model Character::SetWeight with owned fields and the native negative sentinel.
    // Updating the current collision component tests replacement rather than a saved pointer.
    // Deliberately change LastError to expose wrappers that lose the native caller's result.
    uint64_t owner=0,collision=0;assert(copy_field(address(actor)+0x50,owner));
    assert(copy_field(owner+0x250,collision));put(actor,0x7BC,weight);
    if (collision) put(reinterpret_cast<void*>(collision),0xB0,weight<0 ? 100.0f : weight);
    ++weight_calls;SetLastError(999);
}

static bool weight_action(void* actor, uint32_t, void* context) {
    // Commit a controlled damage reaction through the existing global setter wrapper.
    // The commit serial changes only on native success; the selected hit is consumed there.
    // Selected unpaired hits must already be lighter while native reaction processing runs.
    uint64_t owner=0,collision=0;float effective=0;
    assert(copy_field(address(actor)+0x50,owner) && copy_field(owner+0x250,collision));
    assert(copy_field(collision+0xB0,effective) && context && effective==*static_cast<float*>(context));
    if (weight_accept) {
        uint32_t serial=0;uint64_t owner=0,component=0;assert(copy_field(address(actor)+0xDC,serial));
        put(actor,0x58,weight_reaction);put(actor,0xDC,serial+1);
        assert(copy_field(address(actor)+0x50,owner) && copy_field(owner+0x230,component));
        put(reinterpret_cast<void*>(component),0x90,uint64_t(0));
        put(reinterpret_cast<void*>(component),0x5C,weight_native_impulse);
        if (weight_component_after) put(reinterpret_cast<void*>(owner),0x230,weight_component_after);
    }
    SetLastError(ACTION_ERROR);return weight_accept;
}

static void weight_cases() {
    // Exercise provisional weight during the actual native selected-hit setter path.
    // Rejected, paired and nonreaction results roll back; only committed reactions retain ownership.
    // Existing component, external-owner and cooperative Stop cases remain entirely owned-memory tests.
    static uint8_t victim[0x800]{},victim_owner[0xF00]{},component[0x98]{},collision[0xC0]{},changed_collision[0xC0]{};
    static uint8_t event[0x120]{},reaction[0xD0]{},payload[0xB0]{},initial[0xD0]{},initial_payload[0xB0]{};
    native_set_weight=owned_weight;weight_calls=0;weight_reaction=address(reaction);
    const auto saved_action=original_action;original_action=weight_action;
    put(victim,0,boss_session.vtable);put(victim,0x50,address(victim_owner));
    put(victim_owner,0x230,address(component));put(component,8,address(victim));
    put(victim_owner,0x250,address(collision));put(reaction,0x20,address(payload));
    put(initial,0x20,address(initial_payload));
    const unsigned bridge_slot=boss_import_count;assert(bridge_slot<24);
    const auto saved_bridge=boss_imports[bridge_slot];const auto saved_adapter=boss_adapters[bridge_slot];
    for (unsigned failure=0;failure<11;++failure) {
        put(victim,0x58,address(initial));put(victim,0x7BC,-1.0f);put(collision,0xB0,100.0f);
        put(payload,0,uint32_t(0x40000));put(payload,0x18,uint64_t(0));put(initial_payload,0x18,uint64_t(0));
        put(component,0x90,address(event));put(event,0xE8,boss_session.player_owner);put(event,0x100,address(victim_owner));
        put(event,0xE0,address(boss_private_actions[5].combat_body));put(event,0x11C,int32_t(0));weight_accept=true;
        if (failure==1) put(event,0xE0,uint64_t(0));
        if (failure==2) put(event,0xE8,uint64_t(0));
        if (failure==3) put(event,0x11C,int32_t(1));
        if (failure==4) put(payload,0,uint32_t(0));
        if (failure==5) put(payload,0x18,uint64_t(0x20000000));
        if (failure==6) weight_accept=false;
        if (failure==7) {
            boss_imports[bridge_slot]=boss_imports[5];boss_imports[bridge_slot].key=0xC7A;
            boss_adapters[bridge_slot]=boss_adapters[5];boss_adapters[bridge_slot].kind=4;
            boss_import_count=bridge_slot+1;
        }
        if (failure==10) boss_adapters[5].player_key=0xCB7;
        if (failure==8) put(initial_payload,0x18,uint64_t(0x20000000));
        if (failure==9) put(collision,0xB0,10000.0f);
        const bool retained=!failure || failure==10;
        const bool acquired=retained || failure==4 || failure==5 || failure==6;
        float expected=acquired ? 50.0f : failure==9 ? 10000.0f : 100.0f;
        const auto before=weight_calls;SetLastError(INCOMING);
        assert(observed_action(victim,0x96,&expected)==weight_accept && GetLastError()==ACTION_ERROR);
        assert(launch_weight_count==(retained ? 1 : 0));
        assert(weight_calls==before+(acquired ? (retained ? 1 : 2) : 0));
        float actual=0;assert(copy_field(address(victim)+0x7BC,actual) && actual==(retained ? 50.0f : -1.0f));
        if (retained) {
            assert(copy_field(address(collision)+0xB0,actual) && actual==50);
            const auto calls=weight_calls;put(component,0x90,address(event));
            assert(!launcher_hit(victim).owner && weight_calls==calls && launch_weight_count==1);
            restore_launch_weights(boss_session.player,true);assert(launch_weight_count==1);
            assert(NiohResearchStop(nullptr)==ERROR_BUSY && launch_weight_count==1 && weight_calls==calls);
            SetLastError(INCOMING);observed_frame(player.data(),.25f);
            assert(!launch_weight_count && GetLastError()==FRAME_ERROR);
            assert(copy_field(address(victim)+0x7BC,actual) && actual==-1);
            dispatch->control.enabled=1;
        } else if (acquired) assert(copy_field(address(collision)+0xB0,actual) && actual==100);
        boss_adapters[5].player_key=0xCF5;boss_import_count=bridge_slot;
        boss_imports[bridge_slot]=saved_bridge;boss_adapters[bridge_slot]=saved_adapter;
    }
    // Current-resistance bands are configurable trials, not universal enemy classes.
    // Inline fallback and active override blocks must choose the same labeled human tier.
    // Only the exact committed damage result can receive a per-victim vertical change.
    static uint8_t profile[0xE0]{},stats[0xBC0]{},override_stats[0x130]{},other_component[0x98]{};
    for (unsigned scenario=0;scenario<10;++scenario) {
        put(victim,0x58,address(initial));put(victim,0x7BC,-1.0f);put(collision,0xB0,100.0f);
        put(victim_owner,0x230,address(component));put(component,8,address(victim));
        put(victim_owner,0x240,address(stats));put(victim_owner,0xE90,scenario==4 ? uint64_t(0) : address(profile));
        put(profile,0x0C,uint32_t(scenario==3 ? 1 : 0));put(profile,0xD8,uint32_t(100));
        const uint32_t resistance=scenario==0 ? 68 : scenario==2 ? 200 : 83;
        put(stats,0xAF8,resistance);put(stats,0xB98,scenario==5 ? address(override_stats) : uint64_t(0));
        put(override_stats,0x120,uint32_t(68));
        put(component,0x90,address(event));put(component,0x5C,0.0f);
        put(event,0xE8,boss_session.player_owner);put(event,0x100,address(victim_owner));
        put(event,0xE0,address(boss_private_actions[5].combat_body));put(event,0x11C,int32_t(0));
        put(payload,0,uint32_t(scenario==9 ? 0 : 0x40000));put(payload,0x18,uint64_t(scenario==8 ? 0x20000000 : 0));
        weight_native_impulse=scenario==6 ? 11.0f : 16.0f;
        weight_component_after=scenario==7 ? address(other_component) : 0;
        const bool low=scenario==0 || scenario==5, fallback=scenario==2 || scenario==3 || scenario==4;
        float expected=low ? 75.0f : fallback ? 50.0f : 45.0f;
        SetLastError(INCOMING);assert(observed_action(victim,0x96,&expected) && GetLastError()==ACTION_ERROR);
        float impulse=0;assert(copy_field(address(component)+0x5C,impulse));
        const float expected_impulse=scenario>=6 ? weight_native_impulse : low ? 14.0f : fallback ? 16.0f : 17.0f;
        if (impulse!=expected_impulse) std::fprintf(stderr,"launch scenario%u impulse%g expected%g\n",scenario,impulse,expected_impulse);
        assert(impulse==expected_impulse);
        assert(launch_weight_count==(scenario>=7 ? 0 : 1));
        restore_launch_weights(address(victim),true);assert(!launch_weight_count);
    }
    put(victim_owner,0x230,address(component));put(victim_owner,0xE90,uint64_t(0));
    weight_native_impulse=16;weight_component_after=0;
    // Direct selected-hit acquisition isolates unchanged serial and existing ownership endings.
    put(initial_payload,0x18,uint64_t(0));weight_accept=true;
    for (unsigned ending=0;ending<10;++ending) {
        put(victim,0,boss_session.vtable);put(victim,0x58,address(initial));put(victim,0xDC,uint32_t(1));
        put(victim,0x7BC,-1.0f);put(payload,0,uint32_t(0x40000));put(payload,0x18,uint64_t(0));
        put(victim_owner,0x250,address(collision));put(collision,0xB0,100.0f);put(component,0x90,address(event));
        const auto hit=launcher_hit(victim);assert(hit.owner && launch_weight_count==1);
        put(victim,0x58,address(reaction));put(victim,0xDC,uint32_t(ending==6 ? 1 : 2));
        const auto acquired_calls=weight_calls;
        if (ending==7) put(victim,0,boss_session.vtable+8);
        if (ending==8) put(victim_owner,0x250,address(changed_collision));
        if (ending==9) put(victim,0x50,address(victim_owner)+8);
        finish_launch_weight(victim,hit,true);
        if (ending>=6) {
            const bool replaced=ending==7 || ending==9;float actual=0;
            assert(!launch_weight_count && weight_calls==acquired_calls+(replaced ? 0 : 1));
            assert(copy_field(address(victim)+0x7BC,actual) && actual==(replaced ? 50.0f : -1.0f));
            put(victim,0x50,address(victim_owner));continue;
        }
        assert(launch_weight_count==1);const auto calls=weight_calls;
        if (ending==0) put(victim,0x58,address(neutral.data()));
        if (ending==1) put(victim,0,boss_session.vtable+8);
        if (ending==2) put(victim,0x7BC,75.0f);
        if (ending==3) put(victim_owner,0x250,address(changed_collision));
        if (ending==4) put(victim_owner,0x250,uint64_t(0));
        restore_launch_weights(address(victim),ending==5);
        assert(!launch_weight_count && weight_calls==calls+(ending==1 || ending==2 ? 0 : 1));
        float actual=0;assert(copy_field(address(victim)+0x7BC,actual));
        assert(actual==(ending==1 ? 50.0f : ending==2 ? 75.0f : -1.0f));
    }
    // Native sword rows and curated imports can add one small boost to an already airborne victim.
    // Compare the new native result with the source row, so repeated finishing cannot accumulate.
    // Grounded, paired, foreign, stale, other-weapon and disabled hits retain their native result.
    static uint8_t sword[0xD0]{},sword_payload[0xB0]{},sword_combat[0x80]{};
    static uint64_t sword_row=address(sword_combat);
    uint64_t player_current=0;uint32_t player_bank=0;
    assert(copy_field(address(player.data())+0x58,player_current) && copy_field(address(player.data())+0x68,player_bank));
    const auto active=boss_active;const auto kind=boss_adapters[5].kind;
    constexpr uint32_t sword_keys[]={0xC76,0xC78,0xCB3,0xCF4,0xC7A,0xCB9,0xCF7};
    constexpr int32_t sword_motions[]={2100,2120,3100,4140,2300,3320,4320};
    for (unsigned scenario=0;scenario<21;++scenario) {
        put(victim,0,boss_session.vtable);put(victim,0x50,address(victim_owner));put(victim,0x58,address(initial));
        put(victim,0x7BC,-1.0f);put(victim_owner,0x230,address(component));put(victim_owner,0x250,address(collision));
        put(collision,0xB0,100.0f);put(component,8,address(victim));put(component,0x90,address(event));
        put(initial_payload,0,uint64_t(scenario==8 ? 0 : scenario==19 ? 0x200000000ULL : 0x400));
        put(initial_payload,0x18,uint64_t(scenario==9 ? 0x20000000 : 0));
        put(payload,0,uint64_t(scenario==20 ? 0x40000 : 0x40400));put(payload,0x18,uint64_t(scenario==10 ? 0x20000000 : 0));
        const unsigned native=scenario<7 ? scenario : 0;
        put(sword,0,sword_keys[native]);put(sword,0x20,address(sword_payload));sword[0x40]=1;
        put(sword,0x48,address(&sword_row));put(sword,0x50,uint16_t(0));put(sword,0x52,uint16_t(1));
        put(sword_payload,0x18,uint64_t(scenario==11 ? 0x20000000 : 0x194C0000));
        put(sword_payload,0x20,scenario==12 ? int32_t(9999) : sword_motions[native]);
        sword_combat[0x17]=6;sword_combat[0x1B]=scenario==17 ? 19 : 8;
        boss_active=0;put(player.data(),0x58,address(sword));put(player.data(),0x68,uint32_t(scenario==13 ? 1 : 0));
        boss_air_juggle_boost=scenario==14 ? 0 : 2;
        put(event,0xE0,scenario==15 ? uint64_t(0) : address(sword_combat));
        put(event,0xE8,scenario==16 ? uint64_t(0) : boss_session.player_owner);put(event,0x11C,int32_t(0));
        if (scenario==7) {
            boss_active=active;boss_adapters[5].kind=1;put(player.data(),0x58,player_current);
            put(event,0xE0,address(boss_private_actions[5].combat_body));
        }
        weight_native_impulse=scenario==7 ? 16 : scenario==17 ? 19 : scenario==18 ? 11 : scenario==20 ? 6 : 8;
        const bool boosts=scenario<=7 || (scenario>=17 && scenario!=18);
        float expected=100;const auto calls=weight_calls;
        const auto hit=launcher_hit(victim);
        assert(weight_action(victim,0x96,&expected));finish_launch_weight(victim,hit,true);
        const float wanted=boosts ? (weight_native_impulse+2>20 ? 20 : weight_native_impulse+2) : weight_native_impulse;
        float actual=0;assert(copy_field(address(component)+0x5C,actual) && actual==wanted);
        finish_launch_weight(victim,hit,true);assert(grapple_field(address(component),0x5C,wanted));
        assert(!launch_weight_count && weight_calls==calls);boss_adapters[5].kind=kind;
    }
    boss_active=active;boss_air_juggle_boost=2;put(player.data(),0x58,player_current);put(player.data(),0x68,player_bank);
    // Izuna's already-airborne opening must retain native lift for its following catch.
    // Give the opener its validated bridge and replay the selected player-owned air hit.
    // Other sword hits above still receive their configured juggle boost.
    const unsigned count=boss_import_count;boss_import_count=7;
    boss_imports[6]=boss_imports[5];boss_imports[6].key=0xC7A;
    boss_adapters[6]=boss_adapters[5];boss_adapters[6].kind=4;
    put(victim,0x58,address(initial));put(initial_payload,0,uint64_t(0x400));
    put(event,0xE0,address(boss_private_actions[5].combat_body));
    assert(!launcher_hit(victim).owner && !launch_weight_count);boss_import_count=count;
    weight_native_impulse=16;
    native_set_weight=nullptr;original_action=saved_action;weight_accept=true;
}

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
    if (key==0xD4A) return address(grapple_descriptor.data());
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
    reset();for (auto& binding : boss_skill_bindings) binding={};boss_active_slot=0; pending_heavy={}; boss_hold_variant=0; boss_hold_milliseconds=0;
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
    grapple_descriptor.fill(0); grapple_payload.fill(0); grapple_descriptor[0x40]=1;
    put(grapple_descriptor.data(),0,uint32_t(0xD4A));
    put(grapple_descriptor.data(),0x20,address(grapple_payload.data()));
    put(grapple_descriptor.data(),0x82,uint16_t(37));
    put(grapple_payload.data(),0x18,uint64_t(0x194C0000));
    put(grapple_payload.data(),0x20,int32_t(5050));
}

static void hold_reset(unsigned stance=2, bool select_heavy=true) {
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
        // Native RB+Y/X/A selects high=0, mid=1, low=2 (2000-family is mid).
        adapter.player_key=stance==0 ? 0xCB7 : 0xC7A; adapter.player_motion=stance==0 ? 3300 : 2300;
        adapter.transition_count=stance==0 ? 40 : 42; adapter.recovery_frame=stance==0 ? 58 : 46;
        put(heavy_descriptors[0].data(),0,adapter.player_key);
        put(heavy_descriptors[0].data(),0x82,adapter.transition_count);
        put(heavy_payloads[0].data(),0x20,adapter.player_motion);
        put(heavy_payloads[0].data(),0x24,adapter.recovery_frame);
        put(heavy_payloads[0].data(),0x0B,uint8_t(stance));
        put(player.data(),0x470,stance);
    }
    boss_skill_bindings[0]={3,stance==2 ? 1u : stance==1 ? 2u : 4u,6,0,0,0,0};
    state(0,0,3); publish_player_context(.25f); publish(); pad_buttons=XINPUT_GAMEPAD_Y;
    observe_game_input(trace->header);
    if (select_heavy) {
        SetLastError(INCOMING); assert(!observed_action(player.data(),0xBC0,nullptr));
        assert(GetLastError()==ACTION_ERROR && pending_heavy.active && !boss_active);
        assert(dispatch->control.dispatch_count==0 && same_field(address(player.data()),0x58,address(neutral.data())));
        assert(native_idle_fallbacks==0);
    }
    bindings(false);
}

static void held_slot_cases() {
    // Frost/guard entries share native heavy templates but do not own held Triangle.
    // Place optional entries before and after a real hold to reproduce both selection orders.
    // Ordinary heavy and empty-Ki grapple must resolve the same configured hold slot.
    for (unsigned stance : {2u,0u}) {
        boss_hold_stances=7; hold_reset(stance); pending_heavy={};
        boss_imports[6]=boss_imports[5]; boss_adapters[6]=boss_adapters[5]; boss_import_count=7;
        boss_imports[6].key=stance==2 ? 0xC71 : 0xC81;
        assert(!observed_action(player.data(),0xBC0,nullptr));
        assert(pending_heavy.active && pending_heavy.hold==5);
        if (stance==2) {
            pending_heavy={};
            assert(!observed_action(player.data(),0xD4A,nullptr));
            assert(pending_heavy.active && pending_heavy.hold==5);
        }
        const uint32_t key=boss_adapters[5].player_key;
        boss_imports[4]=boss_imports[6]; boss_adapters[4]=boss_adapters[6];
        assert(stance_hold(key)==5); // Exclude optional entries even before the held import.
        boss_imports[6].key=boss_imports[5].key;
        assert(stance_hold(key)==5); // A later matching template cannot override the binding.
        boss_skill_bindings[0].variant=7;assert(stance_hold(key)==6);
        boss_skill_bindings[0].variant=6;
        boss_adapters[5].kind=0; boss_adapters[6].kind=0;
        assert(stance_hold(key)==boss_import_count);
        boss_hold_stances=0;
        assert(stance_hold(key)==boss_import_count);
    }
    boss_hold_stances=7;
}

static void airborne_cases() {
    // Replay exact recorded source graphs against owned immutable action storage.
    // Assert stance isolation, native contact/landing branches and unchanged paired clocks.
    // Source bytes and counters prove adapter behavior, never successful gameplay contact.
    hold_reset(1); pending_heavy={}; boss_import_count=18;
    static uint8_t descriptors[12][0xD0],payloads[12][0xB0],rows[12][128][0x30];
    static uint64_t pointers[12][128];
    static uint8_t low_descriptor[0xD0],low_payload[0xB0],high_descriptor[0xD0],high_payload[0xB0];
    memcpy(low_descriptor,heavy_descriptors[0].data(),sizeof(low_descriptor));
    memcpy(low_payload,heavy_payloads[0].data(),sizeof(low_payload));
    put(low_descriptor,0,uint32_t(0xCF5)); put(low_descriptor,0x20,address(low_payload));
    put(low_descriptor,0x82,uint16_t(46)); put(low_payload,0x20,int32_t(4300)); put(low_payload,0x24,int16_t(38));
    memcpy(high_descriptor,low_descriptor,sizeof(high_descriptor));memcpy(high_payload,low_payload,sizeof(high_payload));
    put(high_descriptor,0,uint32_t(0xCB7));put(high_descriptor,0x20,address(high_payload));put(high_descriptor,0x82,uint16_t(40));
    put(high_payload,0x20,int32_t(3300));put(high_payload,0x24,int16_t(58));
    for (unsigned phase=0;phase<12;++phase) {
        const auto& source=airborne_sources[phase]; const unsigned slot=phase+5;
        auto& move=boss_imports[slot]; move={}; boss_private_actions[slot]={};
        move.key=source.key;move.motion=source.motion;move.flags=source.flags;
        move.recovery_frame=source.recovery;move.transition_count=uint16_t(source.count);
        move.next_variant=phase==1 ? 7 : -1;
        move.descriptor=address(descriptors[phase]);move.payload=address(payloads[phase]);
        move.clip=0xF0000+phase*0x100;move.timing_record=0x100000+phase*0x100;
        for (unsigned byte=0;byte<std::strlen(source.payload)/2;++byte) {
            unsigned value=0;assert(std::sscanf(source.payload+byte*2,"%2x",&value)==1);payloads[phase][byte]=uint8_t(value);
        }
        for (unsigned row=0;row<source.count;++row) {
            for (unsigned byte=0;byte<0x30;++byte) {
                unsigned value=0;assert(std::sscanf(source.rows[row]+byte*2,"%2x",&value)==1);rows[phase][row][byte]=uint8_t(value);
            }
            pointers[phase][row]=address(rows[phase][row]);
        }
        put(descriptors[phase],0,move.key);put(descriptors[phase],0x20,move.payload);
        descriptors[phase][0x40]=1;put(descriptors[phase],0x78,address(pointers[phase]));
        put(descriptors[phase],0x82,move.transition_count);
        boss_adapters[slot]=boss_adapters[5];
        auto& adapter=boss_adapters[slot];
        adapter.kind=phase==0 || phase==5 || phase==9 ? 2 : phase>=2 && phase<=4 ? 3 : 4;
        if (adapter.kind==3) {adapter.player_descriptor=0;adapter.player_key=0;adapter.player_motion=0;adapter.transition_count=0;adapter.recovery_frame=0;}
        if (phase>=5) {adapter.player_descriptor=address(low_descriptor);adapter.player_key=0xCF5;adapter.player_motion=4300;adapter.transition_count=46;adapter.recovery_frame=38;}
        if (phase>=9) {adapter.player_descriptor=address(high_descriptor);adapter.player_key=0xCB7;adapter.player_motion=3300;adapter.transition_count=40;adapter.recovery_frame=58;}
    }
    boss_imports[17]=boss_imports[5];boss_adapters[17]=boss_adapters[5];boss_adapters[17].player_key=0xCF5;
    boss_frost_variants[0]=11;boss_frost_variants[1]=6;
    assert(boss_native_successor(5,0xC7A)==6 && boss_native_successor(17,0xC7A)==-1);
    assert(boss_native_successor(13,0xC79)==-1);
    assert(boss_native_successor(5,0x3B2)==-1 && boss_native_successor(6,0x3B2)==7);
    assert(boss_native_successor(7,0x3B4)==8 && boss_native_successor(8,0x3B6)==9);
    for (unsigned slot=5;slot<17;++slot) assert(boss_prepare_private_action(slot));
    assert(boss_move_timing(5).startup_speed==8 && boss_move_timing(17).startup_speed==2);
    assert(boss_move_timing(5).startup_end==12 && boss_move_timing(17).startup_end==8);
    for (unsigned slot=7;slot<=9;++slot) assert(boss_move_timing(slot).startup_speed==1);
    for (unsigned phase : {1u,2u,3u,5u,6u,7u,9u,10u}) {
        const auto& clone=boss_private_actions[phase+5];
        assert(clone.transition_count==airborne_sources[phase].count);
        assert(!memcmp(clone.transition_bodies,rows[phase],clone.transition_count*0x30));
    }
    const auto& finish=boss_private_actions[9];
    for (unsigned row=0;row<3;++row) {int16_t target=-1;memcpy(&target,finish.transition_bodies[row]+20,2);assert(target==0xBB8);}
    int16_t weight=0;assert(copy_field(boss_private_payload_address(7)+0x28,weight) && weight==10000);
    const auto& dash=boss_private_actions[11];int16_t onset=0,cost=0;
    memcpy(&onset,dash.payload+0x38,2);memcpy(&cost,dash.payload+0x16,2);
    assert(dash.payload[0x33]==40 && onset==-1 && cost==20 && dash.payload[9]==0xFA);
    assert(boss_private_actions[13].payload[0x33]==40 && boss_private_actions[13].transition_count>46);
    assert(boss_native_successor(14,0xC82)==15 && boss_native_successor(15,0xC83)==16);
    assert(boss_native_successor(13,0xC81)==-1 && boss_native_successor(16,0xC79)==-1);
    assert(boss_move_timing(14).startup_speed==1 && boss_move_timing(16).recovery==30);
    memcpy(&onset,boss_private_actions[15].payload+0x38,2);memcpy(&cost,boss_private_actions[15].payload+0x16,2);
    assert(onset==-1 && cost==10 && boss_private_actions[15].payload[0x33]==40);
    for (unsigned offset : {0x24u,0x26u,0x38u}) {memcpy(&onset,boss_private_actions[16].payload+offset,2);assert(onset==30);}
    rows[1][1][0]=0;assert(!boss_prepare_private_action(6));rows[1][1][0]=22;
    assert(boss_prepare_private_action(6));
    // The isolated C71 shares source bytes but cannot resolve the full Swallow's dash.
    // Retain native fall routing and the current stance without borrowing another graph.
    // Its immutable clone must not alter the Low Frost Moon transition table.
    boss_import_count=19;boss_imports[18]=boss_imports[10];boss_adapters[18]=boss_adapters[10];
    auto& jump=boss_adapters[18];jump.kind=5;jump.player_descriptor=0;jump.player_key=0;
    jump.player_motion=0;jump.transition_count=0;jump.recovery_frame=0;boss_private_actions[18]={};
    assert(boss_prepare_private_action(18) && boss_private_actions[18].payload[0x0B]==4);
    assert(boss_native_successor(18,0xC72)==-1 && boss_native_successor(10,0xC72)==11);
    assert(boss_private_actions[18].transition_bodies[1][0x0A]==0xff);
    assert(boss_private_actions[10].transition_bodies[1][0x0A]!=0xff);
    assert(grapple_field(address(boss_private_actions[18].transition_bodies[0]),0x14,int16_t(0x11)));
    // Commit the actual guard lookup and all three native phases with owned retained resources.
    // Selector-only tests cannot catch a source-validation or resource-borrowing failure here.
    // Ordinary completion must restore the four player slots after the imported landing.
    static uint8_t guard[0xD0]{},skill[0xD0]{},guard_row[0x30]{};
    static uint64_t guard_pointer=address(guard_row),source_entries[12];
    for (unsigned phase=0;phase<12;++phase) source_entries[phase]=address(descriptors[phase]);
    put(jin_bank.data(),0x128,address(source_entries));put(jin_bank.data(),0x130,uint32_t(12));
    put(guard,0x78,address(&guard_pointer));put(guard,0x82,uint16_t(1));
    guard_row[0x0B]=5;guard_row[0x0C]=0;guard_row[0x0D]=0;guard_row[0x0E]=1;
    put(guard_row,0x14,int16_t(0xFA2));put(skill,0,uint32_t(0xFA2));skill[0x40]=1;
    put(skill,0x20,address(high_payload));
    high_payload[0x0B]=0;put(player.data(),0x470,uint32_t(0));
    put(player.data(),0x58,address(guard));put(player.data(),0x90,address(guard_row));
    original_lookup=[](void*,uint32_t,uint32_t* bank) {
        // Supply the original guard skill descriptor before the production lookup adapts it.
        // Report bank zero so the test can observe the private import changing bank ownership.
        // Return only static fixture memory; no live action bank participates in this call.
        *bank=0;return address(skill);
    };
    boss_native_bindings=0;boss_skill_bindings[0]={2,4,15,0,0,0,0};publish();
    {
        DispatchReason reason=Disabled;DispatchCommand request{};ReplacementScope scope(player.data(),request,reason);
        uint32_t bank=0;
        assert(observed_lookup(player.data()+0x70,0xFA2,&bank)==boss_private_descriptor_address(14));
        assert(bank==1 && reason==Accepted && boss_active && boss_active_slot==14);
    }
    put(player.data(),0x58,boss_private_descriptor_address(14));boss_finish_call(player.data());
    for (unsigned slot : {15u,16u}) {
        SetLastError(FRAME_ERROR);
        assert(observed_action(player.data(),boss_imports[slot].key,nullptr));
        assert(boss_active_slot==slot && grapple_field(boss_session.player,0x58,boss_private_descriptor_address(slot)));
    }
    put(player.data(),0x58,address(neutral.data()));boss_finish_call(player.data());assert(!boss_active);bindings(false);
    boss_skill_bindings[0]={};boss_native_bindings=0;original_lookup=native_lookup;
    boss_frost_variants[0]=boss_frost_variants[1]=0;
}

static void weapon_policy_cases() {
    // Reproduce Jin's stance-conditioned weapon selection on imported sword actions.
    // Only the two exact source equipment effects may be removed from the private schedule.
    // Other events and the shared source payload remain unchanged.
    replacement_reset();
    static uint8_t effects[2][0x80]{};static uint64_t pointers[58]{};
    const char* raw="0000ffff000000000000ffffffffffff00000000ffffffffffffffffffff000000000000000000000000ff02ff00ffffffffffff00000000000000000000ffffffff6464646464646464ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff5100ffffffffffffffffffffffffffffffffffff";
    for (unsigned i=0;i<2;++i) {
        for (unsigned j=0;j<0x80;++j) {unsigned v=0;assert(std::sscanf(raw+j*2,"%2x",&v)==1);effects[i][j]=uint8_t(v);}
        effects[i][0x2B]+=uint8_t(i);effects[i][0x6C]+=uint8_t(i);pointers[46+i]=address(effects[i]);
        put(jin_payloads[0].data(),0x40+i*6,int16_t(46+i));
    }
    put(jin_bank.data(),0x80,address(pointers));put(jin_bank.data(),0x88,uint16_t(58));
    const auto before=jin_payloads[0];assert(boss_prepare_private_action(2));
    assert(grapple_field(boss_private_payload_address(2),0x40,int16_t(-1)));
    assert(grapple_field(boss_private_payload_address(2),0x46,int16_t(-1)) && before==jin_payloads[0]);
    boss_private_actions[2]={};effects[0][0x18]=0;assert(!boss_prepare_private_action(2));effects[0][0x18]=0xff;
}

static void mid_string_cases(unsigned family) {
    // Give each of five source strikes the same verified Mid heavy input template.
    // The native buffered/direct rows request the next source only after another Triangle press.
    // Confirm source isolation, native exits, final termination and unchanged stance ownership.
    constexpr unsigned keys[3][5]={{0xBBF,0xC63,0xC64,0xC65,0xC66},{0xBC0,0xC6C,0xC6D,0,0},{0xC6E,0xC6F,0xC70,0,0}};
    constexpr int16_t recovery[3][5]={{20,25,35,30,30},{25,30,30,0,0},{35,45,45,0,0}};
    const unsigned count=family ? 3 : 5;
    hold_reset(1,false);pending_heavy={};boss_hold_stances=0;boss_import_count=5+count;
    static uint8_t descriptors[5][0xD0]{},payloads[5][0xB0]{},rows[5][75][0x30]{};
    static uint64_t pointers[5][75];
    const auto base=boss_imports[5];const auto adapter=boss_adapters[5];
    const char* follows[]={"ffff5100ffffffffffff020101ffff00000000007b0c0000ff806464000040000a002900ffffffffffffffffffffffff",
        "ffff5100ffffffffffff000101ffff00000000007b0c000400806464000040002a003400ffffffffffffffffffffffff"};
    for (unsigned r=0;r<2;++r) for (unsigned b=0;b<0x30;++b) {
        unsigned byte=0;assert(std::sscanf(follows[r]+b*2,"%2x",&byte)==1);player_rows[0][7+r][b]=uint8_t(byte);
    }
    for (unsigned phase=0;phase<count;++phase) {
        auto& move=boss_imports[5+phase];move=base;move.key=keys[family][phase];move.motion=(family==0 ? 2100 : family==1 ? 2300 : 2400)+10*int(phase);
        move.recovery_frame=recovery[family][phase];move.transition_count=phase+1==count ? 74 : 75;
        memcpy(descriptors[phase],jin_descriptors[0].data(),0xD0);memcpy(payloads[phase],jin_payloads[0].data(),0xB0);
        move.descriptor=address(descriptors[phase]);move.payload=address(payloads[phase]);
        put(descriptors[phase],0,move.key);put(descriptors[phase],0x20,move.payload);
        put(descriptors[phase],0x78,address(pointers[phase]));put(descriptors[phase],0x80,uint16_t(0));
        put(descriptors[phase],0x82,move.transition_count);put(payloads[phase],0x20,move.motion);put(payloads[phase],0x24,move.recovery_frame);
        memset(rows[phase],0xff,sizeof(rows[phase]));for (unsigned r=0;r<75;++r)pointers[phase][r]=address(rows[phase][r]);
        boss_adapters[5+phase]=adapter;boss_adapters[5+phase].kind=phase ? 4 : 2;boss_private_actions[5+phase]={};
    }
    for (unsigned phase=0;phase<count;++phase) {
        const unsigned slot=5+phase;assert(boss_prepare_private_action(slot));
        const auto& clone=boss_private_actions[slot];
        for (unsigned r : {7u,8u}) {
            assert(grapple_field(address(clone.transition_bodies[r]),0x14,int16_t(phase+1<count ? keys[family][phase+1] : -1)));
            assert(clone.transition_bodies[r][0x0B]==1 && clone.transition_bodies[r][0x0C]==1);
        }
        assert(grapple_field(address(player_rows[0][7].data()),0x14,int16_t(0xC7B)));
        if (phase+1<count) assert(boss_native_successor(slot,keys[family][phase+1])==int(slot+1));
        else assert(sword_string_successor(boss_imports[slot])==0);
        assert(clone.payload[0x0B]==4);
    }
}

static void tracking_cases() {
    // Follow moving targets after startup while bounding each turn by real frame delta.
    // Range, paired/source ownership and locked-handle changes reject without position writes.
    // Pauses and NPC callbacks never accumulate turns or change camera data.
    static uint8_t controller[0xA0]{},movement[0x100]{},target[0xF00]{},target_actor[0x800]{},component[0x10]{},profile[0x10]{},target_current[0xD0]{},target_payload[0xB0]{};
    static uint64_t registry=0x123456,handle=0x1234000000012345ULL,result=0,camera=0x987654;
    static unsigned calls=0,scenario=0;
    native_set_yaw=[](void* node,float angle) {
        // Accept yaw writes only on the owned movement component, never the target or camera.
        // Count each committed turn and write the same field used by the native setter.
        // Deliberately change LastError so the outer hook must preserve its promised error state.
        assert(node==movement);put(node,0x54,angle);++calls;SetLastError(990);
    };
    native_locked_target=[](const uint64_t* value) {
        // Resolve the fixture handle while injecting lifecycle changes inside the lookup callback.
        // Clear ownership, movement or action fields to test the production post-lookup revalidation.
        // Return the controlled target and alter LastError to exercise callback error preservation.
        assert(scenario<24 && *value==handle);
        if (scenario==13) put(player.data(),8,uint64_t(0));
        if (scenario==14) put(controller,0x40,handle+1);
        if (scenario==15) put(player.data(),0x38,uint64_t(0));
        if (scenario==16) put(player.data(),0x50,uint64_t(0));
        if (scenario==17) put(player.data(),0x58,address(neutral.data()));
        SetLastError(991);return result;
    };
    tracking_registry=address(&registry);tracking_controller_vtable=0x765432;
    for (scenario=0;scenario<27;++scenario) {
        boss_hold_stances=7;hold_reset(0,false);pending_heavy={};
        boss_import_count=7;boss_imports[5].key=0xC79;boss_imports[5].motion=5014;boss_imports[5].recovery_frame=-1;boss_imports[5].clip=0x123450;
        boss_imports[6]=boss_imports[5];boss_imports[6].key=scenario==8 ? 0 : 0xC7A;
        boss_adapters[6]=boss_adapters[5];boss_adapters[6].kind=4;
        boss_active=1;boss_active_slot=5;boss_active_player=boss_session.player;boss_private_actions[5].ready=true;
        put(boss_private_actions[5].descriptor,0x20,boss_private_payload_address(5));
        put(boss_private_actions[5].payload,0x18,uint64_t(scenario==7 ? 0x20000000 : 0x194C0000));
        put(player.data(),0x58,boss_private_descriptor_address(5));put(player.data(),8,address(controller));
        put(controller,0,scenario==26 ? uint64_t(0) : tracking_controller_vtable);
        put(controller,0x90,scenario>=24 ? address(target) : uint64_t(0));
        put(controller,0x40,scenario>=24 ? uint64_t(0) : handle);put(player.data(),0xDC,uint32_t(50));put(movement,0x54,0.0f);
        put(player.data(),0x38,scenario==19 ? uint64_t(0) : address(movement));put(player.data(),0x18,address(movement));
        put(player.data(),0x28,scenario==9 ? 26.0f : scenario==18 ? std::numeric_limits<float>::quiet_NaN() : 0.0f);
        put(player.data(),0x24,1.0f);put(player.data(),0x6A8,1.0f);put(motion.data(),0x58,boss_imports[5].clip);
        put(owner.data(),0xF0,0.0f);put(owner.data(),0xF4,0.0f);put(owner.data(),0xF8,0.0f);
        put(target,0,handle);put(target,0xF0,scenario==5 || scenario==21 ? 300.0f : scenario==20 ? -100.0f : 100.0f);
        put(target,0xF4,scenario==22 ? 700.0f : 0.0f);put(target,0xF8,scenario==5 || scenario==21 ? 100.0f : scenario==6 ? 700.0f : 300.0f);
        if (scenario==11) put(target,0xF0,std::numeric_limits<float>::infinity());
        if (scenario==12 || scenario==25) put(target,4,uint16_t(1));
        put(target,0xE90,address(profile));put(profile,0xC,uint32_t(scenario==3 ? 1 : 0));
        put(target,0x230,address(component));put(component,8,address(target_actor));put(target_actor,0,boss_session.vtable);
        put(target_actor,0x50,scenario==4 ? uint64_t(0) : address(target));
        put(target_actor,0x58,address(target_current));put(target_current,0x20,address(target_payload));
        put(target_payload,0x18,uint64_t(scenario==23 ? 0x20000000 : 0));
        result=scenario==1 ? 0 : scenario==2 ? boss_session.player_owner : address(target);
        boss_tracking_rates[0]=scenario==10 ? 0 : 540;
        boss_session.player_camera_slot=address(&camera);const auto before_camera=camera;
        uint8_t before_player[12],before_target[12];memcpy(before_player,owner.data()+0xF0,12);memcpy(before_target,target+0xF0,12);
        const unsigned before=calls;SetLastError(ACTION_ERROR);boss_advance_clock(player.data(),1);
        const bool accepted=scenario==0 || scenario==5 || scenario==19 || scenario==20 || scenario==21 || scenario==22 || scenario==24;
        if (calls!=before+unsigned(accepted)) std::fprintf(stderr,"tracking scenario%u calls%u expected%u\n",scenario,calls-before,unsigned(accepted));
        assert(calls==before+unsigned(accepted));
        assert(!memcmp(before_player,owner.data()+0xF0,12) && !memcmp(before_target,target+0xF0,12) && camera==before_camera);
        if (accepted) {
            float angle=0;assert(copy_field(address(movement)+0x54,angle));
            constexpr float step=540.0f/60*3.141592741f/180;
            assert(std::abs(angle-(scenario==20 ? -step : step))<.00001f);
            assert(GetLastError()==ACTION_ERROR);
            put(target,0xF0,-300.0f);put(target,0xF8,100.0f);put(player.data(),0x28,18.0f);
            put(player.data(),0x24,1.0f);put(player.data(),0x6A8,1.0f);
            boss_advance_clock(player.data(),1);assert(calls==before+2);
            float turned=0;assert(copy_field(address(movement)+0x54,turned) && std::abs(turned-(angle-step))<.00001f);
            boss_advance_clock(player.data(),0);boss_advance_clock(target_actor,1);assert(calls==before+2);
            put(target_payload,0x18,uint64_t(0x20000000));boss_advance_clock(player.data(),1);assert(calls==before+2);
            put(target_payload,0x18,uint64_t(0));
            for (unsigned group=1;group<=2;++group) {
                for (unsigned phase=0;phase<3;++phase) {
                    auto& move=boss_imports[5];move.key=(group==1 ? 0xC81 : 0xC71)+phase;
                    move.motion=phase==0 ? 1050 : group==1 ? (phase==1 ? 5050 : 5051) : (phase==1 ? 5000 : 5001);
                    move.flags=(group==1 && phase==2) ? 0x1BCE0000 : 0;move.recovery_frame=-1;move.next_variant=-1;
                    move.transition_count=group==1 ? (phase==2 ? 75 : 18) : (phase==1 ? 17 : 18);
                    boss_adapters[5].kind=phase ? 4 : 2;
                    put(player.data(),0x28,20.0f);put(player.data(),0x24,1.0f);put(player.data(),0x6A8,1.0f);
                    put(movement,0x54,0.0f);put(profile,0xC,uint32_t(1));
                    const auto prior=calls;boss_advance_clock(player.data(),1);assert(calls==prior+1);
                    float yaw=0;assert(copy_field(address(movement)+0x54,yaw));
                    assert(std::abs(yaw+boss_tracking_rates[group]/60*3.141592741f/180)<.00001f);
                }
            }
        }
    }
    native_set_yaw=nullptr;native_locked_target=nullptr;tracking_registry=0;boss_tracking_rates[0]=540;
}

static void slam_cases() {
    // Use captured C75/C77/C78 payloads and automatic rows with the existing high-stance adapter.
    // Verify actual Frost dispatch, ordinary source continuations, idle exit and Ki Pulse recovery.
    // All three phases retain native speed, including the full20..28 hit window and87-frame tail.
    boss_hold_stances=7;hold_reset(0);pending_heavy={};frost_input={};pad_buttons=0;
    boss_hold_stances=0;for (auto& binding : boss_skill_bindings) binding={};
    for (auto& frost : boss_frost_variants) frost=0;
    boss_frost_variants[2]=6;boss_frost_speed=8;boss_import_count=8;
    static uint8_t descriptors[3][0xD0]{},payloads[3][0xB0]{},rows[3][74][0x30]{};
    static uint64_t pointers[3][74],entries[3],combat_pointer;
    static uint8_t combat[0x80]{},vitals[0xA0]{};
    constexpr uint32_t keys[]={0xC75,0xC77,0xC78};constexpr int motions[]={5010,5012,5013};
    const char* bodies[]={"02000100000200000000ff01750cffff010900000000000000004c190000000092130000ffffffffffff000001000200ffffff00ffffffff000000000000ffff45270000ffff09000000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffff2e000000ffff2f000000ffffffffffffffffffffffffffffffffffff","02000100000200000000ff01770cffff010900000000000000004c190000000094130000ffffffffffff000001000200ffffff00ffffffff000000000000ffff45270000ffff11270000ffff01000000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffff2e000000ffff2f000000ffffffffffffffffffffffffffffffffffff","02000000000200000000ff01780cffff010900000000140000004c190000000095130000ffffffffffff000001000200ffffff00ffffffff000000000000ffff24270000050011270500ffff1b000a001200ffff0000ffffffff0000ffff142700001e00ffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffff2e000000ffff2f000000ffffffffffffffffffffffffffffffffffff"};
    const char* automatic[]={"ffffffffffffffffffff01ffffffff0000000000770c000800806464040000000080ff7fffffffffffffffffffffffff","ffffffffffffffffffff01ffffffff0000000000780c0000ff806464040000000080ff7fffffffffffffffffffffffff","ffffffffffffffffffff01ffffffff0000000000b80b0000ff806464040000000080ff7fffffffffffffffffffffffff"};
    const auto adapter=boss_adapters[5];
    for (unsigned phase=0;phase<3;++phase) {
        const unsigned slot=phase+5;boss_private_actions[slot]={};
        auto& move=boss_imports[slot];move={};move.key=keys[phase];move.motion=motions[phase];
        move.flags=0x194C0000;move.recovery_frame=-1;move.transition_count=74;move.next_variant=-1;
        move.descriptor=address(descriptors[phase]);move.payload=address(payloads[phase]);
        move.clip=0xF3000+phase*0x100;move.timing_record=0xF4000+phase*0x100;
        for (unsigned byte=0;byte<0xB0;++byte) {unsigned v=0;assert(std::sscanf(bodies[phase]+byte*2,"%2x",&v)==1);payloads[phase][byte]=uint8_t(v);}
        memset(rows[phase],0xff,sizeof(rows[phase]));
        for (unsigned byte=0;byte<0x30;++byte) {unsigned v=0;assert(std::sscanf(automatic[phase]+byte*2,"%2x",&v)==1);rows[phase][0][byte]=uint8_t(v);}
        for (unsigned row=0;row<74;++row) pointers[phase][row]=address(rows[phase][row]);
        memset(descriptors[phase],0,sizeof(descriptors[phase]));descriptors[phase][0x40]=1;
        put(descriptors[phase],0,move.key);put(descriptors[phase],0x20,move.payload);
        put(descriptors[phase],0x38,address(jin_bank.data()));put(descriptors[phase],0x78,address(pointers[phase]));
        put(descriptors[phase],0x82,uint16_t(74));entries[phase]=move.descriptor;
        boss_adapters[slot]=adapter;boss_adapters[slot].kind=phase ? 4 : 2;
    }
    combat_pointer=address(combat);put(descriptors[2],0x48,address(&combat_pointer));put(descriptors[2],0x52,uint16_t(1));
    put(jin_bank.data(),0x128,address(entries));put(jin_bank.data(),0x130,uint32_t(3));
    assert(boss_native_successor(5,0xC77)==6 && boss_native_successor(6,0xC78)==7);
    assert(boss_native_successor(5,0xC76)==-1 && boss_native_successor(7,0xC71)==-1);
    for (unsigned slot=5;slot<8;++slot) assert(boss_prepare_private_action(slot));
    for (unsigned phase=0;phase<3;++phase) assert(!memcmp(boss_private_actions[phase+5].transition_bodies[0],rows[phase][0],0x30));
    for (unsigned offset : {0x24u,0x26u,0x38u}) {int16_t recovery=0;assert(copy_field(boss_private_payload_address(7)+offset,recovery) && recovery==29);}
    int16_t cost=0;assert(copy_field(boss_private_payload_address(7)+0x16,cost) && cost==20);
    assert(boss_private_actions[7].payload[0x33]==40 && grapple_field(boss_private_descriptor_address(7),0x48,address(&combat_pointer)));
    unsigned pulses=0;
    for (unsigned row=0;row<boss_private_actions[7].transition_count;++row)
        if (grapple_field(address(boss_private_actions[7].transition_bodies[row]),0x14,int16_t(0xD5F))) {
            assert(grapple_field(address(boss_private_actions[7].transition_bodies[row]),0x20,int16_t(29)));++pulses;
        }
    assert(pulses);
    for (unsigned slot=5;slot<8;++slot) assert(boss_move_timing(slot).startup_speed==1);
    memset(vitals,0,sizeof(vitals));put(owner.data(),0x240,address(vitals));
    put(player.data(),0x470,uint32_t(2));publish();tick();
    put(vitals,0x8C,25.0f);put(vitals,0x90,25.0f);publish();tick();assert(frost_input.opened);
    pad_buttons=XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_Y;put(player.data(),0x470,uint32_t(0));publish();tick();
    pad_buttons=XINPUT_GAMEPAD_RIGHT_SHOULDER;memset(vitals,0,sizeof(vitals));publish();tick();
    pad_buttons|=XINPUT_GAMEPAD_Y;publish();tick();assert(boss_active_slot==5 && boss_active && dispatch->control.dispatch_count==1);
    constexpr float ends[]={24,40,20};
    for (unsigned phase=0;phase<3;++phase) {
        const unsigned slot=phase+5;assert(boss_active_slot==slot);
        put(motion.data(),0x58,boss_imports[slot].clip);
        for (float frame : {0.0f,ends[phase]-2,ends[phase]}) {
            put(player.data(),0x28,frame);put(player.data(),0x6A8,1.0f);put(player.data(),0x24,1.0f);
            assert(boss_advance_clock(player.data(),1)==1 && grapple_field(address(player.data()),0x28,frame));
        }
        if (phase<2) {SetLastError(FRAME_ERROR);assert(observed_action(player.data(),keys[phase+1],nullptr));}
    }
    for (float frame : {20.0f,24.0f,28.0f,29.0f,86.0f}) {
        put(player.data(),0x28,frame);put(player.data(),0x6A8,1.0f);put(player.data(),0x24,1.0f);
        assert(boss_advance_clock(player.data(),1)==1);
    }
    SetLastError(INCOMING);assert(observed_action(player.data(),0xBB8,nullptr));assert(!boss_active);bindings(false);
    boss_frost_variants[2]=0;boss_hold_stances=7;frost_input={};
}

static void frost_cases() {
    // Exercise same-stance rejection, genuine double edges and the exact750ms expiry.
    // Keep sampling continuous while testing controller/lifecycle resets and conflicting inputs.
    // Then pass the native Ki Pulse fields through the actual frame dispatcher and import adapter.
    boss_frost_milliseconds=750; // Explicit historical engine-policy fixture; production now fixes the native window.
    static uint8_t walk[0xD0]{},walk_payload[0xB0]{};
    put(walk,0x20,address(walk_payload));walk[0x40]=1;walk_payload[0x0B]=4;
    for (const auto& movement : {std::array<uint32_t,2>{0xC61,2030},{0xC9E,3030},{0xCDB,4030},
            {0xC65,2040},{0xCA2,3040},{0xCDF,4040}}) {
        put(walk,0,movement[0]);put(walk_payload,0x20,movement[1]);
        assert(frost_continuation(address(walk),movement[0]));
    }
    for (unsigned failure=0;failure<10;++failure) {
        FrostMoonInput input{}; GameInput sample{}; unsigned fired=0;
        for (unsigned tick=0;tick<90;++tick) {
            sample.qpc=1+tick*10000; sample.buttons[0]=XINPUT_GAMEPAD_RIGHT_SHOULDER;
            const unsigned second=failure==2 ? 76 : 30;
            const WORD face=failure==1 ? XINPUT_GAMEPAD_A : XINPUT_GAMEPAD_Y;
            if (tick==10 || tick==second || (failure==3 && tick>10 && tick<30)) sample.buttons[0]|=face;
            if (failure==4 && tick==20) sample.buttons[0]=0;
            if (failure==5 && tick==20) sample.buttons[0]|=XINPUT_GAMEPAD_B;
            if (failure==6 && tick==20) sample.buttons[0]|=XINPUT_GAMEPAD_LEFT_SHOULDER;
            sample.buttons[1]=sample.buttons[0];
            sample.packets[0]=failure==9 && tick>=20 ? 1 : 10;
            fired+=frost_edge(input,sample,failure==7 && tick>=20 ? 1 : 0,
                tick<10 ? 0 : 2,failure==8 && tick>=20 ? 1 : 0,tick>=1 && tick<15,0x10000,1000000);
        }
        assert(fired==(failure==0 || failure==4 ? 3u : 0u));
    }
    FrostMoonInput continued{}; GameInput continuous{};
    continuous.qpc=1; frost_edge(continued,continuous,0,0,0,false,0x10000,1000000);
    continuous.qpc=10001; frost_edge(continued,continuous,0,0,0,true,0x10000,1000000);
    continuous.qpc=20001; frost_edge(continued,continuous,0,0,0,true,0x10000,1000000);
    assert(continued.opened==10001);
    continuous.qpc=30001; frost_edge(continued,continuous,0,0,0,true,0x10000,1000000);
    assert(continued.opened==10001); // Refills cannot slide the window away from first availability.
    // A second consumer of the same published sample must not erase the first tap.
    // Stick motion can advance packets without adding a stance-button edge.
    // Keep the opportunity and its deadline while ignoring duplicate observations.
    FrostMoonInput duplicate{};GameInput sampled{};sampled.qpc=1;
    frost_edge(duplicate,sampled,0,0,0,false,0x10000,1000000);
    sampled.qpc=10001;frost_edge(duplicate,sampled,0,0,0,true,0x10000,1000000);
    sampled.qpc=20001;sampled.buttons[0]=XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_Y|XINPUT_GAMEPAD_LEFT_THUMB;
    frost_edge(duplicate,sampled,0,2,0,false,0x10000,1000000);
    const auto duplicate_deadline=duplicate.closes;
    assert(duplicate.choice==2);
    assert(!frost_edge(duplicate,sampled,0,2,0,false,0x10000,1000000));
    assert(duplicate.choice==2 && duplicate.closes==duplicate_deadline);
    sampled.qpc+=10000;sampled.packets[0]++;sampled.buttons[0]=XINPUT_GAMEPAD_RIGHT_SHOULDER;
    frost_edge(duplicate,sampled,0,2,0,false,0x10000,1000000);
    sampled.qpc+=10000;sampled.buttons[0]|=XINPUT_GAMEPAD_Y;
    assert(frost_edge(duplicate,sampled,0,2,0,false,0x10000,1000000)==3);
    // Native timers can outlive750ms and freeze; the first RB must not erase their remaining time.
    // Refill after consumption cannot extend the saved opportunity.
    // Verify expiry independently of native target stance changes.
    boss_frost_milliseconds=0;FrostMoonInput native_window{};GameInput native_sample{};native_sample.qpc=1;
    frost_edge(native_window,native_sample,0,0,0,false,0x10000,1000000,0);
    for (unsigned step=1;step<=45;++step) {
        native_sample.qpc=1+step*20000;native_sample.buttons[0]=step==45 ? WORD(XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_X) : 0;
        frost_edge(native_window,native_sample,0,0,0,true,0x10000,1000000,84-float(step)*1.2f);
    }
    assert(native_window.choice==1 && !native_window.spent && native_window.closes>native_sample.qpc);
    const auto native_end=native_window.closes;
    native_sample.qpc+=20000;native_sample.buttons[0]=0;
    frost_edge(native_window,native_sample,0,1,0,false,0x10000,1000000,0);
    native_sample.qpc+=20000;native_sample.buttons[0]=XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_X;
    assert(frost_edge(native_window,native_sample,0,1,0,true,0x10000,1000000,90)==2);
    assert(native_window.closes==native_end);
    boss_frost_milliseconds=750;
    // Native RB+A/X/Y commits low2/mid1/high0 before the second chord edge.
    // Replay all six recorded Flux routes, including both previously broken mid/high directions.
    // Assert the mapping at pulse capture, binding selection and private payload commit.
    constexpr unsigned native[]={2,1,0};
    constexpr WORD faces[]={XINPUT_GAMEPAD_A,XINPUT_GAMEPAD_X,XINPUT_GAMEPAD_Y};
    constexpr uint32_t flux_keys[3][3]={{0,0xD77,0xD78},{0xD74,0,0xD73},{0xD76,0xD75,0}};
    constexpr int32_t flux_motions[3][3]={{0,4006,4007},{2007,0,2006},{3007,3006,0}};
    for (unsigned movement=0;movement<3;++movement)
    for (unsigned origin=0;origin<3;++origin) for (unsigned target=0;target<3;++target) {
        if (origin==target) continue;
        boss_hold_stances=7;hold_reset(native[target],false);pending_heavy={};frost_input={};pad_buttons=0;
        boss_hold_stances=0;boss_frost_variants[target]=6;
        static uint8_t vitals[0xA0]{},flux[0xD0]{},flux_payload[0xB0]{};
        memset(vitals,0,sizeof(vitals));put(owner.data(),0x240,address(vitals));
        put(player.data(),0x470,uint32_t(native[origin]));publish();tick();
        put(vitals,0x8C,25.0f);put(vitals,0x90,25.0f);latch_native_frost();
        const auto opened=frost_input.opened;assert(opened && frost_input.origin==origin);
        if (movement) {
            constexpr uint32_t moving_keys[2][3]={{0xCDB,0xC9E,0xC61},{0xCDF,0xCA2,0xC65}};
            put(walk,0,moving_keys[movement-1][origin]);put(walk_payload,0x20,int32_t((4-origin)*1000+(movement==1 ? 30 : 40)));
            put(player.data(),0x58,address(walk));
        }
        pad_buttons=XINPUT_GAMEPAD_RIGHT_SHOULDER|faces[target]|(movement ? XINPUT_GAMEPAD_LEFT_THUMB : 0);
        put(player.data(),0x470,uint32_t(native[target]));publish();tick();
        assert(frost_input.choice==target && !boss_active);
        pad_buttons=0;memset(vitals,0,sizeof(vitals));publish();tick();
        put(flux,0,flux_keys[origin][target]);put(flux,0x20,address(flux_payload));
        put(flux_payload,0x20,flux_motions[origin][target]);flux_payload[0x0B]=uint8_t(native[target]);
        if (movement) {
            // Continue moving in the destination stance between the two chord edges.
            // No movement state may extend the timer or consume its first tap.
            // Damage and reconnect rejection are still exercised by the surrounding cases.
            constexpr uint32_t moving_keys[2][3]={{0xCDB,0xC9E,0xC61},{0xCDF,0xCA2,0xC65}};
            put(walk,0,moving_keys[movement-1][target]);put(walk_payload,0x20,int32_t((4-target)*1000+(movement==1 ? 30 : 40)));
            put(player.data(),0x58,address(walk));
        } else put(player.data(),0x58,address(flux));
        pad_buttons=XINPUT_GAMEPAD_RIGHT_SHOULDER|faces[target]|(movement ? XINPUT_GAMEPAD_LEFT_THUMB : 0);publish();tick();
        assert(boss_active && dispatch->control.dispatch_count==1 && frost_input.opened==opened);
        assert(boss_private_actions[5].payload[0x0B]==native[target]);
        boss_frost_variants[target]=0;
    }
    // Native action callbacks can see the opportunity before RB consumes its timer.
    boss_hold_stances=7;hold_reset(2);pending_heavy={};frost_input={};pad_buttons=0;
    boss_frost_variants[0]=6;
    static uint8_t early_vitals[0xA0]{};put(owner.data(),0x240,address(early_vitals));
    publish();tick();put(early_vitals,0x8C,25.0f);put(early_vitals,0x90,25.0f);
    latch_native_frost();assert(frost_input.opened);
    const auto earliest=frost_input.opened;memset(early_vitals,0,sizeof(early_vitals));
    publish();tick();assert(frost_input.opened==earliest);boss_frost_variants[0]=0;
    for (bool damage : {false,true}) {
    boss_hold_stances=7;
    hold_reset(0); pending_heavy={}; frost_input={}; pad_buttons=0;
    boss_hold_stances=1; boss_frost_variants[2]=6;
    static std::array<uint8_t,0xA0> vitals{};
    vitals.fill(0); put(owner.data(),0x240,address(vitals.data()));
    put(player.data(),0x470,uint32_t(2)); publish(); tick();
    // Ki Pulse opens in low stance before RB changes it to high.
    // Consuming the native pulse on the first tap must not erase the double-tap window.
    // The high-only Frost binding must leave ordinary high Triangle native.
    put(vitals.data(),0x8C,25.0f); put(vitals.data(),0x90,25.0f);
    publish(); tick();
    assert(frost_input.opened && frost_input.origin==0);
    pad_buttons=XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_Y;
    put(player.data(),0x470,uint32_t(0)); publish(); tick();
    assert(!boss_active && frost_input.choice==2);
    if (damage) {
        auto hurt=neutral; put(hurt.data(),0,uint32_t(0x3E8)); put(player.data(),0x58,address(hurt.data()));
        publish(); tick(); assert(frost_input.spent); put(player.data(),0x58,address(neutral.data()));
    }
    pad_buttons=XINPUT_GAMEPAD_RIGHT_SHOULDER; vitals.fill(0); publish(); tick();
    pad_buttons|=XINPUT_GAMEPAD_Y; publish(); tick();
    assert(bool(boss_active)==!damage && dispatch->control.dispatch_count==(damage ? 0 : 1));
    publish(); tick(); assert(dispatch->control.dispatch_count==(damage ? 0 : 1));
    boss_frost_variants[2]=0; boss_hold_stances=7; frost_input={};
    }
}

int main() {
    // Stress native input priority, resource isolation and recovery under rejected commits.
    // Run the three moves through ordinary setter calls with no armed controller gesture.
    // Moving entry, lock-on-independent selection and native running exclusions share this path.
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency=freq.QuadPart;
    held_slot_cases();
    weapon_policy_cases();
    airborne_cases();
    for (unsigned family=0;family<3;++family) mid_string_cases(family);
    tracking_cases();
    slam_cases();
    frost_cases();
    // Empty-Ki selection resolves D4A before the ordinary heavy opener.
    // Hold must defer that exact native selection; release replays the grapple entry.
    // Other stances and running descriptors must retain native selection.
    for (bool held : {false,true}) {
        hold_reset(); pending_heavy={};
        assert(!observed_action(player.data(),0xD4A,nullptr));
        assert(pending_heavy.active && !boss_active);
        if (held) pending_heavy.started-=frequency/4;
        else pad_buttons=0;
        publish(); tick();
        assert(!pending_heavy.active);
        if (held) assert(boss_active && boss_active_slot==5);
        else assert(!boss_active && same_field(address(player.data()),0x58,address(grapple_descriptor.data())));
    }
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
    assert(copy_field(contact_row+0x1B,impulse) && impulse==16 && launcher_combat[0x1B]==12);
    for (unsigned byte=0;byte<sizeof(launcher_combat);++byte) if (byte!=0x17 && byte!=0x1B) {
        uint8_t actual=0; assert(copy_field(contact_row+byte,actual) && actual==launcher_combat[byte]);
    }
    assert(boss_prepare_private_action(5));
    weight_cases();
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
    assert(copy_field(private_payload+0x24,combo) && combo==21);
    assert(copy_field(private_payload+0x26,cancel) && cancel==21);
    assert(copy_field(private_payload+0x38,pulse) && pulse==21);
    assert(copy_field(launcher.payload+0x24,source_recovery) && source_recovery==-1);
    unsigned pulses=0;
    for (unsigned i=0;i<boss_private_actions[5].transition_count;++i) {
        const auto* body=boss_private_actions[5].transition_bodies[i]; int16_t key=0,start=0;
        memcpy(&key,body+0x14,2); memcpy(&start,body+0x20,2);
        if (key==0xD5F) { assert(start==21); ++pulses; }
    }
    assert(pulses==3);
    original_frame=native_clock_frame; put(motion.data(),0x58,launcher.clip);
    for (const auto& sample : {std::array<float,2>{0,2},{6.5f,1.5f},{7,1},{8,1},{12,1},{20,1},{21,1},{53,1},{60,1},{64,1},{65,1}}) {
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
    launcher.motion=5014;
    ++launcher.transition_count;
    assert(boss_move_timing(5).recovery==-1 && boss_move_timing(5).startup_speed==1);
    std::puts("native replacement checks passed: three stance holds, native mid/high taps, three-link heavy, camera-independent input, cancellations and LastError");
}
