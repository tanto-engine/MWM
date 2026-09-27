# Tanto Move Dataset

This is the fresh research collection. Each JSON file describes one move or ordered move string under `weapons/<weapon>/<boss>/`. `dataset.json` names the weapon and boss categories; stable record IDs match those paths. Existing legacy runtime records are not imported into this collection.

`steps` preserve execution order and full 32-bit action IDs, motion IDs and timing IDs. `review_status` is `candidate`, `reviewed` or `rejected`; review does not itself make a move playable. `priority` is `low`, `mid`, `high` or `null` when unset. Description basis and review notes separate observations from unconfirmed names or visual interpretations. No speed, physics, Ki Pulse or binding settings are inferred from a capture.

Evidence archives retain the original `encounter.json` and `events.jsonl` byte-for-byte. They live outside Git, named by SHA256. Each reference identifies its session, take, annotation and exact journal lines; native pointers stay in the original recording rather than becoming permanent move identities. Keep these archives even when deleting working Recorder sessions.

Run `python -B dataset/validate.py --evidence-root 'C:\path\to\evidence'` from MWM, or `python -B validate.py` inside the Downloads snapshot. Validation checks classification, IDs, hashes, annotations, same-actor step ordering and the recorded native transition. It streams each archive journal once and indexes curated records by stable ID. It does not confirm that the visual action is Omnislice or that the described preparation occurs.

Add new weapon/boss names to `dataset.json`, then add a separate JSON record and evidence reference. Repeated captures can support one record through its evidence list. Preserve uncertain entries as candidates. Only a later, explicit review/import step should produce Engine-compatible runtime definitions; this dataset is excluded from the current legacy runtime package.
