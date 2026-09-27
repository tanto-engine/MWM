# Tanto Engine

Private Nioh framework for move adaptation, controller input, timing, Ki Pulse, physics and native hooks. MWM and Recorder package only the runtime components they need; players do not need this repository.

Session preparation matches the game build, actor, source bank and full action signature before copying move data into owned memory. Lifecycle checks reject stale objects and release only state the runtime still owns.

Each selected boss profile owns its verified archive resources. Motion decoding loads the requested clips while retaining native lookup indices; unused animations consume no clip allocations. Resource errors identify the profile and failed clip. Product import graphs supply the required phases, with explicit trial signatures for new boss moves.

Native hooks adapt input, transitions, recovery, resources and voice events for reviewed imports. Boss voice events can reuse William's sound rows. Paired actions retain native contact rules; recordings alone do not create playable moves.

Preset v8 exposes reviewed bindings and bounded move speeds. Physics, Ki Pulse authoring and Frost Moon timing remain developer-controlled. The current backend is sword-specific; ten weapon mods are not yet implemented.

Keep `tanto-engine`, `MWM` and `tanto-recorder` as sibling checkouts. `runtime/native/Build.ps1` builds native libraries; `Test-Offline.ps1` runs the two maintained suites. Offline results do not establish gameplay or hardware acceptance.

The 2026-09-27 MWM source trial is blocked by reported drift and a missing death screen; activation was stopped. Its trace recorded no intended substitutions, and Hideyori resource loading remained pending. Re-establish normal attachment, Disable and death/retry behavior with no replacements before comparing one boss adapter at a time. The MWM README preserves the detailed ID evidence and current uncertainties.

An offline reproduction found that pending archive I/O prevented the temporary loader frame hook from detaching. Cleanup now disables that hook after submission, retains objects needed by I/O callbacks, and also runs on error or timeout. A stalled native load stops activation instead of retrying indefinitely. This corrects a proven lifecycle defect; the reported gameplay symptoms still require a fresh manual check.

The subsequent Jin Low-heavy-only source check passed the user's string, neutral movement and death/retry checks, with matching native substitution traces. The full multi-boss setup remains unverified; this result is scoped to that one configuration.

`build_product.py` stages each product's selected code and data, then builds its EXE. Recorder receives two read-only memory/discovery modules and no gameplay hooks. Electron products bundle a separate worker and web interface into one portable EXE. Builds record source pins, dependencies, file hashes and version tags.

[CODE_GUIDE.md](CODE_GUIDE.md) explains the implementation. [NATIVE-WALKTHROUGH.md](runtime/native/NATIVE-WALKTHROUGH.md) follows the hooks, and [RELEASES.md](RELEASES.md) defines packaging and publication.
