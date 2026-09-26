// Current frame-scheduled repeat behavior, using owned memory and stubbed hooks.
#define main frame_dispatch_baseline_main
#include "frame_dispatch_cases.cpp"
#undef main

int main() {
    // Exercise repeated gesture consumption using the inherited preview fixture.
    // Advance committed sequence and generation values through the native repeat policy.
    // Holding an old gesture must never replenish execution after recovery.
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency = freq.QuadPart;
    DispatchCommand copied{};

    // 1. A fresh chord after native restoration can dispatch in the same Start.
    reset(); tick(); exit_move(); publish(2); tick();
    assert(boss_active && dispatch->control.dispatch_count == 2 && dispatch->control.consumed_sequence == 2);
    exit_move();

    // 2. Republishing the consumed chord cannot replay it.
    reset(); tick(); exit_move(); publish(1);
    assert(choose_dispatch(player.data(), 0, nullptr, copied, true) == SequenceConsumed);
    const auto previous_calls = action_calls; tick();
    assert(action_calls == previous_calls && dispatch->control.dispatch_count == 1);

    // 3. A fresh sequence is blocked while the imported action is active.
    reset(); tick(); publish(2);
    assert(choose_dispatch(player.data(), 0, nullptr, copied, true) == BossPreviewActive);
    assert(dispatch->control.consumed_sequence == 1 && dispatch->control.dispatch_count == 1);
    exit_move();

    // 4. An early current-descriptor change does not bypass active restoration.
    reset(); tick(); put(player.data(), 0x58, address(neutral.data())); publish(2);
    assert(choose_dispatch(player.data(), 0, nullptr, copied, true) == BossPreviewActive);
    exit_move(); assert(dispatch->control.dispatch_count == 1); bindings(false);

    // 5. Stop immediately disarms; ordinary native recovery still restores slots.
    reset(); tick();
    assert(NiohResearchStop(nullptr) == ERROR_BUSY && dispatch->control.enabled == 0);
    exit_move(); publish(2); tick();
    assert(dispatch->control.dispatch_count == 1 && !boss_active);
    assert(NiohResearchStop(nullptr) == 0);

    // 6. Release and expiry reject otherwise fresh, unlatched sequences.
    reset(); tick(); exit_move(); command.held = 0; publish(2);
    assert(choose_dispatch(player.data(), 0, nullptr, copied, true) == Released);
    command.held = 1; publish(2);
    command.edge_qpc -= frequency; command.expires_qpc = command.heartbeat_qpc - 1;
    memcpy(&dispatch->command, &command, sizeof(command));
    assert(choose_dispatch(player.data(), 0, nullptr, copied, true) == Expired);
    assert(dispatch->control.dispatch_count == 1 && dispatch->control.consumed_sequence == 1);
    std::puts("boss repeat offline checks passed: 6 focused scenarios");
    return 0;
}
