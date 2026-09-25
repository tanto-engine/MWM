"""Client for CE's existing local Lua server. Execute only our research scripts."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import struct

k=C.WinDLL('kernel32',use_last_error=True)
k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
k.CreateFileW.restype=W.HANDLE
k.ReadFile.argtypes=[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p]
k.ReadFile.restype=W.BOOL
k.WriteFile.argtypes=k.ReadFile.argtypes
k.WriteFile.restype=W.BOOL
k.CloseHandle.argtypes=[W.HANDLE]
k.CloseHandle.restype=W.BOOL

def call(script):
    h=k.CreateFileW(r'\\.\pipe\NiohResearchFresh',0xC0000000,0,None,3,0,None)
    if h==C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        code=script.encode('utf8')
        packet=b'\x01'+struct.pack('<I',len(code))+code+struct.pack('<Q',0)
        written=W.DWORD()
        if not k.WriteFile(h,packet,len(packet),C.byref(written),None) or written.value!=len(packet):
            raise C.WinError(C.get_last_error())
        result=b''
        while len(result)<8:
            buf=C.create_string_buffer(8-len(result)); count=W.DWORD()
            if not k.ReadFile(h,buf,len(buf),C.byref(count),None) or not count.value:
                raise OSError('CE pipe response interrupted')
            result+=buf.raw[:count.value]
        return struct.unpack('<Q',result)[0]
    finally:
        k.CloseHandle(h)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--script',type=Path)
    group.add_argument('--check',action='store_true')
    a=p.parse_args()
    text=a.script.read_text(encoding='utf8') if a.script else 'return 73191'
    if a.script:
        status=Path(__file__).with_name('ce-script-status.txt').as_posix()
        text=("local ok,v=xpcall(function()\n"+text+"\nend,debug.traceback)\n"
            +"local f=assert(io.open([["+status+"]],'w')); f:write(ok and 'ok' or tostring(v)); f:close()\n"
            +"if not ok then return 999999991 end; return v or 0")
    value=call(text)
    print(value)
    if a.script:
        print(Path(__file__).with_name('ce-script-status.txt').read_text(encoding='utf8'))
