from pathlib import Path
import struct, hashlib, json, os
from pypdf import PdfReader

out = Path(__file__).parent
game = Path(os.environ.get('NIOH_EXE', r'C:\Program Files (x86)\Steam\steamapps\common\Nioh\nioh.exe'))
b = game.read_bytes()
u16 = lambda p: (
    # Decode one unsigned 16-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from('<H', b, p)[0])
u32 = lambda p: (
    # Decode one unsigned 32-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from('<I', b, p)[0])
u64 = lambda p: (
    # Decode one unsigned 64-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from('<Q', b, p)[0])
pe = u32(0x3c)
assert b[pe:pe+4] == b'PE\0\0'
opt = pe + 24
assert u16(opt) == 0x20b
sections = []
for i in range(u16(pe+6)):
    p = opt + u16(pe+20) + 40*i
    sections.append(dict(name=b[p:p+8].rstrip(b'\0').decode(),virtual_size=u32(p+8),rva=u32(p+12),raw_size=u32(p+16),raw=u32(p+20)))
def offset(rva):
    # Translate a PE RVA through section or header ranges.
    # Return its corresponding offset in the local file image.
    # Reject addresses that cannot be attributed to an image range.
    for s in sections:
        if s['rva'] <= rva < s['rva']+max(s['virtual_size'],s['raw_size']):
            return s['raw'] + rva-s['rva']
    if rva < u32(opt+60): return rva
    raise ValueError(hex(rva))
def string(p):
    # Decode a null-terminated import name from the local image.
    # Keep undecodable bytes visible through replacement characters.
    # Support import-table inventory without loading executable code.
    return b[p:b.index(b'\0',p)].decode('ascii',errors='replace')
imports = {}
imp_rva = u32(opt+112+8)
if imp_rva:
    p = offset(imp_rva)
    while any(b[p:p+20]):
        original, _, _, name, first = struct.unpack_from('<IIIII',b,p)
        name = string(offset(name))
        t = offset(original or first)
        funcs = []
        while u64(t):
            v = u64(t)
            funcs.append('#'+str(v & 0xffff) if v >> 63 else string(offset(v)+2))
            t += 8
        imports[name] = funcs
        p += 20
report = dict(path=str(game),size=len(b),sha256=hashlib.sha256(b).hexdigest(),machine=hex(u16(pe+4)),pe_magic=hex(u16(opt)),timestamp=u32(pe+8),image_base=hex(u64(opt+24)),size_of_image=hex(u32(opt+56)),dll_characteristics=hex(u16(opt+70)),sections=sections,imports=imports,delay_import_rva=hex(u32(opt+112+8*13)))
(out/'local-binary.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ['imports','sections']},indent=2))
print('IMPORTS',json.dumps(imports,indent=2))
ref=Path(os.environ.get('NIOH2_REFERENCE', Path.home() / 'Downloads/skill expanded mod'))
r=PdfReader(ref/'movelist_v0.4.6.pdf')
text='\n\n'.join(f'PAGE {i+1}\n'+p.extract_text() for i,p in enumerate(r.pages))
(out/'reference-movelist.txt').write_text(text,encoding='utf8')
print('PDF pages',len(r.pages),'characters',len(text))
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ref.iterdir() if p.is_file()}
(out/'reference-hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf8')
