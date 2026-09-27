#pragma once
#include <xinput.h>

// Steam's virtual controller exists inside the game process. External WinMM
// can report a connected, permanently neutral DS4 while Nioh receives XInput.
// Observe that same API on the player frame; never acquire or write a device.
struct GameInput {
    volatile LONG64 sequence;
    int64_t qpc;
    DWORD codes[4];
    WORD buttons[4];
    BYTE left_trigger[4], right_trigger[4];
    DWORD packets[4];
};
static_assert(sizeof(GameInput) == 64, "Trace input area size");
using InputStateFn = DWORD (WINAPI*)(DWORD, XINPUT_STATE*);
static InputStateFn game_input_state;
static int64_t input_rescan;
// A fresh press requires a prior neutral sample; reconnecting while holding Triangle must not invent a new press.
// pressed/released/sampled share the trace QPC clock, and slot binds that history to one controller.
struct TriangleInput {
    int64_t pressed, released, sampled;
    unsigned slot;
    bool down, neutral;
};
static TriangleInput triangle_input{};

static bool selected_game_controller(const GameInput& sample, unsigned& slot) {
    // Controller selection is 1-based in settings; XInput slots are 0-based.
    // An explicit slot must report success (code zero); automatic mode requires exactly one connected pad.
    // Ambiguous or disconnected input cannot choose which player gesture to dispatch.
    if (boss_controller_selection) {
        slot=boss_controller_selection-1;
        return slot<4 && !sample.codes[slot];
    }
    unsigned connected=0;
    for (unsigned i=0;i<4;++i) if (!sample.codes[i]) { ++connected; slot=i; }
    return connected==1;
}

static void resolve_game_input() {
    // Find the same XInput entrypoint already imported by Nioh.
    // Resolve from the loaded module so Steam's in-process controller translation is retained.
    // External WinMM samples can remain neutral while the actual game receives input.
    // Use the module Nioh already imported, including Steam's installed hook.
    HMODULE module = GetModuleHandleW(L"XINPUT1_3.dll");
    if (module) {
        FARPROC address = GetProcAddress(module, "XInputGetState");
        static_assert(sizeof(address) == sizeof(game_input_state), "Function pointer size");
        memcpy(&game_input_state, &address, sizeof(address));
    }
}

static void observe_game_input(TraceHeader& header) {
    // Publish a read-only snapshot of all in-process XInput controller slots.
    // Use sequence markers and bounded rescans while retaining individual connection results.
    // Consumers need real disconnect and ambiguity evidence without fabricated button edges.
    // TODO: verify reconnects for DS4, DualSense, Xbox and SCUF through the game's
    // active input backend; owned-memory tests do not prove physical-device latency.
    auto& input = *reinterpret_cast<GameInput*>(header.reserved);
    GameInput sample{};
    memcpy(&sample,&input,sizeof(sample));
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    sample.qpc = now.QuadPart;
    const bool rescan = now.QuadPart >= input_rescan;
    if (rescan) input_rescan = now.QuadPart + header.qpc_frequency / 4;
    for (DWORD slot = 0; slot != 4; ++slot) {
        if (!rescan && sample.codes[slot]) continue;
        XINPUT_STATE state{};
        sample.codes[slot] = game_input_state ? game_input_state(slot, &state) : ERROR_PROC_NOT_FOUND;
        sample.buttons[slot] = state.Gamepad.wButtons;
        sample.left_trigger[slot] = state.Gamepad.bLeftTrigger;
        sample.right_trigger[slot] = state.Gamepad.bRightTrigger;
        sample.packets[slot] = state.dwPacketNumber;
    }
    QueryPerformanceCounter(&now);
    sample.qpc = now.QuadPart; // Timestamp the completed sample, after device latency.
    unsigned slot=0;
    const bool selected=selected_game_controller(sample,slot);
    if (!selected || !input.sequence || input.codes[slot]
        || slot!=triangle_input.slot || sample.packets[slot]<input.packets[slot]
        || sample.qpc-input.qpc>=header.qpc_frequency/10) triangle_input={};
    if (selected) {
        const bool down=(sample.buttons[slot]&XINPUT_GAMEPAD_Y)!=0;
        if (!down) {
            triangle_input.neutral=true;
            if (triangle_input.down) triangle_input.released=sample.qpc;
        } else if (!triangle_input.down && triangle_input.neutral) {
            triangle_input.pressed=sample.qpc;
            triangle_input.released=0;
        }
        triangle_input.slot=slot; triangle_input.down=down; triangle_input.sampled=sample.qpc;
    }
    // Keep slow device calls outside the publication boundary. Readers retain
    // the prior coherent frame rather than interpreting collection as a disconnect.
    InterlockedIncrement64(&input.sequence);
    memcpy(reinterpret_cast<uint8_t*>(&input)+8,reinterpret_cast<const uint8_t*>(&sample)+8,sizeof(input)-8);
    InterlockedIncrement64(&input.sequence);
}

static bool read_game_input(const TraceHeader& header, GameInput& sample) {
    // Reuse the player frame's completed controller snapshot without device calls.
    // Bound publication and age so a torn or suspended frame cannot create an edge.
    // Every gesture on this frame observes the same buttons and timestamp.
    const auto& input=*reinterpret_cast<const GameInput*>(header.reserved);
    const LONG64 before=InterlockedCompareExchange64(const_cast<volatile LONG64*>(&input.sequence),0,0);
    memcpy(&sample,&input,sizeof(sample));
    const LONG64 after=InterlockedCompareExchange64(const_cast<volatile LONG64*>(&input.sequence),0,0);
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    return before>0 && !(before&1) && before==after && sample.sequence==before
        && header.qpc_frequency>0 && sample.qpc<=now.QuadPart
        && now.QuadPart-sample.qpc<header.qpc_frequency/10;
}
