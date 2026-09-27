# Sword Rebuild 1

**Source status:** the user confirmed all six Jin inputs, Oda's two slashes at 1.1x and Omnislice playback. The isolated Low-heavy check also passed normal movement and death/retry. Hideyori's four phases play, but zero boss Ki cost prevented Pulse; a player-cost correction is enabled for feedback. Sanada's Low LB+LT firing, 1.15× speed and temporary sword hiding are confirmed. The full preset still needs broader gameplay checks.

`data/presets/sword-rebuild-1.json` contains the complete layout. **More → Load Rebuild trial** loads a draft; **Save changes** stores it and **Enable mod** activates it. Hideyori, Oda, Tachibana and Sanada are experimental imports matched to recorded bytes and installed resources. Their animation, hit ownership, projectile and recovery behavior need separate gameplay checks.

Low Square advances Hideyori D30–D33 one press per strike. Mid Frost automatically continues Oda C6E into C6F at the source's frame-40 branch. Omnislice accepts one fresh LB+Square press during native High-heavy recovery; idle, damage, dodge or stance change closes the opportunity. In Low stance, tap and release LB+LT for one Sanada C6A execution; holding has no assigned action. Its missing recorded counter is not silently invented as another shot.

**More → Recorded moves** shows the layout and research notes. **Load Rebuild subset** selects six Jin inputs, including both standing and dodging Mid heavies. Left-stick movement and L3 are independent of Frost Moon's stance-button edges; movement does not extend recovery. Damage, conflicting actions and controller reconnects still cancel the opportunity.

`sword-rebuild-1.json` records the design and dataset references. Runtime presets live under `../data/presets/`: the full trial and the older supported subset. Both buttons remap logical inputs for the selected controller. Source activation does not establish gameplay acceptance.

| Input | Requested action | Source implementation |
| --- | --- | --- |
| Tap LB + LT, Low stance | Sanada hand-cannon | Firing, 1.15× speed and sword hiding confirmed in the source trial |
| Low heavy | Jin three-heavy string, C6E  ->  C6F  ->  C70 | Included |
| Low dodge-heavy | Jin second heavy, C6F | Included; existing heavy continuation rules retained |
| Mid heavy | Jin quick string B, BBF  ->  C63  ->  C64  ->  C65  ->  C66 | Included; trailing Flying Swallow excluded |
| Mid dodge-heavy | Same Jin quick string B | Shares the Mid-heavy graph through native BC8/BC9 dodge entry |
| Low quick | Hideyori four-hit string, D30  ->  D31  ->  D32  ->  D33 | Source trial with Square continuations |
| After High heavy, LB + Square | Omnislice attack, D8D | Playback confirmed; one-shot recovery gate |
| High Frost Moon | Jin downward slash, C75  ->  C77  ->  C78, 1x | Included |
| Mid Frost Moon | Oda final two slashes, C6E  ->  C6F | Both slashes confirmed; automatic continuation, 1.1x |
| Low Frost Moon | Flying Swallow, C71  ->  C72  ->  C73  ->  C74 | Included |

Action numbers above are shorthand, scoped to their boss and source bank. The design stores full IDs. Hideyori's four-hit string is directly supported by the recording; a fifth hit is not inferred. Omnislice should bypass its preparation by entering the attack phase, without seeking past damage or effect events. Its follow-up must open only after a High heavy, consume one fresh LB + Square press, and clear on damage, stance/weapon change or expiration; ordinary High guard-light is not an equivalent binding.

`../data/move-policy.json` gives all eight selected graph roots 40% recoverable Ki, 30 fill frames and 36 hold frames, inherited by their continuations. Airborne phases retain pending Ki until landing. Frost Moon follows the native Ki window, so extending hold provides more input leeway. Newly inferred recovery frames need gameplay tuning; native unmodified attacks retain their game windows.

Hideyori's source actions cost zero Ki. Engine adapts only William's copies to his Low-quick costs (19, 14, 14, 14), keeping the recorded values intact. Pulse recovers a fraction of actual game-adjusted spending; a nonzero percentage alone cannot create a window from a zero-cost string.

Both presets disable the old Okatsu replacements, held-heavy launcher and Mid light ender. The subset leaves the four new boss routes unassigned. High Frost uses 1x playback across all three phases without startup acceleration. Broader contact and recovery acceptance remains pending.
