#pragma once

static uint64_t native_skill_import(unsigned slot, uint32_t key, DispatchCommand& command) {
    // Reuse the validated import path after native input has selected a skill.
    // Prepare the complete source graph before borrowing its resources.
    // A rejected import leaves the native selected action available.
    const auto& move=boss_imports[slot];
    command.reserved[1]=slot; command.desired_key=move.key; command.expected_motion=move.motion;
    command.expected_descriptor=move.descriptor; command.expected_payload=move.payload;
    uint32_t forwarded=key; void* context=nullptr; uint64_t banks[3]{}; auto reason=Accepted;
    if (!boss_prepare_call(replacement_call.actor,key,reason,command,forwarded,context,banks) || reason!=Accepted) return 0;
    *replacement_call.command=command; *replacement_call.reason=Accepted;
    InterlockedIncrement64(&dispatch->control.dispatch_count);
    return boss_private_descriptor_address(slot);
}

static bool selected_sword_row(uint32_t key, uint8_t* row) {
    // Native710A66 publishes the selected row before calling the setter/lookup.
    // Snapshot that row after native input and skill gates select its target.
    // Membership in the current action excludes old rows and ordinary/running Square.
    const uint64_t player=boss_session.player;
    uint64_t current=0,selected=0,table=0; uint16_t start=0,count=0;
    uint8_t check[0x30]; int16_t target=-1;
    if (!copy_field(player+0x58,current) || !copy_field(player+0x90,selected)
        || !copy_bytes(selected,row,0x30) || (row[0x0A]!=0 && row[0x0A]!=2)) return false;
    memcpy(&target,row+0x14,2);
    if (target<0 || uint32_t(target)!=key || !copy_field(current+0x78,table)
        || !copy_field(current+0x80,start) || !copy_field(current+0x82,count) || !count || count>128) return false;
    uint64_t pointers[128]{}; bool owned=false;
    if (!copy_bytes(table+uint64_t(start)*8,pointers,count*8)) return false;
    for (unsigned index=0;index<count;++index) owned=owned || pointers[index]==selected;
    if (!owned || !copy_bytes(selected,check,sizeof(check)) || memcmp(row,check,sizeof(check))
        || !grapple_field(player,0x58,current) || !grapple_field(player,0x90,selected)
        || !grapple_field(current,0x78,table) || !grapple_field(current,0x80,start)
        || !grapple_field(current,0x82,count)) return false;
    return true;
}

static bool tiger_sprint_entry(uint32_t key, uint64_t descriptor, uint64_t payload) {
    // BBA is the native sheathe redirect; D46 is the shared Iai/Tiger preparation.
    // Require the selected sword-skill input and the native current-stance Tiger assignment.
    // The existing player lookup substitutes before either preparation owns an animation.
    const bool sheath=key==0xBBA;
    uint8_t row[0x30];uint64_t gate=0;int32_t skill=0;
    if ((!sheath && key!=0xD46) || !grapple_field(payload,0x20,int32_t(sheath ? -1 : 5000))
        || !grapple_field(payload,0x18,uint64_t(sheath ? 0 : 0x194C0000))
        || !grapple_field(descriptor,0x82,uint16_t(sheath ? 13 : 49))
        || !selected_sword_row(key,row) || row[0x0B]!=0x14 || row[0x0C]>1
        || row[0x0D]!=0xff || row[0x0E]!=0xff) return false;
    memcpy(&skill,row+0x2C,4);
    if (skill!=(sheath ? -1 : 0x4AFB) || !copy_field(boss_session.vtable+0x180,gate) || !gate) return false;
    // Exact-build vtable+180 is73D2C0: the same read-only skill/loadout gate used by720E71.
    using SkillFn=bool (*)(void*,int32_t);
    return reinterpret_cast<SkillFn>(gate)(reinterpret_cast<void*>(boss_session.player),0x4AFB);
}

static int native_bound_slot(uint32_t key, uint64_t descriptor, DispatchCommand& command) {
    // Resolve exact native skills after the game applies stance/loadout/input conditions.
    // Native cancel selection may replace an active ordinary import; paired ownership remains protected.
    // Bindings choose a destination import independently of its permanent source identity.
    uint32_t stance=0;uint64_t payload=0;
    if ((boss_active && boss_paired(boss_imports[boss_active_slot].flags))
        || !copy_field(boss_session.player+0x470,stance) || stance>2
        || !grapple_field(descriptor,0,key) || !grapple_field(descriptor,0x40,uint8_t(1))
        || !copy_field(descriptor+0x20,payload)) return -1;
    const unsigned mask=1u<<(2-stance);
    for (const auto& binding : boss_skill_bindings) {
        if (!binding.kind || binding.kind==3 || binding.kind==4 || !(binding.stances&mask)) continue;
        if (binding.kind==5) {
            // Match the native low-Square opener after the game has selected it.
            // The graph borrows the verified low-heavy exit template but remaps continuation to Square.
            // Running, dodging and stance-switch actions retain their original priorities.
            if (key!=0xCF0 || !grapple_field(payload,0x20,int32_t(4100))
                || !grapple_field(payload,0x18,uint64_t(0x8000000594C0000ULL))) continue;
            if (native_binding_context(command)) return int(binding.variant-1);
            continue;
        }
        if (binding.kind==1) {
            const bool dodge=binding.key==0xBC8 && (key==0xBC8 || key==0xBC9);
            const bool exact=(key==binding.key || dodge) && grapple_field(payload,0x20,binding.motion)
                && grapple_field(payload,0x18,binding.flags)
                && grapple_field(descriptor,0x82,uint16_t(binding.transition_count+(dodge && key==0xBC9)));
            if (dodge) {
                uint8_t row[0x30];
                if (!selected_sword_row(key,row) || row[0x0B]!=1 || row[0x0C]!=1 || row[0x0D]!=0xff) continue;
            }
            if (!exact && !(binding.key==0xFAA && stance==1 && (key==0xBBA || key==0xD46) && native_binding_context(command)
                && tiger_sprint_entry(key,descriptor,payload))) continue;
        } else {
            uint8_t row[0x30];
            if (!selected_sword_row(key,row) || row[0x0B]!=5 || row[0x0C]!=0 || row[0x0D]!=0 || row[0x0E]!=1) continue;
        }
        if (native_binding_context(command)) return int(binding.variant-1);
    }
    return -1;
}

struct MidLightAction {
    uint8_t descriptor[0xD0], original[0xD0], rows[48][0x30];
    uint64_t pointers[48];
    bool ready;
};
static MidLightAction mid_light_actions[3]{};

static bool mid_light_active() {
    // Keep the action hook through Stop while an adapted light attack is current.
    // Previous descriptors remain allocated, but only current rows can schedule the custom ender.
    // Native movement or completion releases this short shutdown boundary.
    bool prepared=false;
    for (const auto& action : mid_light_actions) prepared=prepared||action.ready;
    if (!prepared) return false;
    uint64_t current=0,owner=0,vtable=0;
    if ((copy_field(boss_session.player,vtable) && vtable!=boss_session.vtable)
        || (copy_field(boss_session.player+0x50,owner) && owner!=boss_session.player_owner)) return false;
    MEMORY_BASIC_INFORMATION region{};
    if (VirtualQuery(reinterpret_cast<void*>(boss_session.player),&region,sizeof(region)) && region.State!=MEM_COMMIT) return false;
    if (!copy_field(boss_session.player+0x58,current)) return true;
    for (const auto& action : mid_light_actions)
        if (action.ready && current==reinterpret_cast<uint64_t>(action.descriptor)) return true;
    return false;
}

static uint64_t mid_light_ender(void* context, uint32_t key, uint64_t descriptor) {
    // Prepend LB-held + Triangle-press enders to the three native mid-light tables.
    // Reuse each native buffered/direct combo window and keep all other rows byte-identical.
    // D3A stays a native sword action; its damage, resources, Ki cost and exits remain owned by the game.
    const unsigned index=key-0xC76; auto& target=mid_light_actions[index];
    uint8_t source[0xD0]{}; uint64_t payload=0,table=0; uint16_t start=0,count=0;
    if (!copy_bytes(descriptor,source,sizeof(source))) return 0;
    memcpy(&payload,source+0x20,8); memcpy(&table,source+0x78,8);
    memcpy(&start,source+0x80,2); memcpy(&count,source+0x82,2);
    if (!grapple_field(descriptor,0,key) || !source[0x40] || count!=46
        || !grapple_field(payload,0x18,uint64_t(0x8000000594C0000ULL))
        || !grapple_field(payload,0x20,int32_t(2100+index*10))) return 0;
    uint32_t bank=0; const uint64_t ender=original_lookup(context,0xD3A,&bank); uint64_t ender_payload=0;
    if (bank!=0 || !grapple_field(ender,0,uint32_t(0xD3A)) || !grapple_field(ender,0x40,uint8_t(1))
        || !copy_field(ender+0x20,ender_payload) || !grapple_field(ender_payload,0x20,int32_t(9210))
        || !grapple_field(ender_payload,0x18,uint64_t(0x194C0000))) return 0;
    if (target.ready) return !memcmp(source,target.original,sizeof(source)) ? reinterpret_cast<uint64_t>(target.descriptor) : 0;
    uint64_t pointers[46]{},check[46]{};
    if (!copy_bytes(table+uint64_t(start)*8,pointers,count*8)) return 0;
    for (unsigned row=0;row<count;++row) if (!copy_bytes(pointers[row],target.rows[row+2],0x30)) return 0;
    for (unsigned row=0;row<2;++row) {
        const auto* original=target.rows[9+row]; // Captured native rows7/8: buffered then direct Triangle ender.
        const int16_t low=int16_t(row ? (index==0 ? 24 : index==1 ? 26 : 31) : index==0 ? 5 : 10);
        const int16_t high=int16_t((index==0 ? 24 : index==1 ? 26 : 31)+(row ? 30 : -1));
        if (original[0x0A]!=(row ? 0 : 2) || original[0x0B]!=1 || original[0x0C]!=1
            || !grapple_field(pointers[7+row],0x14,int16_t(0xFA5))
            || !grapple_field(pointers[7+row],0x20,low) || !grapple_field(pointers[7+row],0x22,high)) return 0;
        memcpy(target.rows[row],original,0x30);
        target.rows[row][0x0D]=5; target.rows[row][0x0E]=0; // Native selector5/state0: guard held.
        const int16_t destination=0xD3A; const int32_t skill=-1;
        memcpy(target.rows[row]+0x14,&destination,2); memcpy(target.rows[row]+0x2C,&skill,4);
    }
    if (!copy_bytes(table+uint64_t(start)*8,check,count*8) || memcmp(check,pointers,count*8)
        || !grapple_field(descriptor,0x20,payload)) return 0;
    memcpy(target.original,source,sizeof(source)); memcpy(target.descriptor,source,sizeof(source));
    for (unsigned row=0;row<count+2u;++row) target.pointers[row]=reinterpret_cast<uint64_t>(target.rows[row]);
    table=reinterpret_cast<uint64_t>(target.pointers); start=0; count+=2;
    memcpy(target.descriptor+0x78,&table,8); memcpy(target.descriptor+0x80,&start,2); memcpy(target.descriptor+0x82,&count,2);
    target.ready=true;
    return reinterpret_cast<uint64_t>(target.descriptor);
}
