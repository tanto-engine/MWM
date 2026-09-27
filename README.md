# Tanto Engine

Private Nioh framework for move adaptation, controller input, timing, Ki Pulse, physics and native hooks. MWM and Recorder package only the runtime components they need; players do not need this repository.

Session preparation matches the game build, actor, source bank and full action signature before copying move data into owned memory. Lifecycle checks reject stale objects and release only state the runtime still owns.

Native hooks adapt input, transitions, recovery, resources and voice events for reviewed imports. Boss voice events can reuse William's sound rows. Paired actions retain native contact rules; recordings alone do not create playable moves.

Preset v8 exposes reviewed bindings and bounded move speeds. Physics, Ki Pulse authoring and Frost Moon timing remain developer-controlled. The current backend is sword-specific; ten weapon mods are not yet implemented.

Keep `tanto-engine`, `MWM` and `tanto-recorder` as sibling checkouts. `runtime/native/Build.ps1` builds native libraries; `Test-Offline.ps1` runs the two maintained suites. Offline results do not establish gameplay or hardware acceptance.

`build_product.py` stages each product's selected code and data, then builds its EXE. Recorder receives four read-only modules and no gameplay hooks. Builds record source pins, dependencies, file hashes and version tags; exceptions remain explicit in release receipts.

[CODE_GUIDE.md](CODE_GUIDE.md) explains the implementation. [NATIVE-WALKTHROUGH.md](runtime/native/NATIVE-WALKTHROUGH.md) follows the hooks, and [RELEASES.md](RELEASES.md) defines packaging and publication.
