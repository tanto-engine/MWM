#pragma once

using WeightFn = void (*)(void*,float);
static WeightFn native_set_weight;
// Each temporary override remembers both original and applied weight, plus actor identity, for conditional restoration.
struct LaunchWeight { uint64_t actor,owner,collision,descriptor; float original,applied; };
static LaunchWeight launch_weights[8]{};
static volatile LONG launch_weight_count;
// Snapshot hit evidence before the native setter, then compare after it returns to scope one reaction.
struct LaunchHit { uint64_t owner,component; uint32_t counter; float vertical_impulse,grounded,airborne,boost; bool launcher; };

static void restore_launch_weights(uint64_t actor, bool force, bool all=false) {
    // Restore only our exact override through Character::SetWeight on a native callback.
    // Descriptor changes, Stop and player replacement end the single reaction's ownership.
    // Reused actors or a newer weight owner are retired without overwriting their state.
    if (!InterlockedCompareExchange(&launch_weight_count,0,0)) return;
    for (auto& entry : launch_weights) {
        if (!entry.actor || (!all && actor!=entry.actor)) continue;
        uint64_t vtable=0,owner=0,collision=0,current=0; float value=0;
        const bool readable=copy_field(entry.actor,vtable) && copy_field(entry.actor+0x50,owner);
        MEMORY_BASIC_INFORMATION region{};
        const bool retired=(readable && (vtable!=boss_session.vtable || owner!=entry.owner))
            || (VirtualQuery(reinterpret_cast<void*>(entry.actor),&region,sizeof(region)) && region.State!=MEM_COMMIT);
        bool release=retired;
        float effective=0;
        if (!retired && readable && copy_field(owner+0x250,collision) && (!collision || copy_field(collision+0xB0,effective))
            && copy_field(entry.actor+0x58,current) && copy_field(entry.actor+0x7BC,value)) {
            release=value!=entry.applied || force || current!=entry.descriptor || collision!=entry.collision;
            if (release && value==entry.applied && native_set_weight)
                native_set_weight(reinterpret_cast<void*>(entry.actor),entry.original);
        }
        if (release) {entry={};InterlockedDecrement(&launch_weight_count);}
    }
}

static bool sword_combat_row(uint64_t row) {
    // Attribute airborne hits to the current player's exact native or curated sword combat row.
    // Basic sword key/motion pairs exclude collisions from another weapon or resource bank.
    // Imported graphs retain their own rows; paired attacks never acquire this policy.
    uint64_t current=0,payload=0,flags=0,table=0;uint32_t key=0;int32_t motion=0;uint16_t start=0,count=0;
    if (!copy_field(boss_session.player+0x58,current) || !copy_field(current+0x20,payload)
        || !copy_field(payload+0x18,flags) || (flags&0x20000000ULL)) return false;
    const unsigned slot=boss_active_slot;
    bool sword=boss_active && slot<boss_import_count && boss_private_actions[slot].ready
        && current==boss_private_descriptor_address(slot);
    if (!sword && grapple_field(boss_session.player,0x68,uint32_t(0)) && copy_field(current,key)
        && copy_field(payload+0x20,motion)) {
        constexpr uint32_t keys[]={0xC76,0xC7A,0xCB3,0xCB7,0xCF0,0xCF5};
        constexpr int32_t motions[]={2100,2300,3100,3300,4100,4300};
        for (unsigned group=0;group<6;++group)
            if (key>=keys[group] && key<keys[group]+(group==4 ? 5u : 3u)
                && motion==motions[group]+int32_t(key-keys[group])*10) sword=true;
    }
    if (!sword || !grapple_field(current,0x40,uint8_t(1)) || !copy_field(current+0x48,table)
        || !copy_field(current+0x50,start) || !copy_field(current+0x52,count) || !count || count>64) return false;
    uint64_t pointers[64]{};
    if (!copy_bytes(table+uint64_t(start)*8,pointers,count*8)) return false;
    for (unsigned i=0;i<count;++i) if (pointers[i]==row)
        return same_field(boss_session.player,0x58,current) && same_field(current,0x48,table);
    return false;
}

static LaunchHit launcher_hit(void* actor) {
    // Snapshot the exact selected player hit before native reaction processing frees its event.
    // Classify humans before weight changes; only already-airborne victims gain a sword juggle boost.
    // Register provisional launcher ownership so rejected/paired commits restore the exact sentinel.
    const auto victim=reinterpret_cast<uint64_t>(actor);const unsigned slot=boss_active_slot;
    for (const auto& entry : launch_weights) if (entry.actor==victim) return {};
    LaunchHit hit{};uint64_t event=0,attacker=0,target=0,row=0;int32_t mode=-1;
    uint64_t current=0,payload=0,flags=0,state=0,collision=0;float original=0,weight=0;
    if (!dispatch || !InterlockedCompareExchange(&dispatch->control.enabled,0,0)
        || victim==boss_session.player || !boss_player_valid()
        || !same_field(victim,0,boss_session.vtable) || !copy_field(victim+0x50,hit.owner)
        || !copy_field(hit.owner+0x230,hit.component) || !same_field(hit.component,8,victim)
        || !copy_field(hit.component+0x90,event) || !copy_field(event+0xE8,attacker) || attacker!=boss_session.player_owner
        || !copy_field(event+0x100,target) || target!=hit.owner || !copy_field(event+0xE0,row)
        || !copy_field(event+0x11C,mode) || mode!=0 || !copy_field(victim+0xDC,hit.counter)
        || !copy_field(victim+0x58,current) || !copy_field(current+0x20,payload) || !copy_field(payload,state)
        || !copy_field(payload+0x18,flags) || (flags&0x20000000ULL)
        || !copy_field(hit.owner+0x250,collision) || !copy_field(collision+0xB0,weight) || !(weight>0 && weight<10000)) return {};
    hit.launcher=boss_active && slot<boss_import_count && boss_adapters[slot].kind==2
        && boss_native_successor(slot,0xC7A)<0 && boss_imports[slot].key==0xC79 && boss_imports[slot].motion==5014
        && boss_private_actions[slot].ready && same_field(boss_session.player,0x58,boss_private_descriptor_address(slot))
        && row==reinterpret_cast<uint64_t>(boss_private_actions[slot].combat_body);
    const bool izuna=boss_active && slot<boss_import_count && boss_imports[slot].key==0xC79
        && boss_native_successor(slot,0xC7A)>=0 && same_field(boss_session.player,0x58,boss_private_descriptor_address(slot));
    hit.boost=(state&0x200000400ULL) && !izuna ? boss_air_juggle_boost : 0; // Preserve the native catch trajectory.
    if (!hit.launcher && (!hit.boost || !sword_combat_row(row))) return {};
    int8_t grounded=0,airborne=0;
    if (!copy_field(row+0x17,grounded) || !copy_field(row+0x1B,airborne)) return {};
    hit.grounded=float(grounded);hit.airborne=float(airborne>20 ? 20 : airborne);
    if (!hit.launcher) return hit;
    if (!native_set_weight || !copy_field(victim+0x7BC,original) || !std::isfinite(original)) return {};
    float scale=.5f;hit.vertical_impulse=16;
    uint64_t profile=0,stats=0,alternate=0;uint32_t resistance=0;
    if (copy_field(hit.owner+0xE90,profile) && grapple_field(profile,0x0C,uint32_t(0))
        && copy_field(hit.owner+0x240,stats) && copy_field(stats+0xB98,alternate)
        && copy_field((alternate ? alternate : stats+0x9D8)+0x120,resistance))
        for (const auto& tier : boss_launch_profiles) if (resistance<tier.resistance_below) {
            scale=tier.weight_scale;hit.vertical_impulse=tier.vertical_impulse;break;
        }
    for (auto& entry : launch_weights) if (!entry.actor) {
        entry={victim,hit.owner,collision,current,original,weight*scale};
        InterlockedIncrement(&launch_weight_count);native_set_weight(actor,entry.applied);return hit;
    }
    return {};
}

static void finish_launch_weight(void* actor, const LaunchHit& hit, bool accepted) {
    // Consume only a newly committed unpaired damage reaction with the captured victim identity.
    // Caller711106 reads component+5C after this hook returns; never revisit the freed hit event.
    // Comparing its native source result prevents repeated boosts and leaves later writes untouched.
    if (!hit.owner) return;
    const auto victim=reinterpret_cast<uint64_t>(actor);LaunchWeight* weight=nullptr;
    for (auto& entry : launch_weights) if (entry.actor==victim && entry.owner==hit.owner) weight=&entry;
    uint64_t current=0,payload=0,flags=0,reaction=0;uint32_t counter=0;
    const bool committed=accepted && dispatch && InterlockedCompareExchange(&dispatch->control.enabled,0,0)
        && same_field(victim,0,boss_session.vtable) && same_field(victim,0x50,hit.owner)
        && (!weight || same_field(hit.owner,0x250,weight->collision)) && same_field(hit.owner,0x230,hit.component)
        && same_field(hit.component,8,victim) && copy_field(victim+0xDC,counter) && counter!=hit.counter
        && copy_field(victim+0x58,current) && copy_field(current+0x20,payload)
        && copy_field(payload,reaction) && (reaction&0x40000)
        && copy_field(payload+0x18,flags) && !(flags&0x20000000ULL);
    if (committed) {
        if (weight) weight->descriptor=current;
        const float expected=(reaction&0x200000400ULL) ? hit.airborne : hit.grounded;
        float adjusted=(hit.launcher ? hit.vertical_impulse : expected)+hit.boost;
        if (adjusted>20) adjusted=20;
        if (grapple_field(hit.component,0x5C,expected))
            memcpy(reinterpret_cast<void*>(hit.component+0x5C),&adjusted,sizeof(float));
    }
    if (weight) restore_launch_weights(victim,!committed);
}

static bool resolve_weight_setter(uint64_t module) {
    // Pin the supported Character::SetWeight setter before publishing a callable address.
    // Its RCX/XMM1 ABI stores actor+7BC and tail-calls720040 to refresh collider weights.
    // No extra hook or direct physics-field write is needed for the scoped override.
    const uint8_t expected[]={0xf3,0x0f,0x11,0x89,0xbc,0x07,0,0,0xe9,0x93,0xa0,0xfd,0xff};
    uint8_t actual[sizeof(expected)];
    if (!copy_bytes(module+0x745FA0,actual,sizeof(actual)) || memcmp(actual,expected,sizeof(actual))) return false;
    native_set_weight=reinterpret_cast<WeightFn>(module+0x745FA0);
    return true;
}
