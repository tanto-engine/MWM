"""External read-only action-object and controller sampler. No CE/debugger APIs."""
import argparse, ctypes as C, json, struct, time
from ctypes import wintypes as W
from pathlib import Path
from nioh_readonly_probe import kernel, modules, read
from check_winmm_controller import winmm, JoyInfo, enumerate_controllers

class Gamepad(C.Structure):
    _fields_=[('buttons',W.WORD),('lt',W.BYTE),('rt',W.BYTE),('lx',C.c_short),('ly',C.c_short),('rx',C.c_short),('ry',C.c_short)]
class State(C.Structure):
    _fields_=[('packet',W.DWORD),('pad',Gamepad)]
assert C.sizeof(State)==16
xinput=C.WinDLL('xinput1_4')
xinput.XInputGetState.argtypes=[W.DWORD,C.POINTER(State)]
xinput.XInputGetState.restype=W.DWORD
kernel.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)]
kernel.GetExitCodeProcess.restype=W.BOOL
button_names={1:'dpad_up',2:'dpad_down',4:'dpad_left',8:'dpad_right',0x10:'start',0x20:'back',0x40:'ls',0x80:'rs',0x100:'lb',0x200:'rb',0x1000:'a',0x2000:'b',0x4000:'x',0x8000:'y'}

def record(config,output,status,seconds,stopfile):
    cfg=json.loads(config.read_text());pid=cfg['pid'];vtable=int(cfg['vtable'],0)
    assert any(m['name'].lower()=='nioh.exe' for m in modules(pid))
    objects=sorted(set(int(o['object'],0) for o in cfg['candidates']))
    assert 0<len(objects)<=256
    h=kernel.OpenProcess(0x410,False,pid)
    if not h:raise C.WinError(C.get_last_error())
    joystick_devices=[d for d in enumerate_controllers() if d['read_result']==0]
    started_wall=time.time();started=time.perf_counter();last={};pads={};seen=set();samples=0;readfails=0;actions=0;inputs=0;button_edges=0;max_gap=0;last_tick=None;connected=set();last_flush=started
    joy_last={};joy_available=set();joy_failures=0
    with output.open('w',encoding='utf8') as f:
        def emit(kind,**fields):
            f.write(json.dumps(dict(t=round(time.perf_counter()-started,6),kind=kind,**fields),separators=(',',':'))+'\n')
        emit('session',pid=pid,mode='external_read_only',objects=[hex(x) for x in objects],requested_interval_ms=10,wall_time=started_wall,perf_counter_origin=started,winmm_devices=joystick_devices,atomic_snapshot=False,input_semantics='OS controller observations; not proof of game-accepted input')
        for device in joystick_devices:emit('input_device',backend='winmm',device=device)
        try:
            while time.perf_counter()-started<seconds and not(stopfile and stopfile.exists()):
                now=time.perf_counter();iteration_started=now
                if last_tick is not None:max_gap=max(max_gap,now-last_tick)
                last_tick=now
                exitcode=W.DWORD()
                if not kernel.GetExitCodeProcess(h,C.byref(exitcode)) or exitcode.value!=259:
                    emit('process_exit',code=exitcode.value);break
                for port in range(4):
                    s=State();ok=xinput.XInputGetState(port,C.byref(s))==0
                    if not ok:
                        if port in connected:emit('controller_disconnected',port=port);connected.remove(port)
                        continue
                    connected.add(port);p=s.pad
                    key=(p.buttons,p.lt//16,p.rt//16,p.lx//4096,p.ly//4096,p.rx//4096,p.ry//4096)
                    if pads.get(port)!=key:
                        emit('input',backend='xinput',port=port,packet=s.packet,buttons=p.buttons,down=[name for mask,name in button_names.items() if p.buttons&mask],lt=p.lt,rt=p.rt,lx=p.lx,ly=p.ly,rx=p.rx,ry=p.ry)
                        pads[port]=key;inputs+=1
                for device in joystick_devices:
                    slot=device['slot'];j=JoyInfo();j.size=C.sizeof(j);j.flags=0xff
                    code=winmm.joyGetPosEx(slot,C.byref(j))
                    if code:
                        joy_failures+=1
                        if joy_last.get(slot)!=('error',code):emit('input_unavailable',backend='winmm',slot=slot,code=code)
                        joy_last[slot]=('error',code);joy_available.discard(slot);continue
                    joy_available.add(slot)
                    axes={name:getattr(j,name) for name in ('x','y','z','r','u','v')}
                    key=(j.buttons,j.pov,*[round((v-32767)/4096) for v in axes.values()])
                    if joy_last.get(slot)!=key:
                        before=joy_last.get(slot)
                        old=before[0] if before and isinstance(before[0],int) else None
                        pressed=j.buttons&~old if old is not None else None
                        released=old&~j.buttons if old is not None else None
                        if pressed is not None:button_edges+=pressed.bit_count()+released.bit_count()
                        emit('input',backend='winmm',slot=slot,buttons=j.buttons,buttons_down=[i+1 for i in range(32) if j.buttons&(1<<i)],pressed_mask=pressed,released_mask=released,pov=j.pov,axes=axes)
                        joy_last[slot]=key;inputs+=1
                for obj in objects:
                    try:
                        b=read(h,obj,0xE8)
                        if struct.unpack_from('<Q',b)[0]!=vtable:
                            if last.get(obj)!='invalid':emit('object_invalid',object=hex(obj));last[obj]='invalid'
                            continue
                        owner,cur,prev=struct.unpack_from('<QQQ',b,0x50)
                        idx,pidx=struct.unpack_from('<II',b,0x68)
                        pending=struct.unpack_from('<Q',b,0xB0)[0]
                        counter=struct.unpack_from('<I',b,0xDC)[0]
                        key=(owner,cur,prev,idx,pidx,pending,counter)
                        if last.get(obj)==key:continue
                        desc=None
                        if cur:
                            d=read(h,cur,0xD0)
                            desc=dict(word0=struct.unpack_from('<H',d)[0],payload=hex(struct.unpack_from('<Q',d,0x20)[0]))
                            descriptor_key=(cur,d)
                            if descriptor_key not in seen:
                                emit('descriptor',address=hex(cur),bytes=d.hex());seen.add(descriptor_key)
                        emit('action_state',object=hex(obj),owner_like=hex(owner),current=hex(cur),previous=hex(prev),index=idx,previous_index=pidx,pending=hex(pending),counter=counter,descriptor=desc)
                        last[obj]=key;actions+=1
                    except OSError:
                        readfails+=1
                        if last.get(obj)!='unreadable':emit('object_unreadable',object=hex(obj));last[obj]='unreadable'
                samples+=1
                now=time.perf_counter()
                if now-last_flush>=1:
                    f.flush()
                    info=dict(pid=pid,seconds=round(now-started,2),samples=samples,action_events=actions,input_events=inputs,button_edges=button_edges,controller_ports=sorted(connected),winmm_slots=sorted(joy_available),controller_read_failures=joy_failures,read_failures=readfails,max_sample_gap_ms=round(max_gap*1000,2),running=True)
                    status.write_text(json.dumps(info),encoding='utf8');last_flush=now
                time.sleep(max(0,0.010-(time.perf_counter()-iteration_started)))
        finally:
            info=dict(pid=pid,seconds=round(time.perf_counter()-started,2),samples=samples,action_events=actions,input_events=inputs,button_edges=button_edges,controller_ports=sorted(connected),winmm_slots=sorted(joy_available),controller_read_failures=joy_failures,read_failures=readfails,max_sample_gap_ms=round(max_gap*1000,2),running=False)
            emit('end',**info);status.write_text(json.dumps(info),encoding='utf8');kernel.CloseHandle(h)
    print(json.dumps(info),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--status',type=Path,required=True);p.add_argument('--seconds',type=float,default=300);p.add_argument('--stopfile',type=Path);a=p.parse_args()
    record(a.config,a.output,a.status,a.seconds,a.stopfile)
