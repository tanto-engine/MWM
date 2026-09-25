#pragma once

struct FrostMoonInput {
    int64_t opened, sampled;
    uint64_t descriptor;
    unsigned origin, choice, stance, slot, epoch;
    WORD buttons;
    bool available, spent;
    DWORD packet;
    float fill;
};
static FrostMoonInput frost_input{};

static unsigned frost_edge(FrostMoonInput& state, const GameInput& sample, unsigned slot,
        unsigned stance, unsigned epoch, bool available, uint64_t descriptor, int64_t frequency, float fill=0) {
    // Start one wall-clock window on the native Ki Pulse availability edge.
    // Require RB throughout two separate presses of the same different-stance face button.
    // Device, lifecycle and sampling gaps discard the window without replaying held inputs.
    const WORD buttons=sample.buttons[slot];
    const bool reset=!state.sampled || state.slot!=slot || state.epoch!=epoch
        || sample.qpc<=state.sampled || sample.qpc-state.sampled>=frequency/10 || sample.packets[slot]<state.packet;
    if (reset) {
        state={0,sample.qpc,descriptor,stance,3,stance,slot,epoch,buttons,available,false,sample.packets[slot],fill};
        return 0;
    }
    const WORD pressed=buttons&~state.buttons;
    if (available && (!state.available || fill>state.fill)) {
        state.opened=sample.qpc; state.origin=state.stance; state.descriptor=descriptor;
        state.choice=3; state.spent=false;
    }
    state.sampled=sample.qpc; state.stance=stance; state.available=available; state.buttons=buttons;
    state.packet=sample.packets[slot]; state.fill=fill;
    if (!state.opened || state.spent || sample.qpc-state.opened>=frequency*int64_t(boss_frost_milliseconds)/1000) return 0;
    constexpr WORD faces=XINPUT_GAMEPAD_A|XINPUT_GAMEPAD_X|XINPUT_GAMEPAD_Y;
    constexpr WORD cancel=XINPUT_GAMEPAD_B|XINPUT_GAMEPAD_LEFT_SHOULDER|XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK;
    if ((buttons&cancel) || sample.left_trigger[slot]>30 || sample.right_trigger[slot]>30) {
        state.spent=true; return 0;
    }
    if (!(buttons&XINPUT_GAMEPAD_RIGHT_SHOULDER)) { state.choice=3; return 0; }
    const WORD face=buttons&faces;
    if (!(pressed&faces)) return 0;
    const unsigned choice=face==XINPUT_GAMEPAD_A ? 0 : face==XINPUT_GAMEPAD_X ? 1 : face==XINPUT_GAMEPAD_Y ? 2 : 3;
    if (choice==3 || choice==state.origin) { state.choice=3; return 0; }
    if (state.choice!=choice) { state.choice=choice; return 0; }
    state.spent=true;
    return choice+1;
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
    const unsigned mapped=stance==2 ? 0 : stance==0 ? 1 : 2;
    const bool available=pulse[0]+pulse[2]>0 && (pulse[1]>0 || pulse[3]>0);
    const unsigned choice=frost_edge(frost_input,sample,slot,mapped,dispatch->control.reserved0>>16,
        available,current,dispatch->control.qpc_frequency,pulse[1]);
    uint32_t key=0; uint64_t payload=0; int32_t motion=0;
    if (!copy_field(current,key)) { frost_input.spent=true; return ContextChanged; }
    const bool pulse_action=key>=0xD60 && key<=0xD62 && copy_field(current+0x20,payload)
        && copy_field(payload+0x20,motion) && motion==2009+int(key-0xD60)*1000;
    if (frost_input.opened && current!=frost_input.descriptor && !pulse_action && !repeat_current_allowed(current,key)) {
        frost_input.spent=true; return ContextChanged;
    }
    if (!choice || !boss_frost_variants[choice-1]) return IneligibleRequest;
    const unsigned target=unsigned(boss_frost_variants[choice-1]-1);
    if (!replacement_context(command,boss_adapters[target])) return ContextChanged;
    const auto& move=boss_imports[target];
    command.reserved[1]=target; command.desired_key=move.key; command.expected_motion=move.motion;
    command.expected_descriptor=move.descriptor; command.expected_payload=move.payload; command.edge_qpc=sample.qpc;
    const auto reason=validate_boss_source(command);
    if (reason==Accepted) InterlockedIncrement64(&dispatch->control.dispatch_count);
    return reason;
}
