# Offline action-record ranking; makes no attack/animation-name identification.
from collections import Counter
import json
from pathlib import Path
import statistics

base = Path(__file__).resolve().parent
events = [json.loads(line) for line in (base / "okatsu-take3/events.jsonl").read_text().splitlines()]
session = next(e for e in events if e["kind"] == "session")
end = next(e for e in events if e["kind"] == "end")
states = [e for e in events if e["kind"] == "action_state" and e["role"] == "boss_candidate"]
metas = {role: {e["word0_hex"]: e for e in events if e["kind"] == "metadata"
               and e["role"] == role and e["matches_preceding_state"]}
         for role in ("boss_candidate", "player_candidate")}
runs = []
for e in states:
    if runs and runs[-1]["descriptor"] == e["current"]:
        runs[-1]["raw_observations"] += 1
        continue
    runs.append({"t": e["t"], "word0": e["descriptor"]["word0_hex"], "descriptor": e["current"],
                 "raw_observations": 1, "entry_censored": not runs})
for i, run in enumerate(runs):
    run["end_t"] = runs[i + 1]["t"] if i + 1 < len(runs) else end["t"]
    run["dwell_seconds"] = round(run["end_t"] - run["t"], 6)
    run["exit_censored"] = i == len(runs) - 1
    run["previous"] = runs[i - 1]["word0"] if i else None
    run["next"] = runs[i + 1]["word0"] if i + 1 < len(runs) else None
ranking = []
for word in sorted({r["word0"] for r in runs}):
    occurrences = [r for r in runs if r["word0"] == word]
    complete = [r["dwell_seconds"] for r in occurrences if not r["entry_censored"] and not r["exit_censored"]]
    meta = metas["boss_candidate"][word]
    ranking.append({
        "word0": word, "observed_entries": sum(not r["entry_censored"] for r in occurrences),
        "segments_including_initial_censored": len(occurrences),
        "raw_state_observations": sum(r["raw_observations"] for r in occurrences),
        "total_observed_dwell_seconds": round(sum(r["dwell_seconds"] for r in occurrences), 6),
        "complete_dwell_seconds": complete,
        "complete_dwell_median_seconds": round(statistics.median(complete), 6) if complete else None,
        "predecessors": dict(Counter(r["previous"] or "capture_started" for r in occurrences)),
        "successors": dict(Counter(r["next"] or "capture_ended" for r in occurrences)),
        "occurrences": [{k: v for k, v in r.items() if k not in ("descriptor", "word0")} for r in occurrences],
        "descriptor": meta["address"], "payload": meta["payload"],
        "native_transition_entries": len(meta["transition_entries"]),
        "native_target_keys": sorted({entry["target_key_0x14_i16"] for entry in meta["transition_entries"]}),
        "interpretation": "Unclassified action record; entry count is not an attack count.",
    })
ranking.sort(key=lambda row: (
    # Prioritize repeatedly observed action entries for identification.
    # Sort by entry count, segment count and then the stable action word.
    # Keep the initial censored segment distinct from an observed attack start.
    (-row["observed_entries"], -row["segments_including_initial_censored"], row["word0"])))
shared = []
for word in sorted(metas["boss_candidate"].keys() & metas["player_candidate"].keys()):
    boss, player = metas["boss_candidate"][word], metas["player_candidate"][word]
    b_raw = bytes.fromhex(boss["payload_prefix"]["bytes"])
    p_raw = bytes.fromhex(player["payload_prefix"]["bytes"])
    def item(e):
        # Select comparable action metadata from one saved observation.
        # Preserve payload flags, selector fields and transition slice information.
        # Show why equal action numbers need not identify equal moves.
        return {"descriptor": e["address"], "payload": e["payload"],
                "payload_key_0x0c_i16": e["payload_prefix"]["key_0x0c_i16"],
                "payload_flags_0x18": e["payload_prefix"]["flags_0x18_u64"],
                "payload_field_0x20_i32": e["payload_prefix"]["sentinel_0x20_i32"],
                "transition_table": e["transition_slice"]}
    shared.append({"word0": word, "boss_candidate": item(boss), "player_candidate": item(player),
                   "same_descriptor_pointer": boss["address"] == player["address"],
                   "same_payload_pointer": boss["payload"] == player["payload"],
                   "payload_prefix_differing_offsets": [hex(i) for i, (b, p) in enumerate(zip(b_raw, p_raw)) if b != p]})
result = {
    "source": "work/okatsu-take3/events.jsonl", "boss_candidate": session["boss_candidate"],
    "capture_seconds": end["seconds"], "raw_boss_state_observations": len(states),
    "collapsed_segments": len(runs), "observed_descriptor_entries": len(runs) - 1,
    "discarded_state_only_duplicates": len(states) - len(runs),
    "first_segment_is_left_censored": True, "last_segment_is_right_censored": True,
    "record_ranking": ranking,
    "shared_numeric_keys_with_player": shared,
    "candidate_for_visual_identification": {
        "word0": "0x0C64", "observed_entries": 4,
        "basis": "Most repeated observed entry excluding numeric keys0x0000/0x0008, which are also unclassified. This exclusion is a heuristic, not a validated attack filter.",
        "implementation_readiness": "Not sufficient to bind a confirmed Okatsu attack. Verify the move visually or identify its animation/event resources and actor-dependent dependencies first.",
    },
    "limitations": [
        "Actor roles remain candidate labels; previous input and shared-player-data evidence supports them.",
        "All counts describe record-pointer changes observed by polling, not guaranteed complete game transitions.",
        "Initial segment began before recording; final segment ended after recording. Neither gives a complete dwell.",
        "Thirteen sampling gaps over30ms occurred; short transitions can be absent.",
        "Frequency/dwell cannot distinguish attacks, movement, idle, reactions, or recovery by itself.",
        "Same numeric key in both actor data sets is not proof of interchangeable action content.",
    ],
}
path = base / "okatsu-first-move-ranking.json"
path.write_text(json.dumps(result, indent=2), encoding="utf8")
print(json.dumps({"ranking": [{k: row[k] for k in ("word0", "observed_entries", "segments_including_initial_censored", "total_observed_dwell_seconds", "complete_dwell_seconds", "predecessors", "successors")} for row in ranking], "shared_keys": shared}, indent=2))
