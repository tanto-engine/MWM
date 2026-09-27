#pragma once
#include "trace_protocol.h"

enum { DISPATCH_MAGIC = 0x3144494e, DISPATCH_VERSION = 1 };
// These numeric rejection/acceptance codes are consumed by external trace readers; ordering is part of the ABI.
enum DispatchReason : uint32_t {
    Disabled = 0, IneligibleRequest, NonNullContext, UnstableCommand, NotArmed,
    WrongGeneration, StaleHeartbeat, Released, Expired, SequenceConsumed,
    ShotUsed, WrongActor, IdentityReadFailed, OwnerMismatch, VtableMismatch,
    BankMismatch, CurrentNotAllowed, DesiredInvalid, DesiredMissing,
    DesiredMismatch, Accepted, Contention, InvalidTime, InvalidConfig,
    BossSourceMismatch, BossBindingMismatch, BossFollowupExit, BossPreviewActive,
    BossGuardSuppressed, ContextSuspended, ContextChanged, NativeHeavyTap
};
enum { TRACE_SUBSTITUTED = 1u << 16, TRACE_FINAL_MATCH = 1u << 17 };
enum PlayerContext : uint32_t {
    ContextPlayer = 1, ContextBanks = 2, ContextOriginalSlots = 4,
    ContextAdvancing = 8, ContextImportedAction = 16, ContextNeutralAction = 32
};

static inline bool player_context_ready(uint32_t context) {
    // Decide whether the last player frame permits imported execution.
    // Require verified identity, matching banks, advancing time and owned resource slots.
    // Menus and lifecycle gaps must suspend dispatch without skipping native recovery.
    constexpr uint32_t required = ContextPlayer | ContextBanks | ContextAdvancing;
    return (context & required) == required && (context & (ContextOriginalSlots | ContextImportedAction));
}

// External publisher writes this region only. Matching positive markers commit it.
// Times are QPC ticks, not milliseconds; generation identifies the runtime and chord_sequence identifies one gesture.
// The DLL checks both sequence markers around its copy before trusting any publisher-supplied pointer or timing.
struct DispatchCommand {
    volatile LONG64 sequence_begin;
    int64_t heartbeat_qpc, edge_qpc, expires_qpc;
    uint64_t chord_sequence, generation, player, owner, vtable, banks[3];
    uint64_t expected_descriptor, expected_payload;
    uint32_t desired_key;
    int32_t expected_motion;
    uint32_t armed, held;
    uint64_t reserved[3]; // Latched gesture, move variant, 16-bit player-context epoch.
    volatile LONG64 sequence_end;
};
// DLL writes this region only. A new generation requires a fresh explicit publish.
// Keep publisher command writes separate from runtime acknowledgements to avoid competing writers on the same fields.
struct DispatchControl {
    uint32_t magic, version, command_size, reserved0; // Low 16 bits: context flags; high 16: epoch.
    int64_t qpc_frequency;
    volatile LONG64 generation;
    volatile LONG enabled, status;
    volatile LONG64 consumed_sequence, dispatch_count;
    volatile LONG last_reason;
    uint32_t reserved1;
};
struct DispatchMapping { DispatchControl control; DispatchCommand command; };
static_assert(sizeof(DispatchCommand) == 160 && sizeof(DispatchControl) == 64, "Command layout");
static_assert(sizeof(DispatchMapping) == 224 && offsetof(DispatchMapping, command) == 64, "Mapping layout");
static_assert(offsetof(DispatchCommand, player) == 48 && offsetof(DispatchCommand, banks) == 72,
              "Identity layout");
static_assert(offsetof(DispatchCommand, desired_key) == 112 && offsetof(DispatchCommand, sequence_end) == 152,
              "Command tail layout");

static inline DispatchReason command_status(const DispatchCommand& c, int64_t now,
        int64_t frequency, uint64_t generation, uint64_t consumed, bool shot_used) {
    // Reject stale, malformed or already-consumed external gesture commands.
    // Check generation, time bounds, heartbeat, gesture state and sequence ownership.
    // A reconnect or delayed publisher must not replay an old input into valid gameplay.
    if (c.armed != 1) return NotArmed;
    if (c.generation != generation) return WrongGeneration;
    if (c.reserved[0] > 1 || c.reserved[1] >= 32 || c.reserved[2] > UINT16_MAX) return InvalidConfig;
    if (c.held != 1 && c.reserved[0] != 1) return Released;
    if (!c.chord_sequence || c.chord_sequence > INT64_MAX) return InvalidConfig;
    if (c.chord_sequence <= consumed) return SequenceConsumed;
    if (shot_used) return ShotUsed;
    if (frequency <= 0 || frequency > INT64_MAX / 3 || now <= 0 || c.edge_qpc <= 0
        || c.heartbeat_qpc < c.edge_qpc || c.heartbeat_qpc > now
        || c.expires_qpc <= c.edge_qpc || c.expires_qpc - c.edge_qpc > frequency * 3 / 2)
        return InvalidTime;
    if (now >= c.expires_qpc) return Expired;
    if (now - c.heartbeat_qpc > frequency / 10) return StaleHeartbeat;
    if (c.player < 0x10000 || c.owner < 0x10000 || c.vtable < 0x10000
        || c.expected_descriptor < 0x10000 || c.expected_payload < 0x10000)
        return InvalidConfig;
    if (!c.desired_key || c.desired_key > 0xfffe || c.expected_motion < 0) return DesiredInvalid;
    return Accepted;
}
