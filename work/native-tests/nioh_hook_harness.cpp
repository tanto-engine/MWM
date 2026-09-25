#include <windows.h>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

alignas(8) static std::array<unsigned char, 0x100> actor{};
alignas(8) static std::array<unsigned char, 0x100> owner{};
alignas(8) static std::array<unsigned char, 0xD0> descriptors[2]{};
alignas(8) static std::array<unsigned char, 0x38> payloads[2]{};
static volatile std::uint32_t calls = 0;

template <class T> static void put(void* base, size_t offset, T value) {
    std::memcpy(static_cast<unsigned char*>(base) + offset, &value, sizeof(value));
}

extern "C" __declspec(dllexport) __attribute__((noinline))
bool HarnessAction(void* target, std::uint32_t key, void* context) {
    (void)context;
    // A nontrivial owned function body gives MinHook enough ordinary instructions.
    if (target != actor.data() || (key != 0xC64 && key != 0xCF0)) return false;
    unsigned slot = key == 0xC64 ? 0 : 1;
    put(target, 0x58, static_cast<void*>(descriptors[slot].data()));
    put(target, 0x68, std::uint32_t(slot == 0 ? 1 : 0));
    ++calls;
    return true;
}

int main(int argc, char** argv) {
    unsigned seconds = 60;
    if (argc == 3 && std::strcmp(argv[1], "--seconds") == 0) {
        char* end = nullptr;
        unsigned long parsed = std::strtoul(argv[2], &end, 10);
        if (!end || *end || parsed < 1 || parsed > 120) return 2;
        seconds = static_cast<unsigned>(parsed);
    } else if (argc != 1) {
        std::fputs("usage: nioh_hook_harness.exe [--seconds 1..120]\n", stderr);
        return 2;
    }
    for (unsigned i = 0; i < 2; ++i) {
        put(descriptors[i].data(), 0, std::uint32_t(i == 0 ? 0xC64 : 0xCF0));
        put(descriptors[i].data(), 0x20, static_cast<void*>(payloads[i].data()));
        descriptors[i][0x40] = 1;
        put(payloads[i].data(), 0x20, std::int32_t(100 + i));
        put(payloads[i].data(), 0x34, std::int32_t(200 + i));
    }
    put(actor.data(), 0x50, static_cast<void*>(owner.data()));
    HarnessAction(actor.data(), 0xC64, nullptr);
    FILETIME created{}, exited{}, kernel{}, user{};
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user)) return 3;
    std::uint64_t creation = (std::uint64_t(created.dwHighDateTime) << 32) | created.dwLowDateTime;
    std::printf("{\"pid\":%lu,\"creation_filetime\":\"%llu\",\"action\":\"%p\",\"actor\":\"%p\",\"owner\":\"%p\",\"descriptor0\":\"%p\",\"descriptor1\":\"%p\",\"seconds\":%u}\n",
        GetCurrentProcessId(), static_cast<unsigned long long>(creation),
        reinterpret_cast<void*>(&HarnessAction), actor.data(), owner.data(),
        descriptors[0].data(), descriptors[1].data(), seconds);
    std::fflush(stdout);
    ULONGLONG end = GetTickCount64() + seconds * 1000ULL;
    unsigned tick = 0;
    while (GetTickCount64() < end) {
        HarnessAction(actor.data(), (tick++ & 1) ? 0xCF0 : 0xC64, nullptr);
        Sleep(50);
    }
    std::printf("{\"status\":\"completed\",\"calls\":%u}\n", unsigned(calls));
    return 0;
}
