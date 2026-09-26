#pragma once
#include "boss_session_schema.h"
#include "move_timing.h"

// Exact recorded Nioh 1 sword signatures, separate from storage and clock ownership.
struct SwordMoveSignature {
    uint32_t key;
    int32_t motion;
    uint64_t flags;
    uint32_t kind;
    uint16_t transition_count;
    int16_t recovery;
};

static constexpr bool sword_move_matches(const SwordMoveSignature& source, const MoveImport& move, const MoveAdapter& adapter) {
    return source.key==move.key && source.motion==move.motion && source.flags==move.flags
        && source.kind==adapter.kind && source.transition_count==move.transition_count && source.recovery==move.recovery_frame;
}

static constexpr SwordMoveSignature sword_airborne_sources[]={
    {0xC71,1050,0,2,18,-1}, {0xC71,1050,0,5,18,-1}, {0xC72,5000,0,4,17,-1},
    {0xC73,5001,0,4,18,-1}, {0xC74,5002,0x1BCE0000,4,75,20},
    {0xC81,1050,0,2,18,-1}, {0xC82,5050,0,4,18,-1}, {0xC83,5051,0x1BCE0000,4,75,-1}
};

static bool airborne_sword(const MoveImport& move, const MoveAdapter& adapter) {
    if (move.next_variant!=-1) return false;
    for (const auto& source : sword_airborne_sources) if (sword_move_matches(source,move,adapter)) return true;
    return false;
}

static bool sword_player_template(const MoveAdapter& adapter) {
    struct Template { uint32_t key; int32_t motion; uint16_t count; int16_t recovery; };
    constexpr Template entries[]={
        {0xCF5,4300,46,38}, {0xCF6,4310,46,29}, {0xCF7,4320,44,33},
        {0xCB7,3300,40,58}, {0xC7A,2300,42,46}
    };
    for (const auto& entry : entries)
        if (adapter.player_key==entry.key && adapter.player_motion==entry.motion
            && adapter.transition_count==entry.count && adapter.recovery_frame==entry.recovery
            && (adapter.kind!=1 || (entry.key>=0xCF5 && entry.key<=0xCF7))) return true;
    return false;
}

struct SwordTimingDefinition {
    SwordMoveSignature source;
    MoveTiming timing;
    uint32_t required_successor=0;
    bool frost_only=false, configured_speed=false;
};

// First applicable row owns recovery and startup together. All unlisted phases keep source timing.
static constexpr SwordTimingDefinition sword_timing_definitions[]={
    {{0xC64,1220,0x184C0000,0,28,65},{54,30,2}},
    {{0xC66,1230,0x184C0000,0,22,90},{78,0,1}},
    {{0xC71,1050,0,2,18,-1},{-1,19,1},0,true,true},
    {{0xC71,1050,0,5,18,-1},{-1,19,1},0,false,true},
    {{0xC81,1050,0,2,18,-1},{-1,19,1},0,true,true},
    {{0xC83,5051,0x1BCE0000,4,75,-1},{30,0,1}},
    {{0xC78,5013,0x194C0000,4,74,-1},{29,0,1}},
    {{0xC79,5014,0x194C0000,2,75,-1},{54,12,1},0xC7A,false,true},
    {{0xC79,5014,0x194C0000,2,75,-1},{21,8,2}}
};
static_assert([]() constexpr {
    for (const auto& definition : sword_timing_definitions)
        if (!move_timing_valid(definition.timing)) return false;
    return true;
}(), "Recorded phase definitions must have bounded startup and recovery");
