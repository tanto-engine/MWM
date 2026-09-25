import bisect, hashlib, json, pathlib, struct, subprocess, os, shutil

EXE=pathlib.Path(os.environ.get('NIOH_EXE', r'C:\Program Files (x86)\Steam\steamapps\common\Nioh\nioh.exe'))
OUT=pathlib.Path(__file__).parent / 'action-callers'
OUT.mkdir(exist_ok=True)
data=EXE.read_bytes()
pe=struct.unpack_from('<I', data, 0x3c)[0]
count=struct.unpack_from('<H', data, pe+6)[0]
optsz=struct.unpack_from('<H', data, pe+20)[0]
base=struct.unpack_from('<Q',data,pe+24+24)[0]
sections=[]
for i in range(count):
    off=pe+24+optsz+40*i
    name=data[off:off+8].split(b'\0')[0].decode()
    vs,va,rs,rp=struct.unpack_from('<IIII',data,off+8)
    sections.append(dict(name=name,rva=va,vsize=vs,size=rs,offset=rp))
def read(rva,n):
    # Translate an image-relative address into a PE section's file offset.
    # Read the requested bytes from the local executable image.
    # Support offline caller analysis without opening a game process.
    s=next(s for s in sections if s['rva']<=rva<s['rva']+max(s['size'],s['vsize']))
    offset=s['offset']+rva-s['rva']
    return data[offset:offset+n]
pdata=next(s for s in sections if s['name']=='.pdata')
functions=[struct.unpack_from('<III',data,o) for o in range(pdata['offset'],pdata['offset']+pdata['size']-11,12)]
functions=sorted((a,b,u) for a,b,u in functions if a and b>a)
starts=[f[0] for f in functions]
def function_at(rva):
    # Locate the unwind-table interval containing an instruction RVA.
    # Use binary search over ordered function starts.
    # Avoid scanning every function for each call-site candidate.
    i=bisect.bisect_right(starts,rva)-1
    return functions[i] if i>=0 and functions[i][0]<=rva<functions[i][1] else None
def references(target):
    # Find relative call and jump encodings aimed at a target RVA.
    # Compute signed displacements within the executable text section.
    # Report candidates for disassembly rather than claiming every byte is code.
    text=next(s for s in sections if s['name']=='.text')
    blob=data[text['offset']:text['offset']+text['size']]
    hits=[]
    for i,byte in enumerate(blob[:-4]):
        if byte in (0xe8,0xe9):
            rva=text['rva']+i
            dest=rva+5+struct.unpack_from('<i',blob,i+1)[0]
            if dest==target:
                hits.append(dict(rva=hex(rva),opcode=hex(byte),function=function_at(rva)))
    return hits
OBJDUMP=os.environ.get('OBJDUMP') or shutil.which('objdump') or str(pathlib.Path.home() / 'AppData/Local/Scoop/apps/gcc/current/bin/objdump.exe')
def disasm(begin,end,label):
    # Write a bounded function slice and decode it with objdump.
    # Retain the image-relative address base in the text output.
    # Make candidate caller behavior inspectable offline.
    binary=OUT/(label+'.bin')
    binary.write_bytes(read(begin,end-begin))
    result=subprocess.run([OBJDUMP,'-D','-b','binary','-m','i386:x86-64','-M','intel','--adjust-vma='+hex(begin),str(binary)],capture_output=True,text=True,check=True).stdout
    (OUT/(label+'.txt')).write_text(result)
    return result
if __name__=='__main__':
    import sys
    target=int(sys.argv[1],0) if len(sys.argv)>1 else 0x7119c0
    hits=references(target)
    report=dict(sha256=hashlib.sha256(data).hexdigest(),image_base=hex(base),sections=sections,target=hex(target),references=hits)
    (OUT/('refs-'+hex(target)+'.json')).write_text(json.dumps(report,indent=2))
    for hit in hits:
        f=hit['function']
        if f and f[1]-f[0]<200000:
            disasm(f[0],f[1],hex(f[0]))
    print(json.dumps(report,indent=2))
