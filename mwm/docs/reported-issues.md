# Reported MWM issues

These results describe source changes and offline checks for the alpha.6 candidate. They do not establish live Nioh acceptance. Close only issues whose reported editor or capacity defect is covered; keep the two crashes and gameplay-dependent reports open.

| Issue | Mechanism and result |
|---|---|
| #1 Oda two-hit speed | Frost Moon dispatch previously forced every destination to 1x. Ordinary destinations now use their configured playback rate, including inherited graph-phase settings. Paired animations keep native timing. A native owned-memory test reproduced 2x being discarded and now checks the clock result. |
| #2 Isle of Demons crash | Root cause remains unconfirmed. Preventive loader changes now defer native allocations until the current callback freshly identifies William and the motion-data allocator exists. Regression tests reproduced allocation from an unrelated/reused actor frame before the fix. Loader ownership v9 prevents cached older DLLs from bypassing these guards. No game process was controlled. |
| #3 Okatsu Charged Rush held input | The editor and validator limited held inputs to adapted graphs, while native deferral required a graph's William descriptor. Ordinary Okatsu moves now have an explicit held-input capability and use the existing validated source dispatcher after hold recognition. Native tests cover tap/hold in all three stances and rejecting a pending press after a stance change. |
| #4 Override slots | The session carries 32 compiled original-input entries. Alpha.7 adds 24 separate custom controller routes, each with its own stance, reviewed move, tap/hold gesture and L1/LB + B/Y/LT/X chord. A custom route leaves its named original Nioh input unchanged. Other controller pairs still lack reviewed native interception. |
| #5 Move phases | The session now carries 64 phases. Python validation, gesture variants, native storage and cycle validation use the expanded capacity. Tests exercise 33-phase real presets, all 64 serialized slots, and a native cycle above index 31. |
| #6 Quick Attack stance | The old validator and capability list forced Quick Attack to Low. All three native stance signatures now compile and dispatch separately; the editor offers Low, Mid, High and Any where the move permits it. A graph still needs one concrete stance. |
| #7 Omnislice Ki Pulse | The recorded action usually ends around frame 108, while Pulse onset was frame 120. Its exact recovery onset is now frame 72 and a native test checks this action. Live R1/RB and contact behavior remain unverified. |
| #8 Custom inputs | Fixed the confirmed LB+B competition with native dodge. Alpha.7 also tests independent LB+B tap, LB+Y hold and the original LB+LT analog tap through one command sequence. Physical-controller and live Nioh retests remain necessary before closing the report. |
| #9 Held custom input blocking | The button reservation remained armed after a chord fired or expired. Both the publisher and native consumer now release/reject that stale reservation; the native regression reproduces the prior blocking state. Physical controller and live combat acceptance remain pending. |

The binary session contract is now version 12, 12,416 bytes. Build matching Python/native components together; this change does not update an already released EXE. Capacity increases do not add unsupported source actions or make conflicting stance ownership valid.

Verification of the integrated source: 263 workflow tests and 8 resource tests passed, including the isolated Electron editor test. The native DLLs built. Live gameplay was not assessed.

## Mission-entry investigation

Read-only Windows records show historical local Nioh crashes on 2026-09-27: exception `0xc0000409` at `nioh.exe+0x112a615` (WER subcode 7), and `0xc0000005` at `+0x10fb260`. Archived reports contain loaded module lists, including retained resource/runtime DLLs, but no remaining dump or stack. Their connection to GitHub issue #2 is unknown.

The demonstrated source defect was narrower: the resource hook called the native allocator on the first actor frame even when player identification had failed. Mission creation or teardown can expose incomplete player/allocator state; constructing imported resources in that interval is a plausible crash mechanism. The new gate retries later without allocating, while a validated player frame still submits normally and preserves native failure reporting. Existing asynchronous decodes and retained resources keep their lifetime rules.

Native memory tests cover unrelated actor frames, a reused cached player address, missing data allocator, readiness becoming available, and unchanged native return value/LastError. A separate cache regression proves schema-8 ownership cannot silently select the old DLL. Live mission entry with the reported preset remains necessary to establish whether these guards address the actual crash. Use a fresh game process for that comparison so older retained DLL generations cannot affect the result.

The preventive patch passed the native loader harness (including deferred discovery and reattachment), production DLL build, and all eight resource checks. The complete workflow initially passed 255 tests; a final rerun hit the Electron harness's 35-second timeout, and that unchanged UI test passed independently on retry. No EXE was released.
