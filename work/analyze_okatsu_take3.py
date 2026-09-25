"""Offline summary of an existing capture; does not import a live reader."""
from collections import Counter
import bisect
import json
from pathlib import Path

base = Path(__file__).resolve().parent
events = [json.loads(line) for line in (base / "okatsu-take3/events.jsonl").read_text().splitlines()]
status = json.loads((base / "okatsu-take3/status.json").read_text())
session = next(event for event in events if event["kind"] == "session")
kind_counts = Counter(event["kind"] for event in events)
roles = {}
prior_player_events = [json.loads(line) for line in (base / "sword-living-weapon-take1.jsonl").read_text().splitlines()]
prior_player_events = [e for e in prior_player_events if e["kind"] == "action_state"
                       and e["object"] == "0x24391410330" and e.get("descriptor")]
prior_pointers = {e["current"]: e["descriptor"] for e in prior_player_events}
prior_words = {e["descriptor"]["word0"] for e in prior_player_events}
press_times = [e["t"] for e in events if e["kind"] == "input" and e.get("pressed_mask")]
for role in ("player_candidate", "boss_candidate"):
    states = [e for e in events if e["kind"] == "action_state" and e["role"] == role]
    metas = [e for e in events if e["kind"] == "metadata" and e["role"] == role]
    stable = [e for e in metas if e["matches_preceding_state"]]
    with_payload = [e for e in stable if "payload_prefix" in e]
    entries = [entry for e in stable for entry in e["transition_entries"]]
    successful_entries = [entry for entry in entries if "target_key_0x14_i16" in entry]
    unique_entries = {entry["address"]: entry for entry in successful_entries}
    targets = sorted({entry["target_key_0x14_i16"] for entry in successful_entries})
    words = Counter(e["descriptor"]["word0_hex"] for e in states if e["descriptor"])
    actual_descriptors = {e["current"] for e in states if e["descriptor"]}
    stable_descriptors = {e["address"] for e in stable}
    agreement = sum((e["payload_prefix"]["key_0x0c_i16"] & 0xFFFF) == e["word0_u16"] for e in with_payload)
    mismatches = [{"word0": e["word0_hex"], "payload_key_i16": e["payload_prefix"]["key_0x0c_i16"]}
                  for e in with_payload if (e["payload_prefix"]["key_0x0c_i16"] & 0xFFFF) != e["word0_u16"]]
    changes = Counter(e["change"] for e in states)
    shared_pointers = sorted(actual_descriptors & prior_pointers.keys())
    exact_reused = [e["address"] for e in stable if e["address"] in prior_pointers
                    and e["word0_u16"] == prior_pointers[e["address"]]["word0"]
                    and e["payload"] == prior_pointers[e["address"]]["payload"]]
    timing = {}
    transitions = [b for a, b in zip(states, states[1:]) if a["current"] != b["current"]]
    transition_times = [e["t"] for e in transitions]
    for window in (0.05, 0.1, 0.25):
        hits = 0
        for at in press_times:
            ix = bisect.bisect_left(transition_times, at)
            hits += ix < len(transition_times) and transition_times[ix] - at <= window
        # The fraction of all capture time lying shortly BEFORE some transition.
        # This is a baseline for accidental proximity in a fast-changing stream.
        intervals = [(max(0, at - window), at) for at in transition_times]
        covered = 0
        lo = hi = 0
        for left, right in intervals:
            if left > hi:
                covered += hi - lo
                lo, hi = left, right
            else:
                hi = max(hi, right)
        covered += hi - lo
        timing[str(int(window * 1000)) + "ms"] = {
            "press_observations_with_following_transition": hits,
            "total_press_observations": len(press_times),
            "chance_time_coverage_fraction": round(covered / status["seconds"], 4),
        }
    roles[role] = {
        "object": session[role], "observations": len(states), "change_labels": dict(changes),
        "descriptor_pointer_changes_between_observations": sum(a["current"] != b["current"] for a, b in zip(states, states[1:])),
        "action_key_changes_between_observations": sum((a["current"], a["index"]) != (b["current"], b["index"]) for a, b in zip(states, states[1:])),
        "unique_word_count": len(words), "word_observation_counts": dict(sorted(words.items())),
        "unique_descriptor_count": len(actual_descriptors),
        "owners": sorted({e["owner_like"] for e in states}),
        "owner_mismatch_observations": sum(not e["owner_matches_discovery"] for e in states),
        "prior_sword_capture_comparison": {
            "shared_descriptor_pointers": shared_pointers,
            "shared_pointer_count": len(shared_pointers),
            "shared_descriptor_word_and_payload_count": len(set(exact_reused)),
            "shared_word_values": sorted({e["descriptor"]["word0_u16"] for e in states if e["descriptor"]} & prior_words),
            "specific_quick_heavy_LW_anchor_words_seen": sorted({e["descriptor"]["word0_u16"] for e in states if e["descriptor"]}
                & ({*range(0xCF0, 0xCF6), *range(0xD34, 0xD3B), 0xD4D, 0xD4E})),
            "interpretation": "Exact descriptor-pointer reuse supports shared action data; not independent actor identity proof.",
        },
        "input_temporal_proximity": timing,
        "metadata": {
            "events": len(metas), "stable_events": len(stable), "unstable_events": len(metas) - len(stable),
            "stable_unique_descriptors": len(stable_descriptors),
            "observed_descriptors_without_stable_metadata": sorted(actual_descriptors - stable_descriptors),
            "payload_prefix_successes": len(with_payload),
            "payload_errors": sum("payload_error" in e for e in stable),
            "slice_errors": sum("slice_error" in e for e in stable),
            "requested_transition_entries": sum(e["entries_requested"] for e in stable),
            "omitted_transition_entries": sum(e["entries_omitted"] for e in stable),
            "captured_transition_entries": len(entries),
            "entry_errors": len(entries) - len(successful_entries),
            "unique_entry_addresses": len(unique_entries),
            "unique_target_key_count": len(targets),
            "target_keys_i16": targets,
            "payload_key_word0_comparisons": len(with_payload),
            "payload_key_word0_agreements": agreement,
            "payload_key_word0_mismatches": mismatches,
            "payload_key_comparison": "i16 payload key normalized to the same 16 bits as descriptor u16 word",
        },
    }

inputs = [e for e in events if e["kind"] == "input"]
pressed = Counter()
released = Counter()
for e in inputs:
    for field, counts in (("pressed_mask", pressed), ("released_mask", released)):
        mask = e.get(field) or 0
        for bit in range(mask.bit_length()):
            if mask & (1 << bit):
                counts[f"0x{1 << bit:X}"] += 1
errors = [e for e in events if e["kind"] in (
    "snapshot_race", "object_unreadable", "metadata_unreadable", "tracked_actor_changed", "rediscovery_required")]
result = {
    "source": "work/okatsu-take3/events.jsonl", "status": status,
    "event_kind_counts": dict(kind_counts), "roles": roles,
    "errors": {
        "counts": dict(Counter(e["kind"] for e in errors)),
        "by_object": {obj: dict(Counter(e["kind"] for e in errors if e.get("object") == obj)) for obj in session["objects"]},
        "events": errors,
        "owner_or_actor_replacement_observed": any(e["kind"] in ("tracked_actor_changed", "rediscovery_required") for e in errors),
    },
    "controller": {
        "observations": len(inputs),
        "button_edge_observations": sum(bool(e.get("pressed_mask") or e.get("released_mask")) for e in inputs),
        "press_edges": sum(pressed.values()), "release_edges": sum(released.values()),
        "pressed_bit_counts": dict(pressed), "released_bit_counts": dict(released),
        "first_observation_edges_unknown": bool(inputs and inputs[0]["pressed_mask"] is None),
        "labels": "Raw OS button masks only; physical/game actions uncalibrated",
    },
    "limitations": [
        "Player/boss roles are investigator candidate labels, independently unverified and potentially swapped.",
        "Action records include movement, reactions and other states; not all are attacks.",
        "External sampling can miss short states; timings are wall time, not game frames.",
        "Repeated keys in descriptor and payload support a relationship; semantics remain unproven.",
        "No frame, damage, hitbox, or player-reusability fields established.",
    ],
}
target = base / "okatsu-take3-analysis.json"
target.write_text(json.dumps(result, indent=2), encoding="utf8")
print(json.dumps(result, indent=2))
