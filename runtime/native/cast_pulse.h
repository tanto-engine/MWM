#pragma once

// Keep a sword's actual Pulse deadline across native magic and throwing casts. No Ki,
// item count, effect or cast-speed fields are written by this adapter.
struct CastPulseInput {
    int64_t closes, sampled, edge;
    uint64_t descriptor;
    unsigned slot, epoch, stance, counter;
    WORD buttons;
    DWORD packet;
    bool ready;
};
static CastPulseInput cast_pulse_input{};

static bool pulse_cast_descriptor(uint64_t descriptor) {
    uint64_t payload=0,flags=0;int32_t motion=0;uint8_t enabled=0;
    return copy_field(descriptor+0x40,enabled) && enabled==1
        && copy_field(descriptor+0x20,payload) && copy_field(payload+0x20,motion)
        && copy_field(payload+0x18,flags)
        && (((motion==110 || motion==111) && (flags&~0x400000ULL)==0x2181C0000ULL)
            || (motion==104 && flags==0x2184C0000ULL));
}

static void latch_cast_pulse_window() {
    uint64_t current=0;float pulse[4]{};
    if (!trace || !dispatch || !dispatch->control.enabled || !boss_player_valid()
        || !copy_field(boss_session.player+0x58,current)
        || (!sword_attack_family(boss_session.player,false) && !boss_is_preview_descriptor(current))
        || !read_player_pulse(pulse) || !(pulse[0]+pulse[2]>0)) return;
    const float remaining=(pulse[1]>0 ? pulse[1] : 0)+(pulse[3]>0 ? pulse[3] : 0);
    if (!std::isfinite(remaining) || remaining<=0) return;
    LARGE_INTEGER now;QueryPerformanceCounter(&now);
    cast_pulse_input.closes=now.QuadPart+int64_t(remaining*float(dispatch->control.qpc_frequency)/60);
}

static void observe_cast_pulse_cue(void* state, void* timing_record, void* event) {
    // Native type40 releases the item effect; type41 is later cleanup.
    // The next sound callback witnesses release on the same player-owned timeline.
    auto& input=cast_pulse_input;uint64_t current=0;uint32_t counter=0;
    const uint64_t record=reinterpret_cast<uint64_t>(timing_record),address=reinterpret_cast<uint64_t>(event);
    if (!dispatch || !dispatch->control.enabled || !input.descriptor || input.ready || !boss_player_valid()
        || !copy_field(boss_session.player+0x58,current) || current!=input.descriptor || !pulse_cast_descriptor(current)
        || !copy_field(boss_session.player+0xDC,counter) || counter!=input.counter
        || !same_field(reinterpret_cast<uint64_t>(state),8,boss_session.player_owner)
        || !same_field(reinterpret_cast<uint64_t>(state),0x20,record)) return;
    uint32_t count=0,offset=0,fields[3]{};
    if (!copy_field(record+4,count) || !copy_field(record+8,offset) || !count || count>512
        || offset<0x24 || offset>0x10000 || address<record+offset
        || address-record-offset>=uint64_t(count)*12 || (address-record-offset)%12
        || !copy_bytes(address,fields,sizeof(fields)) || fields[1]!=10) return;
    uint32_t rows[512][3]{},last_effect=0;bool release_found=false;
    if (!copy_bytes(record+offset,rows,count*12)) return;
    for (unsigned i=0;i<count;++i) {
        if (i && rows[i][0]<rows[i-1][0]) return;
        if (rows[i][1]==40) {last_effect=rows[i][0];release_found=true;}
    }
    if (release_found && fields[0]>last_effect) input.ready=true;
}

static DispatchReason choose_cast_pulse(DispatchCommand& command) {
    GameInput sample{};unsigned slot=0;uint32_t stance=0,counter=0;uint64_t current=0;
    if (!trace || !native_binding_context(command) || !read_game_input(trace->header,sample)
        || !selected_game_controller(sample,slot) || !copy_field(boss_session.player+0x470,stance) || stance>2
        || !copy_field(boss_session.player+0x58,current) || !copy_field(boss_session.player+0xDC,counter)) {
        cast_pulse_input={};return IneligibleRequest;
    }
    auto& input=cast_pulse_input;
    if (sample.qpc==input.sampled) return IneligibleRequest;
    const WORD buttons=sample.buttons[slot],pressed=buttons&~input.buttons;
    if (!input.sampled || input.slot!=slot || input.epoch!=command.reserved[2] || input.stance!=stance
        || sample.qpc<input.sampled || sample.qpc-input.sampled>=dispatch->control.qpc_frequency/10
        || sample.packets[slot]<input.packet) input={};
    input.sampled=sample.qpc;input.slot=slot;input.epoch=unsigned(command.reserved[2]);
    input.stance=stance;input.buttons=buttons;input.packet=sample.packets[slot];
    if (!pulse_cast_descriptor(current)) {
        if (input.descriptor) input.closes=0;
        input.descriptor=0;input.edge=0;input.ready=false;
        return IneligibleRequest;
    }
    if (input.descriptor!=current || input.counter!=counter) {
        input.descriptor=current;input.counter=counter;input.edge=0;input.ready=false;
    }
    constexpr WORD blocked=XINPUT_GAMEPAD_A|XINPUT_GAMEPAD_B|XINPUT_GAMEPAD_X|XINPUT_GAMEPAD_Y
        |XINPUT_GAMEPAD_LEFT_SHOULDER|XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK;
    if ((buttons&blocked) || sample.left_trigger[slot]>30 || sample.right_trigger[slot]>30) {
        input.edge=0;return IneligibleRequest;
    }
    if ((pressed&XINPUT_GAMEPAD_RIGHT_SHOULDER) && sample.qpc<input.closes) input.edge=sample.qpc;
    const auto lookup=original_lookup ? original_lookup : reinterpret_cast<LookupFn>(lookup_target);
    if (!input.edge || !input.ready || sample.qpc>=input.closes || !lookup) return IneligibleRequest;
    uint32_t bank=0;const uint64_t descriptor=lookup(reinterpret_cast<void*>(boss_session.player+0x70),0xD5F,&bank);
    if (!descriptor || bank>2 || !same_field(descriptor,0,uint32_t(0xD5F))) return DesiredMissing;
    command.desired_key=0xD5F;command.edge_qpc=input.edge;
    return NativeCastPulse;
}
