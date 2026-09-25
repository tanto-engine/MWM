"""Nioh 1 action research. Standard library only; external memory reads only.

scan discovers native action-node candidates; record logs inputs and actions;
inspect reads a bounded record and its transition slice; report exports CSV.
Offsets are restricted to the executable fingerprint researched in this session.
"""
import argparse
import bisect
import csv
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import struct
import time

from nioh_memory import kernel, modules, read, MEMORY_BASIC_INFORMATION

BUILD_SHA256 = "0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389"
VTABLE_RVA = 0x11A3530
RTTI_NAME = ".?AVCActModuleActionMotNode@@"
READ_ACCESS = 0x410  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
MAX_POINTER = 0x7FFFFFFFFFFF
U16 = lambda b, p: struct.unpack_from("<H", b, p)[0]
I16 = lambda b, p: struct.unpack_from("<h", b, p)[0]
U32 = lambda b, p: struct.unpack_from("<I", b, p)[0]
I32 = lambda b, p: struct.unpack_from("<i", b, p)[0]
U64 = lambda b, p: struct.unpack_from("<Q", b, p)[0]

kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
kernel.GetProcessTimes.restype = W.BOOL
kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
kernel.GetExitCodeProcess.restype = W.BOOL


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as f:
        json.dump(value, f, indent=2, allow_nan=False)


def readable(mbi):
    return (mbi.State == 0x1000 and not mbi.Protect & 0x100
            and mbi.Protect & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80))


def object_fields(b):
    return dict(owner_like=hex(U64(b, 0x50)), current=hex(U64(b, 0x58)),
                previous=hex(U64(b, 0x60)), index=U32(b, 0x68),
                previous_index=U32(b, 0x6C), transition=hex(U64(b, 0x90)),
                previous_transition=hex(U64(b, 0x98)), pending=hex(U64(b, 0xB0)),
                pending_index=I32(b, 0xC0), counter=U32(b, 0xDC))


def descriptor_fields(b):
    return dict(word0_u16=U16(b, 0), word0_hex=f"0x{U16(b, 0):04X}",
                payload=hex(U64(b, 0x20)),
                transition_slice=dict(table=hex(U64(b, 0x78)),
                                      start=U16(b, 0x80), count=U16(b, 0x82)))


def payload_fields(b):
    flags = U64(b, 0x18)
    return dict(key_0x0c_i16=I16(b, 0x0C), flags_0x18_u64=hex(flags),
                flag_bit34=bool(flags & (1 << 34)),
                flag_bit35=bool(flags & (1 << 35)),
                sentinel_0x20_i32=I32(b, 0x20), related_key_0x30_i16=I16(b, 0x30))


class LiveGame:
    def __init__(self, pid):
        self.pid = pid
        self.handle = None
        self._sample_regions = None
        main = [m for m in modules(pid) if m["name"].lower() == "nioh.exe"]
        if len(main) != 1:
            raise ValueError("Exactly one nioh.exe module is required")
        self.main = main[0]
        digest = hashlib.sha256()
        with Path(self.main["path"]).open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != BUILD_SHA256:
            raise ValueError("Unrecognized Nioh executable; offsets are disabled")
        self.handle = kernel.OpenProcess(READ_ACCESS, False, pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            times = [W.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(self.handle, *[C.byref(t) for t in times]):
                raise C.WinError(C.get_last_error())
            creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            self.base = self.main["base"]
            self.vtable = self.base + VTABLE_RVA
            if self.bytes(self.base + 0x711C16, 4) != bytes.fromhex("48 89 7b 58"):
                raise ValueError("Native commit instruction does not match the researched build")
            if self.rtti(self.vtable) != RTTI_NAME:
                raise ValueError("Native action-node RTTI validation failed")
            self.identity = dict(pid=pid, creation_filetime=str(creation),
                                 module_base=hex(self.base), build_sha256=BUILD_SHA256,
                                 vtable=hex(self.vtable), vtable_rva=hex(VTABLE_RVA))
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def alive(self):
        code = W.DWORD()
        return bool(kernel.GetExitCodeProcess(self.handle, C.byref(code)) and code.value == 259)

    def begin_sample(self):
        # A VirtualQueryEx result covers its entire homogeneous region. Reuse it
        # only within this pass. RPM still validates/counts every actual copy.
        # Permission queries and reads are inherently non-atomic either way.
        self._sample_regions = []

    def region(self, address):
        cached = getattr(self, "_sample_regions", None)
        if cached is not None:
            for region in cached:
                if (region.BaseAddress or 0) <= address < (region.BaseAddress or 0) + region.RegionSize:
                    return region
        mbi = MEMORY_BASIC_INFORMATION()
        if not kernel.VirtualQueryEx(self.handle, address, C.byref(mbi), C.sizeof(mbi)):
            raise OSError(f"VirtualQueryEx failed at {address:#x}")
        if cached is not None and len(cached) < 64:
            cached.append(mbi)
        return mbi

    def bytes(self, address, count):
        if not 0x10000 <= address <= MAX_POINTER or not 0 < count <= 1024 * 1024:
            raise OSError("Rejected address or read size")
        end = address + count
        if end > MAX_POINTER + 1:
            raise OSError("Read exceeds user address space")
        cursor = address
        while cursor < end:
            mbi = self.region(cursor)
            stop = (mbi.BaseAddress or 0) + mbi.RegionSize
            if not readable(mbi) or stop <= cursor:
                raise OSError(f"Unreadable or guarded range at {cursor:#x}")
            cursor = min(stop, end)
        try:
            return read(self.handle, address, count)
        except OSError:
            # A region may have changed after its query. Never retain its old
            # classification after a failed copy, including partial copies.
            if getattr(self, "_sample_regions", None) is not None:
                self._sample_regions.clear()
            raise

    def rtti(self, vtable):
        try:
            locator = U64(self.bytes(vtable - 8, 8), 0)
            col = self.bytes(locator, 24)
            if U32(col, 0) != 1 or self.base + U32(col, 20) != locator:
                return None
            at = self.base + U32(col, 12) + 16
            if not self.base <= at < self.base + self.main["size"]:
                return None
            return self.bytes(at, 160).split(b"\0", 1)[0].decode("ascii", errors="replace")
        except OSError:
            return None

    def snapshot(self, address):
        raw = self.bytes(address, 0xF0)
        if U64(raw, 0) != self.vtable:
            raise OSError("Object no longer has the expected action-node vtable")
        return raw, object_fields(raw)


def metadata(game, address, entry_limit=0):
    """Observed prefixes, not claims about full allocation size or game semantics."""
    raw = game.bytes(address, 0xD0)
    result = dict(address=hex(address), descriptor_bytes=raw.hex(),
                  **descriptor_fields(raw), unknown_semantics="No frame, damage or hitbox fields identified")
    payload = int(result["payload"], 0)
    try:
        prefix = game.bytes(payload, 0x38)  # Native code reads through +0x31.
        result["payload_prefix"] = dict(address=hex(payload), bytes=prefix.hex(),
                                        **payload_fields(prefix))
    except OSError as e:
        result["payload_error"] = str(e)
    sl = result["transition_slice"]
    count = min(sl["count"], entry_limit)
    result["transition_entries"] = []
    result["entries_requested"] = count
    result["entries_omitted"] = sl["count"] - count
    if count:
        try:
            pointers = game.bytes(int(sl["table"], 0) + sl["start"] * 8, count * 8)
        except OSError as e:
            result["slice_error"] = str(e)
        else:
            for i in range(count):
                ptr = U64(pointers, i * 8)
                entry = dict(slice_index=i, table_index=sl["start"] + i, address=hex(ptr))
                try:
                    b = game.bytes(ptr, 0x30)
                    entry.update(bytes=b.hex(), byte_0x0a=b[0x0A],
                                 target_key_0x14_i16=I16(b, 0x14),
                                 condition_0x2c_i32=I32(b, 0x2C))
                except OSError as e:
                    entry["error"] = str(e)
                result["transition_entries"].append(entry)
    return result


def discover(game, seed=None):
    found = set()
    scanned = failures = 0
    if seed:
        old = json.loads(seed.read_text(encoding="utf8"))
        if old["pid"] != game.pid or int(old["vtable"], 0) != game.vtable:
            raise ValueError("Seed PID/vtable mismatch; run a fresh scan")
        if "creation_filetime" in old and any(old.get(k) != v for k, v in game.identity.items()):
            raise ValueError("Seed process/build identity mismatch; run a fresh scan")
        found = {int(o["object"], 0) for o in old["candidates"]}
    else:
        needle = struct.pack("<Q", game.vtable)
        cursor = 0
        while cursor <= MAX_POINTER and game.alive():
            try:
                mbi = game.region(cursor)
            except OSError:
                break
            end = (mbi.BaseAddress or 0) + mbi.RegionSize
            if end <= cursor:
                break
            if readable(mbi) and mbi.Type == 0x20000 and mbi.Protect & 0xFF in (4, 8, 0x40, 0x80):
                tail = b""
                for at in range(mbi.BaseAddress, end, 1024 * 1024):
                    try:
                        chunk = game.bytes(at, min(1024 * 1024, end - at))
                    except OSError:
                        failures += 1
                        tail = b""
                        continue
                    data = tail + chunk
                    pos = 0
                    while True:
                        hit = data.find(needle, pos)
                        if hit < 0:
                            break
                        pos = hit + 1
                        candidate = at - len(tail) + hit
                        if candidate % 8 == 0:
                            found.add(candidate)
                    tail = data[-7:]
                    scanned += len(chunk)
                    time.sleep(0.001)
            cursor = end
    candidates = []
    for address in sorted(found):
        try:
            _, state = game.snapshot(address)
            item = dict(object=hex(address), role="unassigned", **state)
            if int(state["current"], 0):
                item["descriptor"] = descriptor_fields(game.bytes(int(state["current"], 0), 0xD0))
            candidates.append(item)
        except OSError:
            failures += 1
    if not candidates or len(candidates) > 256:
        raise ValueError(f"Found {len(candidates)} candidates; expected 1..256. No recording armed")
    return dict(**game.identity, candidates=candidates, bytes_scanned=scanned, failed_reads=failures,
                discovery=("revalidated_seed" if "creation_filetime" in old else "legacy_addresses_revalidated_identity_unproven") if seed else "private_writable_heap_scan",
                recorded_at=time.time(), scope="CActModuleActionMotNode candidates only; actor identity unproven")


def record(game, cfg, folder, seconds, interval_ms, player, boss, entry_limit):
    from controller_reader import ControllerReader
    for key, value in game.identity.items():
        if cfg.get(key) != value:
            raise ValueError(f"Stale or incompatible discovery ({key}); run scan again")
    objects = sorted({int(o["object"], 0) for o in cfg["candidates"]})
    owners = {int(o["object"], 0): o["owner_like"] for o in cfg["candidates"]}
    if not 1 <= len(objects) <= 256 or any(a not in objects for a in (player, boss) if a is not None):
        raise ValueError("Invalid candidates or selected role address")
    if player is not None and player == boss:
        raise ValueError("Player and boss candidates must be distinct")
    required_objects = {address for address in (player, boss) if address is not None}
    folder.mkdir(parents=True, exist_ok=False)
    controller = ControllerReader()
    started = time.perf_counter()
    last = {}
    known_metadata = set()
    failures = gaps = samples = action_events = input_events = edges = 0
    snapshot_races = 0
    steady_gap = gap_total = gap_count = 0
    last_tick = None
    last_status = started
    reason = "duration"
    with (folder / "events.jsonl").open("x", encoding="utf8") as f:
        def emit(kind, observed_at=None, **fields):
            f.write(json.dumps(dict(t=round((time.perf_counter() if observed_at is None else observed_at) - started, 6), kind=kind, **fields),
                               separators=(",", ":"), allow_nan=False) + "\n")

        def status(running):
            return dict(running=running, seconds=round(time.perf_counter() - started, 3),
                        samples=samples, action_events=action_events, input_events=input_events,
                        button_edges=edges, memory_read_failures=failures, max_sample_gap_ms=round(gaps * 1000, 3),
                        snapshot_races=snapshot_races,
                        max_gap_after_first_second_ms=round(steady_gap * 1000, 3),
                        mean_sample_gap_ms=round(gap_total * 1000 / gap_count, 3) if gap_count else None,
                        controller=controller.status(), stop_reason=None if running else reason)

        emit("session", **game.identity, wall_time=time.time(), interval_ms=interval_ms,
             objects=[hex(a) for a in objects], player_candidate=hex(player) if player is not None else None,
             boss_candidate=hex(boss) if boss is not None else None,
             mode="external_read_only", atomic_snapshot=False, metadata_entry_limit=entry_limit,
             region_check_policy="refreshed each sample; reused within that sample; discarded on copy failure",
             stop_policy="duration, process exit, STOP file, or loss of any selected actor's object/owner identity; not a death detector",
             discovery_candidates=cfg["candidates"],
             notes="OS inputs are separate from game-accepted inputs. Roles are investigator labels. "
                   "Temporal adjacency is not causation. Durations are sampled wall time, not frame data.")
        try:
            while time.perf_counter() - started < seconds:
                tick = time.perf_counter()
                if (folder / "STOP").exists():
                    reason = "stop_file"
                    break
                if not game.alive():
                    reason = "process_exit"
                    break
                if hasattr(game, "begin_sample"):
                    game.begin_sample()
                if last_tick is not None:
                    gap = tick - last_tick
                    gaps = max(gaps, gap)
                    gap_total += gap
                    gap_count += 1
                    if tick - started >= 1:
                        steady_gap = max(steady_gap, gap)
                    if gap > 0.030:
                        emit("sampling_gap", start_t=round(last_tick - started, 6), duration_ms=round(gap * 1000, 3))
                last_tick = tick
                for event in controller.poll():
                    kind = event.pop("kind")
                    emit(kind, observed_at=event["observed_monotonic"], **event)
                    input_events += kind == "input"
                    for field in ("pressed_mask", "released_mask"):
                        edges += (event.get(field) or 0).bit_count()
                valid_objects = 0
                valid_required = set()
                invalid_required = set()

                def checked_snapshot(address):
                    try:
                        result = game.snapshot(address)
                    except OSError:
                        if address in required_objects:
                            invalid_required.add(address)
                            valid_required.discard(address)
                        raise
                    if address in required_objects:
                        if result[1]["owner_like"] != owners[address]:
                            invalid_required.add(address)
                            valid_required.discard(address)
                            emit("tracked_actor_changed", object=hex(address),
                                 expected_owner=owners[address], observed_owner=result[1]["owner_like"])
                            raise OSError("Selected actor owner identity changed")
                        if address not in invalid_required:
                            valid_required.add(address)
                    return result

                for address in objects:
                    try:
                        raw, state = checked_snapshot(address)
                        valid_objects += 1
                        identity_matches = state["owner_like"] == owners[address]
                        if last.get(address) == state:
                            continue
                        prior = last.get(address)
                        role = "player_candidate" if address == player and identity_matches else "boss_candidate" if address == boss and identity_matches else "unassigned"
                        current = int(state["current"], 0)
                        desc = None
                        if current:
                            d = game.bytes(current, 0xD0)
                            desc = descriptor_fields(d)
                        after, state_after = checked_snapshot(address)
                        if state_after != state:
                            emit("snapshot_race", object=hex(address))
                            last[address] = "unreadable"
                            snapshot_races += 1
                            continue
                        change = "initial" if not isinstance(prior, dict) else "descriptor" if prior["current"] != state["current"] else "state_only"
                        emit("action_state", object=hex(address), role=role, change=change,
                             owner_matches_discovery=identity_matches,
                             descriptor=desc, **state)
                        action_events += 1
                        last[address] = state
                        if current:
                            limit = entry_limit if role == "boss_candidate" else 0
                            key = (address, current, d, limit)
                            if key not in known_metadata and len(known_metadata) < 8192:
                                try:
                                    detail = metadata(game, current, limit)
                                    _, final_state = checked_snapshot(address)
                                    detail["matches_preceding_state"] = (final_state == state and detail["descriptor_bytes"] == d.hex())
                                    emit("metadata", object=hex(address), role=role, **detail)
                                    if detail["matches_preceding_state"]:
                                        known_metadata.add(key)
                                except OSError as e:
                                    emit("metadata_unreadable", object=hex(address), address=hex(current), error=str(e))
                                    failures += 1
                    except OSError as e:
                        failures += 1
                        if last.get(address) != "unreadable":
                            emit("object_unreadable", object=hex(address), error=str(e))
                        last[address] = "unreadable"
                samples += 1
                missing_required = required_objects - valid_required
                if missing_required:
                    reason = "selected_actor_invalid_rediscovery_required"
                    emit("rediscovery_required", reason=reason, objects=[hex(a) for a in sorted(missing_required)])
                    break
                if not valid_objects:
                    reason = "no_valid_action_objects_rediscovery_required"
                    emit("rediscovery_required", reason=reason)
                    break
                if time.perf_counter() - last_status >= 1:
                    f.flush()
                    (folder / "status.json").write_text(json.dumps(status(True)), encoding="utf8")
                    last_status = time.perf_counter()
                time.sleep(max(0, interval_ms / 1000 - (time.perf_counter() - tick)))
        except KeyboardInterrupt:
            reason = "keyboard_interrupt"
        except BaseException:
            reason = "error"
            raise
        finally:
            final = status(False)
            emit("end", **final)
            (folder / "status.json").write_text(json.dumps(final, indent=2), encoding="utf8")
    print(json.dumps(final, indent=2))


def report(source, folder):
    folder.mkdir(parents=True, exist_ok=False)
    candidates = {}
    transitions = []
    last = {}
    inputs = []
    gaps_by_object = {}
    sampling_gaps = []
    rows = []
    session = None
    with source.open(encoding="utf8") as f:
        for line in f:
            e = json.loads(line)
            if e["kind"] == "session":
                session = e
            if e["kind"] == "sampling_gap":
                sampling_gaps.append((e["start_t"], e["t"]))
                rows.append(dict(t=e["t"], event=e["kind"], subject="all_streams", word0_hex="", index="",
                                 buttons_hex="", pressed_hex="", released_hex="", note=f'{e["duration_ms"]} ms sampling gap'))
            if e["kind"] in ("input", "input_unavailable"):
                inputs.append(e)
                rows.append(dict(t=e["t"], event=e["kind"], subject=f'{e.get("backend")}:{e.get("slot")}',
                                 word0_hex="", index="", buttons_hex=hex(e["buttons"]) if "buttons" in e else "",
                                 pressed_hex=hex(e["pressed_mask"]) if e.get("pressed_mask") is not None else "unknown",
                                 released_hex=hex(e["released_mask"]) if e.get("released_mask") is not None else "unknown",
                                 note="OS observation; button function uncalibrated"))
            if e["kind"] in ("object_unreadable", "snapshot_race", "tracked_actor_changed"):
                last.pop(e["object"], None)
                gaps_by_object.setdefault(e["object"], []).append(e["t"])
                rows.append(dict(t=e["t"], event=e["kind"], subject=e["object"], word0_hex="", index="",
                                 buttons_hex="", pressed_hex="", released_hex="", note="Observation gap; continuity unknown"))
            if e["kind"] != "action_state":
                continue
            obj = e["object"]
            if session and obj == session.get("player_candidate") and e["role"] != "player_candidate":
                gaps_by_object.setdefault(obj, []).append(e["t"])
            info = candidates.setdefault(obj, dict(object=obj, role=e["role"], owner_like=e["owner_like"],
                                                   observations=0, descriptor_changes=0, words=set()))
            info["observations"] += 1
            d = e.get("descriptor") or {}
            word = d.get("word0_hex", "")
            if word:
                info["words"].add(word)
            key = (e["owner_like"], e["current"], e["index"])
            if last.get(obj) == key:
                continue
            if obj in last and last[obj][1] != key[1]:
                info["descriptor_changes"] += 1
            last[obj] = key
            transitions.append(e)
            rows.append(dict(t=e["t"], event="action", subject=f'{e["role"]}:{obj}',
                             word0_hex=word, index=e["index"], buttons_hex="", pressed_hex="", released_hex="",
                             note="candidate record word; sampled transition"))
    if not session:
        raise ValueError("Capture has no session header")
    def csv_out(name, data, fields):
        with (folder / name).open("x", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(data)
    csv_out("timeline.csv", sorted(rows, key=lambda x: x["t"]),
            ["t", "event", "subject", "word0_hex", "index", "buttons_hex", "pressed_hex", "released_hex", "note"])
    ranking = sorted(candidates.values(), key=lambda x: x["descriptor_changes"], reverse=True)
    for row in ranking:
        row["unique_words"] = len(row["words"])
        row["words"] = " ".join(sorted(row["words"]))
    csv_out("candidates.csv", ranking,
            ["object", "role", "owner_like", "observations", "descriptor_changes", "unique_words", "words"])
    player_events = sorted([e for e in transitions if e["role"] == "player_candidate"], key=lambda e: e["t"])
    player_times = [e["t"] for e in player_events]
    edge_events = sorted([e for e in inputs if e["kind"] == "input" and (e.get("pressed_mask") or e.get("released_mask"))], key=lambda e: e["t"])
    input_gaps = [e for e in inputs if e["kind"] == "input_unavailable"]
    associations = []
    def word_of(event):
        return (event.get("descriptor") or {}).get("word0_hex", "") if event else ""
    for i, edge in enumerate(edge_events):
        at = bisect.bisect_right(player_times, edge["t"])
        before = player_events[at - 1] if at else None
        after = player_events[at] if at < len(player_events) and player_times[at] - edge["t"] <= 1 else None
        gap = any(lo <= edge["t"] <= hi for lo, hi in sampling_gaps)
        if before and any(before["t"] <= t <= edge["t"] for t in gaps_by_object.get(before["object"], [])):
            before = None
            gap = True
        if after and (any(edge["t"] <= t <= after["t"] for t in gaps_by_object.get(after["object"], []))
                      or any(e["backend"] == edge["backend"] and e["slot"] == edge["slot"]
                             and edge["t"] <= e["t"] <= after["t"] for e in input_gaps)):
            after = None
            gap = True
        intervening = bool(after and i + 1 < len(edge_events) and edge_events[i + 1]["t"] < after["t"])
        if after and any(lo <= after["t"] and hi >= edge["t"] for lo, hi in sampling_gaps):
            after = None
            gap = True
        associations.append(dict(t=edge["t"], backend=edge["backend"], slot=edge["slot"],
                                 pressed_hex=hex(edge.get("pressed_mask") or 0), released_hex=hex(edge.get("released_mask") or 0),
                                 last_player_word0=word_of(before), next_player_word0=word_of(after),
                                 next_delay_ms=round((after["t"] - edge["t"]) * 1000, 3) if after else "",
                                 intervening_input=intervening, observation_gap=gap,
                                 interpretation="Temporal association only; no game input acceptance established"))
    csv_out("input_action_links.csv", associations,
            ["t", "backend", "slot", "pressed_hex", "released_hex", "last_player_word0", "next_player_word0", "next_delay_ms", "intervening_input", "observation_gap", "interpretation"])
    save_new(folder / "summary.json", dict(session=session, input_observations=len(inputs),
                                           transitions=len(transitions), candidates=len(candidates),
                                           interpretation="Inspect shared timestamps; no automatic input-to-action assignment"))
    print(json.dumps(dict(candidates=len(candidates), transitions=len(transitions), input_observations=len(inputs))))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--pid", type=int, required=True)
    scan.add_argument("--out", type=Path, required=True)
    scan.add_argument("--seed", type=Path, help="Revalidate earlier addresses; does not discover newly spawned actors")
    rec = commands.add_parser("record")
    rec.add_argument("--config", type=Path, required=True)
    rec.add_argument("--outdir", type=Path, required=True)
    rec.add_argument("--seconds", type=float, default=120)
    rec.add_argument("--interval-ms", type=float, default=10)
    rec.add_argument("--player", type=lambda x: int(x, 0))
    rec.add_argument("--boss", type=lambda x: int(x, 0))
    rec.add_argument("--entries", type=int, default=0, help="0..64 transition entries per selected boss descriptor")
    ins = commands.add_parser("inspect")
    ins.add_argument("--pid", type=int, required=True)
    ins.add_argument("--descriptor", type=lambda x: int(x, 0), required=True)
    ins.add_argument("--out", type=Path, required=True)
    ins.add_argument("--entries", type=int, default=64)
    rep = commands.add_parser("report")
    rep.add_argument("--events", type=Path, required=True)
    rep.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    if hasattr(a, "entries") and not 0 <= a.entries <= 64:
        p.error("--entries must be 0..64")
    if a.command == "report":
        report(a.events, a.outdir)
        return
    if a.command == "record":
        if not 0 < a.seconds <= 1800 or not 5 <= a.interval_ms <= 1000:
            p.error("Duration must be 0..1800 seconds; interval must be 5..1000 ms")
        cfg = json.loads(a.config.read_text(encoding="utf8"))
        with LiveGame(cfg["pid"]) as game:
            record(game, cfg, a.outdir, a.seconds, a.interval_ms, a.player, a.boss, a.entries)
    else:
        if a.out.exists():
            p.error("Output already exists; choose a new filename")
        with LiveGame(a.pid) as game:
            result = discover(game, a.seed) if a.command == "scan" else dict(session=game.identity, **metadata(game, a.descriptor, a.entries))
            save_new(a.out, result)
            print(json.dumps({k: v for k, v in result.items() if k not in ("candidates", "transition_entries", "descriptor_bytes")}, indent=2))
            if "candidates" in result:
                print("Candidates:", len(result["candidates"]))


if __name__ == "__main__":
    main()
