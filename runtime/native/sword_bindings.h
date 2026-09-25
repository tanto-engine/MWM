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

static int high_guard_light_slot(uint32_t key, uint64_t descriptor, uint32_t bank, DispatchCommand& command) {
    // Native710A66 publishes the selected row before calling the setter/lookup.
    // Keep its guard-held/Square-pressed timing and skill gates, independent of loadout ID.
    // Membership in the current action excludes old rows and ordinary/running Square.
    const uint64_t player=boss_session.player;
    uint64_t current=0,selected=0,table=0; uint16_t start=0,count=0;
    uint8_t row[0x30],check[0x30]; int16_t target=-1;
    if (!(boss_native_bindings&8) || bank || boss_active || !grapple_field(player,0x470,uint32_t(1))
        || !grapple_field(descriptor,0,key) || !grapple_field(descriptor,0x40,uint8_t(1))
        || !copy_field(player+0x58,current) || !copy_field(player+0x90,selected)
        || !copy_bytes(selected,row,sizeof(row)) || (row[0x0A]!=0 && row[0x0A]!=2)
        || row[0x0B]!=5 || row[0x0C]!=0 || row[0x0D]!=0 || row[0x0E]!=1) return -1;
    memcpy(&target,row+0x14,2);
    if (target<0 || uint32_t(target)!=key || !copy_field(current+0x78,table)
        || !copy_field(current+0x80,start) || !copy_field(current+0x82,count) || !count || count>128) return -1;
    uint64_t pointers[128]{}; bool owned=false;
    if (!copy_bytes(table+uint64_t(start)*8,pointers,count*8)) return -1;
    for (unsigned index=0;index<count;++index) owned=owned || pointers[index]==selected;
    if (!owned || !copy_bytes(selected,check,sizeof(check)) || memcmp(row,check,sizeof(row))
        || !grapple_field(player,0x58,current) || !grapple_field(player,0x90,selected)
        || !grapple_field(current,0x78,table) || !grapple_field(current,0x80,start)
        || !grapple_field(current,0x82,count)) return -1;
    for (unsigned slot=0;slot<boss_import_count;++slot)
        if (boss_imports[slot].key==0xC81 && boss_imports[slot].motion==1050
            && boss_adapters[slot].kind==2 && boss_adapters[slot].player_key==0xC7A
            && replacement_context(command,boss_adapters[slot])) return int(slot);
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
    const unsigned index=key-0xCB3; auto& target=mid_light_actions[index];
    uint8_t source[0xD0]{}; uint64_t payload=0,table=0; uint16_t start=0,count=0;
    if (!copy_bytes(descriptor,source,sizeof(source))) return 0;
    memcpy(&payload,source+0x20,8); memcpy(&table,source+0x78,8);
    memcpy(&start,source+0x80,2); memcpy(&count,source+0x82,2);
    if (!grapple_field(descriptor,0,key) || !source[0x40] || count!=(index==2 ? 44 : 46)
        || !grapple_field(payload,0x18,uint64_t(0x8000000594C0000ULL))
        || !grapple_field(payload,0x20,int32_t(3100+index*10))) return 0;
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
        const int16_t low=int16_t(row ? (index==0 ? 40 : index==1 ? 44 : 52) : 10);
        const int16_t high=int16_t(row ? (index==0 ? 70 : index==1 ? 74 : 82) : low+(index==0 ? 29 : index==1 ? 33 : 41));
        if (original[0x0A]!=(row ? 0 : 2) || original[0x0B]!=1 || original[0x0C]!=1
            || !grapple_field(pointers[7+row],0x14,int16_t(0xD67))
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
