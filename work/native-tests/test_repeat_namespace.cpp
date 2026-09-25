#include <cassert>
#include <cwchar>
#include <cstdio>
#include "../../outputs/okatsu-prototype/native/repeat_namespace.h"

int main() {
    wchar_t trace[96], command[96], next[96];
    repeat_mapping_name(trace, L"Trace", 5032, 0xA0BCDEF012345678ULL);
    repeat_mapping_name(command, L"Command", 5032, 0xA0BCDEF012345678ULL);
    assert(wcscmp(trace, L"Local\\NiohBossRepeatTrace_v2_5032_a0bcdef012345678") == 0);
    assert(wcscmp(command, L"Local\\NiohBossRepeatCommand_v2_5032_a0bcdef012345678") == 0);
    assert(wcscmp(trace, command) != 0);
    repeat_mapping_name(next, L"Trace", 5032, 1);
    assert(wcscmp(next, L"Local\\NiohBossRepeatTrace_v2_5032_0000000000000001") == 0);
    assert(wcscmp(trace, next) != 0);
    std::puts("repeat namespace checks passed: exact lowercase formatting and distinct configuration tags");
}
