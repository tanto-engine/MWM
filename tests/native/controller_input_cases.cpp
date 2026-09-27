#include <windows.h>
#include <cassert>
#include <cstdint>
#include <cstring>
#include "../../runtime/native/trace_protocol.h"
static uint32_t boss_controller_selection;
#include "../../runtime/native/controller_input.h"

static DWORD codes[4] = {0, ERROR_DEVICE_NOT_CONNECTED, ERROR_DEVICE_NOT_CONNECTED, ERROR_DEVICE_NOT_CONNECTED};
static unsigned calls[4];
static WORD buttons[4] = {0x2100,0x2100,0x2100,0x2100};
static GameInput* published;
static DWORD WINAPI fake_input(DWORD slot, XINPUT_STATE* state) {
    // Provide deterministic per-slot XInput responses to the native sampler.
    // Expose controlled packets and connection errors while checking seqlock publication.
    // Reconnect and multiple-controller cases must not fabricate input from uninitialized state.
    // Device calls can take longer than the external poll interval. Keep the
    // last complete snapshot readable while collecting the next one; marking
    // it unavailable here caused false disconnects on otherwise connected pads.
    assert(!(published->sequence & 1));
    ++calls[slot];
    if (!codes[slot]) {
        state->dwPacketNumber = 7;
        state->Gamepad.wButtons = buttons[slot];
        state->Gamepad.bLeftTrigger = 128;
    }
    return codes[slot];
}

int main() {
    // Exercise native input publication across disconnects and controller changes.
    // Feed deterministic per-slot packets into the real seqlock sampler.
    // A valid snapshot must expose ambiguity and never invent a reconnect press.
    TraceHeader header{};
    LARGE_INTEGER frequency;
    QueryPerformanceFrequency(&frequency);
    header.qpc_frequency = frequency.QuadPart;
    published = reinterpret_cast<GameInput*>(header.reserved);
    // Resolver uses only this disposable process; every observation calls our fake.
    resolve_game_input();
    game_input_state = fake_input;
    observe_game_input(header);
    assert(published->sequence == 2 && published->qpc > 0);
    GameInput snapshot{};
    assert(read_game_input(header,snapshot) && snapshot.sequence==published->sequence);
    const auto stamp=published->qpc;
    published->qpc-=frequency.QuadPart;
    assert(!read_game_input(header,snapshot)); published->qpc=stamp;
    ++published->sequence; assert(!read_game_input(header,snapshot)); ++published->sequence;
    published->sequence=2;
    for (unsigned i=0;i<4;++i) assert(calls[i] == 1);
    assert(published->buttons[0] == 0x2100 && published->left_trigger[0] == 128 && published->packets[0] == 7);
    observe_game_input(header);
    assert(published->sequence == 4 && calls[0] == 2 && calls[1] == 1);
    codes[0] = ERROR_DEVICE_NOT_CONNECTED;
    observe_game_input(header);
    assert(published->sequence == 6 && published->codes[0] == ERROR_DEVICE_NOT_CONNECTED && !published->buttons[0]);
    codes[1] = 0;
    input_rescan = 0;
    observe_game_input(header);
    assert(published->sequence == 8 && published->codes[1] == 0 && published->buttons[1] == 0x2100);
    codes[0] = 0;
    input_rescan = 0;
    observe_game_input(header);
    assert(published->codes[0] == 0 && published->codes[1] == 0);
    unsigned selected=0;
    assert(!selected_game_controller(*published,selected));
    boss_controller_selection=2;
    assert(selected_game_controller(*published,selected) && selected==1);
    buttons[1]=XINPUT_GAMEPAD_Y;
    observe_game_input(header);
    assert(!triangle_input.pressed);
    buttons[1]=0; observe_game_input(header);
    buttons[1]=XINPUT_GAMEPAD_Y; observe_game_input(header);
    assert(triangle_input.pressed && triangle_input.slot==1);
    boss_controller_selection=1;
    buttons[0]=XINPUT_GAMEPAD_Y; observe_game_input(header);
    assert(!triangle_input.pressed && !triangle_input.neutral);
    codes[0]=ERROR_DEVICE_NOT_CONNECTED; observe_game_input(header);
    codes[0]=0; input_rescan=0; observe_game_input(header);
    assert(!triangle_input.pressed);
    buttons[0]=0; observe_game_input(header);
    buttons[0]=XINPUT_GAMEPAD_Y; observe_game_input(header);
    assert(triangle_input.pressed && triangle_input.slot==0);
    boss_controller_selection=3;
    assert(!selected_game_controller(*published,selected));
    boss_controller_selection=5;
    assert(!selected_game_controller(*published,selected));
    boss_controller_selection=0;
    game_input_state = nullptr;
    input_rescan = 0;
    observe_game_input(header);
    for (unsigned i=0;i<4;++i) assert(published->codes[i] == ERROR_PROC_NOT_FOUND && !published->buttons[i]);
}
