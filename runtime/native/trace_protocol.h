#pragma once
#include <windows.h>
#include <stdint.h>
#include <stddef.h>

// Magic identifies the shared-memory format; capacity is a bounded history, so slow readers can miss overwritten records.
enum { TRACE_MAGIC = 0x3152494e, TRACE_VERSION = 1, TRACE_CAPACITY = 512 };

// A committed record has matching positive sequence_begin/sequence_end values; zero marks an in-progress slot.
// Address fields describe observations, not owned allocations; QPC timestamps use the header frequency.
struct TraceRecord {
    volatile LONG64 sequence_begin;
    int64_t qpc;
    // valid_fields bit18 marks an accepted frame-generated dispatch: context
    // then contains its gesture decision QPC. Other calls retain the native pointer.
    uint64_t actor, owner, context, before, after, payload;
    uint32_t thread_id, input_key, before_key, after_key;
    int32_t bank, motion_key, timing_key;
    uint32_t native_result, valid_fields, reserved;
    volatile LONG64 sequence_end;
};

// written is the latest committed sequence; dropped counts contention losses before a slot is published.
// The reserved 64 bytes hold GameInput, whose independent odd/even sequence protects controller snapshots.
struct TraceHeader {
    uint32_t magic, version, capacity, record_size;
    int64_t qpc_frequency;
    volatile LONG64 written, dropped;
    volatile LONG status, enabled;
    uint64_t hook_address, module_base;
    uint8_t reserved[64];
};

struct TraceMapping { TraceHeader header; TraceRecord records[TRACE_CAPACITY]; };
static_assert(sizeof(TraceRecord) == 112, "External reader layout mismatch");
static_assert(sizeof(TraceHeader) == 128, "External reader layout mismatch");
static_assert(sizeof(void*) == 8, "Observer requires the Windows x64 ABI");
static_assert(offsetof(TraceRecord, sequence_end) == 104, "Record sequence offset mismatch");
static_assert(offsetof(TraceHeader, written) == 24 && offsetof(TraceHeader, dropped) == 32,
              "Header counter offset mismatch");
static_assert(alignof(TraceRecord) >= 8 && alignof(TraceHeader) >= 8,
              "Interlocked 64-bit fields require eight-byte alignment");
