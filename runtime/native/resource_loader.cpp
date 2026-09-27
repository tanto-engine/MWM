#include <windows.h>
#include <stdint.h>
#include <cstring>
#include "MinHook.h"
#include "motion_package.h"

// The game constructs file resources on its update thread, then queues native
// archive I/O and decoding. Keep the constructor's reference until process exit:
// a mission's actor lifetime must never own an imported animation package.
// The request carries four animation packages, up to four object-asset factory keys and a profile identity.
// birth is the process creation time, preventing a stale request from matching a reused PID.
struct ResourceRequest {
    uint32_t magic, version, pid, count;
    uint64_t birth;
    uint8_t profile_identity[32];
    uint64_t sizes[4];
    char names[4][80];
    uint32_t motion_count, motion_keys[32], reserved;
    uint32_t object_count, object_keys[4], object_reserved;
};
// Phase/error and completion fields publish progress from native callbacks to the external launcher.
// Published object addresses remain backed by retained resources, even after the temporary frame hook is disabled.
struct ResourceState {
    uint32_t magic, version;
    volatile LONG phase, error;
    uint64_t birth;
    uint8_t profile_identity[32];
    uint64_t objects[4];
    volatile LONG completed;
    DWORD thread;
    uint64_t player, owner;
    uint64_t object_assets[4]; // Native E84E60 reads each asset's completion byte at +0x160.
};
static_assert(sizeof(ResourceRequest) == 568);
static_assert(sizeof(ResourceState) == 144);
static ResourceRequest request;
static ResourceState* state;
static HANDLE mapping;
static uintptr_t base;
static void* frame_target;
static float (*frame_original)(void*, float);
static volatile LONG submitting, callbacks;
static uintptr_t tables[4][5];
static uintptr_t original_tables[4];
static bool hooked;

template<class T> T game_function(uintptr_t rva) {
    // Resolve a researched native entrypoint relative to the validated game image.
    // Convert its fixed RVA to the specific calling signature at the call site.
    // Module relocation changes addresses without changing the evidence-backed function identity.
    return reinterpret_cast<T>(base + rva);
}

static void* allocate_data(void* allocator, size_t size) {
    // Allocate decoded motion storage from the native data allocator.
    // Use its allocation virtual slot with the matching native resource category.
    // File-object pools and clip-data ownership use different allocators and cannot be mixed.
    uint64_t category[2] = {0x2d, 0};
    return reinterpret_cast<void* (*)(void*, size_t, void*)>(
        (*reinterpret_cast<uintptr_t**>(allocator))[5])(allocator, size, category);
}
static void free_data(void* allocator, void* pointer) {
    // Return decoded storage through the allocator that originally owned it.
    // Call the matching free virtual slot only for a non-null allocation.
    // Partial decode failures require symmetric cleanup without touching missing blocks.
    if (pointer) reinterpret_cast<void (*)(void*, void*)>(
        (*reinterpret_cast<uintptr_t**>(allocator))[11])(allocator, pointer);
}
static void* create_motion_clip(const uint8_t* bytes, uint32_t size, void* allocator) {
    // Construct one clip through the game's native stream and clip factories.
    // Initialize a temporary stream, decode its bounded bytes and destroy the stream wrapper.
    // The native clip owns its decoded storage after the borrowed input span is released.
    uintptr_t stream[4]{};
    game_function<void* (*)(void*)>(0x3845F0)(stream);
    game_function<bool (*)(void*, const void*, uint64_t, uint64_t)>(0x384650)(stream, bytes, 0, size);
    void* result = game_function<void* (*)(void*, void*)>(0x34EE10)(stream, allocator);
    game_function<void (*)(void*)>(0x384670)(stream);
    game_function<void (*)(void*)>(0x384640)(stream);
    return result;
}

static DWORD decode_motion_resource(void* object, bool selected_motion) {
    // Build native motion or camera resource fields from a validated package.
    // Allocate lookup storage, decode clips and clean every completed allocation on failure.
    // The stock decoder assumes success and can crash on allocator exhaustion.
    auto words = reinterpret_cast<uintptr_t*>(object);
    auto bytes = reinterpret_cast<const uint8_t*>(words[0x428 / 8]);
    const size_t size = words[0x440 / 8];
    if (!motion_package_bounds(bytes, size)) return ERROR_INVALID_DATA;
    auto allocator = reinterpret_cast<void*>(words[2]);
    const uint32_t count = package_u32(bytes, 20), hash = package_u32(bytes, 40), slots = package_u32(bytes, hash);
    auto clips = reinterpret_cast<uintptr_t*>(allocate_data(allocator, count * 8));
    auto lookup = reinterpret_cast<uintptr_t*>(allocate_data(allocator, 40));
    void* pairs = allocate_data(allocator, slots * 8);
    if (clips) memset(clips, 0, count * 8);
    uint32_t failed = 0;
    const bool allocated=clips && lookup && pairs;
    if (!allocated || !decode_motion_clips(bytes, size, allocator, create_motion_clip, clips, count, failed,
            selected_motion ? request.motion_keys : nullptr, selected_motion ? request.motion_count : 0)) {
        if (clips) for (uint32_t i = 0; i != count; ++i) if (clips[i]) {
            auto clip = reinterpret_cast<uintptr_t*>(clips[i]);
            if (--reinterpret_cast<uint32_t*>(clip)[2] == 0)
                reinterpret_cast<void (*)(void*)>(reinterpret_cast<uintptr_t*>(clip[0])[2])(clip);
        }
        free_data(allocator, clips); free_data(allocator, lookup); free_data(allocator, pairs);
        return allocated ? 0x20000000u|failed : ERROR_NOT_ENOUGH_MEMORY;
    }
    memcpy(pairs, bytes + hash + 8, slots * 8);
    lookup[0] = reinterpret_cast<uintptr_t>(allocator); lookup[1] = slots;
    lookup[2] = reinterpret_cast<uintptr_t>(pairs); lookup[3] = lookup[2] + slots * 8; lookup[4] = lookup[0];
    words[0x468 / 8] = reinterpret_cast<uintptr_t>(clips);
    words[0x470 / 8] = words[0x468 / 8] + count * 8;
    words[0x478 / 8] = reinterpret_cast<uintptr_t>(allocator);
    words[0x480 / 8] = reinterpret_cast<uintptr_t>(lookup);
    words[0x488 / 8] = reinterpret_cast<uintptr_t>(allocator);
    free_data(reinterpret_cast<void*>(words[0x430 / 8]), const_cast<uint8_t*>(bytes));
    words[0x428 / 8] = words[0x430 / 8] = 0;
    return 0;
}

template<class T> static bool read_field(uintptr_t address, T& value) {
    // Inspect a loader-side field without dereferencing an untrusted actor pointer.
    // Require a full-width read from the current process into owned storage.
    // Player discovery must tolerate objects disappearing between native frames.
    SIZE_T copied = 0;
    return ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<void*>(address), &value, sizeof(value), &copied)
        && copied == sizeof(value);
}

static void locate_player(void* actor) {
    // Identify William through the researched sword action-bank fingerprint.
    // Respect enabled-bank priority and publish the owner before the actor pointer.
    // Resource discovery must not mistake a boss with a colliding action key for the player.
    const auto node = reinterpret_cast<uintptr_t>(actor);
    uintptr_t vtable = 0, owner = 0;
    if (!read_field(node, vtable) || vtable != base + 0x11A3530
        || !read_field(node + 0x50, owner) || !owner) return;
    for (unsigned slot = 0; slot != 3; ++slot) {
        uintptr_t bank = 0, table = 0; uint32_t count = 0;
        if (!read_field(node + 0x70 + 8 * slot, bank) || !bank) continue;
        if (!read_field(bank + 0x128, table) || !read_field(bank + 0x130, count) || count > 4096) return;
        for (unsigned i = 0; i != count; ++i) {
            uintptr_t descriptor = 0, payload = 0; uint32_t key = 0; uint8_t enabled = 0; int32_t motion = 0;
            if (!read_field(table + 8 * i, descriptor) || !descriptor) continue;
            if (!read_field(descriptor, key) || key != 0xC64) continue;
            if (!read_field(descriptor + 0x40, enabled) || !enabled) continue;
            if (read_field(descriptor + 0x20, payload) && read_field(payload + 0x20, motion) && motion == 2033) {
                state->owner = owner;
                InterlockedExchange64(reinterpret_cast<volatile LONG64*>(&state->player), node);
            }
            return; // Same enabled-bank priority as native73FA40.
        }
    }
}

static void resource_decoded(void* object) {
    // Finalize only resources allocated and tracked by this loader.
    // Verify file size, decode motion packages and publish completion with atomic flags.
    // Borrowers must not receive a package before native I/O and decoding have completed.
    for (unsigned i = 0; i != 4; ++i) if (state->objects[i] == reinterpret_cast<uintptr_t>(object)) {
        if (*reinterpret_cast<uint64_t*>(reinterpret_cast<char*>(object) + 0x440) != request.sizes[i]) {
            InterlockedExchange(&state->error, ERROR_BAD_LENGTH);
            InterlockedExchange(&state->phase, 4);
            return;
        }
        if (i >= 2) {
            const DWORD error = decode_motion_resource(object, i==2);
            if (error) {
                *reinterpret_cast<uintptr_t*>(object) = original_tables[i];
                InterlockedExchange(&state->error, error);
                InterlockedExchange(&state->phase, 4);
                return;
            }
        } else reinterpret_cast<void (*)(void*)>(reinterpret_cast<uintptr_t*>(original_tables[i])[3])(object);
        *reinterpret_cast<uintptr_t*>(object) = original_tables[i];
        InterlockedOr(&state->completed, 1 << i);
        if (InterlockedCompareExchange(&state->completed, 0, 0) == 15)
            InterlockedExchange(&state->phase, 3);
        return;
    }
}

static void track_completion(unsigned i, void* object) {
    // Install a per-object completion callback while preserving its concrete vtable.
    // Copy RTTI and all observed virtual slots into module-lifetime storage.
    // Other resource objects and native type identity must remain unaffected.
    state->objects[i] = reinterpret_cast<uintptr_t>(object);
    auto table = *reinterpret_cast<uintptr_t**>(object);
    original_tables[i] = reinterpret_cast<uintptr_t>(table);
    memcpy(tables[i], table - 1, sizeof(tables[i]));
    // Preserve RTTI and every virtual slot of this concrete file resource.
    tables[i][4] = reinterpret_cast<uintptr_t>(&resource_decoded);
    *reinterpret_cast<uintptr_t**>(object) = tables[i] + 1;
}

static void submit_resources() {
    // Queue retained action, timing, motion and camera resources on the game thread.
    // Use the researched native constructors and archive callbacks after dependencies exist.
    // Mission actors must never own the imported packages or determine their lifetime.
    // TODO: verify retained package and combat-effect dependencies across the mission matrix.
    // Baseline cold-mission playback is confirmed; retaining four packages does not prove every later effect dependency.
    state->thread = GetCurrentThreadId();
    auto allocator = game_function<void* (*)()>(0xFA7080)();
    // FA7080 is the 24 MB file-object pool, not a motion-data allocator. The
    // native clip factory itself uses System+20 when no data allocator is given.
    auto system = *reinterpret_cast<uintptr_t*>(base + 0x2C946B8);
    auto manager = *reinterpret_cast<char**>(base + 0x1871538);
    // Startup frames can precede System availability. Release the submission
    // claim so a later frame retries before dereferencing its allocator field.
    if (!allocator || !system || !manager) {
        InterlockedExchange(&submitting, 0);
        return;
    }
    auto data_allocator = *reinterpret_cast<void**>(system + 0x20);
    // Effects can create an empty object even when its model/projectile resource is absent.
    // F91850 is the native object-asset retain/load path used at 760F67; each successful
    // request owns one reference. Reattaching this immutable loader never submits it again.
    if (request.object_count) {
        auto objects = *reinterpret_cast<void**>(base + 0x1766110);
        auto object_allocator = game_function<void* (*)()>(0xFA6FF0)();
        if (!objects || !object_allocator) { InterlockedExchange(&submitting, 0); return; }
        for (unsigned i=0; i<request.object_count; ++i) {
            auto asset = game_function<void* (*)(void*, int, void*, int)>(0xF91850)(
                objects, int(request.object_keys[i]), object_allocator, 0);
            if (!asset) {
                InterlockedExchange(&state->error, ERROR_OUTOFMEMORY);
                InterlockedExchange(&state->phase, 4);
                return;
            }
            state->object_assets[i] = reinterpret_cast<uintptr_t>(asset);
        }
    }
    auto allocate = reinterpret_cast<void* (*)(void*, size_t, size_t, void*)>(
        (*reinterpret_cast<uintptr_t**>(allocator))[7]);
    uint64_t category[2] = {0x2d, 0};
    // Same constructors, allocator and callback queue used at E824AC/E81D05.
    // Timing's inlined constructor at E830BE is reproduced before queueing;
    // calling its factory would publish the object before completion tracking.
    for (unsigned i = 0; i != 4; ++i) {
        void* object = allocate(allocator, i >= 2 ? 0x490 : 0x478, 8, category);
        if (!object) {
            InterlockedExchange(&state->error, ERROR_OUTOFMEMORY);
            InterlockedExchange(&state->phase, 4);
            return;
        }
        if (i == 1) {
            auto words = reinterpret_cast<uintptr_t*>(object);
            words[0] = base + 0x11AE2F0;
            words[1] = 1;
            words[2] = reinterpret_cast<uintptr_t>(data_allocator);
            words[3] = 0;
            game_function<void* (*)(void*, const char*, bool)>(0xFAF1B0)(
                reinterpret_cast<char*>(object) + 0x20, request.names[i], false);
            words[0] = base + 0x12C5408;
            words[0x468 / 8] = words[0x470 / 8] = 0;
            reinterpret_cast<char*>(object)[0x450] = 1;
        } else {
            game_function<void* (*)(void*, const char*, void*, bool)>(i == 0 ? 0xFAD9F0 : 0xFB7FE0)(
                object, request.names[i], data_allocator, false);
        }
        track_completion(i, object);
        const uintptr_t callback[] = {0xE7F410, 0xE7F060, 0xE7FB70, 0xE7FB70};
        uintptr_t queued[2] = {base + callback[i], reinterpret_cast<uintptr_t>(object) + 0x20};
        game_function<void (*)(void*, void*)>(0x80BB20)(manager + 0x10, queued);
    }
    InterlockedCompareExchange(&state->phase, 2, 1);
}

static float resource_frame(void* actor, float delta) {
    // Use an existing game-thread frame to discover the player and queue resources.
    // Count entered callbacks and preserve native arguments and LastError around loader work.
    // Detach can stop new work while outstanding callbacks and decoded assets remain valid.
    InterlockedIncrement(&callbacks);
    const DWORD error = GetLastError();
    if (!state->player) locate_player(actor);
    if (InterlockedCompareExchange(&state->phase, 0, 0) == 1
        && !InterlockedCompareExchange(&submitting, 1, 0)) submit_resources();
    SetLastError(error);
    const float result = frame_original(actor, delta);
    InterlockedDecrement(&callbacks);
    return result;
}

extern "C" __declspec(dllexport) DWORD WINAPI NiohResourcesStart(void* parameter) {
    // Start or reattach the retained resource loader for one exact profile and process birth.
    // Validate immutable request identity, create its mapping and install the researched frame hook.
    // Failed startup must remain retryable without borrowing a boss object or mission address.
    ResourceRequest incoming{};
    SIZE_T copied = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), parameter, &incoming, sizeof(incoming), &copied)
        || copied != sizeof(incoming) || incoming.magic != 0x3152504e || incoming.version != 5
        || incoming.pid != GetCurrentProcessId() || incoming.count != 4 || incoming.motion_count>32 || incoming.reserved
        || incoming.object_count>4 || incoming.object_reserved) return ERROR_INVALID_DATA;
    // The validated build has 0x149A native asset factories; profile keys select those factories,
    // never caller-provided function pointers. Canonical order also prevents duplicate retains.
    for (unsigned i=0; i<4; ++i)
        if (i<incoming.object_count ? (incoming.object_keys[i]>=0x149A
                || (i && incoming.object_keys[i]<=incoming.object_keys[i-1])) : incoming.object_keys[i]!=0)
            return ERROR_INVALID_DATA;
    FILETIME born{}, exit{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &born, &exit, &kernel, &user)) return GetLastError();
    if (incoming.birth != (uint64_t(born.dwHighDateTime) << 32 | born.dwLowDateTime)) return ERROR_INVALID_DATA;
    const uint8_t missing_identity[32]{};
    if (!memcmp(incoming.profile_identity, missing_identity, sizeof(missing_identity))) return ERROR_INVALID_DATA;
    for (unsigned i = 0; i != 4; ++i)
        if (incoming.names[i][0] == '/' || !memchr(incoming.names[i], 0, 80)
            || !incoming.sizes[i] || incoming.sizes[i] > 64 * 1024 * 1024) return ERROR_INVALID_DATA;
    if (state) {
        if (memcmp(&request, &incoming, sizeof(request))) return ERROR_ALREADY_EXISTS;
        InterlockedExchange64(reinterpret_cast<volatile LONG64*>(&state->player), 0);
        const auto result = MH_EnableHook(frame_target);
        return result == MH_OK || result == MH_ERROR_ENABLED ? 0 : 100 + result;
    }
    base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    frame_target = reinterpret_cast<void*>(base + 0x719050);
    const uint8_t expected[] = {0x40,0x53,0x48,0x83,0xec,0x20,0xf3,0x0f,0x11,0x89,0xa4,0x06,0,0};
    if (memcmp(frame_target, expected, sizeof(expected))) return ERROR_REVISION_MISMATCH;
    wchar_t name[128];
    const int prefix = wsprintfW(name, L"Local\\NiohResources_v8_%lu_", GetCurrentProcessId());
    const wchar_t digits[] = L"0123456789abcdef";
    for (unsigned i = 0; i != 32; ++i) {
        name[prefix + i * 2] = digits[incoming.profile_identity[i] >> 4];
        name[prefix + i * 2 + 1] = digits[incoming.profile_identity[i] & 15];
    }
    name[prefix + 64] = 0;
    mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(ResourceState), name);
    if (!mapping) return GetLastError();
    if (GetLastError() == ERROR_ALREADY_EXISTS) { CloseHandle(mapping); mapping = nullptr; return ERROR_ALREADY_EXISTS; }
    state = reinterpret_cast<ResourceState*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(ResourceState)));
    if (!state) {
        // A failed view has no callbacks or retained state. Release its handle
        // so the next Start can create the same mapping name successfully.
        const DWORD error = GetLastError();
        CloseHandle(mapping); mapping = nullptr;
        return error;
    }
    request = incoming;
    state->magic = 0x3152504e; state->version = 5; state->birth = request.birth;
    memcpy(state->profile_identity, request.profile_identity, sizeof(request.profile_identity));
    MH_STATUS result = MH_Initialize();
    if (result == MH_OK) result = MH_CreateHook(frame_target, reinterpret_cast<void*>(&resource_frame), reinterpret_cast<void**>(&frame_original));
    if (result == MH_OK) { hooked = true; InterlockedExchange(&state->phase, 1); result = MH_EnableHook(frame_target); }
    if (result != MH_OK) { InterlockedExchange(&state->error, 100 + result); InterlockedExchange(&state->phase, 4); }
    return result == MH_OK ? 0 : 100 + result;
}

extern "C" __declspec(dllexport) DWORD WINAPI NiohResourcesDetach(void*) {
    // Remove the temporary loader frame hook without releasing retained assets.
    // Disable new frame entries even when archive I/O is still pending.
    // Native I/O and runtime imports can still reference this module after hook removal.
    // Detach only removes the temporary frame hook. The module, trampoline and
    // owned resources remain loaded, including outstanding I/O after a failure.
    if (!hooked) return 0;
    const auto result = MH_DisableHook(frame_target);
    if (result != MH_OK && result != MH_ERROR_DISABLED) return 100 + result;
    return InterlockedCompareExchange(&callbacks, 0, 0) ? ERROR_BUSY : 0;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, void*) {
    // Keep DLL loading limited to loader-lock-safe bookkeeping.
    // Disable thread attach notifications and defer all native work to explicit exports.
    // Constructing resources or installing hooks under the Windows loader lock is unsafe.
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(module);
    return TRUE;
}
