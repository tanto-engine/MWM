# Tanto Sword Mod

The standalone Nioh 1 Sword Skills Expanded product, developed with Tanto Engine. Users receive `TantoSword.exe`; they do not install or run the development engine. The executable includes the selected micro-runtime, two native libraries, validated Sword definitions and the configuration UI. It excludes engine source headers, tests, research, recordings and recorder tools.

Launch the application, review the bindings and choose **Enable / attach**. **Disable** cooperatively restores owned native state. Closing the window leaves an enabled session running. Settings live under `%LOCALAPPDATA%\Tanto\Sword\runtime` in the packaged application. The game installation provides its assets; the package contains asset identities and checks, not extracted game archives.

## Development and builds

Clone private `neuriv/tanto-engine` next to this checkout. `Trainer.ps1` launches the source UI. `Build.ps1` compiles the engine's native runtime and produces a standalone EXE using the pinned engine revision in `product.json`. Specify `-PythonRuntime` for an environment containing `tanto-engine/requirements-build.txt`. Consumers need neither this source checkout nor the engine checkout.

`data/preset.json` owns the default bindings. `data/moves.json` owns named move definitions; `data/imports/` owns the implemented action graphs. `data/resources/` identifies exact installed-game archive entries, hashes and native package layouts required by those imports. These profiles are operational build inputs, not recording data. MinHook is compiled into the native runtime; its required license accompanies the application resources.

Global weight/impulse and tracking policy is selected by the engine backend at build time. Public settings expose supported bindings and bounded timing controls. Changing private policy requires a development rebuild. A local executable is not an unextractable security boundary.

The current backend supports Nioh 1 sword integrations. The latest tracking, airborne Izuna contact and weapon/sheath fixes still need gameplay acceptance. Offline tests and packaged startup checks do not establish gameplay success. The previous Downloads workbook remains an archival export; it is no longer a runtime dependency or the configuration source.
