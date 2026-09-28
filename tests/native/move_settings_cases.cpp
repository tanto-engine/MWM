#define main inherited_frame_main
#include "frame_dispatch_cases.cpp"
#undef main

int main() {
    // Run the frame dispatcher at 0.5x and 1.5x against owned player and payload fixtures.
    // Check private Ki Pulse fields and playback deltas while shared payload and frame cursor stay unchanged.
    // Paired actions and a neutral player retain native delta; ordinary Frost playback honors configured speed.
    LARGE_INTEGER f;QueryPerformanceFrequency(&f);frequency=f.QuadPart;
    for (float rate : {.5f,1.5f}) {
        reset();boss_move_settings[0]={rate,65,18,35,0};
        const auto source=payload;
        tick();assert(boss_active && payload==source);
        const auto* adapted=boss_private_actions[0].payload;
        int16_t onset=0,fill=0,hold=0,recovery=0;
        memcpy(&recovery,adapted+0x24,2);memcpy(&onset,adapted+0x38,2);
        memcpy(&fill,adapted+0x3A,2);memcpy(&hold,adapted+0x3C,2);
        assert(adapted[0x33]==65 && recovery==54 && onset==54 && fill==18 && hold==35);
        boss_imports[0].clip=0x23450000;
        put(motion.data(),0x58,boss_imports[0].clip);
        put(player.data(),0x28,60.0f);put(player.data(),0x6A8,1.0f);put(player.data(),0x24,.25f);
        assert(boss_advance_clock(player.data(),.25f)==.25f*rate);
        float frame=0;assert(copy_field(address(player.data())+0x28,frame) && frame==60);
        for (bool frost : {false,true}) {
            boss_frost_playback=frost;
            if (!frost) boss_imports[0].flags=0x8038000000ULL;
            put(player.data(),0x6A8,1.0f);put(player.data(),0x24,.25f);
            assert(boss_advance_clock(player.data(),.25f)==.25f*(frost ? rate : 1));
            boss_imports[0].flags=0x184C0000;
        }
        boss_frost_playback=false;
        put(player.data(),0x58,address(neutral.data()));put(player.data(),0x24,.25f);
        assert(boss_advance_clock(player.data(),.25f)==.25f);
        boss_move_settings[0]={};
    }
    std::puts("move settings passed: whole playback, private Pulse, native paired speed, configurable Frost speed, unchanged frame cursor");
}
