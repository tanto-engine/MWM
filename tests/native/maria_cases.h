static void maria_transition_cases() {
    // Exercise every Maria phase in all stances on both attack buttons.
    // Boss input branches cannot auto-play a string or escape into a grab/buff/evade.
    struct Phase { uint32_t key; int32_t motion; uint16_t rows; int16_t recovery, adapted; unsigned kind; int next; };
    constexpr Phase phases[]={
        {0xC80,1000,31,36,50,2,0xC81},{0xC81,1001,23,36,23,4,0xC82},
        {0xC82,1002,13,36,36,4,0},{0xC83,1010,15,36,66,2,0xC84},
        {0xC84,1011,13,36,40,4,0},{0xC85,1020,17,52,43,2,0xC86},
        {0xC86,1021,15,52,88,4,0},{0xC89,1030,17,70,70,2,0},
        {0xC8A,1030,17,70,70,2,0xC81}
    };
    static uint8_t descriptors[9][0xD0]{},payloads[9][0xB0]{},rows[9][31][0x30]{};
    static uint64_t pointers[9][31]{},entries[9]{};
    for (unsigned stance : {0u,1u,2u}) for (unsigned family : {1u,2u}) {
        replacement_reset();boss_import_count=11;
        const auto source=boss_imports[2];auto player_adapter=boss_adapters[2];
        player_adapter.player_key=stance==0 ? 0xCB7 : stance==1 ? 0xC7A : 0xCF5;
        player_adapter.player_motion=stance==0 ? 3300 : stance==1 ? 2300 : 4300;
        player_adapter.transition_count=stance==0 ? 40 : stance==1 ? 42 : 46;
        player_adapter.recovery_frame=stance==0 ? 58 : stance==1 ? 46 : 38;
        put(heavy_descriptors[0].data(),0,player_adapter.player_key);
        put(heavy_descriptors[0].data(),0x82,player_adapter.transition_count);
        put(heavy_payloads[0].data(),0x20,player_adapter.player_motion);
        put(heavy_payloads[0].data(),0x24,player_adapter.recovery_frame);
        for (auto& row : player_rows[0]) {
            int16_t target=0;memcpy(&target,row.data()+0x14,2);
            if (target!=0xCF6) continue;
            // The live CB7 High template has no next-attack pair; Mid uses C7B.
            put(row.data(),0x14,int16_t(stance==0 ? -1 : player_adapter.player_key+1));
            put(row.data(),2,uint16_t(0x50+stance));
        }
        for (unsigned i=0;i<9;++i) {
            const auto& phase=phases[i];auto& move=boss_imports[i+2];move=source;
            move.key=phase.key;move.motion=phase.motion;move.flags=0x184C0000;
            move.transition_count=phase.rows;move.recovery_frame=phase.recovery;
            move.descriptor=address(descriptors[i]);move.payload=address(payloads[i]);
            auto& adapter=boss_adapters[i+2];adapter=player_adapter;adapter.kind=phase.kind;
            boss_move_settings[i+2]={1,40,30,36,uint16_t(family)};boss_private_actions[i+2]={};
            memset(descriptors[i],0,sizeof(descriptors[i]));memset(payloads[i],0,sizeof(payloads[i]));
            descriptors[i][0x40]=1;put(descriptors[i],0,move.key);put(descriptors[i],0x20,move.payload);
            put(descriptors[i],0x78,address(pointers[i]));put(descriptors[i],0x82,move.transition_count);
            put(payloads[i],0x18,move.flags);put(payloads[i],0x20,move.motion);
            put(payloads[i],0x24,move.recovery_frame);put(payloads[i],0x16,int16_t(10));entries[i]=move.descriptor;
            for (unsigned r=0;r<phase.rows;++r) {memset(rows[i][r],0xff,0x30);pointers[i][r]=address(rows[i][r]);}
            // Recorded input-shaped branch, deliberately present even for the isolated slash.
            rows[i][0][0x0A]=2;rows[i][0][0x0B]=0;rows[i][0][0x0C]=1;
            put(rows[i][0],0x14,int16_t(phase.next ? phase.next : 0xC79));
        }
        put(jin_bank.data(),0x128,address(entries));put(jin_bank.data(),0x130,uint32_t(9));
        for (unsigned i=0;i<9;++i) {
            const auto& phase=phases[i];uint8_t before[0xB0];memcpy(before,payloads[i],sizeof(before));
            const unsigned root=i<3 ? 0 : i<5 ? 3 : i<7 ? 5 : i;
            boss_skill_bindings[0]={i==7 ? 6u : family==1 ? 5u : 1u,1u<<(2-stance),root+3,
                player_adapter.player_key,player_adapter.player_motion,player_adapter.transition_count,0x8000000594C0000ULL};
            if (i==2) assert(boss_native_successor(i+2,0xC83)==-1); // Maria C82 is not Jin's airborne C82.
            if (!phase.next && i!=7) {
                // Even if source AI had an automatic loop, the player must press again.
                rows[i][1][0x0A]=1;put(rows[i][1],0x14,int16_t(phases[root].key));
                put(rows[i][1],0x1C,uint32_t(4));put(rows[i][1],0x20,int16_t(INT16_MIN));
                put(rows[i][1],0x22,int16_t(INT16_MAX));
            }
            assert(boss_prepare_private_action(i+2));
            const auto& clone=boss_private_actions[i+2];unsigned next_rows=0;
            const int next=phase.next ? phase.next : i==7 ? 0 : int(phases[root].key);
            const int restart_frame=phase.key==0xC84 ? 126 : phase.adapted;
            for (unsigned r=0;r<clone.transition_count;++r) {
                const auto* row=clone.transition_bodies[r];int16_t target=0;memcpy(&target,row+0x14,2);
                assert(target!=0xC79 && target!=0xCF6);
                if (next && target==next) {
                    ++next_rows;assert(row[0x0B]==(family==1 ? 0 : 1) && row[0x0C]==1);
                    assert(row[0x0A]==0 || row[0x0A]==2);
                    if (!phase.next || stance==0) {
                        int16_t start=0,end=0;memcpy(&start,row+0x20,2);memcpy(&end,row+0x22,2);
                        const int gate=!phase.next ? restart_frame : phase.adapted;
                        assert(row[0x0A]==2 ? end==gate-1 : start==gate);
                    }
                }
                // Same-button generic opener must not bypass the final landing;
                // Pulse, dodge and opposite-button cancels retain their earlier recovery.
                if (phase.key==0xC84 && target==(family==1 ? 0xBBF : 0xBC0)) {
                    int16_t start=0;memcpy(&start,row+0x20,2);assert(start==126);
                }
            }
            assert(next_rows==(next ? 2u : 0u));
            int16_t onset=0,cost=0;memcpy(&onset,clone.payload+0x38,2);memcpy(&cost,clone.payload+0x16,2);
            assert(onset==phase.adapted && cost==10 && !memcmp(before,payloads[i],sizeof(before)));
            auto collision=boss_imports[i+2];collision.motion+=1;
            assert(!recorded_grounded(collision,boss_adapters[i+2]) && sword_string_successor(collision)==-1);
            boss_move_settings[i+2]={};
        }
        // Shared C82 must restart the selected dash root, never the earlier C80 import.
        boss_move_settings[4]={1,40,30,36,uint16_t(family)};
        boss_skill_bindings[0].variant=11;
        assert(boss_string_restart(4)==10 && boss_native_successor(4,0xC8A)==10);
        boss_private_actions[4]={};assert(boss_prepare_private_action(4));
        unsigned restarts=0;
        for (unsigned r=0;r<boss_private_actions[4].transition_count;++r) {
            const auto* row=boss_private_actions[4].transition_bodies[r];int16_t target=0;
            memcpy(&target,row+0x14,2);assert(target!=0xC80);
            if (target==0xC8A) {++restarts;assert(row[0x0B]==(family==1 ? 0 : 1) && row[0x0C]==1);}
        }
        assert(restarts==2);
        const auto binding=boss_skill_bindings[0];
        boss_skill_bindings[0].stances^=7;assert(boss_string_restart(4)==-1);boss_skill_bindings[0]=binding;
        boss_skill_bindings[0].kind=6;assert(boss_string_restart(4)==-1);boss_skill_bindings[0]=binding;
        boss_skill_bindings[0].kind=family==1 ? 1 : 5;assert(boss_string_restart(4)==-1);boss_skill_bindings[0]=binding;
        boss_adapters[10].bank+=8;assert(boss_string_restart(4)==-1);boss_adapters[10].bank-=8;
        boss_adapters[3].bank+=8;assert(boss_string_restart(4)==-1);boss_adapters[3].bank-=8;
        boss_skill_bindings[1]=binding;boss_skill_bindings[1].variant=3;
        assert(boss_string_restart(4)==-1);boss_skill_bindings[1]={};
        boss_skill_bindings[0].variant=3;assert(boss_string_restart(4)==2);
        boss_move_settings[4]={};
    }
}
