# A-W12-04 CG-HW-001 run list and pooling disposition (derived from the store)

Generated 2026-11-04T18:13:50.565088+00:00 read-only from `results/*.json`.
No physical inspection is claimed by this document.

## Runs recorded under CG-HW-001

| Requirement | Attempt | Valid | Boot | Firmware kind | HW config |
|---|---|---|---|---|---|
| A-W02-03 | None | None | cb5d5b06 | CANONICAL | CG-HW-001 |
| A-W02-03 | None | None | cb5d5b06 | CANONICAL | CG-HW-001 |
| A-W02-03 | None | None | cb5d5b06 | CANONICAL | CG-HW-001 |
| A-W02-03 | None | None | cb5d5b06 | CANONICAL | CG-HW-001 |
| A-W02-03 | None | None | cb5d5b06 | CANONICAL | CG-HW-001 |
| A-W07-02 | 1 | True | None | None | None |
| A-W07-02 | 2 | True | None | None | None |
| A-W07-02 | 3 | True | None | None | None |
| A-W07-03 | 1 | True | None | None | None |
| A-W07-03 | 2 | True | None | None | None |
| A-W07-03 | 3 | True | None | None | None |

## Non-poolable runs and disposition

- A-W07-02 attempt 1: None image, excluded from canonical-image pooling
- A-W07-02 attempt 2: None image, excluded from canonical-image pooling
- A-W07-02 attempt 3: None image, excluded from canonical-image pooling
- A-W07-03 attempt 1: None image, excluded from canonical-image pooling
- A-W07-03 attempt 2: None image, excluded from canonical-image pooling
- A-W07-03 attempt 3: None image, excluded from canonical-image pooling
- A-W07-02 superseded attempt(s) archived in results/history/ (3 file(s)): the 2026-11-04 A-W07-02 attempt lacked stabilization/independence proof and the 2026-11-04 A-W12-01 attempt ran under a ramping ambient; neither is pooled with its re-run
- A-W12-01 superseded attempt(s) archived in results/history/ (3 file(s)): the 2026-11-04 A-W07-02 attempt lacked stabilization/independence proof and the 2026-11-04 A-W12-01 attempt ran under a ramping ambient; neither is pooled with its re-run

All remaining runs were recorded on the canonical W06 bench image 73968c19 with
hardware_config_id CG-HW-001 and are poolable with each other.
