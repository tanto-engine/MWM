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
    // An action key alone is ambiguous across source banks and recorded motions.
    // Require motion, flags, adapter kind, transition count and recovery to identify the exact layout.
    // Only this complete match permits a recorded sword timing or airborne rule to apply.
    return source.key==move.key && source.motion==move.motion && source.flags==move.flags
        && source.kind==adapter.kind && source.transition_count==move.transition_count && source.recovery==move.recovery_frame;
}

static bool recorded_grounded(const MoveImport& move, const MoveAdapter& adapter) {
    // Admit only complete signatures matched against the new recording/archive evidence.
    // The normal player-transition adapter owns input and exits; source resources own animation/contact.
    // This excludes paired grabs and prevents a reused numeric ID from choosing another boss's rule.
    constexpr SwordMoveSignature sources[]={
        {0xD30,2000,0x184C0000,2,46,45},{0xD31,2010,0x184C0000,4,46,30},
        {0xD32,2020,0x184C0000,4,46,35},{0xD33,2030,0x184C0000,4,42,-1},
        {0xC6E,1010,0x19400000,2,10,-1},{0xC6F,1011,0x19400000,4,6,-1},
        {0xD8D,5011,0x594C0000,2,27,120},{0xC6A,1130,0x40019480000ULL,2,9,-1}
    };
    for (const auto& source : sources) if (sword_move_matches(source,move,adapter)) return true;
    return false;
}

static inline int16_t recorded_player_ki_cost(const MoveImport& move, const MoveAdapter& adapter, int16_t source_cost) {
    // Hideyori's zero-cost boss string cannot feed William's native recoverable-Ki calculation.
    // Use the supported build's Low-quick CF0..CF3 costs: 19 for the opener, then 14 per strike.
    // Match the full recorded signature; other zero-cost phases, including airborne links, stay unchanged.
    if (source_cost || move.key<0xD30 || move.key>0xD33 || !recorded_grounded(move,adapter)) return source_cost;
    return move.key==0xD30 ? 19 : 14;
}

static inline int recorded_auto_successor(const MoveImport& move) {
    // Oda's selected two-hit Frost route continues at its recorded frame-40 branch.
    // This explicit trial policy replaces the boss's input condition with one automatic second slash.
    // Other recorded branches remain absent until separately reviewed.
    return move.key==0xC6E && move.motion==1010 && move.flags==0x19400000 && move.transition_count==10 ? 0xC6F : -1;
}

// Rows are recorded signatures, not a contiguous key range: duplicate keys distinguish adapter kinds.
static constexpr SwordMoveSignature sword_airborne_sources[]={
    {0xC71,1050,0,2,18,-1}, {0xC71,1050,0,5,18,-1}, {0xC72,5000,0,4,17,-1},
    {0xC73,5001,0,4,18,-1}, {0xC74,5002,0x1BCE0000,4,75,20},
    {0xC81,1050,0,2,18,-1}, {0xC82,5050,0,4,18,-1}, {0xC83,5051,0x1BCE0000,4,75,-1}
};

static bool airborne_sword(const MoveImport& move, const MoveAdapter& adapter) {
    // Exclude entries with an explicit next_variant link before consulting airborne signatures.
    // Accepted rows describe recorded airborne phases, including the isolated-jump adapter kind.
    // Moves reusing an action key cannot inherit airborne adaptation without the other signature fields.
    if (move.next_variant!=-1) return false;
    for (const auto& source : sword_airborne_sources) if (sword_move_matches(source,move,adapter)) return true;
    return false;
}

static bool sword_player_template(const MoveAdapter& adapter) {
    // Validate the William attack that supplies player input, stance and recovery transitions.
    // Compare key, motion, transition count and recovery with the five recorded templates.
    // Replacement kind 1 is restricted to CF5..CF7; skill entries may use the other stance templates.
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

// Recovery and startup belong to one matched row; optional gates distinguish identical source bytes used by different skills.
struct SwordTimingDefinition {
    SwordMoveSignature source;
    MoveTiming timing;
    uint32_t required_successor=0;
    bool frost_only=false, configured_speed=false;
};

static inline int sword_string_successor(const MoveImport& move) {
    // Positive results name the next action key; zero ends a recognized string and -1 means unrecognized.
    // Require recorded flags, motion progression and row count before reusing a next-press transition.
    // These reviewed strings reuse William's next-press rows, never an automatic recording edge.
    struct String { uint32_t keys[5]; int32_t motion; unsigned count; };
    constexpr String strings[]={{{0xBBF,0xC63,0xC64,0xC65,0xC66},2100,5},
        {{0xBC0,0xC6C,0xC6D,0,0},2300,3},{{0xC6E,0xC6F,0xC70,0,0},2400,3}};
    if (move.flags==0x184C0000 && move.key>=0xD30 && move.key<=0xD33
        && move.motion==2000+int32_t(move.key-0xD30)*10 && move.transition_count==(move.key==0xD33 ? 42 : 46))
        return move.key==0xD33 ? 0 : int(move.key+1);
    if (move.flags!=0x194C0000ULL) return -1;
    for (const auto& string : strings) for (unsigned i=0;i<string.count;++i)
        if (move.key==string.keys[i] && move.motion==string.motion+int32_t(i)*10
            && move.transition_count==(i+1==string.count ? 74 : 75))
            return i+1<string.count ? int(string.keys[i+1]) : 0;
    return -1;
}

// First applicable row owns recovery and startup together. All unlisted phases keep source timing.
// Numeric action keys are hexadecimal while motion IDs and frame counts are decimal; they are different namespaces.
static constexpr SwordTimingDefinition sword_timing_definitions[]={
    {{0xC64,1220,0x184C0000,0,28,65},{54,30,2}},
    {{0xC66,1230,0x184C0000,0,22,90},{78,0,1}},
    {{0xC71,1050,0,2,18,-1},{-1,19,1},0,true,true},
    {{0xC71,1050,0,5,18,-1},{-1,19,1},0,false,true},
    {{0xC81,1050,0,2,18,-1},{-1,19,1},0,true,true},
    {{0xC83,5051,0x1BCE0000,4,75,-1},{30,0,1}},
    {{0xC78,5013,0x194C0000,4,74,-1},{29,0,1}},
    {{0xC79,5014,0x194C0000,2,75,-1},{54,12,1},0xC7A,false,true},
    {{0xC79,5014,0x194C0000,2,75,-1},{21,8,2}},
    // Hideyori's final cancel boundary is95; Oda uses its frame40 follow-up then a trial recovery60.
    // Sanada recovery128 follows the retained firing/reholster timeline; all three need gameplay tuning.
    {{0xD33,2030,0x184C0000,4,42,-1},{95,0,1}},
    {{0xC6E,1010,0x19400000,2,10,-1},{40,0,1}},
    {{0xC6F,1011,0x19400000,4,6,-1},{60,0,1}},
    {{0xC6A,1130,0x40019480000ULL,2,9,-1},{128,0,1}}
};
static_assert([]() constexpr {
    // Check every constant timing row, including rows gated by Frost bindings or successor availability.
    // Invalid recovery/startup combinations fail compilation before they can become runtime policy.
    // The separate session validator checks imported resources; this assertion checks definitions only.
    for (const auto& definition : sword_timing_definitions)
        if (!move_timing_valid(definition.timing)) return false;
    return true;
}(), "Recorded phase definitions must have bounded startup and recovery");
