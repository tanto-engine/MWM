// Owned local buffers and stubbed MinHook only; never attaches to another process.
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#define RESEARCH_DISPATCH
#include "../../outputs/okatsu-prototype/native/observer.cpp"

extern "C" MH_STATUS WINAPI MH_Initialize() { return MH_OK; }
extern "C" MH_STATUS WINAPI MH_Uninitialize() { return MH_OK; }
extern "C" MH_STATUS WINAPI MH_CreateHook(void*, void*, void**) { return MH_ERROR_UNSUPPORTED_FUNCTION; }
extern "C" MH_STATUS WINAPI MH_EnableHook(void*) { return MH_OK; }
extern "C" MH_STATUS WINAPI MH_DisableHook(void*) { return MH_OK; }

alignas(8) static std::array<unsigned char, 0x100> actor{}, owner{};
alignas(8) static std::array<unsigned char, 0x138> bank{};
alignas(8) static std::array<unsigned char, 0xD0> current{}, desired{}, duplicate{};
alignas(8) static std::array<unsigned char, 0x40> payload{};
static uint64_t descriptors[2];
static int64_t frequency;
static DispatchCommand c;
static unsigned checks;
static uint32_t seen_key;
static void* seen_context;
static bool native_result, native_commit;
static constexpr DWORD INCOMING = 0x11223344, NATIVE = 0xAABBCCDD;

template<class T> static void put(void* base, size_t offset, T value) {
    memcpy(static_cast<char*>(base) + offset, &value, sizeof(value));
}
static uint64_t address(const void* p) { return reinterpret_cast<uint64_t>(p); }
static void publish() {
    InterlockedExchange64(&dispatch->command.sequence_begin, 0);
    InterlockedExchange64(&dispatch->command.sequence_end, 0);
    memcpy(reinterpret_cast<char*>(&dispatch->command) + 8, reinterpret_cast<char*>(&c) + 8, 144);
    InterlockedExchange64(&dispatch->command.sequence_end, 1);
    InterlockedExchange64(&dispatch->command.sequence_begin, 1);
}
static void reset() {
    actor.fill(0); owner.fill(0); bank.fill(0); current.fill(0); desired.fill(0); payload.fill(0); duplicate.fill(0);
    put(actor.data(), 0, uint64_t(0xabcdef));
    put(actor.data(), 0x50, address(owner.data()));
    put(actor.data(), 0x58, address(current.data()));
    put(actor.data(), 0x70, address(bank.data()));
    put(desired.data(), 0, uint32_t(0xCF0));
    put(desired.data(), 0x20, address(payload.data()));
    desired[0x40] = 1;
    put(payload.data(), 0x20, int32_t(2033));
    put(payload.data(), 0x34, int32_t(-1));
    descriptors[0] = address(desired.data()); descriptors[1] = 0;
    put(bank.data(), 0x128, address(descriptors)); put(bank.data(), 0x130, uint32_t(1));
    stop_dispatch(); begin_dispatch();
    c = DispatchCommand{};
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    c.heartbeat_qpc = c.edge_qpc = now.QuadPart; c.expires_qpc = now.QuadPart + frequency;
    c.chord_sequence = 1; c.generation = dispatch->control.generation;
    c.player = address(actor.data()); c.owner = address(owner.data()); c.vtable = 0xabcdef;
    c.banks[0] = address(bank.data()); c.expected_descriptor = address(desired.data());
    c.expected_payload = address(payload.data()); c.desired_key = 0xCF0; c.expected_motion = 2033;
    c.armed = c.held = 1;
    publish();
    trace->header.enabled = 1; trace->header.written = 0; trace->header.dropped = 0;
    writer_lock = 0;
}
static void expect(DispatchReason reason, void* target = actor.data(), uint32_t key = 24, void* context = nullptr) {
    DispatchCommand copy{};
    auto actual = choose_dispatch(target, key, context, copy);
    if (actual != reason) std::printf("expected reason %u, got %u (check %u)\n", reason, actual, checks);
    assert(actual == reason); ++checks;
}
static bool fake_original(void* target, uint32_t key, void* context) {
    assert(GetLastError() == INCOMING);
    seen_key = key; seen_context = context;
    if (native_commit) put(target, 0x58, address(desired.data()));
    SetLastError(NATIVE); return native_result;
}
static void observed(bool result, bool commit) {
    native_result = result; native_commit = commit; original_action = fake_original;
    SetLastError(INCOMING);
    assert(observed_action(actor.data(), 24, nullptr) == result);
    assert(GetLastError() == NATIVE && seen_context == nullptr);
    ++checks;
}

int main() {
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency = freq.QuadPart;
    assert(open_dispatch(frequency) == 0);
    trace = static_cast<TraceMapping*>(VirtualAlloc(nullptr, sizeof(TraceMapping), MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(trace);
    reset(); expect(Accepted); expect(SequenceConsumed);
    c.chord_sequence = 2; publish(); expect(ShotUsed);
    auto generation = dispatch->control.generation;
    begin_dispatch(); assert(dispatch->control.generation == generation && dispatch->control.dispatch_count == 1); ++checks;
    reset(); expect(WrongActor, owner.data());
    reset(); expect(IneligibleRequest, actor.data(), 3000);
    reset(); expect(NonNullContext, actor.data(), 24, bank.data());
    reset(); c.armed = 0; publish(); expect(NotArmed);
    reset(); --c.generation; publish(); expect(WrongGeneration);
    reset(); c.held = 0; publish(); expect(Released);
    reset(); c.edge_qpc -= frequency / 2; c.heartbeat_qpc -= frequency / 5; publish(); expect(StaleHeartbeat);
    reset(); c.edge_qpc -= frequency; c.expires_qpc = c.heartbeat_qpc - 1; publish(); expect(Expired);
    reset(); c.expires_qpc = c.edge_qpc + frequency * 2; publish(); expect(InvalidTime);
    reset(); c.heartbeat_qpc += frequency; publish(); expect(InvalidTime);
    reset(); c.player = 0; publish(); expect(InvalidConfig);
    reset(); c.desired_key = 0; publish(); expect(DesiredInvalid);
    reset(); InterlockedExchange64(&dispatch->command.sequence_end, 2); expect(UnstableCommand);
    reset(); put(actor.data(), 0x50, uint64_t(0x12345)); expect(OwnerMismatch);
    reset(); put(actor.data(), 0, uint64_t(0x12345)); expect(VtableMismatch);
    reset(); put(actor.data(), 0x78, uint64_t(0x12345)); expect(BankMismatch);
    reset(); put(actor.data(), 0x58, uint64_t(1)); expect(IdentityReadFailed);
    reset(); put(current.data(), 0, uint32_t(0xC64)); expect(CurrentNotAllowed);
    reset(); put(bank.data(), 0x130, uint32_t(0)); expect(DesiredMissing);
    reset(); put(bank.data(), 0x130, uint32_t(4097)); expect(DesiredInvalid);
    reset(); desired[0x40] = 0; expect(DesiredMissing);
    reset(); put(desired.data(), 0, uint32_t(0x10000CF0)); expect(DesiredMissing);
    reset(); c.expected_descriptor = address(duplicate.data()); publish(); expect(DesiredMismatch);
    reset(); put(payload.data(), 0x20, int32_t(999)); expect(DesiredMismatch);
    reset(); put(duplicate.data(), 0, uint32_t(0xCF0)); duplicate[0x40] = 1;
    descriptors[0] = address(duplicate.data()); descriptors[1] = address(desired.data());
    put(bank.data(), 0x130, uint32_t(2)); expect(DesiredMismatch);
    duplicate[0x40] = 0; expect(Accepted);

    reset(); observed(true, true);
    assert(seen_key == 0xCF0 && trace->header.written == 1);
    auto& success = trace->records[0];
    assert(success.input_key == 24 && success.reserved == 0xCF0 && success.after_key == 0xCF0);
    assert(success.native_result == 1 && (success.valid_fields & TRACE_SUBSTITUTED)
        && (success.valid_fields & TRACE_FINAL_MATCH)); ++checks;
    // A second eligible request cannot repeat, even after re-entering an allowed state.
    put(actor.data(), 0x58, address(current.data())); observed(true, false);
    assert(seen_key == 24 && dispatch->control.dispatch_count == 1); ++checks;
    reset(); observed(false, false);
    assert(seen_key == 0xCF0 && trace->records[0].native_result == 0
        && (trace->records[0].valid_fields & TRACE_SUBSTITUTED)
        && !(trace->records[0].valid_fields & TRACE_FINAL_MATCH)); ++checks;
    reset(); observed(false, true);
    assert(trace->records[0].native_result == 0 && (trace->records[0].valid_fields & TRACE_FINAL_MATCH)); ++checks;
    reset(); c.held = 0; publish(); observed(true, false);
    assert(seen_key == 24 && (trace->records[0].valid_fields >> 8 & 255) == Released); ++checks;
    reset(); stop_dispatch(); expect(Disabled);
    auto saved = dispatch; hook_created = true; original_action = fake_original;
    assert(NiohResearchStop(nullptr) == 0 && dispatch == saved && original_action == fake_original); ++checks;
    hook_created = false; cleanup_dispatch(); VirtualFree(trace, 0, MEM_RELEASE); trace = nullptr;
    std::printf("dispatch offline checks passed: %u\n", checks);
}
