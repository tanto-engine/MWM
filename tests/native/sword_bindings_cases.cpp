#define main inherited_frame_main
#include "frame_dispatch_cases.cpp"
#undef main

static std::array<uint8_t,0xD0> light{},living{},tiger{};
static std::array<uint8_t,0xB0> light_payload{},living_payload{},tiger_payload{};
static std::array<std::array<uint8_t,0x30>,46> light_rows{};
static std::array<uint64_t,46> light_pointers{};
static uint32_t sword_bank;
static bool tiger_assigned;

static bool sword_skill(void* actor, int32_t skill) {
    // Model the native stance/loadout gate used by the recorded Tiger transition.
    // Require the concrete fixture player and Tiger's recorded skill identifier.
    // Changing assignment must retain ordinary sheathing and Iai behavior.
    assert(actor==player.data() && skill==0x4AFB);
    return tiger_assigned;
}

static uint64_t sword_lookup(void*, uint32_t key, uint32_t* bank) {
    // Resolve owned William descriptors independently of the source boss imports.
    // Preserve normal bank0 selection for ordinary sword moves.
    // The adapter must reject any descriptor whose recorded signature changes.
    *bank=sword_bank;
    if (key==0xD3A) return address(living.data());
    if (key==0xFAA) return address(tiger.data());
    return address(light.data());
}

static void sword_reset(unsigned index) {
    // Build each recorded mid-light window with distinguishable native remainder rows.
    // Owned metadata matches the player capture while all addresses belong to this process.
    // Assertions can compare every copied row and confirm source memory remains unchanged.
    reset(); original_lookup=sword_lookup; boss_native_bindings=4;sword_bank=0;
    for (auto& binding : boss_skill_bindings) binding={};
    for (auto& adapter : boss_adapters) adapter={};
    for (auto& item : mid_light_actions) item={};
    light.fill(0); living.fill(0); tiger.fill(0); light_payload.fill(0); living_payload.fill(0); tiger_payload.fill(0);
    put(light.data(),0,uint32_t(0xC76+index)); light[0x40]=1;
    put(light.data(),0x20,address(light_payload.data())); put(light.data(),0x82,uint16_t(46));
    put(light.data(),0x78,address(light_pointers.data()));
    light_payload[0x0B]=index ? 4 : 1;put(player.data(),0x470,uint32_t(1));
    put(light_payload.data(),0x18,uint64_t(0x8000000594C0000ULL)); put(light_payload.data(),0x20,int32_t(2100+index*10));
    put(living.data(),0,uint32_t(0xD3A)); living[0x40]=1; put(living.data(),0x20,address(living_payload.data()));
    put(living_payload.data(),0x18,uint64_t(0x194C0000)); put(living_payload.data(),0x20,int32_t(9210));
    put(tiger.data(),0,uint32_t(0xFAA)); tiger[0x40]=1; put(tiger.data(),0x20,address(tiger_payload.data()));
    put(tiger.data(),0x82,uint16_t(21)); put(tiger_payload.data(),0x18,uint64_t(0x40017C00000ULL));
    put(tiger_payload.data(),0x20,int32_t(5090));
    for (unsigned row=0;row<46;++row) { light_rows[row].fill(uint8_t(row)); light_pointers[row]=address(light_rows[row].data()); }
    for (unsigned row=0;row<2;++row) {
        auto& body=light_rows[7+row]; body.fill(0xff); body[0x0A]=row ? 0 : 2; body[0x0B]=1; body[0x0C]=1;
        put(body.data(),2,uint16_t(0x51));put(body.data(),0x14,int16_t(0xFA5));
        put(body.data(),0x20,int16_t(row ? (index==0 ? 24 : index==1 ? 26 : 31) : index==0 ? 5 : 10));
        put(body.data(),0x22,int16_t(row ? (index==0 ? 54 : index==1 ? 56 : 61) : (index==0 ? 23 : index==1 ? 25 : 30)));
    }
    command.armed=0; publish_player_context(.25f); publish();
}

static void guard_binding_cases() {
    // Native-selected rows retain input timing independently of loadout and destination move.
    // Move the same binding across all stances and both baseline target variants.
    // Reject ordinary/running/dodge Square, Triangle, stale rows, disabled contexts and nonplayer banks.
    static std::array<uint8_t,0xD0> guard{};
    constexpr uint32_t stances[]={2,1,0};
    for (unsigned stance=0;stance<3;++stance) for (uint32_t loadout : {0xFA2u,0xCF8u})
    for (unsigned failure=0;failure<17;++failure) {
        uint32_t key=loadout;
        sword_reset(0);boss_native_bindings=0;
        boss_skill_bindings[0]={2,1u<<stance,loadout==0xFA2 ? 1u : 2u,0,0,0,0};
        guard.fill(0);put(light.data(),0,key);put(guard.data(),0x78,address(light_pointers.data()));
        put(guard.data(),0x80,uint16_t(3));put(guard.data(),0x82,uint16_t(40));
        auto& row=light_rows[6];row.fill(0xff);row[0x0A]=key==0xFA2 ? 0 : 2;
        row[0x0B]=5;row[0x0C]=0;row[0x0D]=0;row[0x0E]=1;
        put(row.data(),0x14,int16_t(key));put(row.data(),0x2C,int32_t(0x3580));
        put(player.data(),0x58,address(guard.data()));put(player.data(),0x90,address(row.data()));
        put(player.data(),0x470,stances[stance]);
        if (failure==1 || failure==2) put(player.data(),0x470,stances[(stance+failure)%3]);
        if (failure==3 || failure==4) {row[0x0B]=0;row[0x0C]=1;row[0x0D]=0xff;row[0x0E]=0xff;}
        if (failure==4) {key=0xCD5;put(light.data(),0,key);put(row.data(),0x14,int16_t(key));}
        if (failure==5) {row[0x0B]=2;row[0x0C]=1;row[0x0D]=0xff;row[0x0E]=0xff;}
        if (failure==6) row[0x0D]=1;
        if (failure==7) {light_rows[0]=row;put(player.data(),0x90,address(light_rows[0].data()));}
        if (failure==8) boss_skill_bindings[0]={};
        if (failure==9) sword_bank=1;
        if (failure==10) put(row.data(),0x14,int16_t(key+1));
        if (failure==11) row[0x0A]=0xff;
        if (failure==12) light[0x40]=0;
        if (failure==13) boss_skill_bindings[0].stances=0;
        if (failure==14) dispatch->control.enabled=0;
        if (failure>=15) boss_active=1;
        if (failure==16) boss_imports[boss_active_slot].flags=0x8078000000ULL;
        DispatchCommand request{};
        if (failure==9) {
            DispatchReason reason=Disabled;ReplacementScope scope(player.data(),request,reason);uint32_t bank=0;
            assert(observed_lookup(player.data()+0x70,key,&bank)==address(light.data()) && bank==1);
        } else assert(native_bound_slot(key,address(light.data()),request)==(failure && failure!=15 ? -1 : int(boss_skill_bindings[0].variant-1)));
    }
}

static void tiger_entry_cases() {
    // Reproduce the two preparation entries before the recorded FAA attack.
    // Test native input ownership, stance assignment and disabled/stale contexts.
    // Mid Tiger must substitute immediately while unrelated sheathing remains native.
    static std::array<uint64_t,49> methods{};
    for (uint32_t key : {0xBBAu,0xD46u}) for (unsigned failure=0;failure<13;++failure) {
        sword_reset(0);boss_native_bindings=0;tiger_assigned=failure!=1;
        methods[0x180/8]=reinterpret_cast<uint64_t>(sword_skill);
        boss_session.vtable=address(methods.data());put(player.data(),0,boss_session.vtable);
        command.vtable=boss_session.vtable;publish();
        boss_skill_bindings[0]={1,7,1,0xFAA,5090,21,0x40017C00000ULL};
        put(light.data(),0,key);put(light_payload.data(),0x20,int32_t(key==0xBBA ? -1 : 5000));
        put(light_payload.data(),0x18,uint64_t(key==0xBBA ? 0 : 0x194C0000));
        put(light.data(),0x82,uint16_t(key==0xBBA ? 13 : 49));
        put(player.data(),0x58,address(neutral.data()));put(neutral.data(),0x78,address(light_pointers.data()));
        put(neutral.data(),0x80,uint16_t(0));put(neutral.data(),0x82,uint16_t(46));
        auto& row=light_rows[0];row.fill(0xff);row[0x0A]=0;row[0x0B]=0x14;row[0x0C]=1;
        put(row.data(),0x14,int16_t(key));put(row.data(),0x2C,int32_t(key==0xBBA ? -1 : 0x4AFB));
        put(player.data(),0x90,address(row.data()));
        if (failure==2 || failure==3) put(player.data(),0x470,uint32_t(failure==2 ? 0 : 2));
        if (failure==4) row[0x0B]=0;
        if (failure==5) row[0x0C]=3;
        if (failure==6) put(player.data(),0x90,address(dodge_row.data()));
        if (failure==7) boss_skill_bindings[0]={};
        if (failure==8) dispatch->control.enabled=0;
        if (failure==9) put(light_payload.data(),0x20,int32_t(2004));
        if (failure==10) boss_skill_bindings[0].stances=1;
        if (failure==11) put(row.data(),0x2C,int32_t(2020));
        if (failure==12) {
            GameInput input{};input.sequence=2;LARGE_INTEGER now;QueryPerformanceCounter(&now);input.qpc=now.QuadPart;
            input.buttons[0]=XINPUT_GAMEPAD_LEFT_SHOULDER|XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_B;
            memcpy(trace->header.reserved,&input,sizeof(input));
        }
        DispatchCommand request{};
        assert(native_bound_slot(key,address(light.data()),request)==(failure ? -1 : 0));
        DispatchReason reason=Disabled;ReplacementScope scope(player.data(),request,reason);uint32_t bank=0;
        const auto result=observed_lookup(player.data()+0x70,key,&bank);
        assert(result==(failure ? address(light.data()) : boss_private_descriptor_address(0)));
        assert(bank==(failure ? 0u : 1u));
    }
}

int main() {
    // Verify native trigger ownership, untouched running actions, source isolation and Stop.
    // Exercise both replacement branches through the actual scoped lookup hook.
    // These checks establish descriptor behavior; actual combat playback still needs the player.
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency=freq.QuadPart;
    guard_binding_cases();
    tiger_entry_cases();
    for (unsigned index=0;index<3;++index) {
        sword_reset(index); const auto before=light; const auto rows=light_rows;
        DispatchReason reason=Disabled; DispatchCommand request{}; ReplacementScope scope(player.data(),request,reason);
        uint32_t bank=0;
        const auto adapted=observed_lookup(player.data()+0x70,0xC76+index,&bank);
        assert(adapted && adapted!=address(light.data()) && bank==0 && light==before && light_rows==rows);
        const auto& clone=mid_light_actions[index];
        for (unsigned row=0;row<46u;++row) assert(!memcmp(clone.rows[row+2],rows[row].data(),0x30));
        for (unsigned row=0;row<2;++row) {
            assert(grapple_field(address(clone.rows[row]),0x14,int16_t(0xD3A)));
            assert(clone.rows[row][0x0B]==1 && clone.rows[row][0x0C]==1 && clone.rows[row][0x0D]==5 && clone.rows[row][0x0E]==0);
            assert(grapple_field(address(clone.rows[row]),0x2C,int32_t(-1)));
        }
        assert(observed_lookup(player.data()+0x70,0xC76+index,&bank)==adapted);
        put(player.data(),0x58,adapted); dispatch->control.enabled=0;
        const unsigned calls=action_calls;
        assert(!observed_action(player.data(),0xD3A,nullptr) && action_calls==calls && mid_light_active());
        put(player.data(),0x50,uint64_t(0x99999)); assert(!mid_light_active());
        put(player.data(),0x50,boss_session.player_owner); assert(mid_light_active());
        put(player.data(),0x58,address(neutral.data())); assert(!mid_light_active());
        dispatch->control.enabled=1;
        put(living_payload.data(),0x20,int32_t(999));
        assert(observed_lookup(player.data()+0x70,0xC76+index,&bank)==address(light.data()));
    }
    for (bool enabled : {false,true}) for (bool signature : {false,true}) for (unsigned stance=0;stance<3;++stance) {
        sword_reset(0);boss_native_bindings=0;
        put(player.data(),0x470,stance);
        if (enabled) boss_skill_bindings[0]={1,7,1,0xFAA,5090,21,0x40017C00000ULL};
        if (!signature) put(tiger_payload.data(),0x20,int32_t(5000));
        DispatchReason reason=Disabled;DispatchCommand request{};ReplacementScope scope(player.data(),request,reason);
        uint32_t bank=0;const auto result=observed_lookup(player.data()+0x70,0xFAA,&bank);
        assert((result==boss_private_descriptor_address(0))==(enabled&&signature));
        assert(dispatch->control.dispatch_count==(enabled&&signature ? 1 : 0));
        assert(observed_lookup(player.data()+0x70,0xCD5,&bank)==address(light.data()));
    }
    // Triangle dodge selects BC8/BC9 before the shared D52/D53 attack, not CFD.
    // Keep Square dodge, running, wrong stances and stale rows out of this binding.
    // Both buffered and immediate selections enter the configured Low or Mid string slot.
    for (unsigned stance : {1u,2u}) for (uint32_t key : {0xBC8u,0xBC9u}) for (unsigned failure=0;failure<5;++failure) {
        sword_reset(0);put(player.data(),0x470,stance);
        put(light.data(),0,key);put(light.data(),0x82,uint16_t(key==0xBC8 ? 18 : 19));
        put(light_payload.data(),0x20,int32_t(-1));put(light_payload.data(),0x18,uint64_t(0));
        put(player.data(),0x58,address(neutral.data()));put(neutral.data(),0x78,address(light_pointers.data()));
        put(neutral.data(),0x80,uint16_t(0));put(neutral.data(),0x82,uint16_t(46));
        auto& row=light_rows[0];row.fill(0xff);row[0x0A]=key==0xBC8 ? 2 : 0;row[0x0B]=1;row[0x0C]=1;
        put(row.data(),0x14,int16_t(key));put(player.data(),0x90,address(row.data()));
        boss_skill_bindings[0]={1,1u<<(2-stance),2,0xBC8,-1,18,0};
        if (failure==1) row[0x0B]=0;
        if (failure==2) put(player.data(),0x470,uint32_t(0));
        if (failure==3) put(player.data(),0x90,address(dodge_row.data()));
        if (failure==4) {put(light.data(),0,uint32_t(0xCFC));put(light_payload.data(),0x20,int32_t(4720));}
        DispatchCommand dodge{};assert(native_bound_slot(key,address(light.data()),dodge)==(failure ? -1 : 1));
    }
    // Native Tiger selection can choose another destination without interpreting controller buttons.
    // Clear the target variant after a disabled run to expose any hardcoded C64 route.
    // Selection itself is independent of private source resource preparation.
    sword_reset(0);put(player.data(),0x470,uint32_t(1));
    boss_skill_bindings[0]={1,2,2,0xFAA,5090,21,0x40017C00000ULL};
    DispatchCommand selected{};assert(native_bound_slot(0xFAA,address(tiger.data()),selected)==1);
    boss_skill_bindings[0].stances=4;
    assert(native_bound_slot(0xFAA,address(tiger.data()),selected)==-1);
    // Baseline-only presets still need the lookup hook for explicit native/chord bindings.
    // No Jin adapter, grapple or mid-light flag may accidentally mask this dependency.
    // Removing the last binding releases the hook requirement again.
    boss_import_count=2;boss_native_bindings=0;boss_native_grapple=0;
    for (auto& adapter : boss_adapters) adapter={};
    for (auto& binding : boss_skill_bindings) binding={};
    assert(!replacements_configured());
    boss_skill_bindings[0]={1,7,1,0xFAA,5090,21,0x40017C00000ULL};assert(replacements_configured());
    boss_skill_bindings[0]={2,4,2,0,0,0,0};assert(replacements_configured());
    boss_skill_bindings[0]={};assert(!replacements_configured());
    std::puts("native sword bindings passed: three mid-light enders, scoped Tiger Sprint, native running and disabled rejection");
}
