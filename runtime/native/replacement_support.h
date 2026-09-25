#pragma once

using LookupFn = uint64_t (*)(void*, uint32_t, uint32_t*);
static LookupFn original_lookup;
static void* lookup_target;
static bool lookup_hook_created;
struct ReplacementCall { void* actor; DispatchCommand* command; DispatchReason* reason; };
static thread_local ReplacementCall replacement_call{};
struct PendingHeavy {
    int64_t started;
    uint64_t origin;
    uint32_t origin_key, epoch;
    unsigned tap, controller, hold, native_key;
    bool active, spent;
};
static PendingHeavy pending_heavy{};

static bool heavy_button(unsigned& controller, bool& down, bool& interrupted) {
    // Read Triangle from the player frame's timestamped controller snapshot.
    // Require one connected controller and preserve thumbstick/lock-on independence.
    // Disconnects, ambiguous controllers and competing actions cancel a pending hold.
    GameInput sample{};
    if (!trace || !read_game_input(trace->header,sample)) return false;
    unsigned connected=0;
    for (DWORD slot=0;slot<4;++slot) {
        if (sample.codes[slot]!=ERROR_SUCCESS) continue;
        ++connected; controller=slot;
        down=(sample.buttons[slot] & XINPUT_GAMEPAD_Y)!=0;
        constexpr WORD cancel=XINPUT_GAMEPAD_A|XINPUT_GAMEPAD_B|XINPUT_GAMEPAD_X
            |XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK|XINPUT_GAMEPAD_RIGHT_SHOULDER;
        interrupted=(sample.buttons[slot] & cancel)!=0
            || sample.left_trigger[slot]>30 || sample.right_trigger[slot]>30;
    }
    return connected==1;
}

static bool native_binding_context(DispatchCommand& command) {
    // Revalidate the publisher and concrete player's current resource identity.
    // Match heartbeat, generation, stance, epoch and all action banks before substitution.
    // Both immediate heavy replacement and delayed hold share this lifecycle boundary.
    if (!dispatch || !InterlockedCompareExchange(&dispatch->control.enabled,0,0)) return false;
    if (!snapshot_command(command)) return false;
    // A publisher can advance during controller sampling; compare its committed
    // heartbeat with time read afterward, never the earlier input-poll timestamp.
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    const int64_t frequency=dispatch->control.qpc_frequency;
    uint64_t banks[3]{};
    return frequency>0 && command.heartbeat_qpc<=now.QuadPart
        && now.QuadPart-command.heartbeat_qpc<=frequency/10
        && command.generation==uint64_t(dispatch->control.generation)
        && player_context_status(command)==Accepted && command.player==boss_session.player
        && copy_bytes(command.player+0x70,banks,sizeof(banks)) && !memcmp(banks,command.banks,sizeof(banks));
}

static bool replacement_context(DispatchCommand& command, const MoveAdapter& adapter) {
    // Apply the shared lifecycle check before matching a stance-specific binding.
    // Native high=1, mid=0, low=2; CF6/CF7 payload4 retains the opener's stance.
    // Movement and lock-on never participate in this stance comparison.
    uint32_t stance=0; uint64_t payload=0; uint8_t expected=0xff;
    if (!native_binding_context(command) || !copy_field(adapter.player_descriptor+0x20,payload)
        || !copy_field(payload+0x0B,expected)) return false;
    if (expected==4 && adapter.player_key>=0xCF5 && adapter.player_key<=0xCF7) expected=2;
    return expected<=2 && copy_field(command.player+0x470,stance) && stance==expected;
}

static DispatchReason choose_heavy(DispatchCommand& command) {
    // Finish only a tap/hold decision authorized by native low-heavy selection.
    // Resolve release or the configured deadline on a valid player frame, then consume once.
    // A lifecycle change or interruption discards the pending action rather than replaying it.
    // TODO: verify C79 holds while walking and buffering after the heartbeat fix;
    // the previous live build remained intermittent despite the redirect correction.
    if (!pending_heavy.active) return IneligibleRequest;
    LARGE_INTEGER now;
    unsigned controller=0; bool down=false, interrupted=false;
    uint64_t current=0; uint32_t key=0;
    if (!heavy_button(controller,down,interrupted) || controller!=pending_heavy.controller || interrupted || !triangle_input.pressed
        || !replacement_context(command,boss_adapters[pending_heavy.hold])
        || command.reserved[2]!=pending_heavy.epoch
        || !copy_field(command.player+0x58,current) || !copy_field(current,key)
        || ((current!=pending_heavy.origin || key!=pending_heavy.origin_key) && !repeat_current_allowed(current,key))) {
        pending_heavy.active=false; pending_heavy.spent=true;
        return ContextChanged;
    }
    QueryPerformanceCounter(&now);
    const int64_t decision=down ? triangle_input.sampled : triangle_input.released;
    const bool held=decision-pending_heavy.started>=dispatch->control.qpc_frequency*int64_t(boss_hold_milliseconds)/1000;
    if (down && !held)
        return IneligibleRequest;
    const unsigned slot=held ? pending_heavy.hold : pending_heavy.tap;
    pending_heavy.active=false; pending_heavy.spent=down;
    if (slot==UINT32_MAX) {
        command.desired_key=pending_heavy.native_key;
        return NativeHeavyTap; // Replay the exact native heavy or grapple selection.
    }
    const auto& move=boss_imports[slot];
    command.reserved[1]=slot; command.desired_key=move.key; command.expected_motion=move.motion;
    command.expected_descriptor=move.descriptor; command.expected_payload=move.payload; command.edge_qpc=now.QuadPart;
    const auto reason=validate_boss_source(command);
    if (reason==Accepted) InterlockedIncrement64(&dispatch->control.dispatch_count);
    return reason;
}

struct ReplacementScope {
    ReplacementCall previous;
    ReplacementScope(void* actor, DispatchCommand& command, DispatchReason& reason, DWORD error=GetLastError()) : previous(replacement_call) {
        // Restrict lookup adaptation to this player setter's call stack.
        // Save the prior scope so nested native setters cannot steal its trace state.
        // Background lookups and other actors must always receive native descriptors.
        replacement_call = {actor,&command,&reason};
        SetLastError(error); // MinGW's thread-local lookup may change the Windows error slot.
    }
    ~ReplacementScope() {
        // Restore the outer setter's lookup scope after native execution.
        // Assign the saved thread-local context on every return path.
        // A completed setter must not leave replacement permission on the game thread.
        const DWORD error=GetLastError();
        replacement_call = previous;
        SetLastError(error);
    }
};

template<class T> static bool grapple_field(uint64_t base, unsigned offset, T expected) {
    // Compare one native field at its recorded integer width.
    // Byte selectors and signed action words must not include neighboring payload bytes.
    // Pair ownership still uses complete pointer-width comparisons.
    T value{};
    return copy_field(base+offset,value) && value==expected;
}

static int grapple_resource_index(uint64_t table, int32_t key) {
    // Read the native key/index table in bounded chunks before a paired handoff.
    // Require one matching entry and unchanged table ownership across the scan.
    // Missing victim resources leave the original William grapple untouched.
    uint32_t count=0; uint64_t pairs=0; int index=-1;
    if (!copy_field(table+8,count) || !count || count>32768 || !copy_field(table+16,pairs)) return -1;
    for (uint32_t start=0;start<count;start+=128) {
        int32_t chunk[128][2]{};
        const unsigned rows=(count-start)<128 ? count-start : 128;
        if (!copy_bytes(pairs+uint64_t(start)*8,chunk,rows*8)) return -1;
        for (unsigned row=0;row<rows;++row) if (chunk[row][0]==key) {
            if (index!=-1 || chunk[row][1]<0 || chunk[row][1]>=32768) return -1;
            index=chunk[row][1];
        }
    }
    return grapple_field(table,8,count) && grapple_field(table,16,pairs) ? index : -1;
}

static bool grapple_victim_resources(uint64_t owner) {
    // Preflight the actual native partner's common reaction35030 motion and timing.
    // Bank2 selects motion slot2 and timing slot2; neither slot is borrowed or written.
    // Readable complete dependencies are required before changing the attacker's action.
    uint64_t motion=0,timing=0,bank=0,wrapper=0,clips=0,table=0,clip=0,data=0;
    const auto module=reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr));
    if (!copy_field(owner+0x38,motion) || !copy_field(owner+0x68,timing)
        || !copy_field(motion+0x18,bank) || !grapple_field(bank,0,module+0x13C8FA0)
        || !copy_field(bank+0x468,clips) || !copy_field(bank+0x480,table)) return false;
    const int motion_index=grapple_resource_index(table,35030);
    uint8_t clip_header[0x40];
    if (motion_index<0 || !copy_field(clips+uint64_t(motion_index)*8,clip)
        || !copy_bytes(clip,clip_header,sizeof(clip_header))) return false;
    if (!copy_field(timing+0x20,wrapper) || !copy_field(wrapper,data) || !copy_field(wrapper+8,table)) return false;
    const int timing_index=grapple_resource_index(table,35030);
    uint32_t count=0,offsets=0,relative=0,event_count=0,event_offset=0;
    if (timing_index<0 || !copy_field(data+0x14,count) || uint32_t(timing_index)>=count || count>32768
        || !copy_field(data+0x20,offsets) || !offsets || offsets>0x100000
        || !copy_field(data+offsets+uint64_t(timing_index)*4,relative) || !relative || relative>0x1000000
        || !copy_field(data+relative+4,event_count) || !event_count || event_count>512
        || !copy_field(data+relative+8,event_offset) || event_offset<16 || event_offset>0x100000) return false;
    uint8_t events[512*12];
    return copy_bytes(data+relative+event_offset,events,event_count*12)
        && grapple_field(owner,0x38,motion) && grapple_field(owner,0x68,timing)
        && grapple_field(motion,0x18,bank) && grapple_field(timing,0x20,wrapper);
}

static uint64_t replace_native_grapple(void* context, uint64_t descriptor) {
    // Replace sword301 only after native D4A condition22 has accepted its paired target.
    // Preserve native entry and vulnerability checks before the setter establishes its victim link.
    // The victim updater reads the new attacker key361 and selects its own reaction362.
    // TODO: replace the opening D4A stab with Okatsu's hop while retaining native
    // empty-Ki target selection and successful-contact ownership; the finisher is confirmed.
    if (!boss_native_grapple || boss_active) return 0;
    const uint64_t player=boss_session.player;
    uint32_t index=0; const uint64_t entry=original_lookup(context,0xD4A,&index);
    uint64_t payload=0,table=0,row=0,chosen=0,flags=0,partner=0,component=0,victim=0,mode=0,previous_partner=0;
    uint16_t start=0,count=0;
    if (index!=0 || !entry || !grapple_field(player,0x58,entry) || !grapple_field(entry,0,uint32_t(0xD4A))
        || !copy_field(entry+0x20,payload) || !grapple_field(payload,0x20,int32_t(5050))
        || !grapple_field(payload,0x18,uint64_t(0x194C0000))
        || !copy_field(entry+0x78,table) || !copy_field(entry+0x80,start)
        || !copy_field(entry+0x82,count) || count!=37
        || !copy_field(table+(uint64_t(start)+8)*8,row) || !copy_field(player+0x90,chosen) || chosen!=row
        || !grapple_field(row,0,uint16_t(22)) || !grapple_field(row,0x0B,uint8_t(0xff))
        || !grapple_field(row,0x14,int16_t(0x301))) return 0;
    if (!copy_field(descriptor+0x20,payload) || !grapple_field(descriptor,0,uint32_t(0x301))
        || !grapple_field(payload,0x20,int32_t(5051)) || !grapple_field(payload,0x18,uint64_t(0x80780C0000ULL))
        || !copy_field(player+0x40,flags) || !(flags&(1ULL<<22))
        || !copy_field(player+0x5B0,partner) || partner==boss_session.player_owner) return 0;
    if (!copy_field(partner+0xE90,mode) || !grapple_field(mode,0x0C,uint32_t(0))
        || !copy_field(partner+0x230,component) || !copy_field(component+8,victim) || victim==player
        || !grapple_field(victim,0,boss_session.vtable) || !grapple_field(victim,0x50,partner)
        || !copy_field(victim+0x5B0,previous_partner)
        || (previous_partner && previous_partner!=boss_session.player_owner)) return 0;
    // Native7104DD establishes victim+5B0 and its pending flags after this lookup.
    // Requiring that future state here would silently reject a valid first grapple.
    const uint64_t victim_descriptor=original_lookup(reinterpret_cast<void*>(victim+0x70),0x362,&index);
    if (index!=2 || !victim_descriptor || !grapple_field(victim_descriptor,0,uint32_t(0x362))
        || !grapple_field(victim_descriptor,0x40,uint8_t(1)) || !copy_field(victim_descriptor+0x20,payload)
        || !grapple_field(payload,0x0C,int16_t(0x362)) || !grapple_field(payload,0x18,uint64_t(0x8038000000ULL))
        || !grapple_field(payload,0x20,int32_t(35030)) || !grapple_field(payload,0x34,int32_t(-1))
        || !grapple_victim_resources(partner) || !boss_camera_available()) return 0;
    DispatchCommand command{}; LARGE_INTEGER now; QueryPerformanceCounter(&now);
    const int64_t frequency=dispatch->control.qpc_frequency;
    uint64_t banks[3]{};
    if (!snapshot_command(command) || frequency<=0 || command.heartbeat_qpc>now.QuadPart
        || now.QuadPart-command.heartbeat_qpc>frequency/10
        || command.generation!=uint64_t(dispatch->control.generation)
        || player_context_status(command)!=Accepted || command.player!=player
        || !copy_bytes(player+0x70,banks,sizeof(banks)) || memcmp(banks,command.banks,sizeof(banks))) return 0;
    for (unsigned slot=0;slot<boss_import_count;++slot) {
        const auto& move=boss_imports[slot];
        if (move.key!=0x361 || move.motion!=1311 || move.flags!=0x8078000000ULL || boss_adapters[slot].kind) continue;
        command.reserved[1]=slot; command.desired_key=move.key; command.expected_motion=move.motion;
        command.expected_descriptor=move.descriptor; command.expected_payload=move.payload;
        uint32_t forwarded=0x301; void* unused_context=nullptr; uint64_t private_banks[3]{};
        auto reason=Accepted;
        boss_native_grapple_entry=true;
        const bool prepared=boss_prepare_call(replacement_call.actor,0x301,reason,command,forwarded,unused_context,private_banks);
        boss_native_grapple_entry=false;
        if (!prepared || reason!=Accepted) return 0;
        *replacement_call.command=command; *replacement_call.reason=Accepted;
        InterlockedIncrement64(&dispatch->control.dispatch_count);
        return boss_private_descriptor_address(slot);
    }
    return 0;
}

static uint64_t defer_heavy(uint64_t player, uint32_t key, unsigned tap, unsigned hold, const DispatchCommand& command) {
    // Preserve the native-selected tap while deciding the physical Triangle hold.
    // An empty redirect rejects commitment without resetting the current movement clock.
    // Repeated lookups share the original press and never restart its deadline.
    unsigned controller=0; bool down=false, interrupted=false;
    uint64_t current=0; uint32_t current_key=0;
    if (!heavy_button(controller,down,interrupted) || !down || interrupted || !triangle_input.pressed
        || !copy_field(player+0x58,current) || !copy_field(current,current_key)) return 0;
    if (!pending_heavy.active && !pending_heavy.spent)
        pending_heavy={triangle_input.pressed,current,current_key,uint32_t(command.reserved[2]),tap,controller,hold,key,true,false};
    static const int32_t payload[0xB0/4]={0,0,0,0,0,0,0,0,-1};
    static const struct { uint8_t prefix[0x20]; const void* payload; uint8_t tail[0xA8]; }
        deferred={{},payload,{}};
    return reinterpret_cast<uint64_t>(&deferred);
}

#include "sword_bindings.h"

static uint64_t observed_lookup(void* context, uint32_t key, uint32_t* bank_index) {
    // Replace only the concrete low-heavy action selected by native input resolution.
    // Match William's exact descriptor after stance/running rules, then share the import adapter.
    // No stick threshold, lock-on filter or synthetic button press participates in selection.
    const uint64_t descriptor = original_lookup(context,key,bank_index);
    const DWORD native_error = GetLastError();
    const uint64_t player = reinterpret_cast<uint64_t>(replacement_call.actor);
    if (!descriptor || !bank_index || !replacement_call.reason || !dispatch
        || player != boss_session.player || reinterpret_cast<uint64_t>(context) != player+0x70
        || !InterlockedCompareExchange(&dispatch->control.enabled,0,0)) {
        SetLastError(native_error);
        return descriptor;
    }
    if (*bank_index==0 && boss_native_bindings) {
        DispatchCommand command{};
        if ((boss_native_bindings&4) && key>=0xCB3 && key<=0xCB5 && native_binding_context(command)) {
            const uint64_t adapted=mid_light_ender(context,key,descriptor);
            SetLastError(native_error); return adapted ? adapted : descriptor;
        }
        if ((boss_native_bindings&2) && key==0xFAA && native_binding_context(command)) {
            uint64_t payload=0;
            if (grapple_field(descriptor,0,key) && grapple_field(descriptor,0x40,uint8_t(1))
                && grapple_field(descriptor,0x82,uint16_t(21)) && copy_field(descriptor+0x20,payload)
                && grapple_field(payload,0x18,uint64_t(0x40017C00000ULL)) && grapple_field(payload,0x20,int32_t(5090))) {
                const auto& move=boss_imports[0];
                command.reserved[1]=0; command.desired_key=move.key; command.expected_motion=move.motion;
                command.expected_descriptor=move.descriptor; command.expected_payload=move.payload;
                uint32_t forwarded=key; void* unused=nullptr; uint64_t banks[3]{}; auto reason=Accepted;
                if (boss_prepare_call(replacement_call.actor,key,reason,command,forwarded,unused,banks) && reason==Accepted) {
                    *replacement_call.command=command; *replacement_call.reason=Accepted; *bank_index=1;
                    InterlockedIncrement64(&dispatch->control.dispatch_count);
                    SetLastError(native_error); return boss_private_descriptor_address(0);
                }
            }
        }
    }
    if (key==0x301 && *bank_index==0) {
        const uint64_t paired=replace_native_grapple(context,descriptor);
        if (paired) { *bank_index=1; SetLastError(native_error); return paired; }
    }
    // Empty-Ki Triangle resolves to D4A instead of CF5. Delay its verified native
    // entry before contact; a tap keeps its target checks and paired ownership.
    if (key==0xD4A && *bank_index==0 && boss_hold_variant && (boss_hold_stances&1)) {
        uint64_t payload=0;
        if (grapple_field(descriptor,0,key) && grapple_field(descriptor,0x40,uint8_t(1))
            && grapple_field(descriptor,0x82,uint16_t(37)) && copy_field(descriptor+0x20,payload)
            && grapple_field(payload,0x18,uint64_t(0x194C0000)) && grapple_field(payload,0x20,int32_t(5050)))
            for (unsigned hold=0;hold<boss_import_count;++hold) {
                const auto& adapter=boss_adapters[hold]; DispatchCommand command{};
                if (adapter.kind!=2 || adapter.player_key!=0xCF5 || !replacement_context(command,adapter)) continue;
                if (const uint64_t deferred=defer_heavy(player,key,UINT32_MAX,hold,command)) {
                    SetLastError(native_error); return deferred;
                }
            }
    }
    for (unsigned slot=0; slot<boss_import_count; ++slot) {
        const auto& adapter = boss_adapters[slot];
        if ((adapter.kind!=1 && adapter.kind!=2) || key != adapter.player_key || descriptor != adapter.player_descriptor) continue;
        DispatchCommand command{};
        // A fresh publisher is still required for lifecycle identity and Stop.
        // Native low-heavy requests remain independent of optional chord intent.
        if (!replacement_context(command,adapter)) break;
        unsigned hold=boss_import_count;
        if (boss_hold_variant) for (unsigned i=0;i<boss_import_count;++i)
            if (boss_adapters[i].kind==2 && boss_adapters[i].player_key==key
                && (boss_hold_stances&(key==0xCF5 ? 1 : key==0xCB7 ? 2 : 4))) hold=i;
        if (hold<boss_import_count) {
            if (const uint64_t deferred=defer_heavy(player,key,adapter.kind==1 ? slot : UINT32_MAX,hold,command)) {
                SetLastError(native_error);
                return deferred;
            }
        }
        if (adapter.kind==2) break;
        const auto& move = boss_imports[slot];
        command.reserved[1]=slot; command.desired_key=move.key; command.expected_motion=move.motion;
        command.expected_descriptor=move.descriptor; command.expected_payload=move.payload;
        auto reason=validate_boss_source(command);
        if (reason != Accepted) break;
        uint32_t forwarded=key; void* unused_context=nullptr; uint64_t private_banks[3]{};
        if (!boss_prepare_call(replacement_call.actor,key,reason,command,forwarded,unused_context,private_banks)
            || reason != Accepted) break;
        *replacement_call.command=command;
        *replacement_call.reason=Accepted;
        *bank_index=1; // Private imports use motion/timing slot zero, as the existing adapter does.
        InterlockedIncrement64(&dispatch->control.dispatch_count);
        SetLastError(native_error);
        return boss_private_descriptor_address(slot);
    }
    SetLastError(native_error);
    return descriptor;
}

static bool replacements_configured() {
    // Decide whether this session needs the native action-lookup hook.
    // Search its small immutable adapter table for an enabled replacement.
    // Baseline Okatsu sessions keep their established three-hook path.
    if (boss_native_bindings || boss_native_grapple) return true;
    for (unsigned i=0; i<boss_import_count; ++i) if (boss_adapters[i].kind==1 || boss_adapters[i].kind==2) return true;
    return false;
}
