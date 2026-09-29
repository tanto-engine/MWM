# Recording batch review

This table reviews the original 13 saved notes. The 55 newer sword notes are indexed separately in [SWORD_INTAKE.md](SWORD_INTAKE.md). Entries are candidate move strings, not confirmed imports. Weapon categories follow the user instruction: sword except Sanada's handgun. Priorities remain unset because these notes contain no explicit priority labels.

| Boss | Entry | Observed action IDs in order | Mapping |
| --- | --- | --- | --- |
| Sanada Yukimura | [Handgun draw, shot and sheath](weapons/handgun/sanada_yukimura/handgun_sequence.json) | 0x00000C6A → 0x00000C6A | partial |
| Jin Hayabusa | [Three-move heavy attack string](weapons/sword/jin_hayabusa/heavy_three_move_string.json) | 0x00000C6E → 0x00000C6F → 0x00000C70 | candidate |
| Jin Hayabusa | [Launcher into Izuna Drop](weapons/sword/jin_hayabusa/launcher_izuna_drop.json) | 0x00000C85 → 0x00000C87 → 0x00000C79 → 0x00000C7A → 0x000003B2 → 0x000003B6 | candidate |
| Jin Hayabusa | [Overhead slam](weapons/sword/jin_hayabusa/overhead_slam.json) | 0x00000C75 → 0x00000C77 → 0x00000C78 | candidate |
| Jin Hayabusa | [Quick attack string A](weapons/sword/jin_hayabusa/quick_string_a.json) | 0x00000C67 → 0x00000C68 → 0x00000C69 → 0x00000C6A → 0x00000C6B | candidate |
| Jin Hayabusa | [Quick attack string B into Flying Swallow](weapons/sword/jin_hayabusa/quick_string_b_flying_swallow.json) | 0x00000BBF → 0x00000C63 → 0x00000C64 → 0x00000C65 → 0x00000C66 → 0x00000C71 → 0x00000C72 → 0x00000C73 → 0x00000C74 | candidate |
| Jin Hayabusa | [Two Flying Swallows](weapons/sword/jin_hayabusa/two_flying_swallows.json) | 0x00000C71 → 0x00000C72 → 0x00000C74 → 0x00000C71 → 0x00000C72 → 0x00000C74 | partial |
| Oda Nobunaga | [Normal string into swipe and slash](weapons/sword/oda_nobunaga/normals_swipe_slash.json) | 0x00000C69 → 0x00000C6A → 0x00000C6B → 0x00000C6E → 0x00000C6F | candidate |
| Tachibana Muneshige | [Omnislice](weapons/sword/tachibana_muneshige/omnislice.json) | 0x00000D8C → 0x00000D8D | candidate |
| Toyotomi Hideyori | [Four-hit string](weapons/sword/toyotomi_hideyori/four_hit_string.json) | 0x00000D30 → 0x00000D31 → 0x00000D32 → 0x00000D33 | candidate |
| Toyotomi Hideyori | [Grab into two swipes](weapons/sword/toyotomi_hideyori/grab_two_swipes.json) | 0x000005E4 → 0x000003AA → 0x00000D30 → 0x00000D31 | candidate |
| Toyotomi Hideyori | [Ground slam with fire into normal follow-up](weapons/sword/toyotomi_hideyori/ground_slam_followup.json) | 0x000005E1 → 0x00000D38 → 0x00000D36 | partial |
| Toyotomi Hideyori | [Stab, two swipes, then stab](weapons/sword/toyotomi_hideyori/stab_swipes_stab.json) | 0x00000D34 → 0x00000D38 → 0x00000D36 → 0x00000D37 | candidate |

## Selection notes

Selections work backward from the saved annotation endpoint, then exclude reported trailing rolls, partial follow-ups or death states. Line references retain the original take, execution counter and observation time. Metadata may come from an earlier matching descriptor snapshot in the same take; it is not a second execution. Raw archives preserve all actors and all omitted context.

**Handgun draw, shot and sheath:** Only two repeated 0x00000C6A executions are directly selected for the gun candidate. Native metadata lists 0x00000C6B as an available target, but that ID was not observed. Counter 404 is missing before the return state at 8.937s. Draw/fire/sheath cannot yet be assigned separate observed IDs; the record is partial.

**Three-move heavy attack string:** Three consecutive states precede 0x00000023 at 24.359s (reported backward roll) and 0x00000C71 at 24.984s (next move starting). Those trailing states are excluded from the string.

**Launcher into Izuna Drop:** Six consecutive executions cover the candidate approach/launch/grab/drop sequence. The other actor enters paired victim IDs 0x000003B3 and 0x000003B7 at the same times as 0x000003B2 and 0x000003B6. Exact launch phase boundaries still require review.

**Overhead slam:** The last three boss-candidate executions form the selected sequence. A counter gap precedes its start; the three selected counters are consecutive. These IDs also recur earlier in other Jin recordings.

**Quick attack string A:** Five consecutive late executions precede the partial aerial follow-up at lines 366/368. Earlier actors died and were replaced; this string uses the post-death actor only.

**Quick attack string B into Flying Swallow:** Five consecutive quick-string states are followed by four aerial states. Their order agrees with the note, but individual hits and the visual identity remain candidates.

**Two Flying Swallows:** Both late aerial repetitions are preserved. Each jumps over one action counter before 0x00000C74; 0x00000C73 is seen in another take but is NOT inserted into this one. The intervening 0x00000023 and later death-related states are excluded.

**Normal string into swipe and slash:** Three late normal-string states precede the final two states. An intervening 0x00000000 separates the groups. Discovery begins at 4.297s; the final slash completion is not established by stopping at 13.359s.

**Omnislice:** The user requested this preparation/attack pair as the first Tachibana data point; do not treat that request as confirmation of the visual identity.

**Four-hit string:** Four consecutive late action counters match the reported four-hit order. A counter gap occurs before the selected first state; no missing preparation is invented.

**Grab into two swipes:** 0x000005E4 leads to 0x000003AA; the other actor enters paired 0x000003AB at the same time as 0x000003AA. After an intervening idle state, 0x00000D30 and 0x00000D31 match the two reported swipes. Camera behavior itself is only user-reported.

**Ground slam with fire into normal follow-up:** 0x000005E1 is a ground-slam candidate, followed later by two attack states. There is a long observation gap from 3.140s to 10.812s and a boss counter gap before 0x000005E1. The reported roughly three hits cannot be equated to three observed IDs. Movement between and after attacks is retained in raw evidence, not inserted as attacks.

**Stab, two swipes, then stab:** The selected attack candidates follow the annotated order; idle/movement states separate the first stab from the later three states. The following 0x000005DF at 12.219s is retained as the reported partial onmyo context, not merged into the sword string.

## Incomplete source folders

`tachibana-muneshige-1790499665632-507ee0` and `totoyomi-hideyori-1790502012907-60b360` have no saved descriptions or events.jsonl. Their original manifests are archived and indexed; no move IDs were reconstructed from the action counts.

## Next integration boundary

This collection is ready for review and configuration planning. Before enabling a move, review its full source identity, resolve missing phases, author its Engine import/adaptation and validate its behavior. Configuration should reference these stable move IDs, with separately reviewed allowed settings. Existing MWM UI and capability APIs provide a starting point; dataset-to-runtime compilation and general multi-weapon routing are still needed.
