# Nioh workflow

- Work from this repository. Regenerate live addresses locally; do not commit boss_session.h, session-profile.json, boss-session.json or active sessions.
- Prioritize end-to-end move-port tests. Reuse the working Okatsu implementation.
- Reuse saved controller calibration across sessions/restarts. Recalibrate only if the device/mapping changes or evidence shows it is wrong.
- Reacquire transient process, actor, and resource addresses automatically; this is not input remeasurement.
- Keep a working move enabled for the user's playtesting until stopped or its actor/session becomes invalid. Do not silently impose one-use limits or short timers.
- Be direct about what is enabled, what was verified, and why anything stops.
- Do not control or capture the monitor running Nioh. Keep explanations in chat and documentation short.
- Keep clones, forks, and managed branches under C:\Users\vikna\Downloads\GitHub.
- Current binding is LB + Circle: tap/release for Charged Rush (C64/1220), hold 0.25s for Leaping Slash (C66/1230). Keep movement and lock-on usable; imported voice removal is user-confirmed, with combat FX retained.
