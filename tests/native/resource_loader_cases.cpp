// Loader failure paths run against this process's fake image and kernel mapping.
// No game process, archive, hooks or externally owned memory are involved.
#include <windows.h>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "MinHook.h"

static uint8_t* image;
static bool reject_mapping;
static HANDLE rejected_handle;
static void* unavailable_object(void*,size_t,size_t,void*) {
    // Supply a callable file allocator without granting it any resources.
    // Returning null makes reaching allocation itself visible as a loader error.
    // Missing System dependencies should be rejected before this callback runs.
    return nullptr;
}
static HMODULE WINAPI owned_module(const wchar_t*) {
    // Redirect image-relative resource lookups into a disposable test allocation.
    // The loader sees only the bytes and null globals written by this harness.
    // No Nioh address or module is required to reproduce initialization failures.
    return reinterpret_cast<HMODULE>(image);
}
static void* WINAPI owned_view(HANDLE handle, DWORD access, DWORD high, DWORD low, SIZE_T size) {
    // Force the precise mapping-view allocation failure after handle creation.
    // Successful retries still use a real mapping owned by this process.
    // This distinguishes handle cleanup from merely returning the right error.
    if (!reject_mapping) return MapViewOfFile(handle,access,high,low,size);
    rejected_handle=handle;
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return nullptr;
}
#define GetModuleHandleW owned_module
#define MapViewOfFile owned_view
#include "../../runtime/native/resource_loader.cpp"
#undef MapViewOfFile
#undef GetModuleHandleW

extern "C" MH_STATUS WINAPI MH_Initialize() {
    // Keep initialization within the disposable loader test process.
    // Return success without constructing a real hook manager.
    // Mapping retry behavior can then be checked independently of patching.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_CreateHook(void*, void*, void**) {
    // Allow startup to pass its hook-creation branch in the owned fixture.
    // No trampoline or patched executable instruction is installed here.
    // The test never invokes a frame through a missing original callback.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_EnableHook(void*) {
    // Model a successful enable after the mapping retry succeeds.
    // The callback remains a plain function that this test calls directly.
    // No real gameplay or operating-system function receives a hook.
    return MH_OK;
}
extern "C" MH_STATUS WINAPI MH_DisableHook(void*) {
    // Satisfy the loader's detach dependency without modifying instructions.
    // The owned test uses no live callback or asynchronous resource work.
    // This keeps failure-path checks isolated from MinHook implementation details.
    return MH_OK;
}

int main(int argc,char**) {
    // Reproduce startup failures using real process identity and owned resources.
    // An optional argument isolates null-System startup for a crash reproduction.
    // Successful completion proves retry cleanup without loading any game asset.
    image=static_cast<uint8_t*>(VirtualAlloc(nullptr,0x2CA0000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    assert(image);
    const uint8_t prologue[]={0x40,0x53,0x48,0x83,0xec,0x20,0xf3,0x0f,0x11,0x89,0xa4,0x06,0,0};
    memcpy(image+0x719050,prologue,sizeof(prologue));
    uintptr_t allocator_table[8]{};
    allocator_table[7]=reinterpret_cast<uintptr_t>(&unavailable_object);
    auto allocator_object=allocator_table;
    uint8_t allocator_stub[]={0x48,0xb8,0,0,0,0,0,0,0,0,0xc3};
    const uintptr_t allocator_address=reinterpret_cast<uintptr_t>(&allocator_object);
    memcpy(allocator_stub+2,&allocator_address,8);
    memcpy(image+0xFA7080,allocator_stub,sizeof(allocator_stub));
    char manager[32]{};
    const uintptr_t manager_address=reinterpret_cast<uintptr_t>(manager);
    memcpy(image+0x1871538,&manager_address,8);
    DWORD old=0;
    assert(VirtualProtect(image+0xFA7000,0x1000,PAGE_EXECUTE_READ,&old));
    FlushInstructionCache(GetCurrentProcess(),image+0xFA7080,sizeof(allocator_stub));
    base=reinterpret_cast<uintptr_t>(image);
    ResourceState owned_state{};
    if (argc>1) {
        state=&owned_state;state->phase=1;submitting=1;
        submit_resources();
        assert(submitting==0 && state->phase==1 && !state->error);
        printf("null-System startup did not dereference unavailable globals\n");
        VirtualFree(image,0,MEM_RELEASE);
        return 0;
    }
    ResourceRequest incoming{};
    incoming.magic=0x3152504e;incoming.version=4;incoming.pid=GetCurrentProcessId();incoming.count=4;
    FILETIME born{},ended{},kernel{},user{};
    assert(GetProcessTimes(GetCurrentProcess(),&born,&ended,&kernel,&user));
    incoming.birth=(uint64_t(born.dwHighDateTime)<<32)|born.dwLowDateTime;
    for (unsigned i=0;i<4;++i) { incoming.names[i][0]='A'+char(i);incoming.sizes[i]=1; }
    assert(NiohResourcesStart(&incoming)==ERROR_INVALID_DATA && !state && !mapping);
    memset(incoming.profile_identity,0x11,sizeof(incoming.profile_identity));
    reject_mapping=true;
    assert(NiohResourcesStart(&incoming)==ERROR_NOT_ENOUGH_MEMORY);
    assert(!state && !mapping);
    DWORD flags=0;
    assert(!GetHandleInformation(rejected_handle,&flags) && GetLastError()==ERROR_INVALID_HANDLE);
    reject_mapping=false;
    assert(NiohResourcesStart(&incoming)==0 && state && mapping && state->phase==1);
    assert(state->version==4 && !memcmp(state->profile_identity,incoming.profile_identity,32));
    submitting=1;submit_resources();
    assert(submitting==0 && state->phase==1 && !state->error && !state->objects[0]);
    state->objects[0]=0x123000;state->phase=3;
    assert(NiohResourcesStart(&incoming)==0 && state->objects[0]==0x123000);
    auto changed=incoming;changed.names[0][0]='Z';
    assert(NiohResourcesStart(&changed)==ERROR_ALREADY_EXISTS && state->objects[0]==0x123000);
    memset(changed.profile_identity,0x22,sizeof(changed.profile_identity));
    assert(NiohResourcesStart(&changed)==ERROR_ALREADY_EXISTS && state->objects[0]==0x123000);
    // Keep the first mapping alive while modeling the fresh globals of another
    // immutable DLL copy. A process-only mapping name would collide here.
    ResourceState* first_state=state;HANDLE first_mapping=mapping;
    state=nullptr;mapping=nullptr;hooked=false;
    assert(NiohResourcesStart(&changed)==0 && state && mapping);
    assert(!memcmp(state->profile_identity,changed.profile_identity,32));
    assert(!memcmp(first_state->profile_identity,incoming.profile_identity,32));
    assert(first_state->objects[0]==0x123000 && first_state->phase==3);
    UnmapViewOfFile(state);state=nullptr;CloseHandle(mapping);mapping=nullptr;
    UnmapViewOfFile(first_state);CloseHandle(first_mapping);
    VirtualFree(image,0,MEM_RELEASE);
    printf("resource loader mapping retry, profile separation and missing-System checks passed\n");
    return 0;
}
