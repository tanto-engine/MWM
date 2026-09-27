// Owned-memory regression for MinHook's single-target disable direction.
// Mock peer-thread APIs so the real hook lifecycle never suspends another thread.
#include <windows.h>
#include <tlhelp32.h>
#include <string.h>

static DWORD64 fixture_ip;

static HANDLE WINAPI fixture_snapshot(DWORD flags, DWORD pid) {
    // Supply one synthetic snapshot instead of enumerating operating-system threads.
    // The production caller requests all threads and filters by owner afterward.
    // Handles 1 and 2 belong only to this fixture and are consumed by its mock APIs.
    (void)flags; (void)pid; return (HANDLE)1;
}

static BOOL WINAPI fixture_first(HANDLE snapshot, LPTHREADENTRY32 entry) {
    // Present exactly one peer in this process so production Freeze visits its context.
    // Choose a different thread ID without creating or opening a real thread.
    // Preserve the Toolhelp structure-size contract checked by EnumerateThreads.
    (void)snapshot; entry->dwSize=sizeof(*entry);
    entry->th32OwnerProcessID=GetCurrentProcessId();
    entry->th32ThreadID=GetCurrentThreadId()+1; return TRUE;
}

static BOOL WINAPI fixture_next(HANDLE snapshot, LPTHREADENTRY32 entry) {
    // End the synthetic enumeration after its single peer.
    // Set the precise Toolhelp completion error that the production code expects.
    // This prevents an incomplete-snapshot error from masking the IP-translation check.
    (void)snapshot; (void)entry; SetLastError(ERROR_NO_MORE_FILES); return FALSE;
}

static HANDLE WINAPI fixture_open(DWORD access, BOOL inherit, DWORD tid) {
    // Return a synthetic peer handle for both Freeze and Unfreeze.
    // Access flags and the synthetic ID never reach the Windows thread API.
    // The context and suspend mocks use this handle without owning any OS resource.
    (void)access; (void)inherit; (void)tid; return (HANDLE)2;
}

static DWORD WINAPI fixture_suspend(HANDLE thread) {
    // Report successful suspension so Freeze enters ProcessThreadIPs.
    // No actual thread is suspended; the only context is fixture_ip below.
    // A zero previous suspend count matches the ordinary first-suspension path.
    (void)thread; return 0;
}

static DWORD WINAPI fixture_resume(HANDLE thread) {
    // Satisfy Unfreeze after it visits the synthetic peer.
    // Report the previous suspend count as one to pair with fixture_suspend.
    // No scheduler state or live thread context changes during cleanup.
    (void)thread; return 1;
}

static BOOL WINAPI fixture_get(HANDLE thread, LPCONTEXT context) {
    // Supply the suspended x64 instruction pointer selected by the test stage.
    // The production routine requests CONTEXT_CONTROL and only consumes Rip here.
    // Reads copy fixture state into the real ProcessThreadIPs working context.
    (void)thread; context->Rip=fixture_ip; return TRUE;
}

static BOOL WINAPI fixture_set(HANDLE thread, const CONTEXT* context) {
    // Capture the instruction pointer chosen by the real MinHook relocation logic.
    // Store only Rip because the regression concerns direction, not other registers.
    // The test can distinguish a missing SetThreadContext call from a correct remap.
    (void)thread; fixture_ip=context->Rip; return TRUE;
}

static BOOL WINAPI fixture_close(HANDLE handle) {
    // Consume synthetic snapshot and peer handles without calling CloseHandle.
    // These small sentinel values do not represent Windows resources owned by the test.
    // Keep production cleanup paths active while isolating them from real handles.
    (void)handle; return TRUE;
}

#define CreateToolhelp32Snapshot fixture_snapshot
#define Thread32First fixture_first
#define Thread32Next fixture_next
#define OpenThread fixture_open
#define SuspendThread fixture_suspend
#define ResumeThread fixture_resume
#define GetThreadContext fixture_get
#define SetThreadContext fixture_set
#define CloseHandle fixture_close
#include "../../third_party/minhook/src/hook.c"

__declspec(dllexport) int minhook_disable_regression(void) {
    // Install real entry patches and trampolines in owned memory, without executing either function.
    // Assert enabling maps target to trampoline and both disabling paths map back before resuming.
    // Return a failing stage (zero means success), then release the hook, heap and executable page.
    const unsigned char body[]={0xB8,0x2A,0,0,0,0xC3}; // mov eax,42; ret: one relocatable five-byte instruction.
    unsigned char* code=VirtualAlloc(NULL,4096,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    LPVOID original=NULL;
    int result=1;
    if (!code) return result;
    memcpy(code,body,sizeof(body)); memcpy(code+64,body,sizeof(body));
    result=2; if (MH_Initialize()!=MH_OK) goto done;
    result=3; if (MH_CreateHook(code,code+64,&original)!=MH_OK) goto done;
    fixture_ip=(DWORD64)code;
    result=4; if (MH_EnableHook(code)!=MH_OK || fixture_ip!=(DWORD64)original) goto done;
    result=5; if (MH_DisableHook(code)!=MH_OK || fixture_ip!=(DWORD64)code
        || memcmp(code,body,sizeof(body))) goto done;
    result=6; if (MH_EnableHook(code)!=MH_OK || fixture_ip!=(DWORD64)original) goto done;
    result=7; if (MH_DisableHook(MH_ALL_HOOKS)!=MH_OK || fixture_ip!=(DWORD64)code
        || memcmp(code,body,sizeof(body))) goto done;
    result=8; if (MH_RemoveHook(code)!=MH_OK) goto done;
    result=0;
done:
    MH_Uninitialize(); VirtualFree(code,0,MEM_RELEASE);
    return result;
}
