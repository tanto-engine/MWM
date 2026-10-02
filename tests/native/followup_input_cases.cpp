#define main frame_dispatch_baseline_main
#include "frame_dispatch_cases.cpp"
#undef main

int main() {
    LARGE_INTEGER clock;QueryPerformanceFrequency(&clock);frequency=clock.QuadPart;
    unsigned failures=0;
    for (unsigned family=1;family<=2;++family) {
        const WORD trigger=family==1 ? XINPUT_GAMEPAD_Y : XINPUT_GAMEPAD_X;
        const WORD extras[]={0,0,0,0,WORD(family==1 ? XINPUT_GAMEPAD_X : XINPUT_GAMEPAD_Y),
            XINPUT_GAMEPAD_B,XINPUT_GAMEPAD_A,XINPUT_GAMEPAD_START,XINPUT_GAMEPAD_BACK,
            XINPUT_GAMEPAD_RIGHT_SHOULDER,WORD(XINPUT_GAMEPAD_LEFT_THUMB|XINPUT_GAMEPAD_RIGHT_THUMB),
            XINPUT_GAMEPAD_DPAD_UP,XINPUT_GAMEPAD_DPAD_DOWN,XINPUT_GAMEPAD_DPAD_LEFT,XINPUT_GAMEPAD_DPAD_RIGHT};
        for (unsigned scenario=0;scenario<std::size(extras);++scenario) {
            reset();attack_followup_input={};
            for (auto& binding : boss_skill_bindings) binding={};
            boss_skill_bindings[0]={family==1 ? 7u : 4u,4,1,0,0,0,0};
            state(family==1 ? 0xCB3 : 0xCB7,family==1 ? 3100 : 3300,0);
            put(neutral_payload.data(),0x18,uint64_t(0x8000000594C0000ULL));
            put(neutral_payload.data(),0x24,int16_t(1));put(player.data(),0x28,2.0f);
            put(player.data(),0x470,uint32_t(0));put(player.data(),0xDC,uint32_t(22));
            cast_sample(XINPUT_GAMEPAD_LEFT_SHOULDER);
            auto& sample=*reinterpret_cast<GameInput*>(own_trace.header.reserved);sample.packets[0]=10;
            DispatchCommand request{};assert(choose_attack_followup(request)==IneligibleRequest);
            cast_sample(XINPUT_GAMEPAD_LEFT_SHOULDER|trigger|extras[scenario]);
            sample.packets[0]=scenario==1 ? 1 : 11;
            sample.left_trigger[0]=scenario==2 ? 31 : 0;sample.right_trigger[0]=scenario==3 ? 31 : 0;
            const auto expected=scenario==0 || scenario==10 ? Accepted : IneligibleRequest;
            const auto actual=choose_attack_followup(request);
            if (actual!=expected) {
                std::fprintf(stderr,"follow-up family%u scenario%u: expected%u got%u\n",family,scenario,expected,actual);
                ++failures;
            } else if (scenario==1) {
                // A replaced controller must release and press again; holding cannot replay the edge.
                cast_sample(XINPUT_GAMEPAD_LEFT_SHOULDER|trigger);sample.packets[0]=2;
                assert(choose_attack_followup(request)==IneligibleRequest);
                cast_sample(XINPUT_GAMEPAD_LEFT_SHOULDER);sample.packets[0]=3;
                assert(choose_attack_followup(request)==IneligibleRequest);
                cast_sample(XINPUT_GAMEPAD_LEFT_SHOULDER|trigger);sample.packets[0]=4;
                assert(choose_attack_followup(request)==Accepted);
            }
        }
    }
    assert(!failures);
    std::puts("native follow-up input checks passed: reconnects, core controls and lock-on independence");
}
