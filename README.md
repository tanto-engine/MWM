# Nioh 1 Skill Expanded

Independent sword move-port prototype and research tools for Nioh 1.

With a sword equipped and Okatsu loaded in her mission:

- Tap/release **LB + Circle**: Charged Rush (C64, motion 1220).
- Hold **LB + Circle** for 0.25 seconds: Leaping Slash (C66, motion 1230).

Player use, movement, lock-on, stance preservation and voice removal are confirmed.
Faster tap startup and native Ki Pulse windows are implemented, awaiting gameplay verification.
This prototype requires Okatsu's loaded resources and the researched game build.

## Run

Use Windows x64, Python 3.10+ and GCC/G++. MinHook source and its license are included.
From PowerShell in this folder, run `./Start-Okatsu.ps1`; use `./Stop-Okatsu.ps1` to stop.
Pass `-PythonRuntime C:\path\to\python.exe` if needed. Set `NIOH_EXE` for a different game installation path.
The launcher reuses the saved controller calibration and reacquires session addresses.
See `outputs/okatsu-prototype/Apply.txt` for details and `play-status.json` there for live status.

## Contents

- `outputs/okatsu-prototype/`: current native mod, loader, controller handling and evidence.
- `outputs/boss-probe/`: read-only boss/action/resource and controller tools.
- `outputs/Nioh1-Sword-Move-Observations.xlsx`: player observations and Okatsu move catalog.
- `outputs/Okatsu-Capture-30s/`: original boss capture and metadata.
- `work/`: original research scripts, offline tests, fixtures and spreadsheet builders.
- `third_party/minhook/`: separately licensed dependency and pinned source provenance.

Run `./Test-Offline.ps1` for owned-buffer tests without attaching to the game.
Historical research scripts in `work/` may contain session-specific addresses; they are not launcher steps.
Optional CE scripts require `NIOH_RESEARCH_DIR` set to this repository's `work` folder.
Reference-audit scripts use `NIOH2_REFERENCE` for the separately obtained reference mod.
Optional disassembly/reference tools use `work/requirements-research.txt`.
Spreadsheet builders use `@oai/artifact-tool` from the Codex document runtime.
Generated binaries, live pointers, active session logs and game files are excluded from Git.
