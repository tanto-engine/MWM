# Reported MWM issues

These results describe source changes and offline checks. They do not establish live Nioh acceptance; the GitHub issues remain open.

| Issue | Mechanism and result |
|---|---|
| #1 Oda two-hit speed | Frost Moon dispatch previously forced every destination to 1x. Ordinary destinations now use their configured playback rate, including inherited graph-phase settings. Paired animations keep native timing. A native owned-memory test reproduced 2x being discarded and now checks the clock result. |
| #2 Isle of Demons crash | Root cause remains unconfirmed. Preventive loader changes now defer native allocations until the current callback freshly identifies William and the motion-data allocator exists. Regression tests reproduced allocation from an unrelated/reused actor frame before the fix. Loader ownership v9 prevents cached older DLLs from bypassing these guards. No game process was controlled. |
| #3 Okatsu Charged Rush held input | The editor and validator limited held inputs to adapted graphs, while native deferral required a graph's William descriptor. Ordinary Okatsu moves now have an explicit held-input capability and use the existing validated source dispatcher after hold recognition. Native tests cover tap/hold in all three stances and rejecting a pending press after a stance change. |
| #4 Override slots | Eight was a fixed serialization/storage limit. The session now carries 32 compiled override entries; the editor relies on compiler validation instead of its obsolete eight-row precheck. Native source/stance ownership constraints still apply. |
| #5 Move phases | The session now carries 64 phases. Python validation, gesture variants, native storage and cycle validation use the expanded capacity. Tests exercise 33-phase real presets, all 64 serialized slots, and a native cycle above index 31. |

The binary session contract is now version 12, 12,416 bytes. Build matching Python/native components together; this change does not update an already released EXE. Capacity increases do not add unsupported source actions or make conflicting stance ownership valid.

Verification: 255 workflow tests and 8 resource tests passed, including the isolated Electron editor test. The final native hold-context change also passed the native replacement harness and production DLL build. No EXE release was produced.

## Mission-entry investigation

Read-only Windows records show historical local Nioh crashes on 2026-09-27: exception `0xc0000409` at `nioh.exe+0x112a615` (WER subcode 7), and `0xc0000005` at `+0x10fb260`. Archived reports contain loaded module lists, including retained resource/runtime DLLs, but no remaining dump or stack. Their connection to GitHub issue #2 is unknown.

The demonstrated source defect was narrower: the resource hook called the native allocator on the first actor frame even when player identification had failed. Mission creation or teardown can expose incomplete player/allocator state; constructing imported resources in that interval is a plausible crash mechanism. The new gate retries later without allocating, while a validated player frame still submits normally and preserves native failure reporting. Existing asynchronous decodes and retained resources keep their lifetime rules.

Native memory tests cover unrelated actor frames, a reused cached player address, missing data allocator, readiness becoming available, and unchanged native return value/LastError. A separate cache regression proves schema-8 ownership cannot silently select the old DLL. Live mission entry with the reported preset remains necessary to establish whether these guards address the actual crash. Use a fresh game process for that comparison so older retained DLL generations cannot affect the result.

The preventive patch passed the native loader harness (including deferred discovery and reattachment), production DLL build, and all eight resource checks. The complete workflow initially passed 255 tests; a final rerun hit the Electron harness's 35-second timeout, and that unchanged UI test passed independently on retry. No EXE was released.
