#pragma once
#include <stdint.h>

// A bounded startup phase followed by native playback; recovery only enables cancellation.
// Clock deltas advance normally through events. No phase seeks an animation/event cursor.
struct MoveTiming { int16_t recovery; float startup_end, startup_speed; };

static constexpr bool move_timing_valid(const MoveTiming& timing) {
    // Recovery -1 preserves the source rule; zero is invalid and positive recovery cannot precede startup end.
    // Bound startup to the signed frame range and acceleration to 1x..8x; comparisons also reject NaN.
    // With no startup phase, require 1x speed so an unused acceleration setting cannot look meaningful.
    return timing.recovery>=-1 && timing.recovery!=0
        && timing.startup_end>=0 && timing.startup_end<=32767
        && timing.startup_speed>=1 && timing.startup_speed<=8
        && (timing.startup_end || timing.startup_speed==1)
        && (timing.recovery<0 || timing.startup_end<=timing.recovery);
}

static inline float move_timing_delta(const MoveTiming& timing, float frame, float delta) {
    // Accelerate only a positive, bounded tick while the current frame is inside startup.
    // Cap extra progress at startup_end, but never shorten a native tick already crossing that boundary.
    // Return a delta without seeking the animation cursor; the game still traverses intervening events.
    if (!move_timing_valid(timing) || !(frame>=0 && frame<timing.startup_end) || !(delta>0 && delta<=8)) return delta;
    const float remaining=timing.startup_end-frame;
    const float scaled=delta*timing.startup_speed;
    const float bounded=scaled<remaining ? scaled : remaining;
    return bounded>delta ? bounded : delta;
}

static inline float move_playback_delta(const MoveTiming& timing, float frame, float delta, float speed) {
    // Apply the configured 0.25x..2x playback rate before any separate startup acceleration.
    // Invalid rates or unusually large incoming ticks preserve the original delta.
    // Recovery remains a frame threshold; this helper changes elapsed progress, not cancellation rows.
    if (!(speed>=.25f && speed<=2) || !(delta>0 && delta<=4)) return delta;
    return move_timing_delta(timing,frame,delta*speed);
}
