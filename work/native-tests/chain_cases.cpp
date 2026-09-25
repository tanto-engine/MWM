// Owned memory only. Source rows are copied from the saved Okatsu research and successful-grab evidence.
#define main frame_cases_main
#include "frame_dispatch_cases.cpp"
#undef main

struct RecordedImport { MoveImport spec; const char* payload; const char* rows[28]; };
static const RecordedImport recorded_imports[] = {
    {{0,0,0,0,0x184C0000,0xC64,1220,65,28,-1,0,0,1,{{30,11,0x0E077D36}}},
     "02000100000100000000ff01640cffff0109010004000f0000004c1800000000c40400004100ffffffff000001000200ffffff00ffffffff000000000000ffff15001e00190030000a000c000a001f001e002d0028000f0011273c00140030003f00060014274100ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffffffffffffffffffffffffffffffff", {
         "ffffffffffffffffffff01ffffffff00000000000000000800806464040000000080ff7fffffffffffffffffffffffff",
         "ffffffffffffffffffff020c01ffff0000000000650c0608008064640000000000804500ffffffffffffffffffffffff",
         "ffffffffffffffffffff000c01ffff0000000000650c0608008064640000000046004b00ffffffffffffffffffffffff",
         "ffffffffffffffffffff020001ffff00000000005c0c0608008064640000000000804500ffffffffffffffffffffffff",
         "ffffffffffffffffffff000001ffff00000000005c0c0608008064640000000046004b00ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01000100000000006d0c0008008064640000000000804100ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01000100000000006d0c0008008064640000000042004f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01010100000000006e0c0008008064640000000000804100ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01010100000000006e0c0008008064640000000042004f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01ffff00000000006f0c0008008064640000000000804100ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01ffff00000000006f0c0008008064640000000042004f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff001b0100010000000000700c0008008064640000000000804100ffffffffffffffffffffffff",
         "ffffffffffffffffffff001b0100010000000000700c0008008064640000000042004f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff001b0101010000000000710c0008008064640000000000804100ffffffffffffffffffffffff",
         "ffffffffffffffffffff001b0101010000000000710c0008008064640000000042004f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff001b01ffff0000000000720c0008008064640000000000804100ffffffffffffffffffffffff",
         "ffffffffffffffffffff001b01ffff0000000000720c0008008064640000000042004f00ffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff001f04020100000000001e00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002104020100000000002000000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002204020100000000002100000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff000201ffff00000000001f00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c004700ffffffffffff000500ffff00000000001900000800806464000000000080ff7fffffffffffffffffffffffff",
     }},
    {{0,0,0,0,0x184C0000,0xC66,1230,90,22,-1,0,0,1,{{46,16,0xF519B456}}},
     "02000000000100000000ff01660cffff0109010004000f0000004c1800000000ce0400005a00ffffffff000001000200ffffff00ffffffff000000000000ffff150030001e000a0000003200ffff0000ffff11275a00ffff220032000f001f004200050014275a00ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffffffffffffffffffffffffffffffff", {
         "ffffffffffffffffffff00ffffffff00000000000000000800806464000000005f00ff7fffffffffffffffffffffffff",
         "ffffffffffffffffffff020001ffff00000000005b0c0608008064640000000000805900ffffffffffffffffffffffff",
         "ffffffffffffffffffff000001ffff00000000005b0c060800806464000000005a005f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff020d0100010000000000660c0010008064640000000000805900ffffffffffffffffffffffff",
         "ffffffffffffffffffff000d0100010000000000660c001000806464000000005a005f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff020d0101010000000000670c0010008064640000000000805900ffffffffffffffffffffffff",
         "ffffffffffffffffffff000d0101010000000000670c001000806464000000005a005f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff020d01ffff0000000000680c0010008064640000000000805900ffffffffffffffffffffffff",
         "ffffffffffffffffffff000d01ffff0000000000680c001000806464000000005a005f00ffffffffffffffffffffffff",
         "ffffffffffffffffffff021a01ffff00000000006a0c0608008064640000000000805400ffffffffffffffffffffffff",
         "ffffffffffffffffffff001a01ffff00000000006a0c0608008064640000000055005a00ffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff001f04020100000000001e00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002104020100000000002000000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002204020100000000002100000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff000201ffff00000000001f00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c004700ffffffffffff000500ffff00000000001900000800806464000000000080ff7fffffffffffffffffffffffff",
     }},
    {{0,0,0,0,0x184C0000,0xC61,1210,52,14,3,30,45,1,{{22,12,0x297D2215}}},
     "02000000000100000000ff01610cffff0109010004000f0000004c1800000000ba0400003400ffffffff090001000200ffffff00ffffffff000000000000ffffffff00001e00ffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffffffffffffffffffffffffffffffff", {
         "ffffffffffffffffffff01ffffffff00000000000000000800806464040000000080ff7fffffffffffffffffffffffff",
         "ffffffffffffffffffff020301ffff0000000000620c0608008064640000000000801d00ffffffffffffffffffffffff",
         "ffffffffffffffffffff000301ffff0000000000620c060800806464000000001e002d00ffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff001f04020100000000001e00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002104020100000000002000000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002204020100000000002100000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff000201ffff00000000001f00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c004700ffffffffffff000500ffff00000000001900000800806464000000000080ff7fffffffffffffffffffffffff",
     }},
    {{0,0,0,0,0x184C0000,0xC62,1211,37,14,4,25,40,1,{{10,11,0x2AA47198}}},
     "02000000000100000000ff01620cffff0109010004000f0000004c1800000000bb0400002500ffffffff090001000200ffffff00ffffffff000000000000ffffffff00001e00ffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffffffffffffffffffffffffffffffff", {
         "ffffffffffffffffffff01ffffffff00000000000000000800806464040000000080ff7fffffffffffffffffffffffff",
         "ffffffffffffffffffff020301ffff0000000000630c0608008064640000000000801800ffffffffffffffffffffffff",
         "ffffffffffffffffffff000301ffff0000000000630c0608008064640000000019002800ffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff001f04020100000000001e00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002104020100000000002000000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002204020100000000002100000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff000201ffff00000000001f00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c004700ffffffffffff000500ffff00000000001900000800806464000000000080ff7fffffffffffffffffffffffff",
     }},
    {{0,0,0,0,0x184C0000,0xC63,1212,67,16,5,75,99,1,{{22,12,0xF519B456}}},
     "02000000000100000000ff01630cffff0109010004000f0000004c1800000000bc0400004300ffffffff090001000200ffffff00ffffffff000000000000ffffffff00004600ffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffffffffffffffffffffffffffffffff", {
         "ffffffffffffffffffff01ffffffff00000000000000000800806464040000000080ff7fffffffffffffffffffffffff",
         "ffffffffffffffffffff020001ffff00000000005b0c0608008064640000000000803100ffffffffffffffffffffffff",
         "ffffffffffffffffffff000001ffff00000000005b0c0608008064640000000032003c00ffffffffffffffffffffffff",
         "ffffffffffffffffffff020e01ffff0000000000690c0008008064640000000000804a00ffffffffffffffffffffffff",
         "ffffffffffffffffffff000e01ffff0000000000690c000800806464000000004b006300ffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff001f04020100000000001e00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002104020100000000002000000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002204020100000000002100000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff000201ffff00000000001f00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c004700ffffffffffff000500ffff00000000001900000800806464000000000080ff7fffffffffffffffffffffffff",
     }},
    {{0,0,0,0,0x594C0000,0xC69,1310,-1,13,6,0,0,1,{{0,5,0x6626BF7F}}},
     "02000100000300000000ff04690cffff0109010004000f0000004c59000000001e050000ffffffffffff000001000200ffffff00ffffffff000000000000ffffffff0000ffff11270000ffffffff0a00ffff11272f00ffffffff4100ffff11274c00ffff14270000ffff2d0000001e00070000000700ffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffff0000ffffffffffffffffffffffffffffffffffff", {
         "ffffffffffffffffffff01ffffffff00000000000000000800806464040000000080ff7fffffffffffffffffffffffff",
         "1600ffffffffffffffff00ffffffff00000000006103000800806464000000000080ff7fffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff001f04020100000000001e00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002104020100000000002000000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff002204020100000000002100000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c00ffffffffffffffff000201ffff00000000001f00000800806464000000000080ff7fffffffffffffffffffffffff",
         "5c004700ffffffffffff000500ffff00000000001900000800806464000000000080ff7fffffffffffffffffffffffff",
     }},
    {{0,0,0,0,0x8078000000,0x361,1311,-1,7,-1,0,0,2,{{58,15,0x0E077D36},{132,16,0xDD00D2D7}}},
     "02000300000000000000ff046103ffffffff00000000000000000078800000001f050000ffffffff1027000001000200ffffff00ffffffff", {
         "ffffffffffffffffffff01ffffffff00000000000000000800806464040000000080ff7fffffffffffffffffffffffff",
         "0100ffffffffffffffff00ffffffff00000000001100000800806464000000000080ff7fffffffffffffffffffffffff",
         "3400ffffffffffffffff00ffffffff0000000000c80c0000ff806464400020000080ff7fffffffffffffffffffffffff",
         "e600ffffffffffffffff00ffffffff0000000000af0c0a00ff806464000020000080ff7fffffffffffffffffffffffff",
         "9b011800ffffffffffff002601ffff0000000000a906000200806464000000000080ff7fffffffffffffffffffffffff",
         "01001800ffffffffffff00ffffffff00000000001100000800800000010020000080ff7fffffffffffffffffffffffff",
         "4100ffffffffffffffff00ffffffff0000000000c90c0000ff806464000020000080ff7fffffffffffffffffffffffff",
     }},
};

static std::array<std::array<uint8_t,0xD0>,7> chain_descriptors{};
static std::array<std::array<uint8_t,0xB0>,7> chain_payloads{};
static std::array<std::array<std::array<uint8_t,0x30>,28>,7> chain_rows{};
static std::array<std::array<uint64_t,28>,7> chain_row_pointers{};
static std::array<uint64_t,7> chain_entries{};
alignas(8) static std::array<uint8_t,0x100> camera{}, source_camera{}, replacement_owner{};
alignas(8) static std::array<uint8_t,0x800> other_actor{};
alignas(8) static std::array<uint8_t,0xD0> colliding_descriptor{};
enum SetterResult { SelectRequested, KeepCurrent, SelectNeutral, SelectRequestedFalse };
static SetterResult setter_result;
static void* last_actor;
static void* last_context;
static uint32_t last_key;
static DWORD setter_error;
static bool native_selects_camera_zero;

static DWORD WINAPI chain_input(DWORD, XINPUT_STATE*) {
    // Make input sampling alter LastError inside a controlled frame.
    // Return an unavailable controller result from the harness callback.
    // Chain dispatch must restore the native frame error before invoking its setter.
    SetLastError(ERROR_DEVICE_NOT_CONNECTED);
    return ERROR_DEVICE_NOT_CONNECTED;
}

static void hex_bytes(const char* hex, uint8_t* bytes, size_t capacity) {
    // Load recorded payload and transition bytes into fixed owned buffers.
    // Check hexadecimal length and decode each byte within the supplied capacity.
    // The chain fixture must preserve source evidence without retaining session pointers.
    assert(strlen(hex)%2==0 && strlen(hex)/2<=capacity);
    for (size_t i=0; hex[i]; i+=2) {
        unsigned value=0; assert(sscanf(hex+i,"%2x",&value)==1);
        bytes[i/2]=uint8_t(value);
    }
}

static bool chain_action(void* actor, uint32_t key, void* context) {
    // Model native private-bank selection and configurable setter refusal.
    // Resolve the single supplied descriptor and update only the owned actor state.
    // Tests must distinguish requested imports from native collisions and partial transitions.
    ++action_calls; last_actor=actor; last_key=key; last_context=context; setter_error=GetLastError();
    uint64_t descriptor=address(neutral.data());
    if (context) {
        assert(actor==player.data());
        auto* banks=static_cast<uint64_t*>(context);
        assert(!banks[0] && !banks[2]);
        unsigned slot=0;
        while (slot<boss_import_count && banks[1]!=address(&boss_private_actions[slot].bank)) ++slot;
        assert(slot<boss_import_count && key==boss_imports[slot].key);
        const auto& clone=boss_private_actions[slot];
        assert(clone.ready && clone.bank.count==1 && clone.entry==address(clone.descriptor));
        assert(clone.bank.entries==address(&clone.entry));
        descriptor=clone.entry;
        bindings(true);
        assert(boss_camera_active==(slot==6));
    } else if (key==0x361) descriptor=address(colliding_descriptor.data());
    const SetterResult outcome=setter_result;
    setter_result=SelectRequested;
    if (outcome!=KeepCurrent) {
        if (context && native_selects_camera_zero) put(camera.data(),0x20,uint32_t(0));
        put(actor,0x58,outcome==SelectNeutral ? address(neutral.data()) : descriptor);
        put(actor,0x28,0.0f);
    }
    SetLastError(ACTION_ERROR);
    return outcome==SelectRequested;
}

static void chain_reset() {
    // Build all seven imports and camera components in owned memory.
    // Combine recorded source rows with fresh pointers and clear every private clone.
    // Chain and camera failure cases must not inherit state from previous attempts.
    reset();
    for (auto& item : boss_private_actions) item={};
    for (auto& item : boss_imports) item={};
    boss_active_slot=0; boss_chain_sequence=0; boss_chain_epoch=0;
    boss_chain_cancelled=false; boss_camera_active=false; boss_native_grapple=0;
    chain_descriptors={}; chain_payloads={}; chain_rows={}; chain_row_pointers={};
    camera.fill(0); source_camera.fill(0); replacement_owner.fill(0); other_actor.fill(0);
    colliding_descriptor.fill(0); put(colliding_descriptor.data(),0,uint32_t(0x361));
    put(colliding_descriptor.data(),0x20,address(neutral_payload.data()));
    boss_import_count=7; boss_string_variant=2;
    for (unsigned i=0;i<boss_import_count;++i) {
        auto& spec=boss_imports[i]; spec=recorded_imports[i].spec;
        auto& descriptor=chain_descriptors[i]; auto& bytes=chain_payloads[i];
        hex_bytes(recorded_imports[i].payload,bytes.data(),bytes.size());
        spec.descriptor=address(descriptor.data()); spec.payload=address(bytes.data());
        spec.clip=0x40000+i*0x100; spec.timing_record=0x50000+i*0x100;
        put(descriptor.data(),0,spec.key); descriptor[0x40]=1;
        put(descriptor.data(),0x20,spec.payload);
        put(descriptor.data(),0x78,address(chain_row_pointers[i].data()));
        put(descriptor.data(),0x82,spec.transition_count);
        chain_entries[i]=spec.descriptor;
        for (unsigned row=0;row<spec.transition_count;++row) {
            hex_bytes(recorded_imports[i].rows[row],chain_rows[i][row].data(),0x30);
            chain_row_pointers[i][row]=address(chain_rows[i][row].data());
        }
    }
    boss_session.source_descriptor=boss_imports[0].descriptor;
    boss_session.source_payload=boss_imports[0].payload;
    boss_session.charge_descriptor=boss_imports[1].descriptor;
    boss_session.charge_payload=boss_imports[1].payload;
    put(bank.data(),0x128,address(chain_entries.data())); put(bank.data(),0x130,uint32_t(7));
    boss_session.source_camera_bank=address(source_camera.data());
    boss_session.player_camera_slot=address(camera.data()+8);
    boss_session.camera_original=0x99887700;
    put(source_camera.data(),0,address(GetModuleHandleW(nullptr))+0x13C8FA0);
    put(owner.data(),0x48,address(camera.data()));
    put(camera.data(),8,boss_session.camera_original);
    put(camera.data(),16,uint64_t(0x88776600)); put(camera.data(),24,uint64_t(0x77665500));
    command.reserved[1]=2; command.desired_key=boss_imports[2].key;
    command.expected_descriptor=boss_imports[2].descriptor;
    command.expected_payload=boss_imports[2].payload; command.expected_motion=boss_imports[2].motion;
    publish(); original_action=chain_action; setter_result=SelectRequested;
    game_input_state=nullptr; input_rescan=0;
    last_actor=last_context=nullptr; last_key=0; setter_error=0;
    native_selects_camera_zero=false;
}

static void chain_tick(float frame) {
    // Place the owned actor at a chosen source animation frame.
    // Refresh the held intent and invoke the real frame wrapper.
    // Boundary tests need exact frame windows without depending on wall-clock playback.
    put(player.data(),0x28,frame); publish(command.chord_sequence); tick();
}

static void reach(unsigned slot) {
    // Advance a valid held string to a requested pre-finisher slot.
    // Enter the first action and step each configured source window in order.
    // Later failure checks must begin from a proven sequence of accepted native transitions.
    tick(); assert(boss_active && boss_active_slot==2 && action_calls==1); ++checks;
    for (unsigned previous=2;previous<slot;++previous) {
        chain_tick(float(boss_imports[previous].next_start));
        assert(boss_active_slot==previous+1); ++checks;
    }
}

static void native_request(uint32_t key, void* actor=player.data()) {
    // Issue one ordinary native action request in the owned chain fixture.
    // Preserve the expected setter return, LastError and callback-scope accounting.
    // Only this native route may model successful-contact entry into the paired action.
    SetLastError(INCOMING); assert(observed_action(actor,key,nullptr));
    assert(GetLastError()==ACTION_ERROR && boss_inflight==0); ++checks;
}

static void rejected_pair() {
    // Verify a failed paired adapter cannot forward William's raw action361.
    // Check no setter call occurs and C69 retains its original camera ownership.
    // Rejecting an import must not trigger an unrelated native move with the same key.
    const unsigned before=action_calls;
    SetLastError(INCOMING);
    assert(!observed_action(player.data(),0x361,nullptr));
    assert(GetLastError()==INCOMING && action_calls==before);
    assert(boss_active_slot==5 && boss_active && !boss_camera_active);
    assert(same_field(boss_session.player_camera_slot,0,boss_session.camera_original));
    bindings(true); ++checks;
}

static void expect_idle() {
    // Verify complete imported-playback recovery in the owned fixture.
    // Require idle adapter state, cancelled continuation and restored resource slots.
    // A completed native transition must not leave camera or motion ownership borrowed.
    assert(!boss_active && !boss_camera_active && boss_chain_cancelled);
    assert(same_field(boss_session.player_camera_slot,0,boss_session.camera_original));
    bindings(false); ++checks;
}

static std::array<uint8_t,0xD0> sword_pair{}, victim_reaction{};
static std::array<uint8_t,0xB0> sword_pair_payload{}, victim_reaction_payload{};
static std::array<uint8_t,0xEA0> victim_owner{};
static std::array<uint8_t,0x40> pair_component{}, pair_mode{}, victim_motion{}, victim_timing{}, victim_clip{};
static std::array<uint8_t,0x490> victim_motion_bank{};
static std::array<uint8_t,0x100> victim_timing_data{};
static std::array<uint64_t,3> victim_hash{};
static uint64_t victim_clips[1]{}, victim_wrapper[2]{}, windup_rows[37]{};
static int32_t victim_hash_pair[2]{};
static uint8_t windup_contact[0x30]{};

static uint64_t grapple_lookup(void* context, uint32_t key, uint32_t* index) {
    // Reproduce the confirmed sword and actual partner's native action-bank resolution.
    // Return distinct301/362 records and the unmodified D4A windup descriptor.
    // Any unrelated actor, key or resource family remains outside the import adapter.
    SetLastError(ACTION_ERROR); *index=0;
    if (context==player.data()+0x70) {
        if (key==0xD4A) return address(neutral.data());
        if (key==0x301) return address(sword_pair.data());
    }
    if (context==other_actor.data()+0x70 && key==0x362) {
        *index=2; return address(victim_reaction.data());
    }
    return 0;
}

static bool grapple_action(void* actor, uint32_t key, void* context) {
    // Resolve the pair through the same scoped lookup used by the real action setter.
    // Commit only when the controlled native setter accepts, preserving LastError.
    // Native victim handoff is tested separately from authorizing the player replacement.
    assert(!context); ++action_calls; last_actor=actor; last_key=key;
    uint32_t index=0;
    const uint64_t selected=observed_lookup(static_cast<uint8_t*>(actor)+0x70,key,&index);
    if (setter_result==KeepCurrent) { SetLastError(ACTION_ERROR); return false; }
    assert(selected); put(actor,0x58,selected); put(actor,0x68,index);
    if (actor==player.data() && index==1) {
        put(camera.data(),0x20,uint32_t(0));
        // Native7104DD invokes713D90 only after committing the attacker descriptor.
        put(other_actor.data(),0x5B0,boss_session.player_owner);
        put(other_actor.data(),0x40,uint64_t(0x80020));
    }
    SetLastError(ACTION_ERROR); return true;
}

static void grapple_reset() {
    // Assemble native D4A condition22 and its selected human grapple target in owned memory.
    // Supply the actual362 key/motion/flags and complete common motion/timing lookups.
    // Each negative case removes one native prerequisite without touching live game memory.
    chain_reset(); boss_native_grapple=1;
    sword_pair.fill(0); victim_reaction.fill(0); sword_pair_payload.fill(0); victim_reaction_payload.fill(0);
    victim_owner.fill(0); pair_component.fill(0); pair_mode.fill(0); victim_motion.fill(0); victim_timing.fill(0);
    victim_motion_bank.fill(0); victim_timing_data.fill(0); victim_hash.fill(0);
    state(0xD4A,5050,4); put(neutral_payload.data(),0x18,uint64_t(0x194C0000));
    hex_bytes("1600ffffffffffffffff00ffffffff000000000001030000ff806464000000000080ff7fffffffffffffffffffffffff",windup_contact,sizeof(windup_contact));
    windup_rows[8]=address(windup_contact); put(neutral.data(),0x78,address(windup_rows));
    put(neutral.data(),0x80,uint16_t(0)); put(neutral.data(),0x82,uint16_t(37));
    put(player.data(),0x90,address(windup_contact)); put(player.data(),0x40,uint64_t(1ULL<<22));
    put(player.data(),0x5B0,address(victim_owner.data()));
    put(victim_owner.data(),0x230,address(pair_component.data())); put(pair_component.data(),8,address(other_actor.data()));
    put(victim_owner.data(),0xE90,address(pair_mode.data()));
    put(other_actor.data(),0,boss_session.vtable); put(other_actor.data(),0x50,address(victim_owner.data()));
    put(sword_pair.data(),0,uint32_t(0x301)); sword_pair[0x40]=1;
    put(sword_pair.data(),0x20,address(sword_pair_payload.data()));
    put(sword_pair_payload.data(),0x0C,int16_t(0x301)); put(sword_pair_payload.data(),0x20,int32_t(5051));
    put(sword_pair_payload.data(),0x18,uint64_t(0x80780C0000ULL));
    put(victim_reaction.data(),0,uint32_t(0x362)); victim_reaction[0x40]=1;
    put(victim_reaction.data(),0x20,address(victim_reaction_payload.data()));
    put(victim_reaction_payload.data(),0x0C,int16_t(0x362)); put(victim_reaction_payload.data(),0x20,int32_t(35030));
    put(victim_reaction_payload.data(),0x18,uint64_t(0x8038000000ULL)); put(victim_reaction_payload.data(),0x34,int32_t(-1));
    put(victim_owner.data(),0x38,address(victim_motion.data())); put(victim_owner.data(),0x68,address(victim_timing.data()));
    put(victim_motion.data(),0x18,address(victim_motion_bank.data()));
    put(victim_motion_bank.data(),0,address(GetModuleHandleW(nullptr))+0x13C8FA0);
    put(victim_motion_bank.data(),0x468,address(victim_clips)); put(victim_motion_bank.data(),0x480,address(victim_hash.data()));
    victim_clips[0]=address(victim_clip.data()); victim_hash[1]=1; victim_hash[2]=address(victim_hash_pair);
    victim_hash_pair[0]=35030; victim_hash_pair[1]=0;
    put(victim_timing.data(),0x20,address(victim_wrapper));
    victim_wrapper[0]=address(victim_timing_data.data()); victim_wrapper[1]=address(victim_hash.data());
    put(victim_timing_data.data(),0x14,uint32_t(1)); put(victim_timing_data.data(),0x20,uint32_t(0x24));
    put(victim_timing_data.data(),0x24,uint32_t(0x40)); put(victim_timing_data.data(),0x44,uint32_t(1));
    put(victim_timing_data.data(),0x48,uint32_t(0x24));
    command.armed=0; command.held=0; publish_player_context(.25f); publish();
    original_lookup=grapple_lookup; original_action=grapple_action;
}

static void grapple_cases() {
    // Cover the native-approved pair, collision route rejection and missing partner dependencies.
    // Follow the observed native victim algorithm: attacker payload key plus one, no victim writes.
    // Refusal or lifecycle changes must restore every borrowed player resource and camera slot.
    grapple_reset();
    assert(grapple_victim_resources(address(victim_owner.data())));
    assert(boss_camera_available());
    SetLastError(INCOMING); assert(observed_action(player.data(),0x301,nullptr));
    assert(boss_active && boss_active_slot==6 && boss_camera_active && !boss_native_grapple_entry);
    assert(same_field(boss_session.player,0x58,boss_private_descriptor_address(6))); bindings(true); ++checks;
    int16_t attacker_key=0; assert(copy_field(boss_private_payload_address(6)+0x0C,attacker_key));
    assert(attacker_key==0x361);
    SetLastError(INCOMING); assert(observed_action(other_actor.data(),uint32_t(attacker_key+1),nullptr));
    assert(last_key==0x362 && same_field(address(other_actor.data()),0x58,address(victim_reaction.data()))); ++checks;
    original_action=chain_action;
    SetLastError(INCOMING); assert(observed_action(player.data(),0,nullptr));
    assert(!boss_active && !boss_camera_active); bindings(false); ++checks;
    for (unsigned failure=0;failure<13;++failure) {
        grapple_reset();
        switch (failure) {
        case 0: boss_native_grapple=0; break;
        case 1: put(player.data(),0x90,uint64_t(0)); break; // Collision setter clears the transition row.
        case 2: put(windup_contact,0,uint16_t(0)); break;
        case 3: put(player.data(),0x40,uint64_t(0)); break;
        case 4: put(other_actor.data(),0x5B0,address(victim_owner.data())); break;
        case 5: put(pair_mode.data(),0x0C,uint32_t(1)); break;
        case 6: victim_reaction[0x40]=0; break;
        case 7: victim_hash_pair[0]=35031; break;
        case 8: victim_clips[0]=0; break;
        case 9: victim_wrapper[0]=0; break;
        case 10: put(camera.data(),8,uint64_t(0x88776655)); break;
        case 11: put(other_actor.data(),0x50,uint64_t(0)); break;
        case 12: setter_result=KeepCurrent; break;
        }
        SetLastError(INCOMING); const bool accepted=observed_action(player.data(),0x301,nullptr);
        assert(accepted==(failure!=12));
        assert(!boss_active && !boss_camera_active && !boss_native_grapple_entry); bindings(false);
        if (accepted) assert(same_field(address(player.data()),0x58,address(sword_pair.data())));
        ++checks;
    }
    grapple_reset(); put(other_actor.data(),0x58,address(neutral.data()));
    uint32_t index=0;
    DispatchCommand unrelated{}; auto reason=IneligibleRequest;
    { ReplacementScope scope(other_actor.data(),unrelated,reason);
      assert(observed_lookup(player.data()+0x70,0x301,&index)==address(sword_pair.data())); }
    assert(!boss_active && !boss_camera_active); ++checks;
    chain_reset();
}

int main() {
    // Exercise the configured string, natural grab outcome and camera ownership.
    // Use recorded rows with owned actors and failure-controlled native setters.
    // Offline ordering and lifetime checks do not claim live hit or camera-visual acceptance.
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); frequency=f.QuadPart;
    grapple_cases();

    // William's idle camera can select slot1/2. Imported private actions select
    // slot0, whose original value is null; the paired borrow must restore null.
    for (uint32_t idle_index : {1u,2u}) {
        chain_reset(); native_selects_camera_zero=true;
        boss_session.camera_original=0; put(camera.data(),8,uint64_t(0));
        put(camera.data(),0x20,idle_index);
        assert(boss_camera_available()); // A standalone launcher starts before native camera selection changes.
        reach(5); assert(!boss_camera_active && same_field(address(camera.data()),8,0)); ++checks;
        native_request(0x361);
        assert(boss_active_slot==6 && boss_camera_active);
        assert(same_field(address(camera.data()),8,boss_session.source_camera_bank)); ++checks;
        native_request(0); expect_idle();
        assert(same_field(address(camera.data()),16,0x88776600));
        assert(same_field(address(camera.data()),24,0x77665500)); ++checks;
    }

    // Every link accepts both boundary frames, rejects early/late clocks, and
    // cannot skip a link when the player's elapsed frame was large.
    for (unsigned slot=2;slot<=4;++slot) {
        for (bool end : {false,true}) {
            chain_reset(); reach(slot); const unsigned before=action_calls;
            chain_tick(float(boss_imports[slot].next_start)-0.01f);
            assert(action_calls==before && boss_active_slot==slot && !boss_chain_cancelled); ++checks;
            chain_tick(float(end ? boss_imports[slot].next_end : boss_imports[slot].next_start));
            assert(action_calls==before+1 && boss_active_slot==slot+1 && !boss_chain_cancelled);
            assert(same_field(boss_session.player,0x58,boss_private_descriptor_address(slot+1))); ++checks;
        }
        chain_reset(); reach(slot); const unsigned before=action_calls;
        chain_tick(float(boss_imports[slot].next_end)+0.01f);
        assert(action_calls==before && boss_active_slot==slot && boss_chain_cancelled); ++checks;
        chain_tick(float(boss_imports[slot].next_start));
        assert(action_calls==before); ++checks;
    }

    // Holding preserves one string intent. Release, another chord, stale data,
    // frozen frames and an epoch interruption cancel its remaining links.
    for (unsigned slot=2;slot<=4;++slot) for (unsigned failure=0;failure<7;++failure) {
        chain_reset(); reach(slot); const unsigned before=action_calls;
        put(player.data(),0x28,float(boss_imports[slot].next_start));
        if (failure==0) command.held=0;
        if (failure==1) ++command.chord_sequence;
        if (failure==2) command.heartbeat_qpc-=frequency;
        if (failure==3) ++command.reserved[2];
        if (failure==4) ++command.generation;
        if (failure==5) command.sequence_end=2;
        if (failure==6) frame_delta=0;
        memcpy(&dispatch->command,&command,sizeof(command)); tick();
        assert(action_calls==before && boss_active_slot==slot && boss_chain_cancelled); ++checks;
        command.held=1; command.generation=dispatch->control.generation; frame_delta=0.25f;
        publish(command.chord_sequence+1); tick();
        assert(action_calls==before && boss_active_slot==slot); ++checks;
    }
    chain_reset(); reach(2); put(player.data(),0x78,uint64_t(0x123456)); tick();
    const unsigned suspended_calls=action_calls;
    put(player.data(),0x78,uint64_t(0)); chain_tick(30);
    assert(action_calls==suspended_calls && boss_chain_cancelled && boss_active_slot==2); ++checks;

    // The native miss/idle transition is retained, with no timer-generated grab
    // success and no restart from the already-consumed held gesture.
    chain_reset(); reach(5); const unsigned attempt_calls=action_calls;
    for (float frame : {0.0f,20.0f,100.0f,1000.0f}) chain_tick(frame);
    assert(action_calls==attempt_calls && boss_active_slot==5 && !boss_camera_active); ++checks;
    native_request(0); expect_idle(); tick();
    assert(action_calls==attempt_calls+1); ++checks;

    // Another actor and a colliding William action cannot acquire the private
    // bank or camera; only a native361 request during this player's C69 can.
    chain_reset(); reach(5); native_request(0x361,other_actor.data());
    assert(last_actor==other_actor.data() && last_context==nullptr && last_key==0x361);
    assert(boss_active_slot==5 && !boss_camera_active); bindings(true); ++checks;
    chain_reset(); reach(2); native_request(0x361);
    assert(last_context==nullptr && last_key==0x361); expect_idle();
    for (unsigned slot : {5u,6u}) {
        chain_reset(); const auto& spec=boss_imports[slot];
        command.reserved[1]=slot; command.desired_key=spec.key; command.expected_motion=spec.motion;
        command.expected_descriptor=spec.descriptor; command.expected_payload=spec.payload;
        publish(); tick(); assert(!action_calls && !boss_active && !boss_camera_active); ++checks;
    }

    chain_reset(); reach(5); command.held=0; publish(); tick(); native_request(0x361);
    assert(boss_active_slot==6 && boss_camera_active && last_key==0x361 && last_context);
    assert(same_field(boss_session.player_camera_slot,0,boss_session.source_camera_bank)); ++checks;
    const unsigned pair_calls=action_calls;
    for (float frame : {0.0f,58.0f,132.0f,300.0f}) chain_tick(frame);
    assert(action_calls==pair_calls); ++checks;
    native_request(0); expect_idle();

    // Active-index changes do not revoke ownership of our recorded camera slot.
    // Restoring slot0 must leave the camera object's other slots untouched.
    chain_reset(); reach(5); native_request(0x361);
    assert(boss_active_slot==6 && boss_camera_active); ++checks;
    put(camera.data(),0x20,uint32_t(1));
    native_request(0);
    expect_idle(); assert(same_field(address(camera.data()),16,0x88776600)); ++checks;
    chain_reset(); reach(5); native_request(0x361);
    put(player.data(),0x58,address(neutral.data())); frame_delta=0; tick(); expect_idle();

    // No stale writes after an owner or camera-object replacement. An invalid
    // index still rejects borrowing; a valid idle slot need not equal reserved slot0.
    chain_reset(); reach(5); native_request(0x361);
    const auto camera_before=camera, motion_before=motion, timing_before=timing;
    put(player.data(),0x50,address(replacement_owner.data()));
    put(player.data(),0x58,address(neutral.data())); tick();
    assert(boss_active && boss_camera_active && camera==camera_before && motion==motion_before && timing==timing_before);
    assert(boss_retire_destroyed_actor() && !boss_active && !boss_camera_active);
    assert(camera==camera_before && motion==motion_before && timing==timing_before); ++checks;
    chain_reset(); reach(5); native_request(0x361);
    const auto borrowed_camera=camera;
    put(owner.data(),0x48,address(replacement_owner.data())); native_request(0);
    assert(boss_active && boss_camera_active && camera==borrowed_camera);
    assert(dispatch->control.status==-int(BossBindingMismatch)); ++checks;
    put(owner.data(),0x48,address(camera.data())); tick(); expect_idle();
    chain_reset(); reach(5); put(camera.data(),0x20,uint32_t(3)); rejected_pair();
    chain_reset(); reach(5); native_request(0x361);
    put(camera.data(),8,uint64_t(0x12345678)); put(player.data(),0x58,boss_private_descriptor_address(2));
    boss_finish_call(player.data());
    assert(boss_active && boss_camera_active && boss_chain_cancelled);
    assert(dispatch->control.status==-int(BossBindingMismatch));
    assert(same_field(address(camera.data()),8,0x12345678)); ++checks;

    // All reachable descriptors are prepared before the first action. Changes
    // after preparation are rechecked and cannot fall through to raw key361.
    for (unsigned slot=2;slot<7;++slot) for (unsigned failure=0;failure<5;++failure) {
        chain_reset();
        if (failure==0) put(chain_payloads[slot].data(),0x18,uint64_t(0xBAD));
        if (failure==1) put(chain_descriptors[slot].data(),0,uint32_t(0xBAD));
        if (failure==2) put(chain_descriptors[slot].data(),0x20,uint64_t(0xBAD));
        if (failure==3) chain_descriptors[slot][0x40]=0;
        if (failure==4) put(chain_descriptors[slot].data(),0x82,uint16_t(29));
        tick(); assert(!action_calls && !boss_active && !boss_camera_active); bindings(false); ++checks;
    }
    for (unsigned failure=0;failure<4;++failure) {
        chain_reset(); reach(5);
        if (failure==0) put(chain_payloads[6].data(),0x18,uint64_t(0x184C0000));
        if (failure==1) chain_descriptors[6][0x40]=0;
        if (failure==2) put(chain_payloads[6].data(),0x20,int32_t(-1));
        if (failure==3) put(source_camera.data(),0,uint64_t(0xBAD));
        rejected_pair();
    }

    // Native setter refusal can retain the previous move, choose idle, or have
    // already selected the requested action. Reconcile actual state in all cases.
    chain_reset(); setter_result=KeepCurrent; tick(); expect_idle(); tick(); assert(action_calls==1); ++checks;
    chain_reset(); reach(2); setter_result=KeepCurrent; chain_tick(30);
    assert(boss_active_slot==2 && boss_chain_cancelled && !boss_camera_active); bindings(true); ++checks;
    const unsigned refused_calls=action_calls; chain_tick(30); assert(action_calls==refused_calls); ++checks;
    for (SetterResult outcome : {KeepCurrent,SelectNeutral,SelectRequestedFalse}) {
        chain_reset(); reach(5); setter_result=outcome;
        SetLastError(INCOMING); assert(!observed_action(player.data(),0x361,nullptr));
        assert(GetLastError()==ACTION_ERROR);
        if (outcome==KeepCurrent) {
            assert(boss_active_slot==5 && boss_active && !boss_camera_active && boss_chain_cancelled); bindings(true);
        } else if (outcome==SelectNeutral) expect_idle();
        else assert(boss_active_slot==6 && boss_active && boss_camera_active);
        ++checks;
    }

    // Imported rows keep native condition22/contact pairing. Only unconditional
    // controller combo requests are disabled, and simple moves gain pulse rows.
    chain_reset(); reach(2);
    assert(boss_prepare_private_action(0) && boss_prepare_private_action(1));
    for (unsigned slot=0;slot<5;++slot) for (uint8_t direction : {0x1f,0x21,0x22,0xff}) {
        int16_t selected=-1;
        for (unsigned row=0;row<boss_private_actions[slot].transition_count;++row) {
            const auto* body=boss_private_actions[slot].transition_bodies[row];
            uint16_t condition=0; memcpy(&condition,body,2);
            const bool dodge=body[0x0B]==2 && body[0x0C]==1;
            const bool directional=body[0x0B]==direction && body[0x0C]==4 && body[0x0D]==2 && body[0x0E]==1;
            if (condition!=0x5c || (!dodge && !directional)) continue;
            std::array<uint8_t,0x30> expected{}; memcpy(expected.data(),native_dodge_row,0x30);
            put(expected.data(),0x20,boss_imports[slot].recovery_frame);
            assert(!memcmp(body,expected.data(),0x30));
            memcpy(&selected,body+0x14,2); break;
        }
        assert(selected==0xD12); ++checks;
    }
    for (unsigned slot=2;slot<7;++slot) {
        const auto& clone=boss_private_actions[slot];
        assert(clone.ready && clone.transition_count==boss_imports[slot].transition_count+(slot<5 ? 4 : 0));
        for (unsigned row=0;row<boss_imports[slot].transition_count;++row) {
            auto expected=chain_rows[slot][row]; bool unconditional=true;
            for (unsigned c=0;c<10;++c) if (expected[c]!=0xff) unconditional=false;
            int16_t target=0; memcpy(&target,expected.data()+0x14,2);
            if (unconditional && target && expected[0x0b]!=0xff) put(expected.data(),0x14,int16_t(-1));
            const unsigned at=row+(slot<5 && row>=unsigned(boss_imports[slot].transition_count-5) ? 1 : 0);
            assert(!memcmp(expected.data(),clone.transition_bodies[at],0x30)); ++checks;
        }
        for (unsigned row=boss_imports[slot].transition_count+1;row<clone.transition_count;++row) {
            std::array<uint8_t,0x30> expected{};
            memcpy(expected.data(),boss_pulse_templates[row-boss_imports[slot].transition_count-1],0x30);
            put(expected.data(),0x20,boss_imports[slot].recovery_frame);
            assert(!memcmp(expected.data(),clone.transition_bodies[row],0x30)); ++checks;
        }
    }
    uint16_t condition=0; int16_t paired_key=0;
    memcpy(&condition,boss_private_actions[5].transition_bodies[1],2);
    memcpy(&paired_key,boss_private_actions[5].transition_bodies[1]+0x14,2);
    assert(condition==22 && paired_key==0x361); ++checks;

    chain_reset(); game_input_state=chain_input; reach(3);
    assert(setter_error==FRAME_ERROR); ++checks;
    printf("chain/camera checks: %u\n",checks);
    return 0;
}
