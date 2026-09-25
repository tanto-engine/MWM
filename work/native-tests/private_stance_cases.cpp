#define RESEARCH_RUNTIME_SESSION
// Complete owned payload/descriptor buffers, including an unreadable-tail case.
#include <windows.h>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#define RESEARCH_REPEAT
#include "../../runtime/native/dispatch_protocol.h"
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
#include "../../runtime/native/boss_support.h"
#include "import_fixture.h"

template<class T> static void put(void* p, size_t at, T value) {
    // Write captured native-layout fields into memory owned by the harness.
    // Use memcpy so byte offsets do not create unaligned typed accesses.
    // The fixture must exercise real ABI offsets without requiring live game memory.
    memcpy(static_cast<char*>(p) + at, &value, sizeof(value));
}
static uint64_t lookup(const BossLookupOnlyBank& bank, uint32_t key) {
    // Model native enabled-descriptor lookup in one owned private action bank.
    // Walk its pointer array and compare full keys plus the enabled byte.
    // A cloned stance payload must not change native lookup priority or action identity.
    auto* entries = reinterpret_cast<const uint64_t*>(bank.entries);
    for (uint32_t i = 0; i != bank.count; ++i) {
        uint32_t found = 0; uint8_t enabled = 0;
        assert(copy_field(entries[i], found) && copy_field(entries[i] + 0x40, enabled));
        if (enabled && found == key) return entries[i];
    }
    return 0;
}
// Exact branch effects from0x70F38E..70F3C3, independent of clone implementation.
static int native_stance_result(int old, int8_t metadata) {
    // Model the researched native stance branch independently of the clone.
    // Apply the observed retain-current and explicit-stance metadata rules.
    // Tests must prove player stance behavior rather than merely inspect copied bytes.
    if (metadata == 4 || metadata == 3) return old;
    if (metadata == -1) return old == -1 ? 0 : old;
    return metadata;
}
int main() {
    // Exercise immutable private clones and native stance-retention semantics.
    // Mutate owned source metadata and compare lookup behavior with a separate stance model.
    // Copied bytes alone cannot prove the imported action preserves player control.
    assert(load_runtime_session(nullptr)==ERROR_INVALID_DATA);
    (void)&boss_prepare_call; (void)&boss_finish_call; (void)BOSS_CONFIG_TAG;
    SYSTEM_INFO system{}; GetSystemInfo(&system);
    auto* pages = static_cast<uint8_t*>(VirtualAlloc(nullptr, system.dwPageSize * 2,
                                                   MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(pages);
    DWORD old_protect;
    assert(VirtualProtect(pages + system.dwPageSize, system.dwPageSize, PAGE_NOACCESS, &old_protect));
    auto* payload = pages + system.dwPageSize - 0xB0;
    alignas(16) std::array<uint8_t, 0xD0> descriptor{};
    for (unsigned i = 0; i < 0xB0; ++i) payload[i] = uint8_t(i ^ 0x5a);
    for (unsigned i = 0; i < descriptor.size(); ++i) descriptor[i] = uint8_t(i ^ 0xa5);
    put(payload, 0x18, uint64_t(0x184c0000)); put(payload, 0x20, int32_t(1220)); payload[0xB] = 1;
    put(payload, 0x16, int16_t(15)); put(payload, 0x24, int16_t(65));
    put(payload, 0x26, int16_t(-1));
    payload[0x33] = 0; put(payload, 0x38, uint32_t(0)); put(payload, 0x3C, int16_t(0));
    put(descriptor.data(), 0, uint32_t(0xC64)); descriptor[0x40] = 1;
    put(descriptor.data(), 0x20, reinterpret_cast<uint64_t>(payload));
    put(descriptor.data(), 0x38, uint64_t(0x12345678));
    std::array<std::array<uint8_t, 0x30>, 28> source_rows{};
    std::array<uint64_t, 28> source_pointers{};
    for (unsigned i = 0; i != 28; ++i) {
        source_rows[i].fill(uint8_t(i));
        source_pointers[i] = reinterpret_cast<uint64_t>(source_rows[i].data());
    }
    put(descriptor.data(), 0x78, reinterpret_cast<uint64_t>(source_pointers.data()));
    put(descriptor.data(), 0x80, uint16_t(0)); put(descriptor.data(), 0x82, uint16_t(28));
    std::array<uint8_t, 0xD0> pulse_descriptor{};
    std::array<std::array<uint8_t, 0x30>, 3> pulse_rows{};
    std::array<uint64_t, 49> pulse_pointers{};
    std::array<uint8_t,0x30> dodge_row{}; memcpy(dodge_row.data(),native_dodge_row,0x30);
    pulse_pointers[48]=reinterpret_cast<uint64_t>(dodge_row.data());
    for (unsigned i = 0; i != 3; ++i) {
        memcpy(pulse_rows[i].data(), boss_pulse_templates[i], 0x30);
        pulse_pointers[21+i] = reinterpret_cast<uint64_t>(pulse_rows[i].data());
    }
    put(pulse_descriptor.data(), 0, uint32_t(0xCF0)); pulse_descriptor[0x40] = 1;
    put(pulse_descriptor.data(), 0x78, reinterpret_cast<uint64_t>(pulse_pointers.data()));
    put(pulse_descriptor.data(), 0x82, uint16_t(49));
    boss_session.player_pulse_descriptor = reinterpret_cast<uint64_t>(pulse_descriptor.data());
    boss_session.source_descriptor = reinterpret_cast<uint64_t>(descriptor.data());
    boss_session.source_payload = reinterpret_cast<uint64_t>(payload); fixture_imports();
    std::array<uint8_t, 0xB0> source_payload{}; memcpy(source_payload.data(), payload, source_payload.size());
    const auto source_descriptor = descriptor;
    assert(boss_prepare_private_action());
    const auto& regular = boss_private_actions[0];
    // Native714F06 grants cancel permission only when its signed frame is crossed.
    // The source's -1 can never be crossed by a nonnegative action clock.
    // R1, Living Water and buffered exits need the same positive recovery boundary.
    int16_t cancel_frame=0;
    memcpy(&cancel_frame,regular.payload+0x26,2);
    assert(cancel_frame==65);
    assert(memcmp(source_payload.data(), payload, 0xB0) == 0 && descriptor == source_descriptor);
    auto expected_regular = source_payload;
    expected_regular[0xB] = 4; expected_regular[0x33] = 40;
    put(expected_regular.data(), 0x26, int16_t(65));
    put(expected_regular.data(), 0x38, int16_t(65)); put(expected_regular.data(), 0x3A, int16_t(25));
    put(expected_regular.data(), 0x3C, int16_t(24));
    assert(memcmp(regular.payload, expected_regular.data(), 0xB0) == 0);
    for (unsigned i = 0; i < 0xD0; ++i)
        if ((i < 0x20 || i >= 0x28) && (i < 0x78 || i >= 0x84)) assert(regular.descriptor[i] == descriptor[i]);
    assert(regular.transition_count == 32);
    uint64_t private_table = 0; uint16_t private_start = 99, private_count = 0;
    assert(copy_field(boss_private_descriptor_address() + 0x78, private_table));
    assert(copy_field(boss_private_descriptor_address() + 0x80, private_start) && private_start == 0);
    assert(copy_field(boss_private_descriptor_address() + 0x82, private_count) && private_count == 32);
    assert(private_table == reinterpret_cast<uint64_t>(regular.transition_pointers));
    for (unsigned i = 0; i != 32; ++i) {
        assert(regular.transition_pointers[i] == reinterpret_cast<uint64_t>(regular.transition_bodies[i]));
        if (i < 28) assert(memcmp(regular.transition_bodies[i], source_rows[i].data(), 0x30) == 0);
        else {
            auto expected = i==31 ? dodge_row : pulse_rows[i-28]; put(expected.data(), 0x20, int16_t(65));
            assert(memcmp(regular.transition_bodies[i], expected.data(), 0x30) == 0);
        }
    }
    uint64_t private_payload = 0, source_bank = 0;
    assert(copy_field(boss_private_descriptor_address() + 0x20, private_payload)
        && private_payload == boss_private_payload_address());
    assert(copy_field(boss_private_descriptor_address() + 0x38, source_bank) && source_bank == 0x12345678);
    assert(lookup(regular.bank, 0xC64) == boss_private_descriptor_address());
    assert(lookup(regular.bank, 0xC65) == 0 && lookup(regular.bank, 0x10000C64) == 0);
    assert(boss_is_preview_descriptor(boss_private_descriptor_address()) && !boss_is_preview_descriptor(1));
    for (int stance = 0; stance != 3; ++stance) {
        assert(native_stance_result(stance, int8_t(payload[0xB])) == 1);
        assert(native_stance_result(stance, int8_t(regular.payload[0xB])) == stance);
    }
    assert(boss_prepare_private_action()); // Reuse the same immutable copy.
    pulse_rows[0][0x1C] ^= 1; assert(!boss_prepare_private_action()); pulse_rows[0][0x1C] ^= 1;
    put(pulse_descriptor.data(), 0x82, uint16_t(48)); assert(!boss_prepare_private_action());
    put(pulse_descriptor.data(), 0x82, uint16_t(49));
    dodge_row[0x14]^=1; assert(!boss_prepare_private_action()); dodge_row[0x14]^=1;
    pulse_pointers[48]=1; assert(!boss_prepare_private_action());
    pulse_pointers[48]=reinterpret_cast<uint64_t>(dodge_row.data());
    source_rows[0][0] ^= 1; assert(!boss_prepare_private_action()); source_rows[0][0] ^= 1;
    assert(boss_prepare_private_action());
    const auto saved_tail = regular.payload[0xAF];
    payload[0xAF] ^= 1;
    assert(!boss_prepare_private_action() && regular.payload[0xAF] == saved_tail);
    payload[0xAF] ^= 1;
    put(payload, 0x24, int16_t(0));
    assert(!boss_prepare_private_action()); // Unknown recovery timing fails closed.
    put(payload, 0x24, int16_t(65)); put(payload, 0x16, int16_t(0));
    assert(!boss_prepare_private_action()); // Do not manufacture a window on a zero-cost move.
    put(payload, 0x16, int16_t(15));
    assert(boss_prepare_private_action());
    put(payload, 0x18, uint64_t(1) << 34);
    assert(!boss_prepare_private_action());
    put(payload, 0x18, uint64_t(0x184c0000));
    // A readable0x38 prefix is insufficient: the completeB0 copy must succeed.
    boss_session.source_payload = reinterpret_cast<uint64_t>(pages + system.dwPageSize - 0x38); fixture_imports();
    assert(!boss_prepare_private_action());

    // The second candidate gets separate lifetime-stable storage and lookup.
    alignas(16) auto charged_descriptor = source_descriptor;
    alignas(16) auto charged_payload = source_payload;
    put(charged_descriptor.data(), 0, uint32_t(0xC66));
    put(charged_descriptor.data(), 0x20, reinterpret_cast<uint64_t>(charged_payload.data()));
    put(charged_descriptor.data(), 0x82, uint16_t(22));
    put(charged_payload.data(), 0x20, int32_t(1230));
    put(charged_payload.data(), 0x24, int16_t(90));
    const auto original_charged_payload = charged_payload;
    boss_session.charge_descriptor = reinterpret_cast<uint64_t>(charged_descriptor.data());
    boss_session.charge_payload = reinterpret_cast<uint64_t>(charged_payload.data()); fixture_imports();
    assert(boss_prepare_private_action(1));
    const auto& charged = boss_private_actions[1];
    assert(charged_payload == original_charged_payload && charged.payload[0xB] == 4);
    auto expected_charged = original_charged_payload;
    expected_charged[0xB] = 4; expected_charged[0x33] = 40;
    put(expected_charged.data(), 0x26, int16_t(90));
    put(expected_charged.data(), 0x38, int16_t(90)); put(expected_charged.data(), 0x3A, int16_t(25));
    put(expected_charged.data(), 0x3C, int16_t(24));
    assert(memcmp(charged.payload, expected_charged.data(), 0xB0) == 0);
    assert(charged.transition_count == 26);
    for (unsigned i = 0; i != 26; ++i) {
        assert(charged.transition_pointers[i] == reinterpret_cast<uint64_t>(charged.transition_bodies[i]));
        if (i < 22) assert(memcmp(charged.transition_bodies[i], source_rows[i].data(), 0x30) == 0);
        else {
            auto expected = i==25 ? dodge_row : pulse_rows[i-22]; put(expected.data(), 0x20, int16_t(90));
            assert(memcmp(charged.transition_bodies[i], expected.data(), 0x30) == 0);
        }
    }
    assert(boss_private_descriptor_address(1) != boss_private_descriptor_address(0));
    assert(boss_private_payload_address(1) != boss_private_payload_address(0));
    assert(lookup(charged.bank, 0xC66) == boss_private_descriptor_address(1));
    assert(lookup(charged.bank, 0xC64) == 0 && lookup(regular.bank, 0xC66) == 0);
    assert(boss_is_preview_descriptor(boss_private_descriptor_address(1)));
    for (int stance = 0; stance != 3; ++stance)
        assert(native_stance_result(stance, int8_t(charged.payload[0xB])) == stance);
    assert(boss_prepare_private_action(1));
    assert(!boss_prepare_private_action(2));
    VirtualFree(pages, 0, MEM_RELEASE);
    std::puts("private action checks passed: both full copies, source isolation, stance preservation, native Ki metadata/cost preservation, invalid timing/cost/extent rejection");
}
