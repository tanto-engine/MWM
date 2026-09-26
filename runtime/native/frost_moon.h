#pragma once

struct FrostMoonInput {
    int64_t opened, sampled, closes;
    uint64_t descriptor;
    unsigned origin, choice, stance, slot, epoch;
    WORD buttons;
    bool available, spent, consumed;
    DWORD packet;
};
static FrostMoonInput frost_input{};

static void frost_window(FrostMoonInput& state, int64_t now, unsigned stance,
        uint64_t descriptor, bool available, int64_t frequency, float remaining=0) {
    // Latch the first native D5 opportunity, before RB can consume its Ki timer.
    // Follow native remaining Ki time; after RB consumes it, retain the last native expiry.
    // A subsequent attack can open a new window after this one is spent or expired.
    if (available && !state.available && (!state.opened || state.spent
        || now>=state.closes)) {
        state.opened=now;state.origin=stance;state.descriptor=descriptor;state.choice=3;state.spent=false;state.consumed=false;
        state.closes=now+frequency*int64_t(boss_frost_milliseconds)/1000;
    }
    if (state.opened && state.available && !available) state.consumed=true;
    if (!boss_frost_milliseconds && available && state.opened && !state.spent && !state.consumed
        && std::isfinite(remaining) && remaining>0) state.closes=now+int64_t(remaining*float(frequency)/60);
    state.available=available;
}

static void latch_native_frost() {
    // Observe Ki availability before native action selection consumes the pulse.
    // Reuse the current frame's device/lifecycle observation without generating input edges.
    // This closes the same-frame RB race without an additional hook or direct Ki write.
    uint64_t vitals=0,current=0;uint32_t stance=0;float pulse[4]{};GameInput sample{};
    if (!frost_input.sampled || !trace || !dispatch || !dispatch->control.enabled || !boss_player_valid()
        || !read_game_input(trace->header,sample) || !copy_field(boss_session.player+0x470,stance) || stance>2
        || !copy_field(boss_session.player_owner+0x240,vitals) || !copy_bytes(vitals+0x8C,pulse,sizeof(pulse))
        || !copy_field(boss_session.player+0x58,current)) return;
    LARGE_INTEGER now;QueryPerformanceCounter(&now);
    frost_window(frost_input,now.QuadPart,2-stance,current,
        pulse[0]+pulse[2]>0 && (pulse[1]>0 || pulse[3]>0),dispatch->control.qpc_frequency,
        (pulse[1]>0 ? pulse[1] : 0)+(pulse[3]>0 ? pulse[3] : 0));
}

static unsigned frost_edge(FrostMoonInput& state, const GameInput& sample, unsigned slot,
        unsigned stance, unsigned epoch, bool available, uint64_t descriptor, int64_t frequency, float remaining=0) {
    // Start one wall-clock window on the native Ki Pulse availability edge.
    // Accept two distinct RB/face chord edges, including releasing and repressing RB.
    // Device, lifecycle and sampling gaps discard the window without replaying held inputs.
    const WORD buttons=sample.buttons[slot];
    const bool reset=!state.sampled || state.slot!=slot || state.epoch!=epoch
        || sample.qpc<=state.sampled || sample.qpc-state.sampled>=frequency/10 || sample.packets[slot]<state.packet;
    if (reset) {
        state={0,sample.qpc,0,descriptor,stance,3,stance,slot,epoch,buttons,available,false,false,sample.packets[slot]};
        return 0;
    }
    const WORD pressed=buttons&~state.buttons;
    frost_window(state,sample.qpc,state.stance,descriptor,available,frequency,remaining);
    state.sampled=sample.qpc;state.stance=stance;state.buttons=buttons;state.packet=sample.packets[slot];
    if (!state.opened || state.spent || sample.qpc>=state.closes) return 0;
    constexpr WORD faces=XINPUT_GAMEPAD_A|XINPUT_GAMEPAD_X|XINPUT_GAMEPAD_Y;
    constexpr WORD cancel=XINPUT_GAMEPAD_B|XINPUT_GAMEPAD_LEFT_SHOULDER|XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK;
    if ((buttons&cancel) || sample.left_trigger[slot]>30 || sample.right_trigger[slot]>30) {
        state.spent=true; return 0;
    }
    if (!(buttons&XINPUT_GAMEPAD_RIGHT_SHOULDER)) return 0;
    const WORD face=buttons&faces;
    if (!face) return 0;
    if (!(pressed&(faces|XINPUT_GAMEPAD_RIGHT_SHOULDER))) return 0;
    const unsigned choice=face==XINPUT_GAMEPAD_A ? 0 : face==XINPUT_GAMEPAD_X ? 1 : face==XINPUT_GAMEPAD_Y ? 2 : 3;
    if (choice==3 || choice==state.origin) { state.choice=3; return 0; }
    if (state.choice!=choice) { state.choice=choice; return 0; }
    state.spent=true;
    return choice+1;
}

static bool frost_continuation(uint64_t descriptor, uint32_t key) {
    // Native Pulse and Flux redirects are control states, not interruptions.
    // A recognized chord may also override its accidental light/heavy/dodge action.
    // Damage, paired animations and unrelated actions still invalidate the opportunity.
    uint64_t payload=0;int32_t motion=0;
    if (repeat_current_allowed(descriptor,key)) return true;
    if (!copy_field(descriptor+0x20,payload) || !copy_field(payload+0x20,motion)) return false;
    // Recorded free/lock-on locomotion retains the same first-availability deadline.
    // High has one extra3022 row; normalize its subsequent offsets to the common sword layout.
    // Exact native key/motion/stance pairs exclude imported collisions and running attacks.
    constexpr uint32_t starts[]={0xC5B,0xC97,0xCD5};
    constexpr int offsets[]={20,21,23,30,40,41,30,31,32,33,40,41,42,43,44,45,46,47};
    uint8_t stance=0,enabled=0;
    if (copy_field(payload+0x0B,stance) && stance==4 && copy_field(descriptor+0x40,enabled) && enabled)
        for (unsigned group=0;group<3;++group) if (key>=starts[group] && key<starts[group]+18+(group==1)) {
            unsigned index=key-starts[group];
            if (group==1 && index==2) return motion==3022;
            if (group==1 && index>2) --index;
            return motion==int((group+2)*1000)+offsets[index];
        }
    if (key>=0xD60 && key<=0xD62) return motion==2009+int(key-0xD60)*1000;
    if (key>=0xD73 && key<=0xD78) return motion==2006+int((key-0xD73)/2)*1000+int((key-0xD73)%2);
    if (frost_input.choice>=3) return false;
    if (key==9 && motion==10) return true;
    constexpr uint32_t openers[]={0xC76,0xC7A,0xCB3,0xCB7,0xCF0,0xCF5};
    constexpr int32_t motions[]={2100,2300,3100,3300,4100,4300};
    for (unsigned index=0;index<6;++index)
        if (key>=openers[index] && key<=openers[index]+2 && motion==motions[index]+int(key-openers[index])*10) return true;
    return false;
}

static DispatchReason choose_frost_moon(DispatchCommand& command) {
    // Native conditionD5 calls7AFDF0 on owner+240+40: positive duration and remaining fill/hold.
    // Observe those four floats without writing Ki or changing native stance inputs.
    // Dispatch only a configured skill after its double tap and fresh player/resource checks.
    GameInput sample{}; unsigned connected=0,slot=0; uint32_t stance=0; uint64_t vitals=0,current=0; float pulse[4]{};
    if (!trace || !read_game_input(trace->header,sample)) { frost_input={}; return IneligibleRequest; }
    for (unsigned i=0;i<4;++i) if (!sample.codes[i]) { ++connected; slot=i; }
    if (connected!=1 || !copy_field(boss_session.player+0x470,stance) || stance>2
        || !copy_field(boss_session.player_owner+0x240,vitals) || !copy_bytes(vitals+0x8C,pulse,sizeof(pulse))
        || !copy_field(boss_session.player+0x58,current)) { frost_input={}; return IneligibleRequest; }
    const unsigned mapped=2-stance; // Native high0/mid1/low2 -> preset low0/mid1/high2.
    const bool available=pulse[0]+pulse[2]>0 && (pulse[1]>0 || pulse[3]>0);
    const unsigned choice=frost_edge(frost_input,sample,slot,mapped,dispatch->control.reserved0>>16,
        available,current,dispatch->control.qpc_frequency,
        (pulse[1]>0 ? pulse[1] : 0)+(pulse[3]>0 ? pulse[3] : 0));
    uint32_t key=0;
    if (!copy_field(current,key)) { frost_input.spent=true; return ContextChanged; }
    if (frost_input.opened && current!=frost_input.descriptor && !frost_continuation(current,key)) {
        frost_input.spent=true; return ContextChanged;
    }
    if (!choice || !boss_frost_variants[choice-1]) return IneligibleRequest;
    const unsigned target=unsigned(boss_frost_variants[choice-1]-1);
    if (!native_binding_context(command)) return ContextChanged;
    const auto& move=boss_imports[target];
    command.reserved[1]=target; command.desired_key=move.key; command.expected_motion=move.motion;
    command.expected_descriptor=move.descriptor; command.expected_payload=move.payload; command.edge_qpc=sample.qpc;
    const auto reason=validate_boss_source(command);
    if (reason==Accepted) InterlockedIncrement64(&dispatch->control.dispatch_count);
    return reason;
}
