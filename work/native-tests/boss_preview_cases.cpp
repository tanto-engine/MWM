#define RESEARCH_RUNTIME_SESSION
// Owned buffers and fake setter only. No game process or controller access.
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#define RESEARCH_BOSS
#define RESEARCH_DISPATCH
#include "../../runtime/native/observer.cpp"

static unsigned disable_calls;
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
    return MH_OK;
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
    ++disable_calls; return MH_OK;
}

alignas(8) static std::array<unsigned char, 0x100> player{}, player_owner{};
alignas(8) static std::array<unsigned char,0x478> source{}, source_owner{};
alignas(8) static std::array<unsigned char, 0x100> motion{}, timing{}, source_motion{}, source_timing{};
alignas(8) static std::array<unsigned char, 0x138> source_bank{}, player_bank{};
alignas(8) static std::array<unsigned char, 0xD0> current{}, desired{};
alignas(8) static std::array<unsigned char, 0x40> payload{};
static uint64_t source_entries[2];
static DispatchCommand command;
static unsigned checks;
static int64_t frequency;
static bool wanted_result, wanted_commit, wanted_borrowed, wanted_source_context;
static uint32_t wanted_key;
static uint64_t commit_descriptor;
static constexpr DWORD INCOMING = 0x11223344, NATIVE = 0xAABBCCDD;

template<class T> static void put(void* base, size_t offset, T value) {
    // Write captured native-layout fields into memory owned by the harness.
    // Use memcpy so byte offsets do not create unaligned typed accesses.
    // The fixture must exercise real ABI offsets without requiring live game memory.
    memcpy(static_cast<char*>(base) + offset, &value, sizeof(value));
}
static uint64_t address(const void* p) {
    // Represent an owned fixture pointer in the runtime's integer-address ABI.
    // Preserve the pointer value without allocating or extending its lifetime.
    // Transient test addresses must never become permanent catalogue identities.
    return reinterpret_cast<uint64_t>(p);
}
static void assert_bindings(bool borrowed) {
    // Verify every adapted motion and timing slot against its expected owner.
    // Read all four fields and compare with either original or borrowed resources.
    // A partial restore or mixed resource set must fail the test immediately.
    for (unsigned i = 0; i < 4; ++i) {
        uint64_t actual = 0;
        assert(copy_field(boss_slot(i), actual));
        assert(actual == (borrowed ? boss_borrowed(i) : boss_session.originals[i]));
    }
    ++checks;
}
static bool fake_original(void* actor, uint32_t key, void* context) {
    // Simulate the original native setter using only the owned fixture.
    // Assert forwarded arguments and expose the configured result and LastError.
    // Wrapper tests must distinguish native behavior from the adapter's decisions.
    assert(GetLastError() == INCOMING && actor == player.data() && key == wanted_key);
    if (wanted_source_context) {
        assert(context);
        auto* banks = static_cast<uint64_t*>(context);
        assert(banks[0] == 0 && banks[1] == address(source_bank.data()) && banks[2] == 0);
    } else assert(context == nullptr);
    assert_bindings(wanted_borrowed);
    if (wanted_commit) put(actor, 0x58, commit_descriptor);
    SetLastError(NATIVE); return wanted_result;
}
static void publish() {
    // Commit a prepared command into the harness's shared mapping.
    // Publish the fixture's sequence markers and actor/action fields together.
    // Each failure case must mutate the intended guard without inheriting a torn command.
    InterlockedExchange64(&dispatch->command.sequence_begin, 0);
    InterlockedExchange64(&dispatch->command.sequence_end, 0);
    memcpy(reinterpret_cast<char*>(&dispatch->command) + 8, reinterpret_cast<char*>(&command) + 8, 144);
    InterlockedExchange64(&dispatch->command.sequence_end, 1);
    InterlockedExchange64(&dispatch->command.sequence_begin, 1);
}
static void reset() {
    // Rebuild valid owned actor, resource and command state between cases.
    // Populate the researched native offsets and reset the callback control fields.
    // Prior failures must not leak consumed gestures or borrowed slots into later checks.
    player.fill(0); player_owner.fill(0); source.fill(0); source_owner.fill(0);
    motion.fill(0); timing.fill(0); source_motion.fill(0); source_timing.fill(0);
    source_bank.fill(0); player_bank.fill(0); current.fill(0); desired.fill(0); payload.fill(0);
    boss_session = BossSession{};
    boss_session.player = address(player.data()); boss_session.player_owner = address(player_owner.data());
    boss_session.source_action_resource = address(source.data()); boss_session.source_timing_resource = address(source_owner.data());
    boss_session.vtable = 0xabcdef; boss_session.source_bank = address(source_bank.data());
    boss_session.source_descriptor = address(desired.data()); boss_session.source_payload = address(payload.data());

    boss_session.source_motion_bank=address(source_motion.data()); boss_session.source_timing_wrapper = 0x20002;
    boss_session.player_motion = address(motion.data()); boss_session.player_timing = address(timing.data());
    const auto module=address(GetModuleHandleW(nullptr));
    put(source.data(),0,module+0x13C7970); put(source.data(),0x468,boss_session.source_bank);
    put(source_owner.data(),0,module+0x12C5408); put(source_owner.data(),0x468,uint64_t(0x20002));
    put(source_motion.data(),0,module+0x13C8FA0);
    for (unsigned i = 0; i < 4; ++i) {
        boss_session.originals[i] = 0x10001 + i;
        put(reinterpret_cast<void*>(boss_slot(i)), 0, boss_session.originals[i]);
    }
    put(player.data(), 0, boss_session.vtable);
    put(player.data(), 0x50, boss_session.player_owner);
    put(player.data(), 0x58, address(current.data())); put(player.data(), 0x70, address(player_bank.data()));
    put(player_owner.data(), 0x38, boss_session.player_motion); put(player_owner.data(), 0x68, boss_session.player_timing);




    put(desired.data(), 0, uint32_t(0xC64)); put(desired.data(), 0x20, address(payload.data())); desired[0x40] = 1;
    put(payload.data(), 0x20, int32_t(1220)); put(payload.data(), 0x34, int32_t(-1));
    source_entries[0] = address(desired.data()); source_entries[1] = 0;
    put(source_bank.data(), 0x128, address(source_entries)); put(source_bank.data(), 0x130, uint32_t(1));
    boss_active = boss_inflight = 0; hook_created = true;
    stop_dispatch(); begin_dispatch();
    command = DispatchCommand{};
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    command.edge_qpc = command.heartbeat_qpc = now.QuadPart; command.expires_qpc = now.QuadPart + frequency;
    command.chord_sequence = 1; command.generation = dispatch->control.generation;
    command.player = boss_session.player; command.owner = boss_session.player_owner; command.vtable = boss_session.vtable;
    command.banks[0] = address(player_bank.data()); command.expected_descriptor = boss_session.source_descriptor;
    command.expected_payload = boss_session.source_payload; command.desired_key = 0xC64; command.expected_motion = 1220;
    command.armed = command.held = 1; publish();
    trace->header.enabled = 1; trace->header.written = 0; trace->header.dropped = 0;
    original_action = fake_original;
}
static void call(uint32_t requested, uint32_t forwarded, bool result, uint64_t commit,
                 bool borrowed, bool source_context, void* incoming_context = nullptr) {
    // Drive one research-preview setter call with explicit expected effects.
    // Configure forwarding, resource ownership and native descriptor commitment separately.
    // A failed native return must not hide an incorrect borrowed-resource transition.
    wanted_key = forwarded; wanted_result = result; wanted_commit = commit != 0;
    commit_descriptor = commit; wanted_borrowed = borrowed; wanted_source_context = source_context;
    SetLastError(INCOMING);
    assert(observed_action(player.data(), requested, incoming_context) == result);
    assert(GetLastError() == NATIVE && boss_inflight == 0); ++checks;
}
static void start_preview() {
    // Enter the imported research preview from a known valid fixture.
    // Assert substitution, final native descriptor and all four borrowed slots.
    // Subsequent interruption tests need evidence that the preview actually started.
    call(25, 0xC64, true, address(desired.data()), true, true);
    assert(boss_active && dispatch->control.status == 2 && dispatch->control.dispatch_count == 1);
    assert(trace->records[0].reserved == 0xC64 && (trace->records[0].valid_fields & TRACE_FINAL_MATCH));
    assert_bindings(true); ++checks;
}

int main() {
    // Exercise preview substitution, interruption and resource restoration.
    // Mutate owned identities and setter outcomes while checking exact callback effects.
    // Research-mode compatibility must not weaken the maintained ownership guards.
    LARGE_INTEGER freq; QueryPerformanceFrequency(&freq); frequency = freq.QuadPart;
    assert(open_dispatch(frequency) == 0);
    trace = static_cast<TraceMapping*>(VirtualAlloc(nullptr, sizeof(TraceMapping), MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(trace);
    reset(); start_preview();
    call(3000, 3000, true, address(current.data()), false, false);
    assert(!boss_active && dispatch->control.status == 3); assert_bindings(false); ++checks;

    reset(); start_preview();
    call(3000, 3000, false, 0, false, false); // Refused ordinary action keeps the source descriptor.
    assert(boss_active && dispatch->control.status == 2); assert_bindings(true); ++checks;
    auto before_disable = disable_calls;
    assert(NiohResearchStop(nullptr) == ERROR_BUSY && dispatch->control.enabled == 0
        && trace->header.enabled == 1 && disable_calls == before_disable); ++checks;
    uint64_t foreign_context[3]{};
    call(0xC65, 0xBB8, true, address(current.data()), false, false, foreign_context);
    assert(!boss_active && dispatch->control.status == 3); assert_bindings(false);
    assert(trace->records[2].reserved == 0xBB8 && (trace->records[2].valid_fields >> 8 & 255) == BossFollowupExit); ++checks;
    assert(NiohResearchStop(nullptr) == 0 && disable_calls == before_disable + 1 && dispatch); ++checks;

    reset(); call(24, 0xC64, false, 0, true, true); // Setter refusal restores immediately.
    assert(!boss_active && dispatch->control.status == 3); assert_bindings(false); ++checks;

    reset(); put(source.data(), 0x468, uint64_t(0x12345));
    call(24, 24, true, 0, false, false);
    assert(!boss_active && dispatch->control.dispatch_count == 0
        && (trace->records[0].valid_fields >> 8 & 255) == BossSourceMismatch); ++checks;

    reset(); put(player_owner.data(), 0x38, uint64_t(0x12345));
    DispatchCommand copied{};
    assert(choose_dispatch(player.data(), 24, nullptr, copied) == BossSourceMismatch); ++checks;
    reset(); put(reinterpret_cast<void*>(boss_slot(2)), 0, uint64_t(0xdeadbeef));
    assert(choose_dispatch(player.data(), 24, nullptr, copied) == BossBindingMismatch); ++checks;
    assert(same_field(boss_slot(0), 0, boss_session.originals[0])
        && same_field(boss_slot(2), 0, 0xdeadbeef)); ++checks;
    reset(); desired[0x40] = 0;
    assert(choose_dispatch(player.data(), 24, nullptr, copied) == DesiredMissing); ++checks;

    reset(); boss_inflight = 1;
    assert(NiohResearchStop(nullptr) == ERROR_BUSY && dispatch->control.enabled == 0); ++checks;
    boss_inflight = 0;
    assert(NiohResearchStop(nullptr) == 0); ++checks;
    reset(); start_preview();
    assert(NiohResearchStart(nullptr) == ERROR_BUSY); ++checks;
    call(3000, 3000, true, address(current.data()), false, false);
    assert(NiohResearchStop(nullptr) == 0); ++checks;

    cleanup_dispatch(); VirtualFree(trace, 0, MEM_RELEASE); trace = nullptr;
    std::printf("boss preview offline checks passed: %u\n", checks);
    return 0;
}
