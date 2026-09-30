#pragma once

// Guardian Spirit cast timing111 captured in the supported game. Addresses are
// replaced by owned storage; only the recorded frames/types/indices are reused.
static constexpr uint32_t guardian_cast_events[][3]={
    {1,10,6},{6,10,0},{12,10,4},{18,10,2},{21,0,2},{24,10,10},
    {34,10,5},{45,1,2},{48,10,11},{49,0,1},{75,0,3},{78,10,2},
    {86,10,7},{91,40,0},{98,10,3},{100,10,9},{101,0,0},{103,1,1},
    {103,1,3},{106,10,12},{107,0,4},{132,41,0},{136,10,1},
    {142,10,7},{146,10,2},{152,10,8}
};
alignas(8) static std::array<uint8_t,0x90> cast_pose{};
static DWORD cast_packet;
static uint64_t cast_lookup(void*,uint32_t key,uint32_t* bank_index) {
    assert(key==0xD5F);*bank_index=0;return address(cast_pose.data());
}
static bool cast_action(void* actor,uint32_t key,void* context) {
    assert(actor==player.data() && key==0xD5F && !context);
    put(actor,0x58,address(cast_pose.data()));++action_calls;
    SetLastError(ACTION_ERROR);return true;
}
static void cast_sample(WORD buttons) {
    LARGE_INTEGER now;QueryPerformanceCounter(&now);
    GameInput sample{};sample.sequence=2;sample.qpc=now.QuadPart;sample.codes[0]=0;
    sample.codes[1]=sample.codes[2]=sample.codes[3]=ERROR_DEVICE_NOT_CONNECTED;
    sample.buttons[0]=buttons;sample.packets[0]=++cast_packet;
    memcpy(own_trace.header.reserved,&sample,sizeof(sample));publish();
}
static void cast_setup() {
    reset();cast_packet=0;cast_pose.fill(0);put(cast_pose.data(),0,uint32_t(0xD5F));cast_pose[0x40]=1;
    original_lookup=cast_lookup;original_action=cast_action;
    put(player.data(),0x470,uint32_t(0));put(player.data(),0xDC,uint32_t(11));
    state(0x262,111,3);put(neutral_payload.data(),0x18,uint64_t(0x2181C0000ULL));
    put(neutral_payload.data(),0x24,int16_t(154));put(neutral_payload.data(),0x26,int16_t(154));
    voice_state.fill(0);voice_record.fill(0);
    put(voice_state.data(),8,boss_session.player_owner);put(voice_state.data(),0x20,address(voice_record.data()));
    put(voice_record.data(),4,uint32_t(std::size(guardian_cast_events)));put(voice_record.data(),8,uint32_t(0x24));
    memcpy(voice_record.data()+0x24,guardian_cast_events,sizeof(guardian_cast_events));
    cast_sample(0);DispatchCommand probe{};assert(choose_cast_pulse(probe)==IneligibleRequest);
    LARGE_INTEGER now;QueryPerformanceCounter(&now);cast_pulse_input.closes=now.QuadPart+2*frequency;
}
static void cast_cue(unsigned index) {
    observe_cast_pulse_cue(voice_state.data(),voice_record.data(),voice_record.data()+0x24+index*12);
}
static void cast_pulse_cases() {
    DispatchCommand probe{};
    cast_setup();alignas(8) std::array<uint8_t,0xA0> vitals{};
    put(owner.data(),0x240,address(vitals.data()));
    state(0xCB7,3300,0);put(neutral_payload.data(),0x18,uint64_t(0x8000000594C0000ULL));
    const float timers[4]={6,12,24,30};memcpy(vitals.data()+0x8C,timers,sizeof(timers));
    const auto vitals_before=vitals;cast_pulse_input.closes=0;
    LARGE_INTEGER start,end;QueryPerformanceCounter(&start);latch_cast_pulse_window();QueryPerformanceCounter(&end);
    assert(cast_pulse_input.closes>=start.QuadPart+frequency*7/10-1
        && cast_pulse_input.closes<=end.QuadPart+frequency*7/10+1);
    const auto deadline=cast_pulse_input.closes;
    state(0x262,111,3);put(neutral_payload.data(),0x18,uint64_t(0x2181C0000ULL));
    put(player.data(),0xDC,uint32_t(12));cast_sample(0);assert(choose_cast_pulse(probe)==IneligibleRequest);
    latch_cast_pulse_window();assert(cast_pulse_input.closes==deadline);cast_cue(22);
    cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);assert(choose_cast_pulse(probe)==NativeCastPulse);
    assert(vitals==vitals_before);++checks;

    state(0xCB7,3300,0);put(neutral_payload.data(),0x18,uint64_t(0x8000000594C0000ULL));
    cast_pulse_input.closes=0;put(vitals.data(),0x8C,std::numeric_limits<float>::quiet_NaN());
    latch_cast_pulse_window();assert(!cast_pulse_input.closes);++checks;

    cast_setup();cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    assert(choose_cast_pulse(probe)==IneligibleRequest); // R1 buffered; effect rows still pending.
    cast_cue(14);assert(!cast_pulse_input.ready); // Sound98 precedes the final non-sound row132.
    cast_cue(22);assert(cast_pulse_input.ready); // Sound136 witnesses completion of those rows.
    cast_sample(0);assert(choose_cast_pulse(probe)==NativeCastPulse && probe.desired_key==0xD5F);
    cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);assert(choose_cast_pulse(probe)==IneligibleRequest);++checks;

    cast_setup();cast_cue(22);cast_pulse_input.closes=1;cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    assert(choose_cast_pulse(probe)==IneligibleRequest);++checks;
    cast_setup();cast_cue(22);cast_pulse_input.closes=0;cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    assert(choose_cast_pulse(probe)==IneligibleRequest);++checks;
    cast_setup();cast_cue(22);cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER|XINPUT_GAMEPAD_X);
    assert(choose_cast_pulse(probe)==IneligibleRequest);++checks;
    cast_setup();cast_cue(22);put(player.data(),0x470,uint32_t(1));cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    assert(choose_cast_pulse(probe)==IneligibleRequest && !cast_pulse_input.closes);++checks;
    cast_setup();cast_cue(22);dispatch->control.reserved0+=1u<<16;cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    assert(choose_cast_pulse(probe)==IneligibleRequest && !cast_pulse_input.closes);++checks;
    cast_setup();put(voice_state.data(),8,uint64_t(0x12345));cast_cue(22);
    assert(!cast_pulse_input.ready);++checks;
    cast_setup();put(voice_record.data(),0x24+23*12,uint32_t(120));cast_cue(22);
    assert(!cast_pulse_input.ready);++checks;
    cast_setup();put(player.data(),0xDC,uint32_t(12));cast_cue(22);
    assert(!cast_pulse_input.ready);++checks;
    cast_setup();dispatch->control.enabled=0;cast_cue(22);
    assert(!cast_pulse_input.ready);++checks;
    cast_setup();cast_cue(22);cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    auto& disconnected=*reinterpret_cast<GameInput*>(own_trace.header.reserved);
    disconnected.codes[0]=ERROR_DEVICE_NOT_CONNECTED;
    assert(choose_cast_pulse(probe)==IneligibleRequest && !cast_pulse_input.closes);++checks;
    cast_setup();cast_cue(22);cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    cast_pulse_input.sampled-=frequency/5;
    assert(choose_cast_pulse(probe)==IneligibleRequest && !cast_pulse_input.closes);++checks;
    cast_setup();cast_cue(22);put(neutral_payload.data(),0x20,int32_t(112));cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    assert(choose_cast_pulse(probe)==IneligibleRequest);++checks;

    cast_setup();cast_cue(22);cast_sample(XINPUT_GAMEPAD_RIGHT_SHOULDER);
    const auto payload_before=neutral_payload;
    const auto events_before=voice_record;
    SetLastError(INCOMING);assert(observed_action_impl(player.data(),0,nullptr,ActionRequest::CastPulse));
    assert(action_calls==1 && GetLastError()==ACTION_ERROR && !boss_inflight);
    assert(own_trace.records[0].after_key==0xD5F && (own_trace.records[0].valid_fields&TRACE_CAST_PULSE));
    assert(neutral_payload==payload_before && voice_record==events_before);++checks;
}
