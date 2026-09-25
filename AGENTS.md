# Nioh workflow

- This repository is the canonical source. Keep outputs/Nioh1-Sword-Move-Observations.xlsx and the user's Downloads copy in sync when updating the catalog.
- Prioritize end-to-end move-port tests. Reuse the working Okatsu implementation.
- Reuse saved controller calibration across sessions/restarts. Recalibrate only if the device/mapping changes or evidence shows it is wrong.
- Reacquire transient process, actor, and resource addresses automatically; this is not input remeasurement.
- Keep a working move enabled for the user's playtesting until stopped or its actor/session becomes invalid. Do not silently impose one-use limits or short timers.
- Be direct about what is enabled, what was verified, and why anything stops.
- Do not control or capture the monitor running Nioh. Keep explanations in chat and documentation short.
- Keep clones, forks, and managed branches under C:\Users\vikna\Downloads\GitHub.
- Current binding is LB + Circle: tap/release for Charged Rush (C64/1220), hold 0.25s for Leaping Slash (C66/1230). Keep movement and lock-on usable; imported voice removal is user-confirmed, with combat FX retained.
