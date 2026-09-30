#pragma once
static constexpr uint8_t native_dodge_row[0x30] = {
    0x5c,0,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0,2,1,0xff,0xff,0,0,0,0,0,
    0x12,0x0d,0,0,0xff,0x80,0x64,0x64,0,0,0,0,0,0x80,0xff,0x7f,
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff
};
static std::array<std::array<uint8_t,0x30>,4> native_shortcut_rows{};
static inline void fixture_shortcut_exits(uint64_t* pointers) {
    constexpr uint8_t selectors[]={0x1F,0x1F,0x23,0x20}, states[]={5,7,4,4};
    for (unsigned i=0;i<4;++i) {
        auto& row=native_shortcut_rows[i];memcpy(row.data(),native_dodge_row,0x30);
        row[0]=0x5D;row[0x0B]=selectors[i];row[0x0C]=states[i];row[0x17]=4;row[0x18]=0;
        const int16_t key=int16_t(0xD1B+i);memcpy(row.data()+0x14,&key,2);
        pointers[40+i]=reinterpret_cast<uint64_t>(row.data());
    }
}
static void fixture_imports() {
    // Populate the two baseline imports for legacy owned-memory fixtures.
    // Map their existing source pointers to the maintained runtime import ABI.
    // Research harnesses must exercise the same baseline table contract as production.
    boss_import_count = 2; boss_string_variant = 0;
    boss_imports[0] = {boss_session.source_descriptor,boss_session.source_payload,
        boss_session.source_clip,boss_session.source_timing_record,0x184C0000,
        0xC64,1220,65,28,-1,0,0,1,{{30,11,0x0E077D36},{},{}}};
    boss_imports[1] = {boss_session.charge_descriptor,boss_session.charge_payload,
        boss_session.charge_clip,boss_session.charge_timing_record,0x184C0000,
        0xC66,1230,90,22,-1,0,0,1,{{46,16,0xF519B456},{},{}}};
}
