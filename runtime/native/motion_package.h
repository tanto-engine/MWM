#pragma once
#include <stdint.h>
#include <cstring>

// Validate the entire serialized package before allocating or calling the game.
// Native FB8350 assumes every clip allocation succeeds and dereferences null at
// FB84F3. This loop propagates failure before touching a returned clip.
static uint32_t package_u32(const uint8_t* bytes, size_t offset) {
    // Serialized words may be unaligned; callers have bounded the span.
    uint32_t value;
    memcpy(&value, bytes + offset, 4);
    return value;
}

static bool motion_package_bounds(const uint8_t* bytes, size_t size) {
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
        CreateMotionClip create, uintptr_t* clips, uint32_t capacity, uint32_t& failed,
        const uint32_t* keys=nullptr, uint32_t key_count=0) {
    // Preserve native lookup indices while allocating only requested clips.
    failed = 0;
    if (!motion_package_bounds(bytes, size) || capacity != package_u32(bytes, 20)) return false;
    if (key_count>32 || (key_count && !keys)) return false;
    const uint32_t offsets = package_u32(bytes, 32), sizes = package_u32(bytes, 36);
    uint32_t selected[1024]{}, found=0;
    if (key_count) {
        // Resolve every required clip before the first factory call, including sparse-table holes.
        const uint32_t hash=package_u32(bytes,40), slots=package_u32(bytes,hash);
        for (uint32_t row=0;row<slots;++row) {
            const uint32_t key=package_u32(bytes,hash+8+row*8), index=package_u32(bytes,hash+12+row*8);
            if (index==UINT32_MAX) continue;
            for (uint32_t request=0;request<key_count;++request) if (key==keys[request]) {
                if (!package_u32(bytes,offsets+index*4)) {failed=index;return false;}
                selected[index/32]|=1u<<(index%32);found|=1u<<request;
            }
        }
        if (found!=(key_count==32 ? UINT32_MAX : (1u<<key_count)-1)) return false;
    }
    for (uint32_t i = 0; i != capacity; ++i) {
        if (key_count && !(selected[i/32]&(1u<<(i%32)))) continue;
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
