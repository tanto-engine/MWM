# Read-only search for object layouts using native function-pointer references.
import argparse, ctypes as C, json, struct
from pathlib import Path
from nioh_readonly_probe import kernel, modules, read

def inspect(pid):
    # Find read-only function-pointer arrays near the action setter reference.
    # Inspect RTTI and class hierarchy candidates for related action-node types.
    # Retain hypotheses as research evidence instead of assigning actor roles.
    main=next(m for m in modules(pid) if m['name'].lower()=='nioh.exe')
    h=kernel.OpenProcess(0x410,False,pid)
    if not h: raise C.WinError(C.get_last_error())
    try:
        base=main['base']; hdr=read(h,base,4096)
        pe=struct.unpack_from('<I',hdr,0x3c)[0]
        n=struct.unpack_from('<H',hdr,pe+6)[0]
        start=pe+24+struct.unpack_from('<H',hdr,pe+20)[0]
        sections=[]
        for i in range(n):
            p=start+i*40
            size,rva=struct.unpack_from('<II',hdr,p+8)
            flags=struct.unpack_from('<I',hdr,p+36)[0]
            sections.append(dict(name=hdr[p:p+8].rstrip(b'\0').decode(),start=base+rva,size=size,execute=bool(flags&0x20000000)))
        code=[s for s in sections if s['execute']]
        def executable(a):
            # Check whether a pointer falls inside an executable image section.
            # Use the section ranges already read from the PE header.
            # Bound candidate vtable runs to pointers that could reference code.
            return any(s['start']<=a<s['start']+s['size'] for s in code)
        results=[]; common_type=None; derived=[]
        function=base+0x7119c0
        for s in sections:
            if s['name']!='.rdata': continue
            data=read(h,s['start'],s['size'])
            needle=struct.pack('<Q',function); pos=0
            while True:
                i=data.find(needle,pos)
                if i<0: break
                pos=i+1
                if i%8: continue
                lo=hi=i
                while lo>=8 and executable(struct.unpack_from('<Q',data,lo-8)[0]): lo-=8
                while hi+16<=len(data) and executable(struct.unpack_from('<Q',data,hi+8)[0]): hi+=8
                item=dict(reference=hex(s['start']+i),candidate_vtable=hex(s['start']+lo),method_slot=(i-lo)//8,slots=(hi-lo)//8+1)
                if lo>=8:
                    locator=struct.unpack_from('<Q',data,lo-8)[0]
                    try:
                        col=read(h,locator,24)
                        sig,offset,cd,td,chd,selfrva=struct.unpack('<6I',col)
                        if sig==1 and base+selfrva==locator:
                            name=read(h,base+td+16,192).split(b'\0',1)[0].decode('ascii',errors='replace')
                            item.update(rtti_name=name,subobject_offset=offset)
                            if name=='.?AVCActModuleActionMotNodeCommon@@': common_type=td
                    except OSError: pass
                results.append(item)
            if common_type is not None:
                srva=s['start']-base
                def in_rdata(r,n=4):
                    # Check whether a relative span is contained in the sampled rdata section.
                    # Include the requested size in the upper-bound comparison.
                    # Avoid decoding RTTI arrays beyond the captured section bytes.
                    return srva<=r and r+n<=srva+len(data)
                def word(r):
                    # Decode one little-endian DWORD from the sampled rdata section.
                    # Translate the image RVA into the section-relative offset.
                    # Share the checked RTTI layout interpretation within this inspection.
                    return struct.unpack_from('<I',data,r-srva)[0]
                pos=0
                while True:
                    pos=data.find(b'\x01\x00\x00\x00',pos)
                    if pos<0: break
                    at=pos;pos+=4
                    if at%4 or at+24>len(data): continue
                    sig,off,cd,td,chd,selfrva=struct.unpack_from('<6I',data,at)
                    if selfrva!=srva+at or not in_rdata(chd,16): continue
                    count=word(chd+8);array=word(chd+12)
                    if not 0<count<128 or not in_rdata(array,count*4): continue
                    types=[]
                    for n in range(count):
                        bcd=word(array+n*4)
                        if in_rdata(bcd):types.append(word(bcd))
                    if common_type not in types: continue
                    loc=s['start']+at;ref=0
                    while True:
                        ref=data.find(struct.pack('<Q',loc),ref)
                        if ref<0: break
                        vt=s['start']+ref+8;ref+=8
                        try: name=read(h,base+td+16,192).split(b'\0',1)[0].decode('ascii',errors='replace')
                        except OSError:name='unreadable'
                        derived.append(dict(candidate_vtable=hex(vt),rtti_name=name,subobject_offset=off))
        return dict(pid=pid,base=hex(base),function=hex(function),references=results,derived_vtables=derived)
    finally: kernel.CloseHandle(h)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',required=True,type=int);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result=inspect(a.pid);a.output.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
