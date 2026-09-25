#pragma once
#include <stdint.h>
#include <cstring>

// Validate the entire serialized package before allocating or calling the game.
// Native FB8350 assumes every clip allocation succeeds and dereferences null at
// FB84F3. This loop propagates failure before touching a returned clip.
static uint32_t package_u32(const uint8_t* bytes, size_t offset) {
    // Read a serialized package word without assuming pointer alignment.
    // Copy four bytes from a span already bounded by the caller.
    // Native archive tables may place integers at offsets unsuitable for direct typed loads.
    uint32_t value;
    memcpy(&value, bytes + offset, 4);
    return value;
}

static bool motion_package_bounds(const uint8_t* bytes, size_t size) {
    // Reject a malformed serialized motion or camera package before allocation.
    // Validate table extents, lookup indices, clip signatures and internal clip sizes.
    // The native decoder assumes valid data and can otherwise dereference invalid allocations.
    if (!bytes || size < 48 || memcmp(bytes, "G2A_PACK", 8) || package_u32(bytes, 16) != size) return false;
    const uint32_t count = package_u32(bytes, 20);
    const uint32_t offsets = package_u32(bytes, 32), sizes = package_u32(bytes, 36), hash = package_u32(bytes, 40);
    if (!count || count > 32768 || offsets < 48 || sizes < 48 || hash < 48
        || uint64_t(offsets) + count * 4 > size || uint64_t(sizes) + count * 4 > size
        || uint64_t(hash) + 8 > size) return false;
    const uint32_t slots = package_u32(bytes, hash);
    if (!slots || slots > 65536 || uint64_t(hash) + 8 + uint64_t(slots) * 8 > size) return false;
    for (uint32_t i = 0; i != slots; ++i) {
        const uint32_t index = package_u32(bytes, hash + 12 + i * 8);
        if (index != UINT32_MAX && index >= count) return false;
    }
    for (uint32_t i = 0; i != count; ++i) {
        const uint32_t at = package_u32(bytes, offsets + i * 4), length = package_u32(bytes, sizes + i * 4);
        if (!at && !length) continue;
        if (at < 48 || length < 28 || uint64_t(at) + length > size || memcmp(bytes + at, "_A2G0300", 8)) return false;
        uint16_t bones;
        memcpy(&bones, bytes + at + 18, 2);
        const uint64_t used = 28 + uint64_t(bones >> 4) * 4
            + package_u32(bytes, at + 20) + uint64_t(package_u32(bytes, at + 24)) * 32;
        if (used > length) return false;
    }
    return true;
}

using CreateMotionClip = void* (*)(const uint8_t*, uint32_t, void*);
static bool decode_motion_clips(const uint8_t* bytes, size_t size, void* allocator,
        CreateMotionClip create, uintptr_t* clips, uint32_t capacity, uint32_t& failed) {
    // Construct validated clips while preserving the first allocation failure.
    // Walk bounded package offsets and publish only successfully created clip pointers.
    // The caller can release completed clips without touching a null factory result.
    failed = 0;
    if (!motion_package_bounds(bytes, size) || capacity != package_u32(bytes, 20)) return false;
    const uint32_t offsets = package_u32(bytes, 32), sizes = package_u32(bytes, 36);
    for (uint32_t i = 0; i != capacity; ++i) {
        failed = i;
        const uint32_t at = package_u32(bytes, offsets + i * 4);
        if (!at) continue;
        void* clip = create(bytes + at, package_u32(bytes, sizes + i * 4), allocator);
        if (!clip) return false;
        reinterpret_cast<uint32_t*>(clip)[0x24 / 4] = 1;
        clips[i] = reinterpret_cast<uintptr_t>(clip);
    }
    return true;
}
