#pragma once
#include <stdint.h>

// A bounded startup phase followed by native playback; recovery only enables cancellation.
// Clock deltas advance normally through events. No phase seeks an animation/event cursor.
struct MoveTiming { int16_t recovery; float startup_end, startup_speed; };

static constexpr bool move_timing_valid(const MoveTiming& timing) {
    return timing.recovery>=-1 && timing.recovery!=0
        && timing.startup_end>=0 && timing.startup_end<=32767
        && timing.startup_speed>=1 && timing.startup_speed<=8
        && (timing.startup_end || timing.startup_speed==1)
        && (timing.recovery<0 || timing.startup_end<=timing.recovery);
}

static inline float move_timing_delta(const MoveTiming& timing, float frame, float delta) {
    if (!move_timing_valid(timing) || !(frame>=0 && frame<timing.startup_end) || !(delta>0 && delta<=4)) return delta;
    const float remaining=timing.startup_end-frame;
    const float scaled=delta*timing.startup_speed;
    const float bounded=scaled<remaining ? scaled : remaining;
    return bounded>delta ? bounded : delta;
}
