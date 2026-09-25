from pathlib import Path
import re, json, hashlib

root=Path(__file__).resolve().parent.parent
work=root/'work'
out=root/'outputs'
out.mkdir(exist_ok=True)
main=(work/'research-report-draft.md').read_text(encoding='utf8')
main=main.replace('The accompanying audit preserves original source line numbers.',
    'The [complete reference audit](Nioh1-Reference-Line-Audit.md) preserves original source line numbers.')
assert 'link to be finalized' not in main
(out/'Nioh1-Sword-Hideyori-Research.md').write_text(main,encoding='utf8')

ledger=(work/'reference-line-audit.md').read_text(encoding='utf8')
rows=[int(m.group(1)) for m in re.finditer(r'^\| (\d+) \|',ledger,re.M)]
assert rows[:1284]==list(range(1,1285))
assert rows[1284:]==list(range(1,3331))
# Keep XML tags visible as text inside Markdown tables.
ledger=ledger.replace('<','&lt;').replace('>','&gt;')
intro='''# Nioh 1 research: supplied Skills Expanded reference audit

This is an analysis of the user-supplied Nioh 2 reference, not a Nioh 1 mod or a verified Nioh 1 memory map. All 1,284 CT lines and 3,330 XML lines are accounted for below. Opaque fields retain provisional names; line coverage does not claim a complete binary schema. The 10-line readme and single-page PDF were also reviewed. No reference code was run against a game.

Read the [strategy report](Nioh1-Sword-Hideyori-Research.md) for the proposed Nioh 1 implementation. This appendix places technical findings before the exhaustive per-line ledger, keeping the strategy readable.

'''
hashes=json.loads((work/'reference-hashes.json').read_text())
provenance='## Source identity\n\n| Supplied file | SHA-256 |\n|---|---|\n'
provenance+='\n'.join(f'| {name} | `{h}` |' for name,h in hashes.items())+'\n\n'
readme='''## ReadMe.txt: every original line

| Original line | Meaning |
|---:|---|
| 1 | Describes a Nioh 2 CE table adding bindings and unused attack animations. |
| 2 | Blank. |
| 3 | Introduces usage instructions. |
| 4 | Requires the table and SkillConfig.xml in the same folder. |
| 5 | Blank. |
| 6 | Says to start the game, open the table, and select Nioh 2 in CE. |
| 7 | Blank. |
| 8 | Advises against activation during loading; suggests main or mission menu. |
| 9 | Blank/whitespace. |
| 10 | Says to activate Skills Expanded and wait for its scripts. |

## movelist_v0.4.6.pdf: page review

The complete one-page table was extracted and visually inspected. It maps inputs to named skills across all stances, high, mid, and low columns for 11 weapon rows plus Yokai Shift. It identifies Skills Expanded v0.4.6 for Nioh 2 version 1.28.08. There are no numeric attack IDs, addresses, instruction listings, or resource-lifetime rules in the PDF. The supplied CT is v0.4.7, so the PDF is a companion input guide rather than a definitive specification of every current patch.

The sword row describes Swallow's Wing and Living Weapon strong follow-ups, sword Flash Attack after Ki Pulse, high-stance Omnislice/Reverse Impact/Sacred Bird Cry/Living Weapon quick, mid-stance Living Weapon strong/Swift Step/Water Shadow/Sacred Bird Flight, and low-stance Swift Step/Haze. Those names and inputs belong to the Nioh 2 reference. They do not establish Nioh 1 bindings or Hideyori IDs.

'''
ct=(work/'ct-audit.md').read_text(encoding='utf8')
cfg=(work/'config-audit.md').read_text(encoding='utf8')
audit=intro+provenance+ct+'\n\n'+cfg+'\n\n'+readme+ledger
(out/'Nioh1-Reference-Line-Audit.md').write_text(audit,encoding='utf8')
for p in out.glob('*.md'):
    t=p.read_text(encoding='utf8')
    assert '\ufffd' not in t
    print(p.name, 'bytes', p.stat().st_size, 'lines', len(t.splitlines()))
print('Validated exhaustive CT/XML ledger: 1284 + 3330 sequential entries.')
