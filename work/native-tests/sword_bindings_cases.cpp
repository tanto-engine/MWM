#define main inherited_frame_main
#include "frame_dispatch_cases.cpp"
#undef main

static std::array<uint8_t,0xD0> light{},living{},tiger{};
static std::array<uint8_t,0xB0> light_payload{},living_payload{},tiger_payload{};
static std::array<std::array<uint8_t,0x30>,46> light_rows{};
static std::array<uint64_t,46> light_pointers{};

static uint64_t sword_lookup(void*, uint32_t key, uint32_t* bank) {
    // Resolve owned William descriptors independently of the source boss imports.
    // Preserve normal bank0 selection for ordinary sword moves.
    // The adapter must reject any descriptor whose recorded signature changes.
    *bank=0;
    if (key==0xD3A) return address(living.data());
    if (key==0xFAA) return address(tiger.data());
    return address(light.data());
}

static void sword_reset(unsigned index) {
    // Build each recorded mid-light window with distinguishable native remainder rows.
    // Owned metadata matches the player capture while all addresses belong to this process.
    // Assertions can compare every copied row and confirm source memory remains unchanged.
    reset(); original_lookup=sword_lookup; boss_native_bindings=6;
    for (auto& item : mid_light_actions) item={};
    light.fill(0); living.fill(0); tiger.fill(0); light_payload.fill(0); living_payload.fill(0); tiger_payload.fill(0);
    put(light.data(),0,uint32_t(0xCB3+index)); light[0x40]=1;
    put(light.data(),0x20,address(light_payload.data())); put(light.data(),0x82,uint16_t(index==2 ? 44 : 46));
    put(light.data(),0x78,address(light_pointers.data()));
    put(light_payload.data(),0x18,uint64_t(0x8000000594C0000ULL)); put(light_payload.data(),0x20,int32_t(3100+index*10));
    put(living.data(),0,uint32_t(0xD3A)); living[0x40]=1; put(living.data(),0x20,address(living_payload.data()));
    put(living_payload.data(),0x18,uint64_t(0x194C0000)); put(living_payload.data(),0x20,int32_t(9210));
    put(tiger.data(),0,uint32_t(0xFAA)); tiger[0x40]=1; put(tiger.data(),0x20,address(tiger_payload.data()));
    put(tiger.data(),0x82,uint16_t(21)); put(tiger_payload.data(),0x18,uint64_t(0x40017C00000ULL));
    put(tiger_payload.data(),0x20,int32_t(5090));
    for (unsigned row=0;row<46;++row) { light_rows[row].fill(uint8_t(row)); light_pointers[row]=address(light_rows[row].data()); }
    for (unsigned row=0;row<2;++row) {
        auto& body=light_rows[7+row]; body.fill(0xff); body[0x0A]=row ? 0 : 2; body[0x0B]=1; body[0x0C]=1;
        put(body.data(),0x14,int16_t(0xD67)); put(body.data(),0x20,int16_t(row ? (index==0 ? 40 : index==1 ? 44 : 52) : 10));
        put(body.data(),0x22,int16_t(row ? (index==0 ? 70 : index==1 ? 74 : 82) : (index==0 ? 39 : index==1 ? 43 : 51)));
    }
    command.armed=0; publish_player_context(.25f); publish();
}

int main() {
    // Verify native trigger ownership, untouched running actions, source isolation and Stop.
    // Exercise both replacement branches through the actual scoped lookup hook.
    // These checks establish descriptor behavior; actual combat playback still needs the player.
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency=freq.QuadPart;
    for (unsigned index=0;index<3;++index) {
        sword_reset(index); const auto before=light; const auto rows=light_rows;
        DispatchReason reason=Disabled; DispatchCommand request{}; ReplacementScope scope(player.data(),request,reason);
        uint32_t bank=0;
        const auto adapted=observed_lookup(player.data()+0x70,0xCB3+index,&bank);
        assert(adapted && adapted!=address(light.data()) && bank==0 && light==before && light_rows==rows);
        const auto& clone=mid_light_actions[index];
        for (unsigned row=0;row<(index==2 ? 44u : 46u);++row) assert(!memcmp(clone.rows[row+2],rows[row].data(),0x30));
        for (unsigned row=0;row<2;++row) {
            assert(grapple_field(address(clone.rows[row]),0x14,int16_t(0xD3A)));
            assert(clone.rows[row][0x0B]==1 && clone.rows[row][0x0C]==1 && clone.rows[row][0x0D]==5 && clone.rows[row][0x0E]==0);
            assert(grapple_field(address(clone.rows[row]),0x2C,int32_t(-1)));
        }
        assert(observed_lookup(player.data()+0x70,0xCB3+index,&bank)==adapted);
        put(player.data(),0x58,adapted); dispatch->control.enabled=0;
        const unsigned calls=action_calls;
        assert(!observed_action(player.data(),0xD3A,nullptr) && action_calls==calls && mid_light_active());
        put(player.data(),0x50,uint64_t(0x99999)); assert(!mid_light_active());
        put(player.data(),0x50,boss_session.player_owner); assert(mid_light_active());
        put(player.data(),0x58,address(neutral.data())); assert(!mid_light_active());
        dispatch->control.enabled=1;
        put(living_payload.data(),0x20,int32_t(999));
        assert(observed_lookup(player.data()+0x70,0xCB3+index,&bank)==address(light.data()));
    }
    for (bool enabled : {false,true}) for (bool signature : {false,true}) {
        sword_reset(0); boss_native_bindings=enabled ? 2 : 0;
        if (!signature) put(tiger_payload.data(),0x20,int32_t(5000));
        DispatchReason reason=Disabled; DispatchCommand request{}; ReplacementScope scope(player.data(),request,reason);
        uint32_t bank=0; const auto result=observed_lookup(player.data()+0x70,0xFAA,&bank);
        assert((result==boss_private_descriptor_address(0))==(enabled&&signature));
        assert(dispatch->control.dispatch_count==(enabled&&signature ? 1 : 0));
        assert(observed_lookup(player.data()+0x70,0xCD5,&bank)==address(light.data()));
    }
    std::puts("native sword bindings passed: three mid-light enders, scoped Tiger Sprint, native running and disabled rejection");
}
