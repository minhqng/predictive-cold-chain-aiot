# Member D assessment of main `d22c8d5`

The branch `feat/d-w13-aiw-readiness` merged `origin/main` at
`d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85` on 2026-11-09. The merge had no
content conflicts. The 2026-11-10 follow-up added the 30.5 C S2 evaluation
and A-W21 oracle cross-check. `uv run --locked --extra test pytest` in
`control/` passed all 434 tests after binding PR #91 S1/S2 and PR #95's
supplementary S1 handoff.

## Pinned sources reviewed

| Source | SHA-256 |
|---|---|
| `evidence/A/SOURCES/20261107/datasets/manifest.json` | `5273e528e6505caf55dec79a5fccbe0e6407161c1fedb864b52a7160706cc72d` |
| `evidence/A/SOURCES/20261107/datasets/run_index.csv` | `53d476747c4a865ddec09492c9c49601a72ab766e9862faac0a2c9a43a22bbb4` |
| `evidence/A/SOURCES/20261107/datasets/measurement_summary.csv` | `361e41e574143011cb1891607a6ab8c21e1e9f2b924dc3fc8453bd26c5eee52c` |
| `evidence/A/W04/results/A-W04-06.json` | `ca85686c1907b00d4fe4efd88e598483c2a496ee8ee8e5ad45f2341c0a639169` |
| `evidence/A/W12/results/A-W12-03.json` | `bbfa4485c2bf0f2f1b9eeebd90d735c00b6f98e99adbbc138cb6fda99a9005d9` |
| `evidence/A/W21/results/A-W21-02.json` | `4fbc22d3150d3e67a8e1c2556543c454e68e835426d8fd66a3bc0f6949b1682b` |
| `evidence/A/W21/results/A-W21-03.json` | `b8bb30ba309bd90a555bb99d8c30dca289a15fd1559628937bf069142e8c8cdc` |
| `evidence/D/W09/a-pr95-supplementary-s1-binding.json` | `b8790aad88f4394647d018cf44f83af70a45d7aed1f831b044743998ab95941b` |

## Admission observations

- The handoff contains 18 runs/segments and 9,293 frames: four accepted S1
  runs, five accepted S2 windows, two outside-window segments, four real
  cooling captures marked not scenario-qualified, and three passive repeats
  with an independence caveat.
- The old D W09 negative control remains a valid statement about its old
  source export (957 `UNKNOWN` electrical rows), but it is no longer a current
  inventory of all evidence on main. The new normalized handoff reports
  qualified electrical fields in the accepted S1/S2 sets and cooling captures.
- The accepted S1/S2 runs are mostly OFF baselines. They do not contain a
  frozen D Controller A configuration or an end-to-end requested -> applied ->
  electrical -> thermal controller benchmark.
- A-W08-03 and A-W09-04 are explicitly still `NOT_RUN`; the real cooling
  captures are measurement sources, not canonical acceptance runs.
- A-W12-03 closes the post-freeze fixture/V1/terminal/cable checklist, while
  its notes retain the fuse-to-conductor ampacity issue. Therefore the older
  A `gate-g3-input.json` has partly stale blockers but G3 still cannot be
  declared.
- A-W21-02/03 are useful on-device inputs for D W10 sensor/PZEM cases. Their
  output stage was disabled and fuse removed; they cannot close energized
  actuator, cooling-health, C-persistence, or incident-action evidence.
- PR #95 contributes one hash-verified 600-frame passive S1 run. It remains
  supplementary and is deliberately excluded from the frozen 18-run package.

The authoritative ten-week status and remaining requests are maintained in
`missing-data-summary-W04-W13.md`.
