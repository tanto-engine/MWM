import ctypes as C
from ctypes import wintypes as W
class Device(C.Structure):
    _fields_=[('handle',W.HANDLE),('kind',W.DWORD)]
u=C.WinDLL('user32',use_last_error=True)
u.GetRawInputDeviceList.argtypes=[C.POINTER(Device),C.POINTER(W.UINT),W.UINT]
u.GetRawInputDeviceInfoW.argtypes=[W.HANDLE,W.UINT,C.c_void_p,C.POINTER(W.UINT)]
n=W.UINT();u.GetRawInputDeviceList(None,C.byref(n),C.sizeof(Device)); devices=(Device*n.value)();u.GetRawInputDeviceList(devices,C.byref(n),C.sizeof(Device))
k=C.WinDLL('kernel32',use_last_error=True)
k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
k.CloseHandle.argtypes=[W.HANDLE]
hid=C.WinDLL('hid',use_last_error=True)
hid.HidD_GetPreparsedData.argtypes=[W.HANDLE,C.POINTER(C.c_void_p)]
hid.HidP_GetCaps.argtypes=[C.c_void_p,C.c_void_p]
hid.HidD_FreePreparsedData.argtypes=[C.c_void_p]
for d in devices:
    if d.kind!=2:continue
    length=W.UINT();u.GetRawInputDeviceInfoW(d.handle,0x20000007,None,C.byref(length));name=C.create_unicode_buffer(length.value+1);u.GetRawInputDeviceInfoW(d.handle,0x20000007,name,C.byref(length))
    if '054c' not in name.value.lower():continue
    handle=k.CreateFileW(name.value,0x80000000,3,None,3,0x40000000,None)
    print('device',name.value,'handle',handle,'error',C.get_last_error())
    if handle==C.c_void_p(-1).value:continue
    data=C.c_void_p();caps=(C.c_ushort*32)();print('preparsed',hid.HidD_GetPreparsedData(handle,C.byref(data)));print('caps',hex(hid.HidP_GetCaps(data,caps)&0xffffffff),list(caps));hid.HidD_FreePreparsedData(data);k.CloseHandle(handle)
