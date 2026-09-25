#define RESEARCH_RUNTIME_SESSION
// Owned-memory tests only: no Nioh process, audio playback or controller access.
#include <windows.h>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#define RESEARCH_REPEAT
#include "../../outputs/okatsu-prototype/native/dispatch_protocol.h"
static DispatchMapping mapping{};
static DispatchMapping* dispatch = &mapping;
template<class T> static bool copy_field(uint64_t address, T& value) {
    // Read a native-shaped fixture field through the guarded process API.
    // Require a user-space address and a complete copy into local storage.
    // Unreadable-tail tests must reject the record instead of dereferencing it.
    SIZE_T copied = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<void*>(address),
        &value, sizeof(value), &copied) && copied == sizeof(value);
}
static bool copy_bytes(uint64_t address, void* out, SIZE_T length) {
    // Copy native-shaped fixture records without dereferencing unavailable spans.
    // Use ReadProcessMemory and require the exact requested byte count.
    // Corrupt pointer and unreadable-tail cases must remain ordinary test failures.
    SIZE_T copied = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<void*>(address),
        out, length, &copied) && copied == length;
}
#include "../../outputs/okatsu-prototype/native/boss_support.h"
#include "../../outputs/okatsu-prototype/native/voice_support.h"
#include "import_fixture.h"
template<class T> static void put(void* p, size_t at, T value) {
    // Write captured native-layout fields into memory owned by the harness.
    // Use memcpy so byte offsets do not create unaligned typed accesses.
    // The fixture must exercise real ABI offsets without requiring live game memory.
    memcpy(static_cast<char*>(p) + at, &value, sizeof(value));
}
static uint64_t ptr(void* p) {
    // Represent the owned voice fixture in the runtime's integer-address ABI.
    // Convert its pointer without borrowing memory from another process.
    // Voice ownership tests require exact identities rather than matching action keys.
    return reinterpret_cast<uint64_t>(p);
}
static unsigned checks;
static void check(bool condition) {
    // Count and assert each scoped voice-filter invariant.
    // Fail immediately while retaining a concise aggregate check count.
    // Unrelated sound events and malformed timing bounds must not silently pass.
    ++checks; assert(condition);
}

int main() {
    // Exercise scoped imported-voice matching and malformed timing records.
    // Vary owned actor, event and sound fields around the verified source events.
    // The boss and unrelated combat sounds must keep their original audio path.
    assert(load_runtime_session(nullptr)==ERROR_INVALID_DATA);
    check(sizeof(william_attack_voice.sound)==76);
    check(william_attack_voice.header[1]==1 && william_attack_voice.header[2]==0x24
        && william_attack_voice.header[4]==0x30);
    check(william_attack_voice.sound[7]==0x97933946 && william_attack_voice.sound[12]==80);
    (void)&boss_prepare_call; (void)&boss_finish_call; (void)BOSS_CONFIG_TAG;
    std::array<uint8_t, 0x100> actor{}, owner{}, state{}, motion{}, timing{};
    std::array<uint8_t, 0x1000> regular{}, charged{};
    boss_session.player = ptr(actor.data()); boss_session.player_owner = ptr(owner.data());
    boss_session.vtable = 0x12345678;
    boss_session.player_motion = ptr(motion.data()); boss_session.player_timing = ptr(timing.data());
    boss_session.source_timing_record = ptr(regular.data()); boss_session.charge_timing_record = ptr(charged.data());
    put(actor.data(), 0, boss_session.vtable); put(actor.data(), 0x50, boss_session.player_owner);
    put(owner.data(), 0x38, boss_session.player_motion); put(owner.data(), 0x68, boss_session.player_timing);
    put(state.data(), 8, boss_session.player_owner);
    fixture_imports();
    boss_active_player = boss_session.player; boss_active_owner = boss_session.player_owner; boss_active = 1;
    boss_private_actions[0].ready = boss_private_actions[1].ready = true;
    for (unsigned slot = 0; slot != 2; ++slot) {
        auto& record = slot ? charged : regular;
        put(record.data(), 4, uint32_t(2)); put(record.data(), 8, uint32_t(0x24));
        put(record.data(), 0x10, uint32_t(0x100));
        put(record.data(), 0x24, uint32_t(slot ? 46 : 30)); put(record.data(), 0x28, uint32_t(10));
        put(record.data(), 0x2c, uint32_t(slot ? 16 : 11));
        const size_t sound = 0x100 + (slot ? 16 : 11) * 0x4c + 0x1c;
        put(record.data(), sound, slot ? 0xF519B456u : 0x0E077D36u);
        put(actor.data(), 0x58, boss_private_descriptor_address(slot)); put(state.data(), 0x20, ptr(record.data()));
        const auto before_record = record;
        const auto before_actor = actor;
        auto filtered = [&]() {
            // Re-evaluate the same native sound event after each fixture mutation.
            // Capture only owned timing buffers and call the production predicate.
            // Rejected fields must not be hidden by rebuilding a different event.
            return boss_suppress_voice(state.data(), record.data(), record.data()+0x24);
        };
        check(filtered()); check(record == before_record && actor == before_actor);
        put(record.data(), sound, uint32_t(0xA14FFCB9)); check(!filtered()); // SE_OKATSU_RUSH preserved.
        put(record.data(), sound, slot ? 0xF519B456u : 0x0E077D36u);
        put(record.data(), 0x28, uint32_t(0)); check(!filtered()); put(record.data(), 0x28, uint32_t(10));
        put(record.data(), 0x2c, uint32_t(0xffffffff)); check(!filtered()); put(record.data(), 0x2c, uint32_t(slot ? 16 : 11));
        put(record.data(), 0x24, uint32_t(1)); check(!filtered()); put(record.data(), 0x24, uint32_t(slot ? 46 : 30));
        put(state.data(), 8, uint64_t(0xBAD)); check(!filtered()); put(state.data(), 8, boss_session.player_owner);
        put(state.data(), 0x20, uint64_t(0xBAD)); check(!filtered()); put(state.data(), 0x20, ptr(record.data()));
        put(actor.data(), 0x58, boss_private_descriptor_address(1-slot)); check(!filtered());
        put(actor.data(), 0x58, boss_private_descriptor_address(slot));
        check(!boss_suppress_voice(state.data(), record.data(), record.data()+0x25));
        check(!boss_suppress_voice(state.data(), record.data(), record.data()+0x3c));
        put(record.data(), 4, uint32_t(513)); check(!filtered()); put(record.data(), 4, uint32_t(2));
        put(record.data(), 0x10, uint32_t(0x25)); check(!filtered()); put(record.data(), 0x10, uint32_t(0x100));
        put(actor.data(), 0, uint64_t(0xBAD)); check(!filtered()); put(actor.data(), 0, boss_session.vtable);
        boss_active = 0; check(!filtered()); boss_active = 1;
        boss_active_owner = 0; check(!filtered()); boss_active_owner = boss_session.player_owner;
        check(!boss_suppress_voice(reinterpret_cast<void*>(1), record.data(), record.data()+0x24));
        check(filtered());
    }
    std::printf("voice predicate: %u owned-memory checks passed\n", checks);
}
