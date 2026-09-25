// Direct unit calls only. MinHook is stubbed: this test never patches any code.
#include <cassert>
#include <cstring>
#include <cstdio>
#include "../../outputs/okatsu-prototype/native/observer.cpp"

static unsigned uninitialize_calls;
extern "C" MH_STATUS WINAPI MH_Initialize() {
    // Stub hook-library startup inside the disposable test process.
    // Return the fixture's startup result without installing a hook manager.
    // Native callback guards can then be tested without patching game code.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_Uninitialize() {
    // Stub hook-library cleanup for direct callback tests.
    // Expose the fixture's cleanup behavior without releasing a real hook library.
    // Failure paths must preserve owned mappings once callbacks could retain them.
    ++uninitialize_calls; return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_CreateHook(void*, void*, void**) {
    // Control hook creation outcomes without modifying executable instructions.
    // Return the fixture's requested success or failure from this link-time stub.
    // The harness exercises rollback and ownership independently of MinHook internals.
    return MH_ERROR_UNSUPPORTED_FUNCTION;
}
extern "C" MH_STATUS WINAPI MH_EnableHook(void*) {
    // Control hook-enable outcomes within the owned-memory fixture.
    // Use the local stub instead of patching the supplied target address.
    // Partial startup must be testable without any running game or real trampoline.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_DisableHook(void*) {
    // Model hook disabling while leaving this process's code unchanged.
    // Return the fixture result and preserve its local call accounting where needed.
    // Stop and rollback tests can inspect cleanup without racing an actual hook.
    return MH_OK;
}

static DWORD seen_incoming;
static bool desired_result;
static constexpr DWORD INCOMING = 0x11223344, NATIVE = 0xAABBCCDD;
static bool fake_original(void*, uint32_t key, void* context) {
    // Simulate the original native setter using only the owned fixture.
    // Assert forwarded arguments and expose the configured result and LastError.
    // Wrapper tests must distinguish native behavior from the adapter's decisions.
    seen_incoming = GetLastError();
    assert(key == 0xC64 && context == reinterpret_cast<void*>(0x123456));
    SetLastError(NATIVE);
    return desired_result;
}

static void check_call(bool enabled, bool locked, bool expected_result) {
    // Exercise the passive observer with trace enabled, disabled or contended.
    // Use an unreadable owned-test address and assert arguments, return and LastError.
    // Tracing failures must never change the underlying native call's behavior.
    trace->header.enabled = enabled;
    writer_lock = locked;
    desired_result = expected_result;
    SetLastError(INCOMING);
    // Deliberately unreadable actor tests RPM failures without a dereference.
    bool result = observed_action(reinterpret_cast<void*>(1), 0xC64, reinterpret_cast<void*>(0x123456));
    DWORD error = GetLastError();
    assert(seen_incoming == INCOMING && error == NATIVE);
    assert(result == expected_result);
    writer_lock = 0;
}

int main() {
    // Exercise passive trace failures without changing native setter behavior.
    // Use a real owned mapping and controlled callbacks under writer contention.
    // Tracing must preserve results and errors even when actor memory cannot be read.
    mapping_handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
        0, sizeof(TraceMapping), nullptr);
    assert(mapping_handle);
    trace = reinterpret_cast<TraceMapping*>(MapViewOfFile(mapping_handle, FILE_MAP_ALL_ACCESS,
        0, 0, sizeof(TraceMapping)));
    assert(trace);
    ZeroMemory(trace, sizeof(*trace));
    original_action = fake_original;
    check_call(false, false, false);
    check_call(true, false, true);
    assert(trace->header.written == 1 && trace->records[0].native_result == 1);
    assert(trace->records[0].valid_fields == 0);
    assert(trace->records[0].sequence_begin == 1 && trace->records[0].sequence_end == 1);
    check_call(true, true, false);
    assert(trace->header.written == 1 && trace->header.dropped == 1);

    // Stop keeps an existing hook's mapping and trampoline even when disabled.
    hook_created = true;
    auto saved_trace = trace;
    auto saved_handle = mapping_handle;
    assert(NiohResearchStop(nullptr) == 0);
    assert(trace == saved_trace && mapping_handle == saved_handle && original_action == fake_original);
    assert(trace->header.enabled == 0 && trace->header.status == 0);
    assert(cleanup_before_hook(123) == 123 && trace == saved_trace && uninitialize_calls == 0);

    // Initialization failures before any hook existed release their resources.
    hook_created = false;
    minhook_initialized = true;
    assert(cleanup_before_hook(108) == 108);
    assert(!trace && !mapping_handle && !original_action && !minhook_initialized);
    assert(uninitialize_calls == 1);
    std::puts("observer unit checks passed: LastError, native return, invalid reads, contention, stop lifetime, prehook cleanup");
    return 0;
}
