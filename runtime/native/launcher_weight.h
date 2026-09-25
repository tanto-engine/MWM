#pragma once

using WeightFn = void (*)(void*,float);
static WeightFn native_set_weight;
struct LaunchWeight { uint64_t actor,owner,collision,descriptor; float original,applied; };
static LaunchWeight launch_weights[8]{};
static volatile LONG launch_weight_count;
struct LaunchHit { uint64_t owner; uint32_t counter; };

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

static LaunchHit launcher_hit(void* actor) {
    // Match the victim's selected native hit before the setter consumes its event queue.
    // Component+90 identifies the event; exact attacker and private combat-row identity scope C79.
    // Mid Izuna, other attacks, victimless attempts and disabled sessions cannot acquire weight.
    const auto victim=reinterpret_cast<uint64_t>(actor);const unsigned slot=boss_active_slot;
    LaunchHit hit{};uint64_t component=0,event=0,attacker=0,target=0,row=0;int32_t mode=-1;
    if (!native_set_weight || !dispatch || !InterlockedCompareExchange(&dispatch->control.enabled,0,0)
        || victim==boss_session.player || !InterlockedCompareExchange(&boss_active,0,0) || slot>=boss_import_count
        || !boss_player_valid() || boss_adapters[slot].kind!=2 || boss_adapters[slot].player_key!=0xCF5
        || boss_imports[slot].key!=0xC79 || boss_imports[slot].motion!=5014 || !boss_private_actions[slot].ready
        || !same_field(boss_session.player,0x58,boss_private_descriptor_address(slot))
        || !same_field(victim,0,boss_session.vtable) || !copy_field(victim+0x50,hit.owner)
        || !copy_field(hit.owner+0x230,component) || !same_field(component,8,victim)
        || !copy_field(component+0x90,event) || !copy_field(event+0xE8,attacker) || attacker!=boss_session.player_owner
        || !copy_field(event+0x100,target) || target!=hit.owner || !copy_field(event+0xE0,row)
        || row!=reinterpret_cast<uint64_t>(boss_private_actions[slot].combat_body)
        || !copy_field(event+0x11C,mode) || mode!=0 || !copy_field(victim+0xDC,hit.counter)) return {};
    return hit;
}

static void apply_launch_weight(void* actor, const LaunchHit& hit) {
    // Require the setter to commit a reaction that consumes a selected impact event.
    // Halve effective native collision weight while preserving the original override sentinel.
    // Paired/immovable states are excluded; the separate private impulse supplies launch height.
    if (!hit.owner || !dispatch || !InterlockedCompareExchange(&dispatch->control.enabled,0,0)) return;
    const auto victim=reinterpret_cast<uint64_t>(actor);
    for (const auto& entry : launch_weights) if (entry.actor==victim) return;
    uint64_t current=0,payload=0,flags=0,collision=0;uint32_t reaction=0,counter=0;float original=0,weight=0;
    if (!same_field(victim,0,boss_session.vtable) || !same_field(victim,0x50,hit.owner)
        || !copy_field(victim+0xDC,counter) || counter==hit.counter || !copy_field(victim+0x58,current)
        || !copy_field(current+0x20,payload) || !copy_field(payload,reaction) || !(reaction&0x40000)
        || !copy_field(payload+0x18,flags) || (flags&0x20000000ULL)
        || !copy_field(hit.owner+0x250,collision) || !copy_field(collision+0xB0,weight)
        || !copy_field(victim+0x7BC,original) || !std::isfinite(original) || !(weight>0 && weight<10000)) return;
    for (auto& entry : launch_weights) if (!entry.actor) {
        entry={victim,hit.owner,collision,current,original,weight*.5f};
        InterlockedIncrement(&launch_weight_count);
        native_set_weight(actor,entry.applied);
        break;
    }
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
