"""Bounded controller calibration and chord dry-run. Never modifies a game.

Uses the sibling boss-probe/controller_reader.py only when the CLI is run.
Inference and chord adaptation can be tested without loading controller APIs.
"""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time

from chord_gate import ChordGate


PHASES = (("neutral", "Release every button and trigger; leave sticks centered."),
          ("lb", "Hold LB only; keep LT and all other controls released."),
          ("lt", "Release LB. Fully hold LT only; leave other controls alone."),
          ("both", "Keep LT fully held and hold LB as well."),
          ("release", "Release every button and trigger; leave sticks centered."))


def identity(event):
    keys = ("backend", "slot", "name", "manufacturer", "product", "num_buttons",
            "num_axes", "axis_ranges", "caps_result")
    return {key: event[key] for key in keys if key in event}


def axis_ranges(device):
    if device["backend"] == "xinput":
        return {axis: [0, 255] if axis in ("lt", "rt") else [-32768, 32767]
                for axis in ("lt", "rt", "lx", "ly", "rx", "ry")}
    return device.get("axis_ranges", {})


def one_bit(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0 and value & (value - 1) == 0


def infer_calibration(phases, device):
    """Require clear, held observations; uncertainty produces no mapping."""
    medians, buttons, spreads = {}, {}, {}
    ranges = axis_ranges(device)
    if not ranges:
        raise ValueError("No advertised axis ranges for this device")
    for phase, _ in PHASES:
        samples = phases.get(phase, [])
        if len(samples) < 10:
            raise ValueError(f"Too few settled observations in {phase}")
        masks = {sample["buttons"] for sample in samples}
        if len(masks) != 1 or any(sample.get("pov") not in (None, 65535) for sample in samples):
            raise ValueError(f"Buttons or D-pad changed during settled {phase}")
        buttons[phase] = masks.pop()
        medians[phase], spreads[phase] = {}, {}
        for axis, limits in ranges.items():
            low, high = limits
            if high <= low:
                continue
            values = [sample["axes"].get(axis) for sample in samples]
            if any(not isinstance(v, (int, float)) or isinstance(v, bool)
                   or not low <= v <= high or not math.isfinite(v) for v in values):
                raise ValueError(f"Invalid {axis} values in {phase}")
            medians[phase][axis] = statistics.median(values)
            spreads[phase][axis] = max(values) - min(values)
    if buttons["neutral"] or buttons["release"]:
        raise ValueError("Neutral/release phase contains a held button")
    lb = buttons["lb"]
    lt_bits = buttons["lt"]
    if not one_bit(lb) or (lt_bits and (not one_bit(lt_bits) or lt_bits == lb)):
        raise ValueError("LB/LT button evidence is ambiguous")
    if buttons["both"] != lb | lt_bits:
        raise ValueError("Both-controls phase does not reproduce the isolated button states")

    candidates = []
    for axis, neutral in medians["neutral"].items():
        low, high = ranges[axis]
        span = high - low
        full = medians["lt"][axis]
        if abs(full - neutral) >= 0.4 * span:
            candidates.append(axis)
    if len(candidates) != 1:
        raise ValueError(f"Expected one clearly changed LT axis; found {candidates}")
    axis = candidates[0]
    for name, neutral in medians["neutral"].items():
        low, high = ranges[name]
        tolerance = max(2, 0.05 * (high - low))
        if any(spreads[phase][name] > tolerance for phase, _ in PHASES):
            raise ValueError(f"Unstable held axis {name}")
        if any(abs(medians[phase][name] - neutral) > tolerance for phase in ("lb", "release")):
            raise ValueError(f"Axis {name} did not stay neutral during LB/release")
        if name != axis and any(abs(medians[phase][name] - neutral) > tolerance for phase in ("lt", "both")):
            raise ValueError(f"An additional axis {name} changed during LT/both")
    neutral, full = medians["neutral"][axis], medians["lt"][axis]
    low, high = ranges[axis]
    if abs(medians["both"][axis] - full) > 0.05 * (high - low):
        raise ValueError("Both-controls phase does not reproduce the LT endpoint")
    if min(abs(full - low), abs(full - high)) > 0.08 * (high - low):
        raise ValueError("LT was not held near a full-travel endpoint")
    return dict(schema=1, device=identity(device),
                identity_scope="Backend, slot and reported capabilities; not a physical-device serial",
                lb_mask=lb, lt=dict(axis=axis, neutral=neutral, full=full,
                                   advertised_range=[low, high], accompanying_button_mask=lt_bits),
                phase_medians=medians, phase_buttons=buttons,
                semantics="Prompt-calibrated OS controls; game input acceptance and gameplay context unverified")


def normalize_lt(raw, mapping):
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    low, high = mapping["advertised_range"]
    if not low <= raw <= high or not math.isfinite(raw) or mapping["full"] == mapping["neutral"]:
        return None
    value = (raw - mapping["neutral"]) / (mapping["full"] - mapping["neutral"])
    if not -0.05 <= value <= 1.05:
        return None
    return min(1.0, max(0.0, value))


class CalibratedChord:
    """Adapt one matching event stream. Reconnection never fabricates an edge."""
    def __init__(self, calibration):
        self.calibration = calibration
        self.gate = ChordGate()
        self.connected = False
        if calibration.get("schema") != 1 or not one_bit(calibration["lb_mask"]):
            raise ValueError("Invalid calibration schema or LB mask")

    def process(self, event, context_valid=False):
        if not context_valid:
            self.gate.reset()
        expected = self.calibration["device"]
        if (event.get("backend"), event.get("slot")) != (expected["backend"], expected["slot"]):
            return None
        if event["kind"] == "input_device":
            self.gate.reset()
            self.connected = identity(event) == expected
            return dict(kind="device_match", accepted=self.connected)
        if event["kind"] == "input_unavailable":
            self.connected = False
            self.gate.reset()
            return dict(kind="device_unavailable")
        if event["kind"] != "input":
            return None
        if event.get("edge_basis") == "unknown":
            self.gate.reset()
        buttons = event.get("buttons")
        lt = normalize_lt(event.get("axes", {}).get(self.calibration["lt"]["axis"]), self.calibration["lt"])
        valid = isinstance(buttons, int) and not isinstance(buttons, bool) and 0 <= buttons <= 0xFFFFFFFF
        lb = bool(buttons & self.calibration["lb_mask"]) if valid else False
        fired = self.gate.update(lb, lt, context_valid and valid, self.connected)
        return dict(kind="logical_input", observed_monotonic=event.get("observed_monotonic"),
                    lb=lb, lt=lt, connected=self.connected, context_valid=context_valid,
                    chord_candidate=fired)


def cue_matches(path, phase):
    try:
        cue = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(cue, dict) and cue.get("phase") == phase


def collect(reader, backend, slot, held_seconds, settle_seconds, evidence,
            cue_file=None, status_file=None, total_seconds=120, wait_seconds=30):
    phases, device, latest = {}, None, None
    started = time.perf_counter()
    completed = []

    def status(state, phase, **extra):
        if status_file is not None:
            target = Path(status_file)
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_text(json.dumps(dict(state=state, phase=phase,
                completed_phases=list(completed), elapsed_seconds=round(time.perf_counter() - started, 3),
                cue_required=cue_file is not None, **extra)), encoding="utf8")
            temporary.replace(target)

    def abort(message, phase):
        status("failed", phase, error=message)
        raise ValueError(message)

    def check_total(phase):
        if time.perf_counter() - started >= total_seconds:
            abort("Total calibration deadline reached", phase)

    def poll(phase, stage):
        nonlocal device, latest
        for event in reader.poll():
            evidence.write(json.dumps(dict(phase=phase, stage=stage, **event)) + "\n")
            if (event.get("backend"), event.get("slot")) != (backend, slot):
                continue
            if event["kind"] == "input_device":
                if device is not None and identity(event) != device:
                    abort("Device identity changed during calibration", phase)
                device = identity(event)
            elif event["kind"] == "input_unavailable":
                abort("Controller became unavailable during calibration", phase)
            elif event["kind"] == "input":
                latest = event

    for phase, instruction in PHASES:
        print(f"{phase.upper()}: {instruction} Settle {settle_seconds:g}s, then hold {held_seconds:g}s.", flush=True)
        if cue_file is not None:
            status("waiting_for_cue", phase)
            waiting = time.perf_counter()
            while True:
                check_total(phase)
                if time.perf_counter() - waiting >= wait_seconds:
                    abort(f"Timed out waiting for {phase} cue", phase)
                poll(phase, "waiting_for_cue")
                if cue_matches(cue_file, phase):
                    evidence.write(json.dumps(dict(kind="phase_cue", phase=phase,
                        t=time.perf_counter() - started)) + "\n")
                    break
                time.sleep(0.01)
        status("settling", phase)
        phase_start = time.perf_counter()
        phases[phase] = []
        recording = False
        while time.perf_counter() - phase_start < settle_seconds + held_seconds:
            check_total(phase)
            poll(phase, "recording" if recording else "settling")
            if time.perf_counter() - phase_start >= settle_seconds:
                if not recording:
                    status("recording", phase)
                    recording = True
                if latest is None or device is None:
                    abort("No valid observation from the selected device", phase)
                sample = {key: latest.get(key) for key in ("buttons", "pov", "axes")}
                phases[phase].append(sample)
                evidence.write(json.dumps(dict(kind="calibration_sample", phase=phase,
                    t=time.perf_counter() - started, source_observed_monotonic=latest["observed_monotonic"],
                    basis="Latest reader event, including held state between change events", **sample)) + "\n")
            time.sleep(0.01)
        evidence.flush()
        completed.append(phase)
        status("phase_complete", phase)
    try:
        profile = infer_calibration(phases, device)
    except ValueError as exc:
        abort(str(exc), phase)
    status("complete", phase)
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cal = commands.add_parser("calibrate")
    cal.add_argument("--backend", choices=("winmm", "xinput"), default="winmm")
    cal.add_argument("--slot", type=int, default=0)
    cal.add_argument("--held-seconds", type=float, default=2)
    cal.add_argument("--settle-seconds", type=float, default=3)
    cal.add_argument("--cue-file", type=Path,
                     help='Wait for {"phase":"neutral"}, then lb/lt/both/release; 30s per wait, 120s total')
    dry = commands.add_parser("dry-run")
    dry.add_argument("--calibration", type=Path, required=True)
    dry.add_argument("--seconds", type=float, default=30)
    for command in (cal, dry):
        command.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "calibrate" and not (0 <= args.slot <= (3 if args.backend == "xinput" else 15)
            and 1 <= args.held_seconds <= 10 and 1 <= args.settle_seconds <= 5):
        parser.error("Slot must be 0..3 for XInput or 0..15 for WinMM; hold 1..10s and settle 1..5s")
    if args.command == "dry-run" and not 0 < args.seconds <= 120:
        parser.error("Dry-run duration must be 0..120s")
    # Import/construct controller APIs only after explicit CLI invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boss-probe"))
    from controller_reader import ControllerReader
    args.outdir.mkdir(parents=True, exist_ok=False)
    try:
        reader = ControllerReader()
        with (args.outdir / "raw-events.jsonl").open("x", encoding="utf8") as evidence:
            if args.command == "calibrate":
                profile = collect(reader, args.backend, args.slot, args.held_seconds, args.settle_seconds, evidence,
                                  cue_file=args.cue_file, status_file=args.outdir / "status.json")
                profile["created_unix"] = time.time()
                (args.outdir / "calibration.json").write_text(json.dumps(profile, indent=2), encoding="utf8")
                print(json.dumps(dict(status="calibrated", lb_mask=hex(profile["lb_mask"]), lt=profile["lt"])), flush=True)
            else:
                mapper = CalibratedChord(json.loads(args.calibration.read_text(encoding="utf8")))
                print("DRY-RUN ONLY: context means this test window, not validated gameplay. Release LB and LT first.", flush=True)
                start = time.perf_counter()
                while time.perf_counter() - start < args.seconds:
                    for event in reader.poll():
                        evidence.write(json.dumps(event) + "\n")
                        logical = mapper.process(event, context_valid=True)
                        if logical is not None:
                            logical.update(t=round(time.perf_counter() - start, 6), game_modified=False)
                            print(json.dumps(logical), flush=True)
                            evidence.write(json.dumps(logical) + "\n")
                    time.sleep(0.01)
                print("Dry-run stopped.", flush=True)
    except (ValueError, OSError, KeyboardInterrupt) as exc:
        reason = str(exc) or "Interrupted"
        (args.outdir / "failure.json").write_text(json.dumps(dict(error=reason)), encoding="utf8")
        parser.exit(2, f"Stopped without calibration/game changes: {reason}\n")


if __name__ == "__main__":
    main()
