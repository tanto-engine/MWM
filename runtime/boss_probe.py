# Nioh 1 action research. Standard library only; external memory reads only.
#
# scan discovers native action-node candidates; record logs inputs and actions;
# inspect reads a bounded record and its transition slice; report exports CSV.
# Offsets are restricted to the executable fingerprint researched in this session.
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
U16 = lambda b, p: (
    # Decode one unsigned 16-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from("<H", b, p)[0])
I16 = lambda b, p: (
    # Decode one signed 16-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from("<h", b, p)[0])
U32 = lambda b, p: (
    # Decode one unsigned 32-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from("<I", b, p)[0])
I32 = lambda b, p: (
    # Decode one signed 32-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from("<i", b, p)[0])
U64 = lambda b, p: (
    # Decode one unsigned 64-bit field from the supplied byte snapshot.
    # Use an explicit little-endian layout at the requested offset.
    # Keep native structure interpretation consistent across research readers.
    struct.unpack_from("<Q", b, p)[0])

kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
kernel.GetProcessTimes.restype = W.BOOL
kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
kernel.GetExitCodeProcess.restype = W.BOOL


def save_new(path, value):
    # Write a new evidence document without overwriting prior captures.
    # Create its parent directory and reject non-finite JSON values.
    # Keep saved observations reproducible and uniquely addressed.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as f:
        json.dump(value, f, indent=2, allow_nan=False)


def readable(mbi):
    # Classify committed memory using its protection flags.
    # Exclude guard pages and non-readable access modes.
    # Discovery uses this filter before copying remote regions.
    return (mbi.State == 0x1000 and not mbi.Protect & 0x100
            and mbi.Protect & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80))


def object_fields(b):
    # Decode researched fields from one action-node byte snapshot.
    # Keep pointers as diagnostic strings and action indices as integers.
    # Separate raw object state from any inferred move identity.
    return dict(owner_like=hex(U64(b, 0x50)), current=hex(U64(b, 0x58)),
                previous=hex(U64(b, 0x60)), index=U32(b, 0x68),
                previous_index=U32(b, 0x6C), transition=hex(U64(b, 0x90)),
                previous_transition=hex(U64(b, 0x98)), pending=hex(U64(b, 0xB0)),
                pending_index=I32(b, 0xC0), counter=U32(b, 0xDC))


def descriptor_fields(b):
    # Decode the action key, payload pointer and transition slice.
    # Preserve both full DWORD and low-word representations.
    # Native lookup comparisons require the complete key.
    return dict(action_key_u32=U32(b, 0), action_key_hex=f"0x{U32(b, 0):08X}",
                word0_u16=U16(b, 0), word0_hex=f"0x{U16(b, 0):04X}",
                payload=hex(U64(b, 0x20)),
                combat_slice=dict(table=hex(U64(b,0x48)),start=U16(b,0x50),count=U16(b,0x52)),
                transition_slice=dict(table=hex(U64(b, 0x78)),
                                      start=U16(b, 0x80), count=U16(b, 0x82)))


def payload_fields(b):
    # Decode motion selection, timing override and researched payload flags.
    # Use the motion ID only when the override is negative.
    # Preserve raw fields without assigning unsupported combat semantics.
    flags = U64(b, 0x18)
    motion, override = I32(b, 0x20), I32(b, 0x34)
    result = dict(key_0x0c_i16=I16(b, 0x0C), flags_0x18_u64=hex(flags),
                motion_id=motion, timing_override=override,
                timing_id=motion if override < 0 else override,
                flag_bit34=bool(flags & (1 << 34)),
                flag_bit35=bool(flags & (1 << 35)),
                sentinel_0x20_i32=I32(b, 0x20), related_key_0x30_i16=I16(b, 0x30),
                recovery_frame=I16(b,0x24),cancel_frame=I16(b,0x26),ki_pulse_percent=b[0x33])
    if len(b)>=0x3E:
        result.update(ki_pulse_start=I16(b,0x38),ki_pulse_fill=I16(b,0x3A),ki_pulse_hold=I16(b,0x3C))
    return result


class LiveGame:
    def __init__(self, pid):
        # Open a read-only process after verifying its executable hash.
        # Confirm the native commit instruction and action-node RTTI.
        # Close the handle if initialization cannot establish the supported build.
        self.pid = pid
        self.handle = None
        self._sample_regions = None
        main = [m for m in modules(pid) if m["name"].lower() == "nioh.exe"]
        if len(main) != 1:
            raise ValueError("Exactly one nioh.exe module is required")
        self.main = main[0]
        digest = hashlib.sha256()
        with Path(self.main["path"]).open("rb") as f:
            for chunk in iter(lambda: (
                # Read the next bounded chunk for a file hash.
                # An empty chunk terminates the sentinel iterator at end of file.
                # Avoid copying the entire executable or capture into memory to fingerprint it.
                f.read(1024 * 1024)), b""):
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
        # Release the process handle owned by this reader.
        # Clear the reference after closing it.
        # Allow cleanup from initialization failure or context exit.
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        # Expose the initialized read-only reader to a with block.
        # The constructor has already established process identity.
        # The matching context exit owns handle cleanup.
        return self

    def __exit__(self, *exc):
        # Close the process handle when the with block exits.
        # Preserve any exception raised while inspecting the game.
        # Failed reads must remain visible to the caller.
        self.close()

    def alive(self):
        # Query the exit status through the existing process handle.
        # Accept only the Windows still-active result.
        # Stop capture when its original process lifetime ends.
        code = W.DWORD()
        return bool(kernel.GetExitCodeProcess(self.handle, C.byref(code)) and code.value == 259)

    def begin_sample(self):
        # Discard memory-region classifications from the previous sample.
        # Reuse region queries only within the next sampling pass.
        # Avoid treating permissions from an earlier frame as current.
        # A VirtualQueryEx result covers its entire homogeneous region. Reuse it
        # only within this pass. RPM still validates/counts every actual copy.
        # Permission queries and reads are inherently non-atomic either way.
        self._sample_regions = []

    def region(self, address):
        # Query the region containing an address, reusing this sample's cache.
        # Limit retained regions to keep long scans from growing the cache.
        # Actual byte reads still verify every requested copy.
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
        # Read a bounded span after checking each covered region.
        # Reject guards, overflow and partial copies before decoding.
        # Invalidate cached permissions when a region changes during the read.
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
        # Follow the MSVC locator to the class name within the image.
        # Check locator self-reference and image bounds before decoding.
        # Return no identity for unreadable or unrelated vtables.
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
        # Read one action-node prefix and verify its expected vtable.
        # Decode state only after the object type check succeeds.
        # Detect freed or repurposed actor addresses during capture.
        raw = self.bytes(address, 0xF0)
        if U64(raw, 0) != self.vtable:
            raise OSError("Object no longer has the expected action-node vtable")
        return raw, object_fields(raw)


def metadata(game, address, entry_limit=0):
    # Capture a descriptor, recovery/Pulse payload and bounded native row slices.
    # Retain individual read errors alongside the available raw evidence.
    # Do not discard an entire action because an optional dependency vanished.
    raw = game.bytes(address, 0xD0)
    result = dict(address=hex(address), descriptor_bytes=raw.hex(),
                  **descriptor_fields(raw), unknown_semantics="Damage scaling, hitboxes and unnamed row fields remain unverified")
    payload = int(result["payload"], 0)
    try:
        prefix = game.bytes(payload, 0x40)  # Include native recovery and Pulse durations through+0x3C.
        result["payload_prefix"] = dict(address=hex(payload), bytes=prefix.hex(),
                                        **payload_fields(prefix))
    except OSError as e:
        result["payload_error"] = str(e)
    for name,size,limit in [('transition',0x30,min(entry_limit,128)),('combat',0x80,min(entry_limit,16))]:
        sl=result[name+'_slice']; count=min(sl['count'],limit)
        entries=result[name+'_entries']=[]
        prefix='' if name=='transition' else 'combat_'
        result[prefix+'entries_requested']=count
        result[prefix+'entries_omitted']=sl['count']-count
        if not count:
            continue
        try:
            pointers = game.bytes(int(sl["table"], 0) + sl["start"] * 8, count * 8)
        except OSError as e:
            result[prefix+'slice_error'] = str(e)
        else:
            for i in range(count):
                ptr = U64(pointers, i * 8)
                entry = dict(slice_index=i, table_index=sl["start"] + i, address=hex(ptr))
                try:
                    b = game.bytes(ptr, size)
                    entry['bytes']=b.hex()
                    if name=='transition':
                        entry.update(byte_0x0a=b[0x0A],target_key_0x14_i16=I16(b,0x14),
                                     condition_0x2c_i32=I32(b,0x2C))
                except OSError as e:
                    entry["error"] = str(e)
                entries.append(entry)
    return result


def discover(game, seed=None, stop_requested=None):
    # Find aligned action-node vtable references in writable private memory.
    # Revalidate candidate snapshots and bind them to process identity.
    # Support cancellation during long scans without arming stale actors.
    found = set()
    scanned = failures = 0
    if seed:
        old = json.loads(seed.read_text(encoding="utf8"))
        if old["pid"] != game.pid or int(old["vtable"], 0) != game.vtable:
            raise ValueError("Seed PID/vtable mismatch; run a fresh scan")
        if "creation_filetime" in old and any(old.get(k) != v for k, v in game.identity.items()):
            raise ValueError("Seed process/build identity mismatch; run a fresh scan")
        found = {int(o["object"], 0) for o in old["candidates"]}
        # Retries often rebuild actors nearby in the same native allocation pool.
        # Search only their64KiB neighborhoods after exact process-birth validation.
        # This read-only bounded path avoids a multi-gigabyte scan between deaths.
        if "creation_filetime" in old:
            windows=set(); needle=struct.pack('<Q',game.vtable)
            for address in tuple(found):
                if stop_requested and stop_requested(): raise InterruptedError('Discovery cancelled')
                try:
                    region=game.region(address)
                    if not readable(region): continue
                    start=max(region.BaseAddress,address & ~0xffff)
                    end=min(region.BaseAddress+region.RegionSize,start+0x10000)
                    if (start,end) in windows: continue
                    windows.add((start,end)); raw=game.bytes(start,end-start); scanned+=len(raw)
                    position=raw.find(needle)
                    while position!=-1:
                        if (start+position)%8==0: found.add(start+position)
                        position=raw.find(needle,position+1)
                except OSError:
                    failures+=1
    else:
        needle = struct.pack("<Q", game.vtable)
        cursor = 0
        while cursor <= MAX_POINTER and game.alive():
            if stop_requested and stop_requested():
                raise InterruptedError("Discovery cancelled")
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
                    if stop_requested and stop_requested():
                        raise InterruptedError("Discovery cancelled")
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


def record(game, cfg, folder, seconds, interval_ms, player, boss, entry_limit,
           stop_requested=None, session_context=None):
    # Record controller changes and coherent action snapshots into one timeline.
    # Recheck owner identity and descriptor reads before assigning roles.
    # End a take on actor loss so the encounter loop can rediscover it.
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
    # Scout captures have no confirmed boss identity. Losing any discovered
    # candidate must trigger discovery again, even while William remains valid.
    required_objects = set(objects) if boss is None else {address for address in (player, boss) if address is not None}
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
            # Append a timestamped event to the current take's stream.
            # Use the supplied observation clock when a sample was read earlier.
            # Keep controller and action events on the same elapsed-time axis.
            f.write(json.dumps(dict(t=round((time.perf_counter() if observed_at is None else observed_at) - started, 6), kind=kind, **fields),
                               separators=(",", ":"), allow_nan=False) + "\n")

        def status(running):
            # Summarize sampling gaps, identity races and controller counters.
            # Distinguish an active capture from its final stop reason.
            # Make missed observations visible when judging sequence continuity.
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
             encounter_context=session_context,
             mode="external_read_only", atomic_snapshot=False, metadata_entry_limit=entry_limit,
             region_check_policy="refreshed each sample; reused within that sample; discarded on copy failure",
             stop_policy="duration, process exit, STOP file, or loss of selected actor identity (all candidates in scout mode); not a death detector",
             discovery_candidates=cfg["candidates"],
             notes="OS inputs are separate from game-accepted inputs. Roles are investigator labels. "
                   "Temporal adjacency is not causation. Durations are sampled wall time, not frame data.")
        try:
            while time.perf_counter() - started < seconds:
                tick = time.perf_counter()
                if (folder / "STOP").exists() or (stop_requested and stop_requested()):
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
                    # Verify the sampled actor still belongs to its discovered owner.
                    # Track required identities that fail or change during this tick.
                    # Do not let a later successful read erase an earlier identity failure.
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
    return final


def report(source, folder):
    # Reconstruct a diagnostic timeline from a saved external capture.
    # Associate input edges with nearby actions using ordered timestamps.
    # Break associations across gaps rather than claiming input causation.
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
        # Export one diagnostic table with explicit columns.
        # Use a new UTF-8 CSV file suitable for spreadsheet inspection.
        # Preserve the source capture and previous reports.
        with (folder / name).open("x", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(data)
    csv_out("timeline.csv", sorted(rows, key=lambda x: (
        # Order retained evidence by its sampled elapsed time.
        # Use the timestamp stored on each event or report row.
        # Allow adjacent-event lookup without changing the original observations.
        x["t"])),
            ["t", "event", "subject", "word0_hex", "index", "buttons_hex", "pressed_hex", "released_hex", "note"])
    ranking = sorted(candidates.values(), key=lambda x: (
        # Rank actor candidates by observed descriptor changes.
        # Read the change count accumulated from the saved timeline.
        # Guide inspection without claiming the busiest actor is the boss.
        x["descriptor_changes"]), reverse=True)
    for row in ranking:
        row["unique_words"] = len(row["words"])
        row["words"] = " ".join(sorted(row["words"]))
    csv_out("candidates.csv", ranking,
            ["object", "role", "owner_like", "observations", "descriptor_changes", "unique_words", "words"])
    player_events = sorted([e for e in transitions if e["role"] == "player_candidate"], key=lambda e: (
        # Order retained evidence by its sampled elapsed time.
        # Use the timestamp stored on each event or report row.
        # Allow adjacent-event lookup without changing the original observations.
        e["t"]))
    player_times = [e["t"] for e in player_events]
    edge_events = sorted([e for e in inputs if e["kind"] == "input" and (e.get("pressed_mask") or e.get("released_mask"))], key=lambda e: (
        # Order retained evidence by its sampled elapsed time.
        # Use the timestamp stored on each event or report row.
        # Allow adjacent-event lookup without changing the original observations.
        e["t"]))
    input_gaps = [e for e in inputs if e["kind"] == "input_unavailable"]
    associations = []
    def word_of(event):
        # Extract the recorded descriptor word for an optional adjacent event.
        # Return a blank cell when that observation is unavailable.
        # A missing association must not masquerade as a move ID.
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
    # Dispatch explicit scan, record, inspect or report research commands.
    # Validate bounds before opening a read-only game connection.
    # Keep offline reporting usable without an attached process.
    p = argparse.ArgumentParser(description='Record Nioh action state without game-memory writes.')
    commands = p.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--pid", type=int, required=True)
    scan.add_argument("--out", type=Path, required=True)
    scan.add_argument("--seed", type=Path, help="Revalidate this process's earlier actors and nearby64KiB allocation blocks")
    rec = commands.add_parser("record")
    rec.add_argument("--config", type=Path, required=True)
    rec.add_argument("--outdir", type=Path, required=True)
    rec.add_argument("--seconds", type=float, default=120)
    rec.add_argument("--interval-ms", type=float, default=10)
    rec.add_argument("--player", type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)))
    rec.add_argument("--boss", type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)))
    rec.add_argument("--entries", type=int, default=0, help="0..64 transition entries per selected boss descriptor")
    ins = commands.add_parser("inspect")
    ins.add_argument("--pid", type=int, required=True)
    ins.add_argument("--descriptor", type=lambda x: (
        # Parse an explicit CLI address or action key.
        # Accept decimal and prefixed hexadecimal through Python integer parsing.
        # Reject malformed values before the command can attach to a process.
        int(x, 0)), required=True)
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
