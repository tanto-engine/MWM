# SKM — Single-Katana Moveset Mod

The standalone Nioh 1 Sword Skills Expanded product, developed with Tanto Engine. Users receive `SKM.exe`; they do not install or run the development engine. The executable includes the selected micro-runtime, two native libraries, validated Sword definitions and the configuration UI. It excludes engine source headers, tests, research, recordings and developer authoring tools.

Launch the application, review the moveset and choose **Enable / attach**. **Disable** cooperatively restores owned native state. Closing the window leaves an enabled session running. Settings live under `%LOCALAPPDATA%\Tanto\Sword\runtime` in the packaged application. The game installation provides its assets; the package contains asset identities and checks, not extracted game archives.

## Configure a moveset

- **Moveset:** select the custom chord's stance, tap/release move, hold move and hold threshold. Select buttons by name or choose **Press to bind**, release all controls and press one input. Apply saves the changes. Cancel binding changes no saved control.
- **Native overrides:** select the Low heavy string and each stance's heavy hold. The table edits reviewed native source + stance overrides, including Tiger Sprint, guard/light, heavy attack and dodge attack. Select a row to edit it; **Native** removes that source/stance override. Running and dodge inputs retain native priority. Low dodge continuation requires Low Jin D. A graph shared by several bindings must retain one stance; conflicting assignments are rejected.
- **Frost Moon:** choose a move for each destination stance. Activate with R1 / RB and that stance button twice. The engine owns the activation window and startup speed.
- **Move speed:** select an implemented unpaired move, set its multiplier from 0.25 to 2, then choose **Set move speed** and **Apply**. This changes playback speed without cutting the clip's start or end. Paired phases retain engine timing; Frost startup remains engine-owned.

Selectors come from the engine's implemented import capabilities. Raw recordings and unimplemented catalogue entries do not become playable options. Configuration validation is separate from gameplay acceptance.

**Save moveset** saves controller mapping metadata with the preset, so loading into another supported mapping preserves logical controls. Cancel leaves edits unapplied. Legacy bare presets still load in the current mapping's mask namespace. **Restore baseline** preserves the current controller mapping and restores baseline moves and logical buttons. Saved schema 4–7 presets migrate to schema 8 on load; obsolete public Frost timing and private physics fields are discarded during that migration.

## Controllers

Choose **Saved mapping** for an existing calibrated controller, **DS4 mapping** for the retained PS4 layout, or **XInput controller 1–4** for Xbox or PS4/PS5 exposed through XInput. Select the game's XInput slot explicitly when several controllers are connected; **Auto** requires exactly one. Switching mappings translates existing logical bindings before saving. Capture uses the game's published controller observations while the runtime is active and the selected OS controller while offline. Reconnection requires releasing controls before a new press can bind.

The retained DS4 WinMM layout and standard XInput controls include triggers. Direct HID-only devices and unmapped paddles require a supported mapping; a device name does not prove button compatibility. PS4/PS5/Xbox hardware and gameplay acceptance remain pending.

## Development and builds

Clone private `neuriv/tanto-engine` next to this checkout. `Trainer.ps1` launches the source UI. `Build.ps1` compiles the engine's native runtime and produces a standalone EXE using the pinned engine revision in `product.json`. Specify `-PythonRuntime` for an environment containing `tanto-engine/requirements-build.txt`. Consumers need neither source checkout.

`data/preset.json` owns default bindings. `data/moves.json` owns names and source identities; `data/imports/` owns implemented action graphs. `data/resources/` identifies installed-game archive entries, hashes and native package layouts. These profiles are operational build inputs. MinHook's required license accompanies the application resources.

Global weight/impulse, tracking and Frost activation/startup policy belong to the engine backend. Ki Pulse tuning is developer-only: an optional `data/move-policy.json` uses schema 1 and `moves: {"implemented.move_id": {"ki_pulse": {"percent": 40, "fill_frames": 25, "hold_frames": 24}}}`. The engine validates the supported fields and bounds; public presets and the consumer UI do not expose Ki Pulse tuning. Rebuild and perform gameplay acceptance after changing private policy. A local executable is not an unextractable security boundary.

## Review a recorded move for implementation

Keep the Recorder bundle and review its reconstruction, action identities and transitions. Author the catalogue/import/resource definitions using an existing supported source family and player adapter. Unknown boss families, native skill signatures and paired protocols require engine work; recording alone does not implement them.

Run the source-only review helper against an authored manifest:

```powershell
python .\review_import.py .\data\imports\okatsu.json --evidence C:\Captures\reviewed\reconstruction.json --reviewed --out C:\Captures\reviewed\import-review.json
```

Omit `--evidence` to inspect definition and resource gaps first. `--catalogue` and `--resources` accept draft inputs outside the product tree. The report checks existing import validation, catalogue signatures, resource identities and supplied reconstruction identities, and lists missing requirements. `--reviewed` records a developer attestation; it does not certify execution or gameplay. The helper writes only a report, rejects replacing inputs/product data, and never installs a recording or enables a move.

After addressing the report, review player adaptation, ownership, recovery, voices, paired roles and installed archive bytes. Add the reviewed definitions to the maintained product imports, run the Engine's existing offline test entrypoints and obtain current-build gameplay evidence before distributing a build. This source change includes no new executable or gameplay certification. The previous Downloads workbook remains archival, not a runtime dependency.

## Release discipline

Every EXE compilation uses `Build.ps1` and Engine’s shared release gate. Set a new version and corresponding `CHANGELOG.md` entry, commit all three repositories, and pin the exact Engine commit first. Output is immutable `dist/<version>/` with checksums, source hashes, test log and `release.json`. See `../tanto-engine/RELEASES.md`. No build replaces a published version. Offline checks never imply gameplay acceptance.
