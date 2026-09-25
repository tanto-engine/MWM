from pathlib import Path
from collections import Counter, defaultdict
import re, json, xml.etree.ElementTree as ET, hashlib, html, os

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get('NIOH2_REFERENCE', Path.home() / 'Downloads/skill expanded mod'))
ctfile = SRC / 'Nioh2_SE_1.28.08_v0.4.7.CT'
cfgfile = SRC / 'SkillConfig.xml'
ct = ctfile.read_text(encoding='utf-8-sig').splitlines()
cfg = cfgfile.read_text(encoding='utf-8-sig').splitlines()
ET.parse(ctfile)
tree = ET.parse(cfgfile)
groups=[]; records=[]; actions=[]; issues=[]; current=None; in_comment=False
cfg_rows=[]
word = lambda b,i: int.from_bytes(b[i:i+2], 'little')
for n, raw in enumerate(cfg,1):
    s=raw.strip()
    enabled_code = re.sub(r'<!--.*?-->', '', s)
    m=re.search(r'<ActionGroup\s+name="([^"]+)"\s+enable="([^"]+)"', enabled_code)
    if m:
        current={'name':m[1], 'enabled':m[2].lower()=='true', 'line':n, 'records':[], 'actions':[]}
        groups.append(current)
        desc=f'Open group {m[1]}; enabled={m[2]}.'
    elif re.search(r'<Skill\s+value=', enabled_code):
        v=re.search(r'<Skill\s+value="([^"]+)"', enabled_code)[1]
        tokens=v.split(); malformed=[x for x in tokens if not re.fullmatch(r'[0-9A-Fa-f]{2}',x)]
        if malformed: issues.append({'line':n,'issue':'Invalid hex byte token','values':malformed})
        b=bytes.fromhex(v)
        if len(b)!=55: issues.append({'line':n,'issue':'Wrong packed record width','length':len(b)})
        comment=' '.join(re.findall(r'<!--(.*?)-->',s)).strip()
        rec={'line':n,'group':current['name'],'enabled':current['enabled'],'width':len(b),'bytes':b.hex(' '), 'comment':comment,
             'selector2':word(b,2),'marker4':b[4], 'modeA':b[10], 'inputB_E':b[11:15].hex(' '),
             'word14':word(b,20),'word16':word(b,22),'word20':word(b,32),'word22':word(b,34),'word2C':word(b,44)}
        records.append(rec);current['records'].append(n)
        desc=(f'Packed skill {len(b)} bytes; selector@+02={word(b,2):04X}; marker@+04={b[4]:02X}; mode@+0A={b[10]:02X}; '
              f'input-like bytes@+0B..0E={b[11:15].hex(" ").upper()}; target-like u16@+14={word(b,20):04X}; '
              f'u16@+16={word(b,22):04X}; window-like u16@+20/+22={word(b,32)}/{word(b,34)}; hook u16@+2C={word(b,44):04X}. '
              f'Author comment: {comment or "none"}.')
    elif re.search(r'<Action\s+id=', enabled_code):
        m=re.search(r'<Action\s+id="([^"]+)"\s+length="([^"]+)"\s+numSkills="([^"]+)"', enabled_code)
        if not m:
            issues.append({'line':n,'issue':'Does not match CT attribute order'});desc='Action does not match expected CT parser syntax.'
        else:
            a={'line':n, 'group':current['name'], 'enabled':current['enabled'], 'offset':int(m[1],16),'length':int(m[2]),'numSkills':int(m[3])}
            actions.append(a);current['actions'].append(n)
            desc=f'Target SkillBase+0x{a["offset"]:X}; prepend first {a["numSkills"]} group records to {a["length"]} descriptor(s), stride 0x60. XML id is an offset, length is a descriptor count.'
            if a['numSkills']>len(current['records']): issues.append({'line':n,'issue':'numSkills exceeds group records'})
            if a['numSkills']<1 or a['length']<1: issues.append({'line':n,'issue':'Nonpositive descriptor or skill count'})
    elif not s: desc='Blank formatting line; no runtime effect.'
    elif s.startswith('<!--'): desc='XML author comment (not a parsed skill): '+re.sub(r'<!--|-->','',s).strip()
    elif s.startswith('<?xml'): desc='XML declaration; UTF-8.'
    elif s=='<Skills>':desc='Open group skill-record list.'
    elif s=='</Skills>':desc='Close group skill-record list.'
    elif s=='<Actions>':desc='Open target descriptor list.'
    elif s=='</Actions>':desc='Close target descriptor list.'
    elif s=='</ActionGroup>':desc='Close group '+current['name']+'.'
    elif s=='<SkillConfig>':desc='Open document root.'
    elif s=='</SkillConfig>':desc='Close document root.'
    else:desc='Other XML/text: '+s;issues.append({'line':n,'issue':'Unclassified line','text':s})
    cfg_rows.append((n,desc))

targets=defaultdict(list)
for a in actions:
    if a['enabled']:
        for k in range(a['length']):targets[a['offset']+0x60*k].append(a['line'])
overlaps={hex(k):v for k,v in targets.items() if len(v)>1}
statistics={'ct_lines':len(ct),'config_lines':len(cfg),'config_groups':len(groups), 'enabled_groups':sum(g['enabled'] for g in groups),
    'skill_records':len(records),'enabled_skill_records':sum(r['enabled'] for r in records),
    'action_rows':len(actions),'descriptor_assignments':sum(a['length'] for a in actions if a['enabled']),
    'unique_enabled_descriptors':len(targets),'record_width_counts':dict(Counter(r['width'] for r in records)),
    'marker_counts':dict(Counter(f'{r["marker4"]:02X}' for r in records)), 'validation_issues':issues,'overlapping_descriptors':overlaps,
    'groups':groups,'records':records,'actions':actions,
    'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ctfile,cfgfile)}}
(ROOT/'work/config-analysis.json').write_text(json.dumps(statistics,indent=2),encoding='utf-8')

# The entire CT was already manually read. Per-line entries preserve the exact statement,
# with semantic annotations; long bulk byte literals are replaced with their validated length.
ct_notes={17:'Define lookup by parameter-table name.',21:'Define hexadecimal byte-string splitter.',29:'Define sign helper (unused here).',33:'Define rounding helper (unused here).',38:'Define decimal-to-hex helper (unused here).',48:'Define raw patch transaction; captures originals by target address.',61:'Define restore of a named raw patch set.',68:'Define repeated 64-bit pointer dereference.',82:'Define unused speed-pointer helper.',86:'Initialize the parameter-base registry.',89:'Find PC-root signature in executable memory.',94:'Interpret bracketed disassembly operand as PC-root address.',96:'Resolve Nioh 2 skill-data root using six dereferences and +0x50.',99:'Find action-root signature.',103:'Resolve action-data root with three dereferences.',105:'Find buff-root signature.',109:'Resolve buff-data root with three dereferences and +8.',111:'Late failure diagnostic only; does not abort preceding dereferences.',116:'Scan original callback site for skill gate hook.',119:'Allocate combined hook-code/data storage in target process.',124:'Actor discriminator comparison; literal 64 is assembler syntax.',125:'Commented-out branch; no runtime effect.',127:'EF marker forces successful skill-gate return.',129:'FD marker forces unsuccessful skill-gate return via npc label.',131:'Skill-specific 16-bit code test; comment names Cloudcrush.',135:'Entity byte comparison used for mid-vs-other branch.',174:'Branch that forces AL to one.',179:'Misleadingly named branch only forces AL to zero; not a boss importer.',183:'Expose record+0x2C 16-bit code in r9.',187:'Start data-storage label; injected records begin +8 later.',189:'Patch original callback and test with detour.',195:'Begin root teardown.',197:'Restore original indirect callback.',200:'Wildcard symbol cleanup statement.',201:'Wildcard allocation cleanup statement.',214:'Relative config path depends on working directory.',216:'First record written eight bytes after data label.',217:'First skill-pointer source initially same location.',221:'Define local text-file reader.',232:'Define schema-specific Lua-pattern parser.',236:'Attempt XML comment removal via a Lua pattern.',239:'Requires group name then enable attributes and fixed section order.',241:'Only case-insensitive true groups are injected.',245:'Extract skill literal attribute.',250:'Requires Action id, length, numSkills attributes in that order.',263:'Define write of one packed record.',266:'Advance destination by exactly 55 decimal bytes.',269:'Define descriptor-list replacement.',270:'Interpret XML id as byte offset relative to SkillBase.',271:'Repeat descriptor count; this is not an animation frame length.',272:'Backup first 11 descriptor bytes for restore.',274:'Read pointer to native skill-pointer array.',275:'Read 16-bit array starting index.',276:'Read one-byte native skill count.',280:'Prepend N new skill-record pointers.',281:'Store pointer to injected record.',283:'Advance packed record source by 55 bytes.',286:'Copy old skill-record pointers after new pointers.',292:'Replace descriptor pointer with new array.',293:'Reset descriptor starting index to zero.',294:'Store increased count in one byte without overflow guard.',296:'Next descriptor is 0x60 bytes later.',297:'Reset skills pointer for repeated descriptor.',301:'Define restore of descriptor backups.',312:'First pass writes all group skill records.',324:'Second pass patches descriptor lists.',327:'Count records in this group.',329:'Skip group with no records.',338:'Parse number of prefix skill records.',340:'Reject nonpositive skill count.',342:'Reject requested prefix longer than group.',345:'Convert id from hex; pass length and count to injector.',352:'Advance source by full group record count.',363:'Restore descriptor bytes on disabling config entry.',464:'Store PC-root address in leading qword; unused by this CT later.',992:'Define Extras patch list; it is never applied in this CT.',1003:'Apply KiUsage only.',1004:'Apply DamageProp only; Extras is omitted.',1121:'Scan injected record arena for one specific record.',1123:'Change special hook marker at record+4.',1125:'Change 16-bit special skill code at record+0x2C.',1129:'Hardcoded restoration of marker.',1131:'Hardcoded restoration of special skill code.',1149:'Scan second callback site for accidental-aim prevention.',1156:'Call original callback before overriding result.',1157:'Apply actor discriminator.',1159:'Apply 16-bit action-like discriminator.',1162:'Apply nested single-byte state/input discriminator.',1164:'Force zero callback result.',1167:'Install detour at original six-byte call.',1173:'Restore original six-byte indirect call.',1189:'Define selected per-move speed-related writes, not universal speed API.',1199:'Define ActionBase property writes.',1204:'Define BuffBase duration write.',1238:'Scan injected records for optional move mutation.',1240:'Replace three bytes of target-like field.',1265:'Hardcoded restoration of target-like field.',1281:'Add Nioh 2 executable to CE auto-attach list.'}

ct_rows=[]
for n,raw in enumerate(ct,1):
    s=html.unescape(raw.strip())
    if n in ct_notes:desc=ct_notes[n]+' Statement: '+s
    elif not s:desc='Blank formatting line; no runtime effect.'
    elif s.startswith(('--','//')):desc='Comment only: '+s.lstrip('-/').strip()
    elif re.match(r"\{0x[^,]+,\s*'",s):
        m=re.match(r"\{([^,]+),\s*'([^']+)'\},?\s*(.*)",s)
        if m:
            size=len(m[2].split()); literal=m[2] if size<20 else f'[{size} literal bytes; complete bytes remain in supplied source]'
            desc=f'Raw data patch at current named base + ({m[1]}), {size} byte(s): {literal}. '+m[3].lstrip('-').strip()
        else:desc='Data patch row: '+s
    elif s.startswith('ParamPatcher('):desc='Apply named raw-byte patch set: '+s
    elif s.startswith('ParamDepatcher('):desc='Restore named raw-byte patch set: '+s
    elif s.startswith('<') and not '<AssemblerScript>' in s and not '<LuaScript>' in s:desc='Cheat-table XML metadata/structure: '+s
    elif s in ('end','end;','}', '}', '{$lua}', '{$asm}', '[ENABLE]','[DISABLE]'):desc='Language/control-block boundary: '+s
    elif s.startswith(('if ','elseif ','else','for ','goto ','::')):desc='Control flow: '+s
    elif s.startswith(('read','write','return ','local ','function ')):desc='Lua data/function operation: '+s
    elif re.match(r'^(cmp|jne|je|jmp|mov|movzx|test|xor|call|nop|db|aobscan|registersymbol|unregistersymbol|dealloc|alloc|label)',s):desc='Assembler operation: '+s
    else:desc='Source statement: '+s
    ct_rows.append((n,desc))

def esc(s):return s.replace('|','\\|').replace('\n',' ')
out=['# Reference line audit', '', 'This ledger accounts for every physical line of both supplied source files. CT code was manually read without execution. Every XML line was classified, every Skill literal was decoded and validated, and every Action target was checked statically. Long repeated bytes are summarized rather than copied. Raw parameter values are not assigned semantics beyond the CT code and author comments; `target-like` and `window-like` are explicit hypotheses.', '', 'The source files were not edited. No game process was accessed. See the companion research report for conclusions and caveats.', '', '## CT: Nioh2_SE_1.28.08_v0.4.7.CT', '', '| Original line | Annotation |','|---:|---|']
out += [f'| {n} | {esc(d)} |' for n,d in ct_rows]
out += ['', '## XML: SkillConfig.xml', '', 'All offsets are record-relative hexadecimal; decoded paired words are little-endian interpretations for inspection. Only word reads at +0x14 and +0x2C and byte read +4 are directly established by the CT hook; other labels reflect patterns in the configuration and require runtime confirmation. Numbers shown for +0x20/+0x22 are decimal for ease of comparing adjacent windows.', '', '| Original line | Annotation |','|---:|---|']
out += [f'| {n} | {esc(d)} |' for n,d in cfg_rows]
(ROOT/'work/reference-line-audit.md').write_text('\n'.join(out)+'\n',encoding='utf-8')

# Compact review stream: every non-structural source line, with structural coverage
# proven by the complete ledger and machine validation, plus all group boundaries.
review=[]
recmap={r['line']:r for r in records}; amap={a['line']:a for a in actions};gmap={g['line']:g for g in groups}
for n,s in enumerate(cfg,1):
    if n in gmap:review.append(f'{n} GROUP {gmap[n]["name"]} enabled={gmap[n]["enabled"]}')
    elif n in recmap:
        r=recmap[n];review.append(f'{n} S {r["width"]}B sel={r["selector2"]:04X} mk={r["marker4"]:02X} mode={r["modeA"]:02X} in={r["inputB_E"]} dst={r["word14"]:04X}/{r["word16"]:04X} win={r["word20"]}/{r["word22"]} skill={r["word2C"]:04X} {r["comment"]}')
    elif n in amap:
        a=amap[n];review.append(f'{n} A base+{a["offset"]:X} rows={a["length"]} firstN={a["numSkills"]}')
    elif s.strip().startswith('<!--'):review.append(f'{n} COMMENT {s.strip()}')
(ROOT/'work/config-review.txt').write_text('\n'.join(review)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in statistics.items() if k not in ('groups','records','actions')},indent=2))
print('Review stream lines:',len(review),'Ledger CT rows:',len(ct_rows),'Ledger config rows:',len(cfg_rows))
