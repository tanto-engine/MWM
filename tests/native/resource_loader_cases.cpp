// Loader failure paths run against this process's fake image and kernel mapping.
// No game process, archive, hooks or externally owned memory are involved.
#include <windows.h>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "MinHook.h"

static uint8_t* image;
static bool reject_mapping;
static HANDLE rejected_handle;
static unsigned allocation_calls;
static void* unavailable_object(void*,size_t,size_t,void*) {
    // Supply a callable file allocator without granting it any resources.
    // Returning null makes reaching allocation itself visible as a loader error.
    // Missing System dependencies should be rejected before this callback runs.
    ++allocation_calls;
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
    // Mission transitions can still tick NPCs while William's action banks are absent.
    // Complete allocator globals alone must not authorize resource construction on that frame.
    // A previously published player address also cannot authorize a reused actor allocation.
    uintptr_t system_words[5]{};system_words[4]=allocator_address;
    const uintptr_t system_address=reinterpret_cast<uintptr_t>(system_words);
    memcpy(image+0x2C946B8,&system_address,8);
    uint8_t actor[0x88]{};
    state=&owned_state;state->phase=1;
    frame_original=[](void*,float delta) { SetLastError(77);return delta+1; };
    for (bool reused : {false,true}) {
        state->player=reused ? reinterpret_cast<uintptr_t>(actor) : 0;
        submitting=0;allocation_calls=0;state->phase=1;state->error=0;
        assert(resource_frame(actor,.5f)==1.5f && GetLastError()==77);
        assert(!allocation_calls && !submitting && state->phase==1 && !state->error);
    }
    // A supported player frame may submit only after the motion-data allocator exists.
    // When it becomes ready, the original allocation failure remains visible and terminal.
    // This proves deferral did not disable ordinary activation or swallow native failures.
    uint8_t bank[0x138]{},descriptor[0x48]{},payload[0x24]{};
    const uintptr_t player_vtable=base+0x11A3530,owner_address=0x10000;
    const uintptr_t bank_address=reinterpret_cast<uintptr_t>(bank),descriptor_address=reinterpret_cast<uintptr_t>(descriptor);
    const uintptr_t table_address=reinterpret_cast<uintptr_t>(&descriptor_address),payload_address=reinterpret_cast<uintptr_t>(payload);
    const uint32_t count=1,key=0xC64;const int32_t motion=2033;
    memcpy(actor,&player_vtable,8);memcpy(actor+0x50,&owner_address,8);memcpy(actor+0x70,&bank_address,8);
    memcpy(bank+0x128,&table_address,8);memcpy(bank+0x130,&count,4);
    memcpy(descriptor,&key,4);descriptor[0x40]=1;memcpy(descriptor+0x20,&payload_address,8);memcpy(payload+0x20,&motion,4);
    for (bool ready : {false,true}) {
        system_words[4]=ready ? allocator_address : 0;
        state->player=0;submitting=0;allocation_calls=0;state->phase=1;state->error=0;
        assert(resource_frame(actor,.5f)==1.5f && GetLastError()==77);
        assert(state->player==reinterpret_cast<uintptr_t>(actor) && state->owner==owner_address);
        if (ready) assert(allocation_calls==1 && state->phase==4 && state->error==ERROR_OUTOFMEMORY);
        else assert(!allocation_calls && !submitting && state->phase==1 && !state->error);
    }
    // Pending/completed owners avoid rescanning banks after discovering this player.
    // Reattachment clears that publication and must still discover the current player at phase 3.
    for (LONG phase : {2L,3L}) {
        const uintptr_t next_owner=owner_address+phase;
        memcpy(actor+0x50,&next_owner,8);
        state->phase=phase;state->player=reinterpret_cast<uintptr_t>(actor);state->owner=owner_address;allocation_calls=0;
        resource_frame(actor,.5f);
        assert(state->owner==owner_address && !allocation_calls);
        state->player=0;
        resource_frame(actor,.5f);
        assert(state->player==reinterpret_cast<uintptr_t>(actor) && state->owner==next_owner && !allocation_calls);
    }
    state=nullptr;submitting=0;
    const uintptr_t absent=0;memcpy(image+0x2C946B8,&absent,8);
    ResourceRequest incoming{};
    incoming.magic=0x3152504e;incoming.version=5;incoming.pid=GetCurrentProcessId();incoming.count=4;
    FILETIME born{},ended{},kernel{},user{};
    assert(GetProcessTimes(GetCurrentProcess(),&born,&ended,&kernel,&user));
    incoming.birth=(uint64_t(born.dwHighDateTime)<<32)|born.dwLowDateTime;
    for (unsigned i=0;i<4;++i) { incoming.names[i][0]='A'+char(i);incoming.sizes[i]=1; }
    assert(NiohResourcesStart(&incoming)==ERROR_INVALID_DATA && !state && !mapping);
    memset(incoming.profile_identity,0x11,sizeof(incoming.profile_identity));
    auto invalid=incoming;invalid.object_count=5;
    assert(NiohResourcesStart(&invalid)==ERROR_INVALID_DATA && !state);
    invalid=incoming;invalid.object_count=1;invalid.object_keys[0]=0x149A;
    assert(NiohResourcesStart(&invalid)==ERROR_INVALID_DATA && !state);
    invalid=incoming;invalid.object_count=2;invalid.object_keys[0]=invalid.object_keys[1]=3257;
    assert(NiohResourcesStart(&invalid)==ERROR_INVALID_DATA && !state);
    reject_mapping=true;
    assert(NiohResourcesStart(&incoming)==ERROR_NOT_ENOUGH_MEMORY);
    assert(!state && !mapping);
    DWORD flags=0;
    assert(!GetHandleInformation(rejected_handle,&flags) && GetLastError()==ERROR_INVALID_HANDLE);
    reject_mapping=false;
    assert(NiohResourcesStart(&incoming)==0 && state && mapping && state->phase==1);
    assert(state->version==5 && !memcmp(state->profile_identity,incoming.profile_identity,32));
    submitting=1;submit_resources();
    assert(submitting==0 && state->phase==1 && !state->error && !state->objects[0]);
    // An unfinished archive decode no longer needs the temporary player-frame hook.
    // Detach must release that hook while retaining pending objects and their callbacks.
    // A second loader must not overwrite an enabled hook left by a timed-out first loader.
    state->objects[0]=0x123000;state->phase=2;
    assert(NiohResourcesDetach(nullptr)==0 && state->objects[0]==0x123000 && state->phase==2);
    callbacks=1;
    assert(NiohResourcesDetach(nullptr)==ERROR_BUSY);
    callbacks=0;
    assert(NiohResourcesDetach(nullptr)==0);
    state->phase=3;
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
