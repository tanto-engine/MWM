# Reported MWM issues

These results describe source changes and offline checks. They do not establish live Nioh acceptance; the GitHub issues remain open.

| Issue | Mechanism and result |
|---|---|
| #1 Oda two-hit speed | Frost Moon dispatch previously forced every destination to 1x. Ordinary destinations now use their configured playback rate, including inherited graph-phase settings. Paired animations keep native timing. A native owned-memory test reproduced 2x being discarded and now checks the clock result. |
| #2 Isle of Demons crash | Unresolved. The report identifies mission entry with the mod enabled, but supplies no crash dump, exception address, active preset or runtime log. Existing resource ownership and mission-transition regressions are useful safeguards; passing them cannot identify this crash. No game process was controlled for this investigation. |
| #3 Okatsu Charged Rush held input | The editor and validator limited held inputs to adapted graphs, while native deferral required a graph's William descriptor. Ordinary Okatsu moves now have an explicit held-input capability and use the existing validated source dispatcher after hold recognition. Native tests cover tap/hold in all three stances and rejecting a pending press after a stance change. |
| #4 Override slots | Eight was a fixed serialization/storage limit. The session now carries 32 compiled override entries; the editor relies on compiler validation instead of its obsolete eight-row precheck. Native source/stance ownership constraints still apply. |
| #5 Move phases | The session now carries 64 phases. Python validation, gesture variants, native storage and cycle validation use the expanded capacity. Tests exercise 33-phase real presets, all 64 serialized slots, and a native cycle above index 31. |

The binary session contract is now version 12, 12,416 bytes. Build matching Python/native components together; this change does not update an already released EXE. Capacity increases do not add unsupported source actions or make conflicting stance ownership valid.

Verification: 255 workflow tests and 8 resource tests passed, including the isolated Electron editor test. The final native hold-context change also passed the native replacement harness and production DLL build. No EXE release was produced.
