# Tanto Move Dataset

This is the fresh research collection. Each JSON file describes one move or ordered move string under `weapons/<weapon>/<boss>/`. `dataset.json` names the weapon and boss categories; stable record IDs match those paths. Existing legacy runtime records are not imported into this collection.

`steps` preserve selected execution order and full 32-bit action IDs, motion IDs and timing IDs. Repeated executions remain separate steps; one ID need not equal one hit. `observed_links` distinguish order from consecutive counters and available native transitions. Intermediate movement can be excluded, so an ordered string is not automatically an executable chain.

`review_status` is `candidate`, `reviewed` or `rejected`; `mapping_status: partial` flags incomplete phase coverage. `priority` is `low`, `mid`, `high` or `null` when unset. Exact original notes remain in evidence references and `intake.json`; review notes explain selections and omissions. No speed, physics, Ki Pulse or binding settings are inferred.

Evidence archives retain the original `encounter.json` and `events.jsonl` byte-for-byte. They are included under `evidence/` in this private repository, named by SHA256. Consumer UI builds include the readable collection, not the raw ZIPs. Each reference identifies its session, take, annotation and exact journal lines; native pointers stay in the original recording rather than becoming permanent move identities. Keep these archives even when deleting working Recorder sessions.

`intake.json` accounts for all 15 source folders and maps every saved annotation to a record. Thirteen descriptions produced 12 sword strings and one handgun candidate. Two manifest-only folders lack notes and raw events. The spelling `Totoyomi` is preserved in source notes but indexed as `toyotomi_hideyori`. See [REVIEW.md](REVIEW.md) for the selected sequences and gaps.

Run `python -B dataset/validate.py --evidence-root 'C:\path\to\evidence'` from MWM, or `python -B validate.py` inside the Downloads snapshot. Validation checks classification, IDs, hashes, annotation coverage, descriptor consistency, same-actor order and recorded native targets. It does not confirm visual names, hit counts, actor identity or gameplay compatibility.

Add new weapon/boss names to `dataset.json`, then add a separate JSON record and evidence reference. Repeated captures can support one record through its evidence list. Preserve uncertain entries as candidates. Only a later, explicit review/import step should produce Engine-compatible runtime definitions; this dataset is excluded from the current legacy runtime package.
