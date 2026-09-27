# Read SKM as a Nioh player

SKM means **single-katana moveset mod**. This repository owns your selectable sword moves, their default bindings and the trainer. The sibling `tanto-engine` repository owns memory integration and the rules for adapting reviewed boss moves to William. Read its `CODE_GUIDE.md` for terms such as action bank, adapter, hook, ownership and ABI.

Keep 3–5 direct opening comments per function/callback: player-facing purpose, mechanism and the important constraint. Use additional inline comments for ownership, conversion or persistence rules that are easy to get wrong.

## Follow a settings change

1. `Trainer.ps1` launches `launch.py`, or explicitly asks it to enable/disable the runtime. `launch.py` selects packaged code or the sibling Engine, sets product/state paths, and dispatches only its allowed worker modules. Existing packaged preferences remain under `Tanto/Sword/runtime` despite the product rename.
2. `app/trainer.py` obtains reviewed capabilities from Engine. A displayed name is mapped to a stable move ID; controller labels map to saved button bits. The form distinguishes pending edits from Apply, and Save cancellation does not apply a pending moveset.
3. The Engine validator checks the complete preset, not just the last edited box. Native skill overrides are scoped by source and stance. Speed changes affect reviewed playback, while paired phases, Frost startup, Ki Pulse authoring and physics remain controlled by Engine.
4. Press-to-bind first requires all controls to be released. It accepts one calibrated input from the selected controller and changes the form only. Changing devices translates through logical button meaning; a device's name alone does not establish compatibility.
5. Enable starts the Engine lifecycle. Disable asks it to restore owned state cooperatively. Closing the trainer is separate from disabling an enabled session. Live gameplay and physical-controller acceptance remain distinct from configuration tests.

## Read the product data

| File | What it describes | Important boundary |
|---|---|---|
| `product.json` | EXE name, backend kind, version and exact Engine commit | A release version is different from a preset schema version; an Engine pin identifies source, not gameplay acceptance. |
| `data/mod.json` | Stable product identity and readable SKM name | Renaming the display/repository does not require changing the legacy settings namespace. |
| `data/preset.json` | Default stance, native/custom bindings and reviewed speeds | Schema v8 settings are validated; private physics/Pulse/timing policy is not an unrestricted user field. |
| `data/controller-calibration.json` | Saved controller layout and raw/logical button meaning | A bitmask represents button states; a source-device bit may differ from its game-facing equivalent. |
| `data/moves.json` | Readable names, source identities and review/implementation status | A catalogue entry may be research only. It does not automatically become a menu choice. |
| `data/imports/*.json` | Reviewed source signatures, graph phases, continuations, recovery and voice events | Full bank/action identity matters. Identical small action numbers from different bosses are not interchangeable. |
| `data/resources/*.json` | Installed archive entries, sizes, hashes and motion/timing mappings | These identify game assets; they are not extracted animation archives shipped with the mod. |

An import's `source_voices` can retain events that preparation must verify; `voices` identifies the subset routed through the player voice adapter. A source flag or byte prefix with no proven interpretation remains identity evidence, not a freely editable mechanic. JSON must remain valid data, so explanations live here and beside its validators instead of being inserted as invalid JSON comments.

`review_import.py` compares an authored import with catalogue/resource definitions and optional reconstruction evidence. Its `reviewed` flag records developer review only. The helper writes a report; it never installs a recording or marks a move executable/gameplay-accepted.

## Builds and repository hygiene

`Build.ps1` delegates every EXE compilation to Engine's shared release gate. `CHANGELOG.md` describes version changes; Engine's `RELEASES.md` explains the required clean commits, exact pin, offline checks, immutable artifacts and tags. `.gitignore` excludes builds and local runtime state. `.gitattributes` preserves appropriate text/binary treatment.

Tests live in Engine and run through `Test-Offline.ps1`; do not create a second product-specific test workflow. A source comment change does not modify an already released EXE, and this review does not claim new SKM gameplay acceptance.
