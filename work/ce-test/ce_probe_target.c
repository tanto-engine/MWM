#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

/* Disposable debugger target. Never opens or modifies another process. */
__declspec(dllexport) volatile LONG64 probe_counts[2] = {0, 0};
static HANDLE stop_event;

/* A single stable, native breakpoint location. RCX identifies the caller:
   0 = main thread, 1 = worker thread. */
__declspec(dllexport) __attribute__((noinline, noclone))
LONG64 research_probe(uint64_t caller)
{
    // Provide a stable breakpoint address shared by two disposable threads.
    // Increment the caller's counter with an interlocked operation.
    // Detect missed continuation without touching another process.
    if (caller > 1) {
        return -1;
    }
    return InterlockedIncrement64(&probe_counts[caller]);
}

static DWORD WINAPI worker_main(LPVOID unused)
{
    // Exercise the same probe from a second native thread.
    // Wait on the stop event between calls instead of spinning.
    // Let the parent verify debugger cleanup across thread contexts.
    (void)unused;
    while (WaitForSingleObject(stop_event, 100) == WAIT_TIMEOUT) {
        research_probe(1);
    }
    return 0;
}

int main(int argc, char **argv)
{
    // Run a bounded disposable process for debugger research.
    // Publish probe addresses and counters while both threads execute.
    // Join the worker before closing its event so normal exit proves recovery.
    unsigned long duration_seconds = 60;
    if (argc > 2) {
        fprintf(stderr, "Usage: ce_probe_target.exe [seconds: 1..60]\n");
        return 2;
    }
    if (argc == 2) {
        char *end = NULL;
        errno = 0;
        duration_seconds = strtoul(argv[1], &end, 10);
        if (errno || end == argv[1] || *end != '\0' ||
            duration_seconds < 1 || duration_seconds > 60) {
            fprintf(stderr, "Duration must be an integer from 1 to 60.\n");
            return 2;
        }
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    stop_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!stop_event) {
        fprintf(stderr, "CreateEvent failed: %lu\n", GetLastError());
        return 3;
    }
    DWORD worker_id = 0;
    HANDLE worker = CreateThread(NULL, 0, worker_main, NULL, 0, &worker_id);
    if (!worker) {
        fprintf(stderr, "CreateThread failed: %lu\n", GetLastError());
        CloseHandle(stop_event);
        return 3;
    }
    printf("pid=%lu main_tid=%lu worker_tid=%lu pointer_bits=%u "
           "probe=0x%" PRIxPTR " counter0=0x%" PRIxPTR
           " counter1=0x%" PRIxPTR " duration_seconds=%lu\n",
           GetCurrentProcessId(), GetCurrentThreadId(), worker_id,
           (unsigned)(sizeof(void *) * 8), (uintptr_t)&research_probe,
           (uintptr_t)&probe_counts[0], (uintptr_t)&probe_counts[1],
           duration_seconds);

    ULONGLONG started = GetTickCount64();
    ULONGLONG next_report = started + 1000;
    while (GetTickCount64() - started < duration_seconds * 1000ULL) {
        research_probe(0);
        if (GetTickCount64() >= next_report) {
            printf("elapsed_ms=%llu counter0=%lld counter1=%lld\n",
                   GetTickCount64() - started,
                   InterlockedCompareExchange64(&probe_counts[0], 0, 0),
                   InterlockedCompareExchange64(&probe_counts[1], 0, 0));
            next_report += 1000;
        }
        Sleep(250);
    }
    SetEvent(stop_event);
    /* The worker must return before the event handle can be closed. */
    WaitForSingleObject(worker, INFINITE);
    CloseHandle(worker);
    CloseHandle(stop_event);
    printf("finished elapsed_ms=%llu counter0=%lld counter1=%lld\n",
           GetTickCount64() - started,
           InterlockedCompareExchange64(&probe_counts[0], 0, 0),
           InterlockedCompareExchange64(&probe_counts[1], 0, 0));
    return 0;
}
