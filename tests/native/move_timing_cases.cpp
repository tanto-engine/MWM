#include <cassert>
#include <initializer_list>
#include <limits>
#include "../../runtime/native/move_timing.h"

int main() {
    // Exercise startup acceleration, exact boundaries and a native tick already crossing startup end.
    // Feed invalid recovery, speed and non-finite frames to verify the original delta is preserved.
    // Combine whole-playback speed with startup speed to check their order without live animation state.
    const MoveTiming timing{54,12,8};
    assert(move_timing_valid(timing));
    for (const auto invalid : {MoveTiming{0,12,8}, MoveTiming{10,12,8}, MoveTiming{54,-1,8},
            MoveTiming{54,0,8}, MoveTiming{54,12,0}, MoveTiming{54,12,9},
            MoveTiming{54,12,std::numeric_limits<float>::quiet_NaN()}}) {
        assert(!move_timing_valid(invalid));
        assert(move_timing_delta(invalid,0,1)==1);
    }
    // Acceleration stops at the boundary without slowing an already crossing native tick.
    assert(move_timing_delta(timing,0,1)==8);
    assert(move_timing_delta(timing,10,1)==2);
    assert(move_timing_delta(timing,11.5f,1)==1);
    assert(move_timing_delta(timing,12,1)==1);
    assert(move_timing_delta(timing,0,0)==0);
    assert(move_timing_delta(timing,std::numeric_limits<float>::quiet_NaN(),1)==1);
    assert(move_timing_delta(timing,std::numeric_limits<float>::infinity(),1)==1);
    assert(move_playback_delta(timing,20,1,.5f)==.5f);
    assert(move_playback_delta(timing,20,1,2)==2);
    assert(move_playback_delta(timing,0,1,.5f)==4);
    assert(move_playback_delta(timing,11.5f,1,.5f)==.5f);
    assert(move_playback_delta(timing,0,0,2)==0);
    assert(move_playback_delta(timing,0,1,std::numeric_limits<float>::quiet_NaN())==1);
}
