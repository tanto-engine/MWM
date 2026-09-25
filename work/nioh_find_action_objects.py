"""One read-only heap search for the observed native action-node vtable."""
import argparse, ctypes as C, json, struct, time
from pathlib import Path
from nioh_readonly_probe import kernel, modules, read, MEMORY_BASIC_INFORMATION

def discover(pid,vtable):
    assert any(m['name'].lower()=='nioh.exe' for m in modules(pid))
    h=kernel.OpenProcess(0x410,False,pid)
    if not h: raise C.WinError(C.get_last_error())
    started=time.perf_counter(); regions=[]; cursor=0; candidates=[]; failures=0; scanned=0
    try:
        while True:
            mbi=MEMORY_BASIC_INFORMATION()
            if not kernel.VirtualQueryEx(h,cursor,C.byref(mbi),C.sizeof(mbi)): break
            stop=(mbi.BaseAddress or 0)+mbi.RegionSize
            if stop<=cursor: break
            if mbi.State==0x1000 and mbi.Type==0x20000 and mbi.Protect&0xff in (4,8,0x40,0x80) and not mbi.Protect&0x100:
                regions.append((mbi.BaseAddress,mbi.RegionSize))
            cursor=stop
        print('Private writable committed bytes:',sum(s for a,s in regions), 'regions:',len(regions),flush=True)
        needle=struct.pack('<Q',vtable)
        for address,size in regions:
            tail=b''
            for delta in range(0,size,1024*1024):
                at=address+delta;n=min(1024*1024,size-delta)
                try: chunk=read(h,at,n)
                except OSError: failures+=1;tail=b'';continue
                data=tail+chunk;pos=0
                while True:
                    i=data.find(needle,pos)
                    if i<0: break
                    pos=i+1; obj=at-len(tail)+i
                    if obj%8: continue
                    try:
                        b=read(h,obj,0x110)
                        q=lambda o:struct.unpack_from('<Q',b,o)[0]
                        u=lambda o:struct.unpack_from('<I',b,o)[0]
                        current=q(0x58); previous=q(0x60)
                        item=dict(object=hex(obj),owner_like=hex(q(0x50)),current=hex(current),previous=hex(previous),current_index=u(0x68),previous_index=u(0x6c),object_bytes=b.hex(' '))
                        if current:
                            d=read(h,current,0x28)
                            item['current_word0']=struct.unpack_from('<H',d)[0]
                            item['current_payload']=hex(struct.unpack_from('<Q',d,0x20)[0])
                        candidates.append(item)
                    except OSError: pass
                scanned+=len(chunk);tail=data[-7:]
                time.sleep(0.001)
        return dict(pid=pid,vtable=hex(vtable),seconds=time.perf_counter()-started,bytes_scanned=scanned,failed_chunks=failures,candidates=candidates)
    finally:kernel.CloseHandle(h)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',required=True,type=int);p.add_argument('--vtable',required=True,type=lambda x:int(x,0));p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r=discover(a.pid,a.vtable);a.output.write_text(json.dumps(r,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in r.items() if k!='candidates'},indent=2))
    print('Candidates:',len(r['candidates']))
    print(json.dumps([{k:v for k,v in c.items() if k!='object_bytes'} for c in r['candidates'][:30]],indent=2))
