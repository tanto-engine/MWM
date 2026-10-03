#include <cassert>
#include <cstdio>
#include "../../runtime/native/cast_pulse_profiles.h"

int main() {
    unsigned count=0,onmyo=0,shuriken=0,native=0,shared=0,throw_only=0;
    bool delays[9]{},widths[11]{};
    for (const auto& profile : cast_pulse_profiles) {
        ++count;onmyo+=profile.onmyo>0;shuriken+=profile.shuriken>0;
        native+=!profile.rows;shared+=profile.onmyo && profile.shuriken;
        throw_only+=!profile.onmyo && profile.shuriken;
        assert(profile.delay>=2 && profile.delay<=8);
        assert(!profile.onmyo || (profile.onmyo>=5 && profile.onmyo<=10));
        assert(!profile.shuriken || (profile.shuriken>=5 && profile.shuriken<=10));
        assert(!profile.onmyo || !profile.shuriken || profile.onmyo==profile.shuriken);
        delays[profile.delay]=true;widths[profile.onmyo]=true;widths[profile.shuriken]=true;
    }
    assert(native==20 && onmyo==(count*60+50)/100 && shuriken==(count*70+50)/100);
    assert(shared && throw_only);
    for (unsigned delay=2;delay<=8;++delay) assert(delays[delay]);
    for (unsigned width=5;width<=10;++width) assert(widths[width]);
    printf("Cast profiles: %u phases, %u Onmyo, %u shuriken, %u shared, %u shuriken-only\n",
           count,onmyo,shuriken,shared,throw_only);
}
