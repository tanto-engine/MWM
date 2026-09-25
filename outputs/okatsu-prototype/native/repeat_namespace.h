#pragma once
#include <windows.h>
#include <stdint.h>

static inline void repeat_mapping_name(wchar_t (&name)[96], const wchar_t* kind,
                                       DWORD pid, uint64_t tag) {
    // Name command and trace mappings for one process and configuration tag.
    // Append a fixed-width hexadecimal tag to the stable research namespace.
    // Reacquired actor sessions must not consume another module instance's shared commands.
    const int prefix = wsprintfW(name, L"Local\\NiohBossRepeat%s_v2_%lu_", kind, pid);
    const wchar_t hex[] = L"0123456789abcdef";
    for (unsigned i = 0; i != 16; ++i)
        name[prefix + i] = hex[(tag >> ((15 - i) * 4)) & 15];
    name[prefix + 16] = L'\0';
}
