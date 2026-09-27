# Sword Rebuild 1

`sword-rebuild-1.json` defines the new requested layout and cites exact dataset steps. It is an authoring design, not a loadable runtime preset. Five routes have existing Jin adapters; four remain blocked. Source observations are not promoted to reviewed imports by appearing here.

| Input | New move |
| --- | --- |
| LB + LT, any stance | Sanada handgun |
| Low heavy | Jin three-move heavy string |
| Low dodge attack | Jin second heavy |
| Mid heavy | Jin quick string B, five attacks without the recorded aerial follow-up |
| Low quick | Hideyori four-hit string |
| LB + Square after High heavy | Omnislice attack directly, skipping step-back/sheath |
| Frost Moon into High | Jin downward slash at 1x |
| Frost Moon into Mid | Oda final two-hit swipe/slash |
| Frost Moon into Low | Flying Swallow |

Hideyori's four-hit capture has four consecutive observed actions; there is no established five-hit alternative in this batch. Oda uses only the final two actions. Omnislice requires initialization for direct entry into its attack, plus a one-use follow-up gate that clears on stance changes or interruptions. A general guard-light binding would not meet that requirement.

`../data/presets/sword-rebuild-1-supported.json` is the separate loadable Jin-only subset. Its name explicitly says incomplete; the four blocked routes are absent, so Low quicks remain native and Mid Frost has no replacement. It starts with only the requested supported overrides, without the old optional Okatsu, held-heavy or Mid dodge replacements. The saved default and user's active configuration are untouched.

All selected attack recoveries use the existing Engine Pulse policy: 40 percent recoverable Ki, 25 fill frames and 24 hold frames. Frost tracks the remaining native Pulse window. Airborne sequences recover at landing rather than introducing a midair cancel; paired actions must finish their synchronized phase first. High downward-slash phases use 1x speed, while Flying Swallow retains its existing specialized startup. These settings need gameplay assessment before claiming fair timing on every move.

Remaining work is concrete: author and verify the four bosses' resource/import adaptations; resolve Sanada's missing gun phase and projectile behavior; implement a four-hit Low quick chain, an all-stance analog-trigger chord and the High-heavy follow-up gate. The design records these blockers per route. Offline checks verified the five supported bindings, source action/motion matches, string order, Frost destinations and compiled Pulse/speed settings; they did not test gameplay.
