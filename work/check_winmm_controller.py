"""Read-only legacy joystick query; no acquisition, capture, or device writes."""
import ctypes as C, json
from ctypes import wintypes as W

class JoyInfo(C.Structure):
    _fields_=[(name,W.DWORD) for name in ('size','flags','x','y','z','r','u','v','buttons','button_number','pov','reserved1','reserved2')]
class JoyCaps(C.Structure):
    _fields_=[('manufacturer',W.WORD),('product',W.WORD),('name',W.WCHAR*32)]+[(name,W.UINT) for name in ('xmin','xmax','ymin','ymax','zmin','zmax','num_buttons','period_min','period_max','rmin','rmax','umin','umax','vmin','vmax','caps','max_axes','num_axes','max_buttons')]+[('regkey',W.WCHAR*32),('oem',W.WCHAR*260)]
assert C.sizeof(JoyInfo)==52
assert C.sizeof(JoyCaps)==728
winmm=C.WinDLL('winmm')
winmm.joyGetNumDevs.restype=W.UINT
winmm.joyGetDevCapsW.argtypes=[C.c_size_t,C.POINTER(JoyCaps),W.UINT]
winmm.joyGetDevCapsW.restype=W.UINT
winmm.joyGetPosEx.argtypes=[W.UINT,C.POINTER(JoyInfo)]
winmm.joyGetPosEx.restype=W.UINT

def enumerate_controllers():
    results=[]
    for i in range(winmm.joyGetNumDevs()):
        c=JoyCaps(); capcode=winmm.joyGetDevCapsW(i,C.byref(c),C.sizeof(c))
        s=JoyInfo();s.size=C.sizeof(s);s.flags=0xff
        code=winmm.joyGetPosEx(i,C.byref(s))
        if capcode==0 or code==0:
            results.append(dict(slot=i,caps_result=capcode,read_result=code,name=c.name,manufacturer=c.manufacturer,product=c.product,num_buttons=c.num_buttons,num_axes=c.num_axes,state={n:getattr(s,n) for n in ('buttons','x','y','z','r','u','v','pov')} if code==0 else None))
    return results

if __name__=='__main__':print(json.dumps(enumerate_controllers(),indent=2))
