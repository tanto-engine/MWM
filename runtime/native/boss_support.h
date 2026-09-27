#pragma once
#include "boss_session_config.h"

static volatile LONG boss_active;
static volatile LONG boss_inflight;
static uint64_t boss_active_player, boss_active_owner;
static unsigned boss_active_slot;
#ifdef RESEARCH_REPEAT
static bool boss_frost_playback;
#endif
#ifdef RESEARCH_REPEAT
static uint64_t boss_chain_sequence;
static uint32_t boss_chain_epoch;
static bool boss_chain_cancelled, boss_camera_active;
static uint64_t boss_camera_borrowed;
static thread_local bool boss_native_grapple_entry;
#endif

[[maybe_unused]] static bool boss_paired(uint64_t flags) {
    // Identify the two recorded native attacker-pair families.
    // Keep Okatsu's contact actor and Jin's airborne attacker under one recovery policy.
    // These states may begin only through an observed native paired transition.
    return flags == 0x8078000000ULL || flags == 0x8038000000ULL;
}
#ifdef RESEARCH_REPEAT
// Native pool/build evidence: descriptor slots0xD0, payload slots0xB0. These
// copies remain immutable and allocated for the DLL lifetime: previous-action
// references can outlive the visible preview.
struct BossLookupOnlyBank {
    uint8_t unused[0x128];
    uint64_t entries;
    uint32_t count, padding;
};
static_assert(sizeof(BossLookupOnlyBank) == 0x138, "Lookup-only header size");
struct BossPrivateAction {
    alignas(16) uint8_t descriptor[0xD0];
    alignas(16) uint8_t payload[0xB0];
    BossLookupOnlyBank bank;
    uint64_t entry;
    uint8_t transition_bodies[64][0x30];
    uint64_t transition_pointers[64];
    uint8_t combat_body[0x80];
    uint64_t combat_entry;
    uint16_t transition_count;
    bool ready;
};
static BossPrivateAction boss_private_actions[32]{};
static bool boss_preserve_weapon(unsigned slot, uint8_t* payload) {
    // Native704E50 schedules these source effects;709002 applies their equipment command.
    // Jin rows46/47 select weapon slots by stance, so remove only those exact pure commands.
    // Preserve every other event and all shared source data; reject changed effect identities.
    if (!boss_adapters[slot].kind || recorded_grounded(boss_imports[slot],boss_adapters[slot])) return true;
    static const uint8_t expected[0x80]={
        0x00,0x00,0xff,0xff,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff,0xff,0xff,0xff,0xff,
        0x00,0x00,0x00,0x00,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0x02,0xff,0x00,0xff,0xff,
        0xff,0xff,0xff,0xff,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xff,0xff,
        0xff,0xff,0x64,0x64,0x64,0x64,0x64,0x64,0x64,0x64,0xff,0xff,0xff,0xff,0xff,0xff,
        0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,
        0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0x51,0x00,0xff,0xff,
        0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff
    };
    for (unsigned offset=0x40;offset<0xA0;offset+=6) {
        int16_t effect=-1;memcpy(&effect,payload+offset,2);
        if (effect!=46 && effect!=47) continue;
        uint64_t table=0,row=0;uint16_t count=0;uint8_t bytes[0x80];
        const uint64_t bank=boss_adapters[slot].bank;
        if (!copy_field(bank+0x80,table) || !copy_field(bank+0x88,count) || count!=58
            || !copy_field(table+uint64_t(effect)*8,row) || !copy_bytes(row,bytes,sizeof(bytes))) return false;
        if (effect==47) {--bytes[0x2B];--bytes[0x6C];}
        if (memcmp(bytes,expected,sizeof(bytes))) return false;
        const int16_t disabled=-1;memcpy(payload+offset,&disabled,2);
    }
    return true;
}
static int boss_native_successor(unsigned slot, uint32_t key);
static MoveSettings boss_settings(unsigned slot) {
    // A zero speed marks an unset row; the fallback supplies 1x playback and baseline Ki Pulse settings.
    // The remaining defaults are 40 percent Pulse, 25 fill frames and 24 hold frames.
    // Return a value copy so private payload adaptation does not change the session table.
    return boss_move_settings[slot].speed ? boss_move_settings[slot] : MoveSettings{1,40,25,24,0};
}
static MoveTiming boss_move_timing(unsigned slot) {
    // Match the full recorded move signature before changing startup or recovery frames.
    // Table order resolves C79 variants; Frost bindings and an available successor select their special rows.
    // Unlisted moves keep source recovery and 1x startup rather than inheriting another attack's timing.
    const auto& move=boss_imports[slot];
    bool frost_bound=false;
    for (auto frost : boss_frost_variants) frost_bound=frost_bound || frost==slot+1;
    for (const auto& definition : sword_timing_definitions) {
        if (!sword_move_matches(definition.source,move,boss_adapters[slot])
            || (definition.frost_only && !frost_bound)
            || (definition.required_successor && boss_native_successor(slot,definition.required_successor)<0)) continue;
        auto timing=definition.timing;
        if (definition.configured_speed) timing.startup_speed=float(boss_frost_speed);
        return timing;
    }
    return {move.recovery_frame,0,1};
}
static uint64_t boss_private_descriptor_address(unsigned slot = 0) {
    // Expose the immutable descriptor for one configured import.
    // Its slot indexes module-lifetime storage instead of a borrowed actor allocation.
    // The game may retain previous-action pointers after visible playback ends.
    return reinterpret_cast<uint64_t>(boss_private_actions[slot].descriptor);
}
static uint64_t boss_private_payload_address(unsigned slot = 0) {
    // Expose the matching private payload for one imported descriptor.
    // The payload shares the descriptor's fixed module-lifetime slot.
    // Replacing or freeing it would invalidate native retained action references.
    return reinterpret_cast<uint64_t>(boss_private_actions[slot].payload);
}

// Exact CF0 rows21..23. Stance selectors differ; all retain native conditionD5,
// R1 input23, targetD5F and transition flagbit1 used by native Ki Pulse handling.
static constexpr uint8_t boss_pulse_templates[3][0x30] = {
    {0x51,0,0xd5,0,0xff,0xff,0xff,0xff,0xff,0xff,0,0x17,1,0xff,0xff,0,0,0,0,0,0x5f,0x0d,0,3,0,0x80,0x64,0x64,2,0,0x20,0,0,0x80,0xff,0x7f,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff},
    {0x50,0,0xd5,0,0xff,0xff,0xff,0xff,0xff,0xff,0,0x17,1,0xff,0xff,0,0,0,0,0,0x5f,0x0d,0,3,0,0x80,0x64,0x64,2,0,0x20,0,0,0x80,0xff,0x7f,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff},
    {0x52,0,0xd5,0,0xff,0xff,0xff,0xff,0xff,0xff,0,0x17,1,0xff,0xff,0,0,0,0,0,0x5f,0x0d,0,3,0,0x80,0x64,0x64,2,0,0x20,0,0,0x80,0xff,0x7f,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff}
};
static constexpr uint8_t boss_dodge_template[0x30] = {
    0x5c,0,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0,2,1,0xff,0xff,0,0,0,0,0,
    0x12,0x0d,0,0,0xff,0x80,0x64,0x64,0,0,0,0,0,0x80,0xff,0x7f,
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff
};

static int boss_native_successor(unsigned slot, uint32_t key) {
    // Keep ordinary automatic branches inside the entry's stance and source bank.
    // Only an explicit contact link or an existing paired action can enter another paired phase.
    // Standalone C79 and Izuna share source bytes but must own different successor graphs.
    const auto& owner=boss_adapters[slot];
    const auto& source=boss_imports[slot];
    if (owner.kind==5) return -1;
    const bool linked=(source.next_variant>=0 && boss_imports[source.next_variant].key==key)
        || (recorded_auto_successor(source)>0 && uint32_t(recorded_auto_successor(source))==key)
        || (sword_string_successor(source)>0 && uint32_t(sword_string_successor(source))==key)
        || (source.key==0xC79 && key==0xC7A)
        || (source.key>=0xC71 && source.key<=0xC73 && key==source.key+1)
        || (source.key>=0xC81 && source.key<=0xC82 && key==source.key+1)
        || (source.key==0xC75 && key==0xC77) || (source.key==0xC77 && key==0xC78)
        || ((source.key==0x3B2 || source.key==0x3B4) && (key==0x3B4 || key==0x3B6));
    if (!linked) return -1;
    for (unsigned next=0;next<boss_import_count;++next) {
        const auto& candidate=boss_adapters[next];
        if (boss_imports[next].key!=key || candidate.kind<2 || candidate.bank!=owner.bank) continue;
        if (candidate.kind==3 ? (owner.kind==3 || boss_imports[slot].next_variant==int(next))
            : (owner.kind!=3 && candidate.player_key==owner.player_key)) return int(next);
    }
    return -1;
}

static bool boss_copy_pulse_transitions(unsigned slot, const uint8_t* descriptor,
        uint8_t (&bodies)[64][0x30], uint16_t& total) {
    // Adapt source transitions without changing their animation timing.
    // Stable copies disable unowned combo inputs and append verified William pulse rows.
    // Native condition checks must retain control of recovery and paired contact.
    // TODO: confirm player-owned damage, Ki damage and R1 recovery in live combat.
    // Native pulse rows and preserved cost verify adaptation, but not live hit ownership or input acceptance.
    uint64_t source_table = 0; uint16_t source_start = 0, source_count = 0;
    memcpy(&source_table, descriptor + 0x78, 8); memcpy(&source_start, descriptor + 0x80, 2);
    memcpy(&source_count, descriptor + 0x82, 2);
    if (source_count != boss_imports[slot].transition_count || source_count > 28 || source_table < 0x10000 || source_table > UINT64_MAX - 0x100000)
        return false;
    uint64_t source_pointers[28]{}, source_check[28]{};
    const uint64_t source_slice = source_table + uint64_t(source_start) * 8;
    if (!copy_bytes(source_slice, source_pointers, source_count * 8)) return false;
    for (unsigned i = 0; i != source_count; ++i) {
        uint8_t check[0x30];
        if (!copy_bytes(source_pointers[i], bodies[i], 0x30) || !copy_bytes(source_pointers[i], check, 0x30)
            || memcmp(bodies[i], check, 0x30)) return false;
        if (boss_adapters[slot].kind==5) {
            int16_t target=0; memcpy(&target,bodies[i]+0x14,2);
            if (target==0xC72) bodies[i][0x0A]=0xff; // Keep jump/fall; omit Swallow dash.
        }
        if (boss_adapters[slot].kind==3 || (bodies[i][0x0A]==1 && bodies[i][0x0B]==0xff)) {
            int16_t target=0; memcpy(&target,bodies[i]+0x14,2);
            if ((target==0 || target>=0xBB8) && boss_native_successor(slot,uint32_t(target))<0) {
                target=0xBB8; memcpy(bodies[i]+0x14,&target,2);
            }
        }
    }
    if (boss_adapters[slot].kind==4 && boss_imports[slot].next_variant>=0) {
        bool contact=false;
        for (unsigned i=0;i<source_count;++i) {
            uint16_t condition=0; int16_t target=0;
            memcpy(&condition,bodies[i],2); memcpy(&target,bodies[i]+0x14,2);
            if (condition==22 && bodies[i][0x0A]==0 && bodies[i][0x0B]==0xff
                && target==int16_t(boss_imports[boss_imports[slot].next_variant].key)) contact=true;
        }
        if (!contact) return false;
    }
    // New chains own their follow-up policy. Remove the source controller's
    // unconditional combo requests so they cannot select William's colliding IDs.
    if (slot >= 2) for (unsigned i = 0; i != source_count; ++i) {
        bool unconditional = true;
        for (unsigned c = 0; c != 10; ++c) if (bodies[i][c] != 0xff) unconditional = false;
        int16_t key = 0; memcpy(&key,bodies[i]+0x14,2);
        if (unconditional && key && bodies[i][0x0b] != 0xff) {
            const int16_t disabled = -1;
            memcpy(bodies[i]+0x14,&disabled,2);
        }
    }
    if (boss_move_timing(slot).recovery < 0) {
        total = source_count;
        return copy_bytes(source_slice,source_check,source_count*8)
            && !memcmp(source_pointers,source_check,source_count*8);
    }
    uint8_t player[0x88], player_check[0x88];
    if (!copy_bytes(boss_session.player_pulse_descriptor, player, sizeof(player))) return false;
    uint32_t key = 0; uint64_t table = 0; uint16_t start = 0, count = 0;
    memcpy(&key, player, 4); memcpy(&table, player + 0x78, 8);
    memcpy(&start, player + 0x80, 2); memcpy(&count, player + 0x82, 2);
    if (key != 0xCF0 || !player[0x40] || count < 49 || count > 4096
        || table < 0x10000 || table > UINT64_MAX - 0x100000) return false;
    uint64_t pulse_pointers[3]{}, pulse_check[3]{};
    if (!copy_bytes(table + (uint64_t(start) + 21) * 8, pulse_pointers, sizeof(pulse_pointers))) return false;
    for (unsigned i = 0; i != 3; ++i) {
        auto* body = bodies[source_count + i];
        if (!copy_bytes(pulse_pointers[i], body, 0x30) || memcmp(body, boss_pulse_templates[i], 0x30)) return false;
        const int16_t recovery_start = boss_move_timing(slot).recovery;
        memcpy(body + 0x20, &recovery_start, 2); // Never enable a pulse before attack recovery.
    }
    uint64_t dodge_pointer=0, dodge_check=0; uint8_t dodge[0x30];
    if (!copy_field(table+(uint64_t(start)+48)*8,dodge_pointer)
        || !copy_bytes(dodge_pointer,dodge,sizeof(dodge))
        || memcmp(dodge,boss_dodge_template,sizeof(dodge))) return false;
    const int16_t recovery_start=boss_move_timing(slot).recovery;
    memcpy(dodge+0x20,&recovery_start,2);
    unsigned insertion=source_count+3;
    for (unsigned i=0;i<source_count;++i) {
        uint16_t condition=0; int16_t target=0;
        memcpy(&condition,bodies[i],2); memcpy(&target,bodies[i]+0x14,2);
        const bool input=(bodies[i][0x0B]==2 && bodies[i][0x0C]==1)
            || (bodies[i][0x0D]==2 && bodies[i][0x0E]==1);
        if (condition==0x5c && target>=0x1e && target<=0x21 && input) { insertion=i; break; }
    }
    // CF0 row48 routes to D12, whose native stance/direction rows retain Living Water skill gates.
    // TODO: verify dodge Ki Pulse in each stance with its learned Living Water skill,
    // including early/late dodges and ordinary no-skill fallback behavior.
    memmove(bodies+insertion+1,bodies+insertion,(source_count+3-insertion)*0x30);
    memcpy(bodies[insertion],dodge,sizeof(dodge));
    if (!copy_bytes(source_slice, source_check, source_count * 8)
        || memcmp(source_pointers, source_check, source_count * 8)
        || !copy_bytes(table + (uint64_t(start) + 21) * 8, pulse_check, sizeof(pulse_check))
        || memcmp(pulse_pointers, pulse_check, sizeof(pulse_check))
        || !copy_field(table+(uint64_t(start)+48)*8,dodge_check) || dodge_pointer!=dodge_check
        || !copy_bytes(boss_session.player_pulse_descriptor, player_check, sizeof(player))
        || memcmp(player, player_check, sizeof(player))) return false;
    total = uint16_t(source_count + 4);
    return true;
}

static bool boss_copy_player_transitions(unsigned slot, const uint8_t* source_descriptor,
        uint8_t (&bodies)[64][0x30], uint16_t& total) {
    // Keep William's native heavy-button buffering, targeting and exit conditions.
    // Copy his transition rows and scale finite windows while retaining Jin's combat tables.
    // Jin's AI transitions must never queue attacks or bypass William's running priority.
    // TODO: confirm the reported guardian summon and final-spin hitboxes after retaining
    // Jin's descriptor tables; matching source bytes cannot prove combat contact in play.
    const auto& adapter = boss_adapters[slot];
    const int16_t adapted_recovery=boss_move_timing(slot).recovery;
    uint8_t descriptor[0xD0], check[0xD0];
    if (!copy_bytes(adapter.player_descriptor, descriptor, 0xD0)
        || !copy_bytes(adapter.player_descriptor, check, sizeof(check))
        || memcmp(descriptor, check, sizeof(check))) return false;
    uint32_t key=0; uint64_t payload=0, table=0; uint16_t start=0, count=0;
    memcpy(&key,descriptor,4); memcpy(&payload,descriptor+0x20,8);
    memcpy(&table,descriptor+0x78,8); memcpy(&start,descriptor+0x80,2); memcpy(&count,descriptor+0x82,2);
    int32_t motion=0; int16_t recovery=0;
    if (key != adapter.player_key || !descriptor[0x40] || count != adapter.transition_count || count > 64
        || !copy_field(payload+0x20,motion) || motion != adapter.player_motion
        || !copy_field(payload+0x24,recovery) || recovery != adapter.recovery_frame) return false;
    uint64_t pointers[64]{}, after[64]{};
    if (!copy_bytes(table+uint64_t(start)*8,pointers,count*8)) return false;
    for (unsigned i=0; i<count; ++i) {
        uint8_t row_check[0x30];
        if (!copy_bytes(pointers[i],bodies[i],0x30) || !copy_bytes(pointers[i],row_check,0x30)
            || memcmp(bodies[i],row_check,0x30)) return false;
        // Signed sentinel windows stay sentinel; scale only actual animation frames.
        for (unsigned offset=0x20; offset<=0x22; offset+=2) {
            int16_t frame=0; memcpy(&frame,bodies[i]+offset,2);
            if (frame > 0 && frame < INT16_MAX && adapted_recovery > 0) {
                const int scaled=(int(frame)*adapted_recovery + recovery/2)/recovery;
                if (scaled >= INT16_MAX) return false;
                frame = int16_t(scaled);
                memcpy(bodies[i]+offset,&frame,2);
            }
        }
        int16_t target=0; memcpy(&target,bodies[i]+0x14,2);
        const int next=sword_string_successor(boss_imports[slot]);
        if ((adapter.kind==2 || adapter.kind==4) && next>=0 && target==int16_t(adapter.player_key+1)) {
            // One physical Triangle per strike, using William's buffered/direct heavy rows.
            // Every source phase retains the selected stance and native exits.
            // The final strike disables this continuation instead of restarting the string.
            target=boss_native_successor(slot,next)>=0 ? int16_t(next) : int16_t(-1);
            memcpy(bodies[i]+0x14,&target,2);
            if (boss_imports[slot].flags==0x184C0000 && boss_imports[slot].key>=0xD30 && boss_imports[slot].key<=0xD33)
                bodies[i][0x0B]=0; // This recorded string advances with Square, not William's template Triangle.
            continue;
        }
        if (target == 0xD5F) memcpy(bodies[i]+0x20,&adapted_recovery,2);
        if ((adapter.kind == 2 || adapter.kind == 4) && ((target >= 0xCF5 && target <= 0xCF7)
            || (target >= 0xCB7 && target <= 0xCB9) || (target >= 0xC7A && target <= 0xC7C)
            || (target==0xD5F && adapted_recovery<0))) {
            const int16_t disabled=-1; memcpy(bodies[i]+0x14,&disabled,2);
        }
    }
    if (!copy_bytes(table+uint64_t(start)*8,after,count*8) || memcmp(pointers,after,count*8)) return false;
    total=count;
    if (adapter.kind == 2 || adapter.kind == 4) {
        // Source automatic links run before generic player exits; AI input choices are excluded.
        uint64_t source_table=0; uint16_t source_start=0, source_count=0;
        memcpy(&source_table,source_descriptor+0x78,8); memcpy(&source_start,source_descriptor+0x80,2);
        memcpy(&source_count,source_descriptor+0x82,2);
        if (source_count != boss_imports[slot].transition_count || source_count>128) return false;
        uint64_t rows[128]{}, check_rows[128]{};
        const uint64_t slice=source_table+uint64_t(source_start)*8;
        if (!copy_bytes(slice,rows,source_count*8)) return false;
        uint8_t automatic[64][0x30]{}; unsigned added=0;
        bool contact_found=boss_imports[slot].next_variant<0;
        const int automatic_key=recorded_auto_successor(boss_imports[slot]);
        if (automatic_key>0 && boss_native_successor(slot,uint32_t(automatic_key))>=0) {
            auto* body=automatic[added++]; memset(body,0xff,0x30);
            body[0x0A]=0; body[0x0F]=0;
            const int16_t key=int16_t(automatic_key), start=40, end=INT16_MAX;
            const uint32_t zero=0;
            memcpy(body+0x10,&zero,4);memcpy(body+0x14,&key,2);body[0x16]=0;body[0x17]=0;
            body[0x18]=0xff;body[0x19]=0x80;body[0x1A]=100;body[0x1B]=100;
            memcpy(body+0x1C,&zero,4);memcpy(body+0x20,&start,2);memcpy(body+0x22,&end,2);
        }
        bool source_end=false;
        for (unsigned i=0;i<source_count;++i) {
            uint8_t body[0x30], check_body[0x30]; int16_t target=0; uint16_t condition=0;
            if (!copy_bytes(rows[i],body,sizeof(body)) || !copy_bytes(rows[i],check_body,sizeof(body))
                || memcmp(body,check_body,sizeof(body))) return false;
            memcpy(&target,body+0x14,2); memcpy(&condition,body,2);
            if (body[0x0B]!=0xff || target<0) continue;
            const bool owned=boss_native_successor(slot,uint32_t(target))>=0;
            if (!owned && body[0x0A]!=1) continue;
            if (count+added>=64) return false;
            if (owned && condition==22 && boss_imports[slot].next_variant>=0
                && boss_imports[boss_imports[slot].next_variant].key==uint32_t(target)) contact_found=true;
            uint32_t flags=0; int16_t end=0;
            memcpy(&flags,body+0x1C,4); memcpy(&end,body+0x22,2);
            if (!(flags&0x2000040) && body[0x0A]==1 && end==INT16_MAX && (flags&4)) source_end=true;
            if (!owned) { target=0xBB8; memcpy(body+0x14,&target,2); } // Native completion exits to William idle.
            memcpy(automatic[added++],body,sizeof(body));
        }
        if (!contact_found || !copy_bytes(slice,check_rows,source_count*8)
            || memcmp(rows,check_rows,source_count*8)) return false;
        if (source_end) for (unsigned i=0;i<count;++i) {
            // Native73F3E0 keeps the last fallback row, regardless of its position priority.
            // Disable only William's competing end fallback; preserve conditional input and interruption rows.
            // The retained source fallback owns either its researched next action or the adapted idle exit.
            uint32_t flags=0; int16_t end=0;
            memcpy(&flags,bodies[i]+0x1C,4); memcpy(&end,bodies[i]+0x22,2);
            if (!(flags&0x2000040) && bodies[i][0x0A]==1 && end==INT16_MAX && (flags&4))
                bodies[i][0x0A]=0xff;
        }
        memmove(bodies+added,bodies,count*0x30);
        memcpy(bodies,automatic,added*0x30); total=uint16_t(count+added);
    }
    return true;
}

static bool boss_copy_launcher_contact(unsigned slot, uint8_t* descriptor, uint8_t (&body)[0x80]) {
    // Native71A460 queries the newly selected reaction: +17 or +1B supplies vertical impulse.
    // Clone only low C79's single combat row: both branches12 become16; source and Izuna stay intact.
    // Descriptor ownership keeps this adjustment contact-driven without touching enemy weight or physics.
    // TODO: verify grounded height and recovery against humans/yokai; both native reaction branches must receive the same boost.
    const auto& move=boss_imports[slot];
    if (boss_adapters[slot].kind!=2 || boss_native_successor(slot,0xC7A)>=0
        || move.key!=0xC79 || move.motion!=5014 || move.flags!=0x194C0000)
        return true;
    uint64_t table=0, row=0, after=0; uint16_t start=0, count=0;
    memcpy(&table,descriptor+0x48,8); memcpy(&start,descriptor+0x50,2); memcpy(&count,descriptor+0x52,2);
    if (count!=1 || table<0x10000 || table>UINT64_MAX-0x80000) return false;
    const auto entry=table+uint64_t(start)*8;
    uint8_t check[0x80];
    if (!copy_field(entry,row) || !copy_bytes(row,body,sizeof(body))
        || !copy_bytes(row,check,sizeof(check)) || memcmp(body,check,sizeof(body))
        || !copy_field(entry,after) || after!=row || body[0x17]!=12 || body[0x1B]!=12) return false;
    body[0x17]=body[0x1B]=16;
    const uint64_t private_table=reinterpret_cast<uint64_t>(&boss_private_actions[slot].combat_entry);
    const uint16_t private_start=0;
    memcpy(descriptor+0x48,&private_table,8); memcpy(descriptor+0x50,&private_start,2);
    return true;
}

static bool boss_prepare_private_action(unsigned slot = 0) {
    // Build or revalidate a single immutable player-adapted action.
    // Compare source identity and metadata before copying stance, Ki and transition fields.
    // A changed source must fail before any private pointer reaches the native setter.
    if (slot >= boss_import_count) return false;
    const auto& spec = boss_imports[slot];
    auto& target = boss_private_actions[slot];
    const uint64_t expected_descriptor = spec.descriptor;
    const uint64_t expected_payload = spec.payload;
    const uint32_t expected_key = spec.key;
    const int32_t expected_motion = spec.motion;
    uint8_t descriptor[0xD0], payload[0xB0], check_descriptor[0xD0], check_payload[0xB0];
    if (!copy_bytes(expected_descriptor, descriptor, sizeof(descriptor))
        || !copy_bytes(expected_payload, payload, sizeof(payload))
        || !copy_bytes(expected_descriptor, check_descriptor, sizeof(check_descriptor))
        || !copy_bytes(expected_payload, check_payload, sizeof(check_payload))
        || memcmp(descriptor, check_descriptor, sizeof(descriptor))
        || memcmp(payload, check_payload, sizeof(payload))) return false;
    uint32_t key = 0; uint64_t source_payload = 0, flags = 0; int32_t motion = -1;
    memcpy(&key, descriptor, sizeof(key));
    memcpy(&source_payload, descriptor + 0x20, sizeof(source_payload));
    memcpy(&flags, payload + 0x18, sizeof(flags));
    memcpy(&motion, payload + 0x20, sizeof(motion));
    // The private context deliberately contains only this direct action. Reject
    // redirects/pending-action modes that could require another context lookup.
    if (key != expected_key || !descriptor[0x40] || source_payload != expected_payload
        || motion != expected_motion || flags != spec.flags) return false;
    if (!boss_preserve_weapon(slot,payload)) return false;
    payload[0x0B] = 4; // Native0x70F3A3: keep current+0x470, retain+0x47C=1 behavior.
    for (unsigned stance=0;stance<3;++stance)
        if (boss_frost_variants[stance]==slot+1) payload[0x0B]=uint8_t(2-stance);
    int16_t recovery_start = 0, base_ki_cost = 0;
    memcpy(&recovery_start, payload + 0x24, sizeof(recovery_start));
    memcpy(&base_ki_cost, payload + 0x16, sizeof(base_ki_cost));
    if (recovery_start != spec.recovery_frame || base_ki_cost < 0
        || (!boss_paired(spec.flags) && boss_adapters[slot].kind != 2 && boss_adapters[slot].kind != 4 && boss_adapters[slot].kind != 5 && base_ki_cost == 0)) return false;
    const int16_t player_ki_cost=recorded_player_ki_cost(spec,boss_adapters[slot],base_ki_cost);
    memcpy(payload+0x16,&player_ki_cost,2);
    recovery_start=boss_move_timing(slot).recovery;
    const auto settings=boss_settings(slot);
    if (airborne_sword(spec,boss_adapters[slot]) && (spec.key==0xC72 || spec.key==0xC82)) {
        // Native71000A accumulates recoverable Ki from the airborne attack's actual cost.
        // A negative onset keeps it pending throughout the airborne phases.
        // Zero-cost follow-ups preserve the balance until their landing recovery frame.
        payload[0x33]=uint8_t(settings.pulse_percent);
        const int16_t pending=-1; memcpy(payload+0x38,&pending,2);
    }
    // Native71000A computes recoverable Ki from this percentage of the actual
    // game-adjusted cost. Native715118 opens its normal timed recovery when the
    // action crosses+0x38; 7B59F0 uses+0x3A/+0x3C as fill/hold durations.
    // The private cost above feeds native spending; never invent recoverable Ki without spending it.
    if (recovery_start >= 0) {
        // Native714EB7/+24 and714F06/+26 require a crossed, nonnegative frame.
        // A retained source cancel=-1 never crosses, even after Pulse becomes visible.
        // One boundary grants attack/cancel permissions and starts recoverable Ki.
        memcpy(payload+0x24,&recovery_start,2);
        memcpy(payload+0x26,&recovery_start,2);
        payload[0x33] = uint8_t(settings.pulse_percent);
        const int16_t fill_frames = int16_t(settings.pulse_fill), hold_frames = int16_t(settings.pulse_hold);
        memcpy(payload + 0x38, &recovery_start, sizeof(recovery_start));
        memcpy(payload + 0x3A, &fill_frames, sizeof(fill_frames));
        memcpy(payload + 0x3C, &hold_frames, sizeof(hold_frames));
    }
    uint8_t transitions[64][0x30]{}; uint16_t transition_count = 0;
    const bool izuna_bridge=boss_adapters[slot].kind==4 && spec.key==0xC7A && spec.motion==1050 && !spec.flags;
    const bool airborne=airborne_sword(spec,boss_adapters[slot]) && spec.key!=0xC74 && spec.key!=0xC83;
    if (!izuna_bridge && !airborne && (boss_adapters[slot].kind == 1 || boss_adapters[slot].kind == 2 || boss_adapters[slot].kind == 4)) {
        if (!boss_copy_player_transitions(slot,descriptor,transitions,transition_count)) return false;
    } else if (!boss_copy_pulse_transitions(slot, descriptor, transitions, transition_count)) return false;
    uint8_t combat[0x80]{};
    if (!boss_copy_launcher_contact(slot,descriptor,combat)) return false;
    const uint64_t private_transitions = reinterpret_cast<uint64_t>(target.transition_pointers);
    const uint16_t private_start = 0;
    memcpy(descriptor + 0x78, &private_transitions, 8);
    memcpy(descriptor + 0x80, &private_start, 2);
    memcpy(descriptor + 0x82, &transition_count, 2);
    const uint64_t private_payload = boss_private_payload_address(slot);
    memcpy(descriptor + 0x20, &private_payload, sizeof(private_payload));
    if (target.ready)
        return !memcmp(descriptor, target.descriptor, sizeof(descriptor))
            && !memcmp(payload, target.payload, sizeof(payload))
            && !memcmp(combat, target.combat_body, sizeof(combat))
            && target.transition_count == transition_count
            && !memcmp(transitions, target.transition_bodies, sizeof(transitions));
    memcpy(target.transition_bodies, transitions, sizeof(transitions));
    target.transition_count = transition_count;
    for (unsigned i = 0; i != transition_count; ++i)
        target.transition_pointers[i] = reinterpret_cast<uint64_t>(target.transition_bodies[i]);
    memcpy(target.payload, payload, sizeof(payload));
    memcpy(target.combat_body,combat,sizeof(combat));
    target.combat_entry=reinterpret_cast<uint64_t>(target.combat_body);
    memcpy(target.descriptor, descriptor, sizeof(descriptor));
    // Descriptor+0x38 retains the source bank; +0x78 owns adapted transitions
    // and C79's +0x48 owns its contact row. The lookup-only
    // 0x138 header is used ONLY by native0x73FA40 through R8.
    target.entry = boss_private_descriptor_address(slot);
    target.bank.entries = reinterpret_cast<uint64_t>(&target.entry);
    target.bank.count = 1;
    target.ready = true;
    return true;
}
#endif

static bool boss_is_preview_descriptor(uint64_t descriptor) {
    // Recognize current descriptors whose resources this adapter owns.
    // Compare exact private pointers and the two legacy research descriptors.
    // Resource recovery depends on identity, not on an action key that William can share.
#ifdef RESEARCH_REPEAT
    for (unsigned slot = 0; slot != boss_import_count; ++slot)
        if (boss_private_actions[slot].ready && descriptor == boss_private_descriptor_address(slot)) return true;
    if (descriptor && descriptor == boss_session.charge_descriptor) return true;
#endif
    return descriptor == boss_session.source_descriptor;
}
struct BossCallScope {
    BossCallScope() {
        // Keep Stop aware of a callback already using retained runtime state.
        // Increment the shared in-flight count before entering guarded callback work.
        // The module cannot retire an actor while that callback still holds its pointers.
        InterlockedIncrement(&boss_inflight);
    }
    ~BossCallScope() {
        // Release callback ownership on every scope-exit path.
        // Decrement the in-flight count after the enclosing native callback work finishes.
        // Stop may complete only after recovery and all entered callbacks have returned.
        InterlockedDecrement(&boss_inflight);
    }
};

static uint64_t boss_slot(unsigned i) {
    // Locate the four player resource slots adapted during imported playback.
    // Resolve fixed motion and timing offsets from this session's verified components.
    // All swaps and restoration checks must address the same ownership boundary.
    const uint64_t slots[] = {boss_session.player_motion + 8, boss_session.player_motion + 0x28,
                              boss_session.player_timing + 0x10, boss_session.player_timing + 0x28};
    return slots[i];
}
static uint64_t boss_borrowed(unsigned i, unsigned slot = boss_active_slot) {
    // Select the retained resource value appropriate for a player slot.
    // The first two slots borrow motion and the remaining two borrow timing.
    // This keeps native animation and timed events attached to one source package.
    const auto& adapter = boss_adapters[slot];
    return adapter.kind ? (i < 2 ? adapter.motion_bank : adapter.timing_wrapper)
        : (i < 2 ? boss_session.source_motion_bank : boss_session.source_timing_wrapper);
}
static bool same_field(uint64_t base, unsigned offset, uint64_t expected) {
    // Compare one live ownership field against its expected identity.
    // Read through the guarded copy routine instead of directly dereferencing it.
    // Replaced or inaccessible objects cannot authorize restoration through stale pointers.
    uint64_t actual = 0;
    return copy_field(base + offset, actual) && actual == expected;
}
static bool boss_player_valid() {
    // Check that this session still identifies the same player components.
    // Require matching actor vtable, owner, motion component and timing component.
    // Transient addresses may be reused after death, loading or equipment replacement.
    return same_field(boss_session.player, 0, boss_session.vtable)
        && same_field(boss_session.player, 0x50, boss_session.player_owner)
        && same_field(boss_session.player_owner, 0x38, boss_session.player_motion)
        && same_field(boss_session.player_owner, 0x68, boss_session.player_timing);
}

[[maybe_unused]] static bool boss_retire_destroyed_actor() {
    // Retire a positively replaced actor without writing its former resource slots.
    // Require no entered callbacks and explicit replacement or unmapped-memory evidence.
    // An ambiguous read failure must not abandon a still-live private action.
    if (!InterlockedCompareExchange(&boss_active, 0, 0)) return true;
    if (InterlockedCompareExchange(&boss_inflight, 0, 0)) return false;
    // Positive retirement evidence only. A transient/guarded read failure is
    // not permission to restore borrowed slots or forget a live private action.
    uint64_t vtable = 0, owner = 0;
    bool replaced = copy_field(boss_active_player, vtable) && vtable != boss_session.vtable;
    replaced = replaced || (copy_field(boss_active_player + 0x50, owner) && owner != boss_active_owner);
    MEMORY_BASIC_INFORMATION region{};
    const bool unmapped = VirtualQuery(reinterpret_cast<void*>(boss_active_player), &region, sizeof(region))
        && region.State != MEM_COMMIT;
    if (!replaced && !unmapped) return false;
    // These addresses no longer identify the old actor. Never write into them.
    // The module and private descriptors still remain allocated until exit.
#ifdef RESEARCH_REPEAT
    boss_camera_active = false;
    boss_chain_cancelled = true;
#endif
    InterlockedExchange(&boss_active, 0);
    return true;
}
static bool writable_slot(uint64_t slot) {
    // Check whether an aligned resource slot can accept an atomic pointer exchange.
    // Require committed writable memory and containment of the entire eight-byte field.
    // Borrow and restore must not cross a guarded or decommitted page boundary.
    MEMORY_BASIC_INFORMATION region{};
    return !(slot & 7) && VirtualQuery(reinterpret_cast<void*>(slot), &region, sizeof(region))
        && region.State == MEM_COMMIT && !(region.Protect & (PAGE_GUARD | PAGE_NOACCESS))
        && (region.Protect & 0xff) == PAGE_READWRITE
        && slot + 8 <= reinterpret_cast<uint64_t>(region.BaseAddress) + region.RegionSize;
}

#ifdef RESEARCH_REPEAT
static bool boss_camera_available() {
    // Validate the private action's camera slot before attempting the grab.
    // Require the recorded owner, reserved slot and expected original or borrowed value.
    // A native paired action must never start with an unresolved camera dependency.
    uint64_t camera = 0; uint32_t index = 0;
    return boss_player_valid() && copy_field(boss_session.player_owner+0x48,camera)
        && copy_field(camera+0x20,index) && index <= 2
        && boss_session.player_camera_slot >= camera+8 && boss_session.player_camera_slot <= camera+24
        && writable_slot(boss_session.player_camera_slot)
        && same_field(boss_session.source_camera_bank,0,reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr))+0x13C8FA0)
        && same_field(boss_session.player_camera_slot,0,boss_camera_active
            ? boss_camera_borrowed : boss_session.camera_original);
}
static bool boss_set_camera(bool borrow, unsigned slot = boss_active_slot) {
    // Borrow or restore the retained paired-action camera package.
    // Use ownership checks and compare-exchange on the recorded component slot.
    // Restoration remains valid after camera selection changes but cannot overwrite a replacement.
    // Two imported361/victim362 pairs restored correctly; the user confirmed string/grab playback.
    // Wider enemy compatibility and interrupted paired recovery still need gameplay acceptance.
    uint64_t camera = 0, current = 0;
    if (!boss_player_valid() || !copy_field(boss_session.player_owner+0x48,camera)
        || boss_session.player_camera_slot < camera+8 || boss_session.player_camera_slot > camera+24
        // William's idle camera may use slot1/2; the paired setter selects reserved slot0 later.
        || (borrow && !boss_camera_available())
        || !writable_slot(boss_session.player_camera_slot)
        || !copy_field(boss_session.player_camera_slot,current)) return false;
    const uint64_t expected = boss_camera_active ? boss_camera_borrowed : boss_session.camera_original;
    const uint64_t next = borrow ? (boss_adapters[slot].kind ? boss_hold_camera_bank : boss_session.source_camera_bank)
        : boss_session.camera_original;
    if (borrow && (next < 0x10000 || !same_field(next,0,reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr))+0x13C8FA0))) return false;
    if (current != expected || uint64_t(InterlockedCompareExchange64(
            reinterpret_cast<volatile LONG64*>(boss_session.player_camera_slot),LONG64(next),LONG64(expected))) != expected)
        return false;
    boss_camera_active = borrow;
    boss_camera_borrowed = borrow ? next : 0;
    return true;
}
#endif

// Called only inside the player's existing setter callback. Never overwrite an
// unexpected third-party value. Preflight all four locations before the first write.
static bool boss_set_bindings(bool borrow, unsigned slot = boss_active_slot) {
    // Swap all four player motion and timing slots as one guarded operation.
    // Preflight each value and roll back only values installed by this call.
    // Third-party or replaced resource pointers must survive failed adaptation unchanged.
    if (!boss_player_valid()) return false;
    uint64_t before[4]{};
    for (unsigned i = 0; i != 4; ++i) {
        if (!writable_slot(boss_slot(i)) || !copy_field(boss_slot(i), before[i])) return false;
        if (before[i] != boss_session.originals[i] && before[i] != boss_borrowed(i)) return false;
    }
    unsigned written = 0;
    for (; written != 4; ++written) {
        const uint64_t value = borrow ? boss_borrowed(written,slot) : boss_session.originals[written];
        auto* address = reinterpret_cast<volatile LONG64*>(boss_slot(written));
        if (uint64_t(InterlockedCompareExchange64(address, LONG64(value), LONG64(before[written]))) != before[written]) break;
    }
    if (written == 4) return true;
    // Roll back only values this call actually installed, still under ownership.
    while (written) {
        --written;
        const uint64_t value = borrow ? boss_borrowed(written,slot) : boss_session.originals[written];
        InterlockedCompareExchange64(reinterpret_cast<volatile LONG64*>(boss_slot(written)),
                                      LONG64(before[written]), LONG64(value));
    }
    return false;
}

static DispatchReason validate_boss_source(const DispatchCommand& c) {
    // Verify that a requested import still matches this session's owned resources.
    // Check actor identity, resource types, slot ownership and native action-bank priority.
    // A valid action number alone cannot distinguish an import from a colliding player move.
#ifdef RESEARCH_REPEAT
    if (c.reserved[1] >= boss_import_count) return InvalidConfig;
    const auto& spec = boss_imports[c.reserved[1]];
    if (!InterlockedCompareExchange(&boss_active,0,0) && spec.flags != 0x184C0000
        && boss_adapters[c.reserved[1]].kind != 1 && boss_adapters[c.reserved[1]].kind != 2 && boss_adapters[c.reserved[1]].kind != 5
        && !(boss_native_grapple_entry && boss_native_grapple && spec.key==0x361
            && spec.motion==1311 && spec.flags==0x8078000000ULL && !boss_adapters[c.reserved[1]].kind)) return InvalidConfig;
#else
    const struct { uint32_t key; int32_t motion; uint64_t descriptor, payload; } spec = {
        0xC64,1220,boss_session.source_descriptor,boss_session.source_payload};
#endif
    const uint32_t key_requested = spec.key;
    const int32_t motion_requested = spec.motion;
    const uint64_t descriptor_requested = spec.descriptor;
    const uint64_t payload_requested = spec.payload;
    if (c.player != boss_session.player || c.owner != boss_session.player_owner
        || c.vtable != boss_session.vtable || c.desired_key != key_requested || c.expected_motion != motion_requested
        || c.expected_descriptor != descriptor_requested
        || c.expected_payload != payload_requested) return BossSourceMismatch;
    const auto module = reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr));
    const auto& adapter = boss_adapters[c.reserved[1]];
    const uint64_t action_resource = adapter.kind ? adapter.action_resource : boss_session.source_action_resource;
    const uint64_t timing_resource = adapter.kind ? adapter.timing_resource : boss_session.source_timing_resource;
    const uint64_t bank = adapter.kind ? adapter.bank : boss_session.source_bank;
    const uint64_t timing_wrapper = adapter.kind ? adapter.timing_wrapper : boss_session.source_timing_wrapper;
    const uint64_t motion_bank = adapter.kind ? adapter.motion_bank : boss_session.source_motion_bank;
    if (!boss_player_valid()
        || !same_field(action_resource, 0, module + 0x13C7970)
        || !same_field(action_resource, 0x468, bank)
        || !same_field(timing_resource, 0, module + 0x12C5408)
        || !same_field(timing_resource, 0x468, timing_wrapper)
        || !same_field(motion_bank, 0, module + 0x13C8FA0))
        return BossSourceMismatch;
    bool originals=true, borrowed=InterlockedCompareExchange(&boss_active,0,0) != 0;
    for (unsigned i = 0; i != 4; ++i) {
        uint64_t value=0;
        if (!copy_field(boss_slot(i),value)) return BossBindingMismatch;
        originals = originals && value == boss_session.originals[i];
        borrowed = borrowed && value == boss_borrowed(i);
    }
    // An ordinary setter restores originals before native redirect resolution.
    // Accept that complete set, but never a partially swapped mixture.
    if (!originals && !borrowed) return BossBindingMismatch;

    uint64_t table = 0; uint32_t count = 0;
    if (!copy_field(bank + 0x128, table)
        || !copy_field(bank + 0x130, count) || !count || count > 4096)
        return DesiredInvalid;
    uint64_t entries[4096];
    if (!copy_bytes(table, entries, size_t(count) * 8)) return DesiredInvalid;
    for (uint32_t i = 0; i != count; ++i) {
        if (!entries[i]) continue;
        uint32_t key = 0; uint8_t enabled = 0;
        if (!copy_field(entries[i], key) || !copy_field(entries[i] + 0x40, enabled)) return DesiredInvalid;
        if (!enabled || key != c.desired_key) continue;
        uint64_t payload = 0; int32_t motion = -1;
        if (entries[i] != c.expected_descriptor || !copy_field(entries[i] + 0x20, payload)
            || payload != c.expected_payload || !copy_field(payload + 0x20, motion)
            || motion != c.expected_motion) return DesiredMismatch;
        return Accepted;
    }
    return DesiredMissing;
}

static bool boss_prepare_call(void* actor, uint32_t key, DispatchReason& reason,
        DispatchCommand& command, uint32_t& forwarded, void*& context, uint64_t (&private_banks)[3]) {
    // Prepare a private setter context only after the requested import is validated.
    // Build reachable actions, borrow resources and scope paired entry to native contact.
    // Failed paired preparation must never fall through to William's colliding action361.
    const uint64_t player = reinterpret_cast<uint64_t>(actor);
    const bool continuing = InterlockedCompareExchange(&boss_active, 0, 0) && player == boss_active_player;
    bool paired_transition = false;
    if (continuing && reason != Accepted) {
#ifdef RESEARCH_REPEAT
        const auto& current = boss_imports[boss_active_slot];
        // Only the game's successful-contact transition may enter the paired
        // action. Button holding never creates a victim or starts its camera.
        int paired_slot=-1;
        if ((current.flags == 0x594C0000 || boss_adapters[boss_active_slot].kind == 2 || boss_adapters[boss_active_slot].kind == 4)
            && current.next_variant >= 0 && key == boss_imports[current.next_variant].key)
            paired_slot=current.next_variant;
        if (boss_adapters[boss_active_slot].kind >= 2) {
            // Let the native paired graph choose its branch, constrained to this source bank.
            const auto& clone=boss_private_actions[boss_active_slot];
            for (unsigned row=0;row<clone.transition_count;++row) {
                int16_t target=0; memcpy(&target,clone.transition_bodies[row]+0x14,2);
                if (target < 0 || uint32_t(target)!=key) continue;
                const int next=boss_native_successor(boss_active_slot,key);
                if (next>=0) paired_slot=next;
            }
        }
        if (paired_slot >= 0 && boss_player_valid()
            && same_field(player,0x58,boss_private_descriptor_address(boss_active_slot))) {
            const auto& next = boss_imports[paired_slot];
            paired_transition = true;
            command = {}; command.player = player; command.owner = boss_active_owner;
            command.vtable = boss_session.vtable; command.reserved[1] = paired_slot;
            command.expected_descriptor = next.descriptor; command.expected_payload = next.payload;
            command.desired_key = next.key; command.expected_motion = next.motion;
            reason = Accepted; forwarded = key;
        } else
#endif
        {
            if (!boss_set_bindings(false)) {
                InterlockedExchange(&dispatch->control.status, -int(BossBindingMismatch));
                reason = BossBindingMismatch;
            }
            if (key == 0xC65 || key == 0xC66 || key == 0xC67 || key == 0xC68) {
                forwarded = 0xBB8; context = nullptr; reason = BossFollowupExit;
            }
            return true;
        }
    }
    if (reason != Accepted) return true;
    reason = validate_boss_source(command);
#ifdef RESEARCH_REPEAT
    const unsigned private_slot = unsigned(command.reserved[1]);
    if (reason == Accepted) {
        const bool izuna=boss_imports[private_slot].key==0xC79 && boss_native_successor(private_slot,0xC7A)>=0;
        if (((boss_imports[private_slot].flags == 0x594C0000 && !boss_adapters[private_slot].kind) || izuna || ((boss_adapters[private_slot].kind==2 || boss_adapters[private_slot].kind==4) && boss_imports[private_slot].next_variant>=0))
            && !boss_camera_available()) reason = BossBindingMismatch;
        int slot = int(private_slot);
        // Finish every reachable clone before starting the first attack. A
        // native successful grab must never discover a missing paired adapter.
        for (unsigned count = 0; slot >= 0 && count < boss_import_count; ++count) {
            if (!boss_prepare_private_action(unsigned(slot))) { reason = BossSourceMismatch; break; }
            slot = boss_imports[slot].next_variant;
        }
        // Jin's paired graph has a native conditional branch beyond next_variant.
        if (boss_adapters[private_slot].kind==2) for (unsigned next=0;next<boss_import_count;++next)
            if (boss_adapters[next].kind>=2 && boss_adapters[next].bank==boss_adapters[private_slot].bank
                && (boss_adapters[next].player_key==boss_adapters[private_slot].player_key || (izuna && boss_adapters[next].kind==3))
                && !boss_prepare_private_action(next)) reason=BossSourceMismatch;
        if (reason == Accepted && boss_paired(boss_imports[private_slot].flags)
            && !boss_set_camera(true,private_slot)) reason = BossBindingMismatch;
    }
#endif
    if (reason != Accepted || !boss_set_bindings(true, unsigned(command.reserved[1]))) {
        if (reason == Accepted) reason = BossBindingMismatch;
#ifdef RESEARCH_REPEAT
        if (boss_camera_active && !boss_paired(boss_imports[boss_active_slot].flags)) boss_set_camera(false);
#endif
        forwarded = key;
        InterlockedExchange(&dispatch->control.last_reason, reason);
        // Never pass a rejected native grab handoff into William's bank with
        // a colliding action ID and no validated paired motion/camera context.
        return !paired_transition;
    }
    boss_active_player = player; boss_active_owner = command.owner;
    private_banks[0] = 0; private_banks[1] = boss_session.source_bank; private_banks[2] = 0;
#ifdef RESEARCH_REPEAT
    private_banks[1] = reinterpret_cast<uint64_t>(&boss_private_actions[private_slot].bank);
    command.expected_descriptor = boss_private_descriptor_address(private_slot);
    command.expected_payload = boss_private_payload_address(private_slot);
#endif
    context = private_banks;
#ifdef RESEARCH_REPEAT
    boss_active_slot = private_slot;
    if (!paired_transition) boss_frost_playback=false;
    if (!continuing) {
        boss_chain_sequence = command.chord_sequence;
        boss_chain_epoch = uint32_t(command.reserved[2]);
        boss_chain_cancelled = false;
    }
#endif
    InterlockedExchange(&boss_active, 1);
    InterlockedExchange(&dispatch->control.status, 2);
    return true;
}

static void boss_finish_call(void* actor) {
    // Reconcile borrowed resources with the descriptor the native setter actually selected.
    // Restore originals after exit and retain borrowing only for a recognized private action.
    // Native setters may fail or choose another state, so their return value is insufficient.
    if (!InterlockedCompareExchange(&boss_active, 0, 0)
        || reinterpret_cast<uint64_t>(actor) != boss_active_player) return;
    uint64_t current = 0;
    if (!same_field(boss_active_player, 0x50, boss_active_owner)
        || !copy_field(boss_active_player + 0x58, current)) {
        InterlockedExchange(&dispatch->control.status, -int(BossBindingMismatch));
        return;
    }
    const bool still_preview = boss_is_preview_descriptor(current);
#ifdef RESEARCH_REPEAT
    if (still_preview) for (unsigned slot = 0; slot != boss_import_count; ++slot) {
        if (current != boss_private_descriptor_address(slot)) continue;
        if (boss_active_slot != slot) boss_chain_cancelled = true;
        boss_active_slot = slot;
        if (boss_camera_active && !boss_paired(boss_imports[slot].flags) && !boss_set_camera(false)) {
            boss_chain_cancelled = true;
            InterlockedExchange(&dispatch->control.status,-int(BossBindingMismatch));
            return;
        }
        break;
    }
#endif
    if (!boss_set_bindings(still_preview)) {
        InterlockedExchange(&dispatch->control.status, -int(BossBindingMismatch));
        return;
    }
    if (!still_preview) {
#ifdef RESEARCH_REPEAT
        if (boss_camera_active && !boss_set_camera(false)) {
            InterlockedExchange(&dispatch->control.status,-int(BossBindingMismatch));
            return;
        }
        boss_chain_cancelled = true;
#endif
        InterlockedExchange(&boss_active, 0);
        InterlockedExchange(&dispatch->control.status, 3);
    } else InterlockedExchange(&dispatch->control.status, 2);
}
