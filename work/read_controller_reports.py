from read_controller_hid import *
import time
class Overlap(C.Structure):
    _fields_=[('internal',C.c_size_t),('high',C.c_size_t),('offset',W.DWORD),('offset_high',W.DWORD),('event',W.HANDLE)]
k.ReadFile.argtypes=[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.POINTER(Overlap)]
k.GetOverlappedResult.argtypes=[W.HANDLE,C.POINTER(Overlap),C.POINTER(W.DWORD),W.BOOL]
k.CreateEventW.argtypes=[C.c_void_p,W.BOOL,W.BOOL,W.LPCWSTR];k.CreateEventW.restype=W.HANDLE
k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];k.CancelIoEx.argtypes=[W.HANDLE,C.POINTER(Overlap)]
hid.HidP_GetUsages.argtypes=[C.c_int,C.c_ushort,C.c_ushort,C.c_void_p,C.POINTER(W.ULONG),C.c_void_p,C.c_void_p,W.ULONG]
h=k.CreateFileW(name.value,0x80000000,3,None,3,0x40000000,None)
p=C.c_void_p();hid.HidD_GetPreparsedData(h,C.byref(p));buf=C.create_string_buffer(547);ov=Overlap();ov.event=k.CreateEventW(None,True,False,None);received=W.DWORD();last=None;total=0;end=time.monotonic()+3
while time.monotonic()<end:
    ok=k.ReadFile(h,buf,len(buf),C.byref(received),C.byref(ov));err=C.get_last_error()
    if not ok and err!=997:print('readerror',err);break
    if k.WaitForSingleObject(ov.event,500)!=0:print('timeout');break
    if not k.GetOverlappedResult(h,C.byref(ov),C.byref(received),False):print('completionerror',C.get_last_error());break
    usages=(C.c_ushort*32)();count=W.ULONG(32);status=hid.HidP_GetUsages(0,9,0,usages,C.byref(count),p,buf,len(buf))&0xffffffff
    state=(received.value,buf.raw[:16].hex(),hex(status),list(usages)[:count.value])
    if state!=last:print(state);last=state
    total+=1
k.CancelIoEx(h,C.byref(ov));k.GetOverlappedResult(h,C.byref(ov),C.byref(received),True);hid.HidD_FreePreparsedData(p);k.CloseHandle(h);k.CloseHandle(ov.event);print('reports',total)
