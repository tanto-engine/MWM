# First Collection

`first-collection.json` records the complete requested design with dataset step references and explicit blockers. It is not a runtime preset. `../data/presets/first-collection-supported.json` is a separately loadable schema-v8 preset containing the five currently implemented routes; the existing default remains available. Load that file in the MWM app and Apply to select the subset. No EXE was built or game configuration applied during authoring.

| Input | Requested action | Source implementation |
| --- | --- | --- |
| LB + LT, any stance | Sanada handgun | Pending firing/sheathing evidence, projectile adapter and stance-independent chord |
| Low heavy | Jin three-heavy string, C6E → C6F → C70 | Included |
| Low dodge attack | Jin second heavy, C6F | Included; existing heavy continuation rules retained |
| Mid heavy | Jin quick string B, BBF → C63 → C64 → C65 → C66 | Included; trailing Flying Swallow excluded |
| Low quick | Hideyori four-hit string, D30 → D31 → D32 → D33 | Pending source resources and quick-string adapter |
| After High heavy, LB + Square | Omnislice attack, D8D | Pending direct attack adapter and follow-up gate |
| High Frost Moon | Jin downward slash, C75 → C77 → C78, 1× | Included |
| Mid Frost Moon | Oda final two slashes, C6E → C6F | Pending source resources and two-phase adapter |
| Low Frost Moon | Flying Swallow, C71 → C72 → C73 → C74 | Included |

Action numbers above are shorthand, scoped to their boss and source bank. The design stores full IDs. Hideyori's four-hit string is directly supported by the recording; a fifth hit is not inferred. Omnislice should bypass its preparation by entering the attack phase, without seeking past damage or effect events. Its follow-up must open only after a High heavy, consume one fresh LB + Square press, and clear on damage, stance/weapon change or expiration; ordinary High guard-light is not an equivalent binding.

`../data/move-policy.json` gives the four selected Jin graph roots 40% recoverable Ki, 30 fill frames and 36 hold frames, inherited by their continuations. This is developer policy shared by source presets using these roots. Existing recovery onset and attack costs stay intact; airborne phases retain pending Ki until landing. Frost Moon follows the native Ki window, so extending hold provides more input leeway without an unrelated timer. The four pending routes must receive the same recovery policy when adapted. Native unmodified attacks retain their game windows; paired grabs must finish before recovery becomes available.

The subset disables the old Okatsu replacements, held-heavy launcher, Mid dodge override and Mid light ender. It leaves the four unfinished routes unassigned rather than substituting old moves. High Frost uses 1× playback across all three phases and has no startup acceleration rule. Configuration compilation and timing checks are offline evidence only; live input, contact and recovery acceptance remain pending.
