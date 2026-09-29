# New sword recording intake

The Downloads batch has 81 Recorder folders and one RAR. Eleven Edward Kelley folders are excluded. The remaining 70 folders are indexed here: 15 older sessions plus 55 newly added sessions. The RAR's 132 files are byte-identical to the corresponding folders, so it creates no extra takes. Raw evidence for every retained folder is stored as a hash-named ZIP; no Edward Kelley bytes or move definitions were imported.

The new sessions contain 55 sword annotations. Each has a named record under `weapons/sword/<boss>/`, a matching non-selectable entry in `data/moves.json`, and an exact annotation/archive reference in `intake.json`. One new Otani Yoshitsugu session has no saved move description; its raw capture is retained without inventing a move. The `recorded_` ID suffix ties each candidate to its annotation, so similar names do not silently collapse into one action.

Across the full non-Edward-Kelley batch, 70 indexed sessions contain 68 saved annotations: 67 sword records and one handgun record. The 13 older selected records have 13 distinct boss-scoped action/motion/timing sequences; the 55 newer sword notes have no selected actor/phase sequence yet. Their journals contain 156,978 action-state rows and 6,329 metadata rows, all marked `role: unassigned`. Excluding idle action key zero, those metadata rows expose 1,085 distinct boss-scoped action/motion/timing triples, or 1,101 when the payload prefix is also distinguished. These are observed action identities across whole encounters, not 1,085 identified moves. No two saved notes have identical text within the same boss, and no two journals have identical bytes. Of the 70 sessions, two manifest-only folders lack journals, and one annotated Toyotomi take is missing from its journal.

| Boss | New annotated sword candidates |
| --- | ---: |
| Hattori Hanzo | 6 |
| Ishida Mitsunari | 8 |
| Maria | 13 |
| Oda Nobunaga | 9 |
| Tachibana Muneshige | 11 |
| Toyotomi Hideyori | 8 |
| **Total** | **55** |

## Why these are not selectable yet

The Recorder's new metadata labels observed actors `unassigned`. A boss name is encounter context, not proof that an action belongs to that boss. The 55 annotations describe what the player saw, but do not identify exact start/end phases or prove their inputs work on William. Source action, motion and timing fields in their product catalogue entries therefore remain null. Every candidate is blocked on actor/phase review, matching installed motion and timing resources, a William adapter, and gameplay acceptance. One Toyotomi annotation (`Dodge Forward Double Stab Into Downward/Upward Double Slash`) references take `3cf8b979-70c1-493a-920b-139abb7bcacf`, which is missing from its saved `events.jsonl`; it is additionally marked `recorded_take_missing`.

The notes report four grabs/grapples, eight projectile/summon/ranged effects, and three buffs. One of the eight is explicitly a bow-shot sequence. These categories come from the descriptions, not verified source type decoding. Their paired actors, external resources and weapon-specific behavior need separate review before they can be routed through a sword input. No new source family is claimed supported.

## Conflicts and existing graphs

The new journals contain 858 distinct nonzero action keys scoped by the named encounter. Forty-three keys have multiple full payload signatures; 36 also have multiple motion IDs. Across old and new journals together, 1,025 nonzero boss-scoped action keys were observed and 56 have multiple action/motion/timing/payload signatures. `signature-review.json` records conflicts from the new intake; it does not cover the older curated sessions. These may belong to different actors in one encounter. Keys shared *between* bosses are separate identities; keys conflicting *within* one named encounter remain unresolved until actor ownership is established. None was merged by short action number.

`unmapped-action-index.json` contains all 918 nonzero action/motion/timing/payload signatures observed in the 55 unmapped sessions, including the unannotated Otani capture. Each row retains its encounter label, first recording and journal line, all recording IDs, and observation count. This is a research index of unassigned actors; it does not classify an action as a boss move or even a sword action. Seven existing selectable atomic actions share an exact boss-scoped action/motion/timing/payload-prefix signature with older curated evidence and this batch (four Hideyori, two Oda, one Tachibana). No complete new annotation matches an existing playable graph. Those overlaps do not promote the 55 candidates.

Existing authored graphs were checked against action/motion/payload sequences from the same take, object and owner. Eleven annotations contain a matching graph **segment**, but those segments are incidental or only part of the reported move. Examples: Oda's `C6E → C6F` occurs long before a Corruption Ground Stab note; Tachibana's `D8D` is one phase in a Sheathing Dash into Quadrasect; Toyotomi's `D30 → D31 → D32 → D33` occurs before a Yokai Pool Summoning note. No new annotation exactly matches an entire existing playable graph. Exact playable matches: **0**; new unique candidates: **55**; confirmed unsupported source types: **0** (source ownership/type remains unclassified).

## Repeatable promotion path

Run `python -B dataset/intake_recordings.py 'C:\path\to\Tanto Recordings'` and `python -B dataset/validate.py` from MWM. Repeating intake does not duplicate sessions or moves. Validation checks every archive hash and annotation, candidate/catalogue parity, and that unmapped entries have no playable action ID or engine profile. It does not assert live gameplay.

For each candidate, inspect its annotated take and time window across all actors, select a coherent source action sequence with full action/motion/timing/payload identity, and resolve any collision in `signature-review.json`. Then verify installed archive entries and companion resources, author a William-safe adapter and graph with required paired/effect roles, run the offline import gate, and finally record current-build gameplay acceptance. A source-recording match alone is insufficient to enable the move.
