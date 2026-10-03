static void ishida_transition_cases() {
    // Repeated C5B and shared endings must follow the selected route, on either attack button.
    constexpr unsigned keys[]={0xC5B,0xC5B,0xC5C,0xC58, 0xC71,0xC72,0xC6E,
        0xC5C,0xC58,0xC7A, 0xC78,0xC5B,0xC5C,0xC58, 0xC6C,0xC6D,0xC71,0xC72,0xC6E};
    constexpr unsigned roots[]={0,4,7,10,14,19};
    static uint8_t descriptors[19][0xD0],payloads[19][0xB0],rows[19][40][0x30];
    static uint64_t pointers[19][40],entries[19];
    for (unsigned family : {1u,2u}) {
        replacement_reset();boss_import_count=21;
        const auto source=boss_imports[2];const auto player_adapter=boss_adapters[2];
        for (unsigned route=0;route<5;++route) for (unsigned i=roots[route];i<roots[route+1];++i) {
            auto& move=boss_imports[i+2];move=source;move.key=keys[i];move.flags=0x10018480000ULL;
            move.recovery_frame=-1;move.next_variant=i+1<roots[route+1] ? int16_t(i+3) : -1;
            move.next_start=move.next_end=0;
            for (const auto& profile : cast_pulse_profiles) if (profile.key==move.key && profile.flags==move.flags) {
                move.motion=profile.motion;move.transition_count=profile.rows;
            }
            assert(ishida_phase(move));move.descriptor=address(descriptors[i]);move.payload=address(payloads[i]);
            boss_adapters[i+2]=player_adapter;boss_adapters[i+2].kind=i==roots[route] ? 2 : 4;
            boss_move_settings[i+2]={1,40,30,36,uint16_t(family)};boss_private_actions[i+2]={};
            memset(descriptors[i],0,0xD0);memset(payloads[i],0,0xB0);descriptors[i][0x40]=1;
            put(descriptors[i],0,move.key);put(descriptors[i],0x20,move.payload);
            put(descriptors[i],0x78,address(pointers[i]));put(descriptors[i],0x82,move.transition_count);
            put(payloads[i],0x18,move.flags);put(payloads[i],0x20,move.motion);put(payloads[i],0x24,int16_t(-1));
            put(payloads[i],0x16,int16_t(10));entries[i]=move.descriptor;
            for (unsigned r=0;r<move.transition_count;++r) {memset(rows[i][r],0xff,0x30);pointers[i][r]=address(rows[i][r]);}
            rows[i][0][10]=2;rows[i][0][11]=0;rows[i][0][12]=1;
            put(rows[i][0],20,int16_t(move.next_variant>=0 ? keys[i+1] : keys[roots[route]]));
        }
        put(jin_bank.data(),0x128,address(entries));put(jin_bank.data(),0x130,uint32_t(19));
        for (unsigned route=0;route<5;++route) for (unsigned i=roots[route];i<roots[route+1];++i) {
            boss_skill_bindings[0]={family==1 ? 5u : 1u,1,roots[route]+3,0xCF5,4300,46,0x8000000594C0000ULL};
            const unsigned next=i+1<roots[route+1] ? i+1 : roots[route];
            assert(boss_native_successor(i+2,keys[next])==int(next+2));
            assert(boss_prepare_private_action(i+2));
            const auto& clone=boss_private_actions[i+2];unsigned input_rows=0;
            for (unsigned r=0;r<clone.transition_count;++r) {
                const auto* row=clone.transition_bodies[r];int16_t target=0;memcpy(&target,row+20,2);
                if (target!=int16_t(keys[next])) continue;
                assert(row[10]==0 || row[10]==2);assert(row[11]==(family==1 ? 0 : 1));++input_rows;
            }
            assert(input_rows==2);++checks;
        }
    }
}
