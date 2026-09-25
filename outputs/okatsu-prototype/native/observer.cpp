// Passive builds forward all game arguments and results unchanged. Repeat mode
// schedules gestures, shortens the C64 windup, and filters two exact boss voices.
#include <windows.h>
#include <stdint.h>
#include <wchar.h>
#include "MinHook.h"
#include "trace_protocol.h"

using ActionFn = bool (*)(void*, uint32_t, void*);
static ActionFn original_action;
static void* hook_target;
static TraceMapping* trace;
static HANDLE mapping_handle;
static volatile LONG writer_lock, lifecycle_lock;
static bool hook_created, minhook_initialized;
#ifdef RESEARCH_REPEAT
// RVA719050 takes RCX=action node, XMM1=delta. XMM0 is the effective delta;
// preserve it except for the explicitly scoped C64 early-clock adjustment.
using FrameFn = float (*)(void*, float);
static FrameFn original_frame;
static void* frame_target;
static bool frame_hook_created;
using VoiceFn = void (*)(void*, void*, void*, int32_t);
static VoiceFn original_voice;
static void* voice_target;
static bool voice_hook_created;
#endif

template<class T> static bool copy_field(uint64_t address, T& value) {
    SIZE_T count = 0;
    return address >= 0x10000 && ReadProcessMemory(GetCurrentProcess(),
        reinterpret_cast<void*>(address), &value, sizeof(value), &count) && count == sizeof(value);
}

#ifdef RESEARCH_DISPATCH
#include "dispatch_support.h"
#endif
#ifdef RESEARCH_REPEAT
#include "voice_support.h"
#include "windup_support.h"
#endif

static bool observed_action_impl(void* actor, uint32_t key, void* context, bool frame_mode) {
    const DWORD incoming_error = GetLastError();
#ifdef RESEARCH_BOSS
    BossCallScope scope;
#endif
    TraceRecord record{};
    const bool record_this = trace && InterlockedCompareExchange(&trace->header.enabled, 0, 0);
    uint32_t forwarded_key = key;
    void* forwarded_context = context;
#ifdef RESEARCH_DISPATCH
    DispatchCommand command{};
    DispatchReason reason = record_this ? choose_dispatch(actor, key, context, command, frame_mode) : Disabled;
    if (reason == Accepted) forwarded_key = command.desired_key;
#else
    (void)frame_mode;
#endif
#ifdef RESEARCH_REPEAT
    if (frame_mode && reason != Accepted) { SetLastError(incoming_error); return false; }
    uint64_t current = 0;
    const bool suppress_guard = !frame_mode && !context && (key == 24 || key == 25)
        && InterlockedCompareExchange(&boss_active, 0, 0)
        && reinterpret_cast<uint64_t>(actor) == boss_active_player && boss_player_valid()
        && copy_field(boss_active_player + 0x58, current) && boss_is_preview_descriptor(current);
    if (suppress_guard) reason = BossGuardSuppressed;
#endif
    if (record_this) {
        record.actor = reinterpret_cast<uint64_t>(actor);
        record.context = reinterpret_cast<uint64_t>(context);
        record.input_key = key;
        record.thread_id = GetCurrentThreadId();
        LARGE_INTEGER now; QueryPerformanceCounter(&now); record.qpc = now.QuadPart;
        if (copy_field(record.actor + 0x50, record.owner)) record.valid_fields |= 1;
        if (copy_field(record.actor + 0x58, record.before) && copy_field(record.before, record.before_key))
            record.valid_fields |= 2;
    }
#ifdef RESEARCH_BOSS
    uint64_t private_banks[3]{};
#ifdef RESEARCH_REPEAT
    if (!suppress_guard)
#endif
    boss_prepare_call(actor, key, reason, command, forwarded_key, forwarded_context, private_banks);
#ifdef RESEARCH_REPEAT
    // A failed frame preflight never turns into an unsolicited key-0 setter.
    if (frame_mode && reason != Accepted) { SetLastError(incoming_error); return false; }
#endif
#endif
#ifdef RESEARCH_DISPATCH
    record.reserved = forwarded_key;
    record.valid_fields |= uint32_t(reason) << 8;
    if (reason == Accepted) record.valid_fields |= TRACE_SUBSTITUTED;
#ifdef RESEARCH_REPEAT
    if (frame_mode) record.valid_fields |= 1u << 18; // Generated from native frame callback.
#endif
#endif
    SetLastError(incoming_error);
#ifdef RESEARCH_REPEAT
    const bool result = suppress_guard ? false : original_action(actor, forwarded_key, forwarded_context);
#else
    const bool result = original_action(actor, forwarded_key, forwarded_context);
#endif
    const DWORD native_error = GetLastError();
#ifdef RESEARCH_BOSS
    boss_finish_call(actor);
#endif
    if (!record_this) { SetLastError(native_error); return result; }
    record.native_result = result;
    if (copy_field(record.actor + 0x58, record.after) && copy_field(record.after, record.after_key))
        record.valid_fields |= 4;
    if (copy_field(record.actor + 0x68, record.bank)) record.valid_fields |= 8;
    if ((record.valid_fields & 4) && copy_field(record.after + 0x20, record.payload)
        && copy_field(record.payload + 0x20, record.motion_key)
        && copy_field(record.payload + 0x34, record.timing_key)) record.valid_fields |= 16;
#ifdef RESEARCH_DISPATCH
    if (reason == Accepted && (record.valid_fields & 20) == 20
        && record.after == command.expected_descriptor && record.after_key == command.desired_key
        && record.payload == command.expected_payload && record.motion_key == command.expected_motion)
        record.valid_fields |= TRACE_FINAL_MATCH;
#endif
    // Contention drops an observation instead of blocking a game thread.
    if (InterlockedCompareExchange(&writer_lock, 1, 0)) {
        InterlockedIncrement64(&trace->header.dropped);
        SetLastError(native_error);
        return result;
    }
    const LONG64 sequence = InterlockedCompareExchange64(&trace->header.written, 0, 0) + 1;
    TraceRecord* slot = &trace->records[(sequence - 1) % TRACE_CAPACITY];
    InterlockedExchange64(&slot->sequence_begin, 0);
    InterlockedExchange64(&slot->sequence_end, 0);
    // The sequence markers are written separately around the payload copy.
    CopyMemory(reinterpret_cast<char*>(slot) + 8, reinterpret_cast<char*>(&record) + 8, sizeof(record)-16);
    InterlockedExchange64(&slot->sequence_end, sequence);
    InterlockedExchange64(&slot->sequence_begin, sequence);
    InterlockedExchange64(&trace->header.written, sequence);
    InterlockedExchange(&writer_lock, 0);
    SetLastError(native_error);
    return result;
}

static bool observed_action(void* actor, uint32_t key, void* context) {
    return observed_action_impl(actor, key, context, false);
}

#ifdef RESEARCH_REPEAT
static float observed_frame(void* actor, float delta) {
    const DWORD incoming_error = GetLastError();
    BossCallScope scope; // Stop retains callbacks while one is in progress.
    SetLastError(incoming_error);
    float result = original_frame(actor, delta);
    const DWORD native_error = GetLastError();
    result = boss_shorten_rush_windup(actor, result);
    if (trace && dispatch && InterlockedCompareExchange(&trace->header.enabled, 0, 0)
        && InterlockedCompareExchange(&dispatch->control.enabled, 0, 0)
        && reinterpret_cast<uint64_t>(actor) == boss_session.player
        && !InterlockedCompareExchange(&boss_active, 0, 0)) {
        DispatchCommand pending{};
        if (snapshot_command(pending) && pending.armed == 1
            && pending.chord_sequence > uint64_t(InterlockedCompareExchange64(&dispatch->control.consumed_sequence, 0, 0))) {
            SetLastError(native_error);
            observed_action_impl(actor, 0, nullptr, true);
        }
    }
    SetLastError(native_error);
    return result;
}

static void observed_voice(void* state, void* timing_record, void* event, int32_t override_bank) {
    const DWORD incoming_error = GetLastError();
    BossCallScope scope;
    const bool suppress = boss_suppress_voice(state, timing_record, event);
    if (suppress && dispatch)
        InterlockedIncrement(reinterpret_cast<volatile LONG*>(&dispatch->control.reserved1));
    SetLastError(incoming_error);
    if (suppress) return;
    original_voice(state, timing_record, event, override_bank);
    // Only void callers were found. The original handler's LastError passes
    // through; the scope's interlocked decrement does not change it.
}

static bool frame_prologue_matches(void* target) {
    const uint8_t expected[] = {0x40,0x53,0x48,0x83,0xec,0x20,0xf3,0x0f,0x11,0x89,0xa4,0x06,0,0,
        0x48,0x8b,0xd9,0xe8,0x5a,0x8e,0x03,0,0x4c,0x8b,0x43,0x50,0xf3,0x0f,0x11,0x83,0xa8,0x06};
    uint8_t actual[sizeof(expected)]; SIZE_T read = 0;
    return ReadProcessMemory(GetCurrentProcess(), target, actual, sizeof(actual), &read)
        && read == sizeof(actual) && !memcmp(actual, expected, sizeof(actual));
}

static bool voice_prologue_matches(void* target) {
    const uint8_t expected[] = {0x44,0x89,0x4c,0x24,0x20,0x55,0x53,0x57,0x41,0x57,
        0x48,0x8d,0xac,0x24,0x68,0xff,0xff,0xff,0x48,0x81,0xec,0x98,0x01,0,0,
        0x49,0x63,0x40,0x08,0x41,0x8b,0xd9};
    uint8_t actual[sizeof(expected)]; SIZE_T read = 0;
    return ReadProcessMemory(GetCurrentProcess(), target, actual, sizeof(actual), &read)
        && read == sizeof(actual) && !memcmp(actual, expected, sizeof(actual));
}

static MH_STATUS disable_repeat_hooks() {
    MH_STATUS result = MH_OK;
    void* targets[] = {voice_hook_created ? voice_target : nullptr,
                      frame_hook_created ? frame_target : nullptr,
                      hook_created ? hook_target : nullptr};
    for (void* target : targets) if (target) {
        MH_STATUS stopped = MH_DisableHook(target);
        if (stopped != MH_OK && stopped != MH_ERROR_DISABLED) result = stopped;
    }
    return result;
}

static MH_STATUS rollback_repeat_hooks(MH_STATUS error) {
    stop_dispatch();
    if (trace) InterlockedExchange(&trace->header.enabled, 0);
    disable_repeat_hooks();
    // Retain all created trampolines/mappings for callbacks already entered.
    return error;
}

static MH_STATUS enable_repeat_hooks() {
    if (!frame_hook_created) {
        MH_STATUS created = MH_CreateHook(frame_target, reinterpret_cast<void*>(&observed_frame),
                                         reinterpret_cast<void**>(&original_frame));
        if (created != MH_OK) return rollback_repeat_hooks(created);
        frame_hook_created = true;
    }
    if (!voice_hook_created) {
        MH_STATUS created = MH_CreateHook(voice_target, reinterpret_cast<void*>(&observed_voice),
                                         reinterpret_cast<void**>(&original_voice));
        if (created != MH_OK) return rollback_repeat_hooks(created);
        voice_hook_created = true;
    }
    MH_STATUS result = MH_EnableHook(hook_target);
    if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    result = MH_EnableHook(frame_target);
    if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    result = MH_EnableHook(voice_target);
    if (result != MH_OK && result != MH_ERROR_ENABLED) return rollback_repeat_hooks(result);
    return MH_OK;
}
#endif

// Only called before a hook exists: no callback can be using these resources.
// Once created, even an enable failure retains the trampoline/mapping for retry.
static DWORD cleanup_before_hook(DWORD error) {
    if (hook_created) return error;
#ifdef RESEARCH_DISPATCH
    cleanup_dispatch();
#endif
    if (minhook_initialized) {
        MH_STATUS result = MH_Uninitialize();
        if (result == MH_OK || result == MH_ERROR_NOT_INITIALIZED)
            minhook_initialized = false;
    }
    if (trace) { UnmapViewOfFile(trace); trace = nullptr; }
    if (mapping_handle) { CloseHandle(mapping_handle); mapping_handle = nullptr; }
    original_action = nullptr;
#ifdef RESEARCH_REPEAT
    original_frame = nullptr;
    original_voice = nullptr;
#endif
    return error;
}

static DWORD start_observer() {
    if (hook_created) {
        MH_STATUS result =
#ifdef RESEARCH_REPEAT
            enable_repeat_hooks();
#else
            MH_EnableHook(hook_target);
#endif
        if (result != MH_OK && result != MH_ERROR_ENABLED) {
            InterlockedExchange(&trace->header.status, -(100 + result));
            return 100 + result;
        }
#ifdef RESEARCH_DISPATCH
        begin_dispatch();
#endif
        InterlockedExchange(&trace->header.enabled, 1);
        InterlockedExchange(&trace->header.status, 1);
        return 0;
    }
    HMODULE main = GetModuleHandleW(nullptr);
    wchar_t path[32768];
    if (!GetModuleFileNameW(main, path, 32768)) return 1;
    wchar_t* name = wcsrchr(path, L'\\');
    if (!name) return 2;
    ++name;
#ifdef RESEARCH_HARNESS
    if (_wcsicmp(name, L"nioh_hook_harness.exe")) return 3;
    hook_target = reinterpret_cast<void*>(GetProcAddress(main, "HarnessAction"));
    if (!hook_target) return 4;
#ifdef RESEARCH_REPEAT
    frame_target = reinterpret_cast<void*>(GetProcAddress(main, "HarnessFrame"));
    if (!frame_target) return 4;
    voice_target = reinterpret_cast<void*>(GetProcAddress(main, "HarnessVoice"));
    if (!voice_target) return 4;
#endif
#else
    if (_wcsicmp(name, L"nioh.exe")) return 3;
    // Launcher also validates the exact executable SHA-256 and process birth time.
    hook_target = reinterpret_cast<char*>(main) + 0x70ece0;
    const uint8_t expected[] = {0x48,0x8b,0xc4,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,
        0x48,0x81,0xec,0x80,0,0,0,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff};
    uint8_t actual[sizeof(expected)]; SIZE_T read = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), hook_target, actual, sizeof(actual), &read)
        || read != sizeof(actual) || memcmp(actual, expected, sizeof(actual))) return 5;
#ifdef RESEARCH_REPEAT
    frame_target = reinterpret_cast<char*>(main) + 0x719050;
    if (!frame_prologue_matches(frame_target)) return 5;
    voice_target = reinterpret_cast<char*>(main) + 0x9670a0;
    if (!voice_prologue_matches(voice_target)) return 5;
#endif
#endif
    wchar_t mapping_name[96];
#ifdef RESEARCH_REPEAT
    repeat_mapping_name(mapping_name, L"Trace", GetCurrentProcessId(), BOSS_CONFIG_TAG);
#elif defined(RESEARCH_BOSS)
    wsprintfW(mapping_name, L"Local\\NiohBossTrace_v1_%lu", GetCurrentProcessId());
#elif defined(RESEARCH_DISPATCH)
    wsprintfW(mapping_name, L"Local\\NiohDispatchTrace_v1_%lu", GetCurrentProcessId());
#else
    wsprintfW(mapping_name, L"Local\\NiohResearchTrace_v1_%lu", GetCurrentProcessId());
#endif
    mapping_handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
                                      sizeof(TraceMapping), mapping_name);
    if (!mapping_handle) return 6;
    const DWORD existed = GetLastError();
    if (existed == ERROR_ALREADY_EXISTS) { CloseHandle(mapping_handle); mapping_handle = nullptr; return 7; }
    trace = reinterpret_cast<TraceMapping*>(MapViewOfFile(mapping_handle, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(TraceMapping)));
    if (!trace) { CloseHandle(mapping_handle); mapping_handle = nullptr; return 8; }
    ZeroMemory(trace, sizeof(*trace));
    LARGE_INTEGER frequency; QueryPerformanceFrequency(&frequency);
    trace->header.magic = TRACE_MAGIC; trace->header.version = TRACE_VERSION;
    trace->header.capacity = TRACE_CAPACITY; trace->header.record_size = sizeof(TraceRecord);
    trace->header.qpc_frequency = frequency.QuadPart;
    trace->header.hook_address = reinterpret_cast<uint64_t>(hook_target);
    trace->header.module_base = reinterpret_cast<uint64_t>(main);
#ifdef RESEARCH_DISPATCH
    const DWORD command_error = open_dispatch(frequency.QuadPart);
    if (command_error) return cleanup_before_hook(command_error);
#endif
    MH_STATUS result = MH_OK;
    if (!minhook_initialized) {
        result = MH_Initialize();
        if (result != MH_OK) return cleanup_before_hook(100 + result);
        minhook_initialized = true;
    }
    result = MH_CreateHook(hook_target, reinterpret_cast<void*>(&observed_action), reinterpret_cast<void**>(&original_action));
    if (result != MH_OK) return cleanup_before_hook(100 + result);
    hook_created = true;
    result =
#ifdef RESEARCH_REPEAT
        enable_repeat_hooks();
#else
        MH_EnableHook(hook_target);
#endif
    if (result != MH_OK) { InterlockedExchange(&trace->header.status, -(100 + result)); return 100 + result; }
#ifdef RESEARCH_DISPATCH
    begin_dispatch();
#endif
    InterlockedExchange(&trace->header.enabled, 1);
    InterlockedExchange(&trace->header.status, 1);
    return 0;
}

extern "C" __declspec(dllexport) DWORD WINAPI NiohResearchStart(void*) {
    if (InterlockedCompareExchange(&lifecycle_lock, 1, 0)) return 9;
#ifdef RESEARCH_BOSS
    if (InterlockedCompareExchange(&boss_active, 0, 0) || InterlockedCompareExchange(&boss_inflight, 0, 0)) {
        InterlockedExchange(&lifecycle_lock, 0); return ERROR_BUSY;
    }
#endif
    DWORD result = start_observer();
    InterlockedExchange(&lifecycle_lock, 0);
    return result;
}

extern "C" __declspec(dllexport) DWORD WINAPI NiohResearchStop(void*) {
    if (InterlockedCompareExchange(&lifecycle_lock, 1, 0)) return 9;
    if (!hook_created) { InterlockedExchange(&lifecycle_lock, 0); return 0; }
#ifdef RESEARCH_BOSS
    InterlockedExchange(&dispatch->control.enabled, 0);
    if (InterlockedCompareExchange(&boss_active, 0, 0) || InterlockedCompareExchange(&boss_inflight, 0, 0)) {
        InterlockedExchange(&trace->header.status, 2);
        InterlockedExchange(&lifecycle_lock, 0);
        return ERROR_BUSY;
    }
#endif
#ifdef RESEARCH_DISPATCH
    stop_dispatch();
#endif
    InterlockedExchange(&trace->header.enabled, 0);
#ifdef RESEARCH_REPEAT
    MH_STATUS result = disable_repeat_hooks();
#else
    MH_STATUS result = MH_DisableHook(hook_target);
#endif
    InterlockedExchange(&trace->header.status, result == MH_OK || result == MH_ERROR_DISABLED ? 0 : -(100+result));
    InterlockedExchange(&lifecycle_lock, 0);
    // Keep DLL/trampoline/mapping allocated until process exit. An already-entered
    // callback can still return through them after the entry patch is removed.
    return result == MH_OK || result == MH_ERROR_DISABLED ? 0 : 100+result;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, void*) {
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(module);
    return TRUE;
}
