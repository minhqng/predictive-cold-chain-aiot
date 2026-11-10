# Pre-merge source lock — Phase 7 (2026-11-10)

Combined candidate: `p7sandbox` branch `phase7-combined` @ **`e9681be`
`chore(integration): add owner cross-team integration layer`**, base
`d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85` (= live remote `main`, verified
unchanged at the start AND at the end of this run — no drift).

| Contribution | PR | HEAD | Verified by (live checks) |
|---|---|---|---|
| A remediation telemetry | #94 | `ae23a36fe98fcf1bf6005dd9fcd79b95fb796570` | own tests 9/9 (disposable copy) + gateway/trace probes under PR schema |
| A acceptance integrity | #95 | `815387d19a3898e6b33ccb65758a554dd0c589e1` | W09 validator OK (20 pinned / 957 rows) in disposable run; W01/W03/W06/W08/W13 validators PASS |
| Observation/admission/export stack | inside #69 stack | — | owner closure byte-equal sidecar under B#102 real `coldguard_ml` |
| B W13 horizon engineering | #102 | `824a5389c29ade0e56ecef7ef21eb35c2a379a7b` | **full ml suite 835 PASS on the real head** (its own uv lock); horizon suite 32/32 on the committed A dataset; 4 owner-depend modules byte-identical to base |
| C command/ACK observability | #69 | `361e73246a3a6746a39a7e2769dffdfb7b1ce486` | `CommandAck.model_validate` 5/5 committed fixtures; ack_consumer service probes (PG/Mosquitto live) |
| D safety/AIW/clock | #90 | `da821094985006945d0306dd7b16be576378bc18` | control 428 PASS merged; clock gate verified: unsynchronized ⇒ `SAFETY_BLOCKED`, D#90 `d90_compatible_evidence` + Phase 4/5 probe suites |

Stacked dependency graphs (ancestry verified via git ancestry `--is-ancestor`):
- B#102 = b-w04 → b-w05 … b-w11 → #102 (8 commits); base branch
  `feat/b-w12-benchmark-g3-review` @ `34435bdba8b4`.
- C#69 = c-w05 → … → c-w12 → #69 (8 stacked commits).
- D#90 = d-w04 → … → d-w12 → #90 (9 stacked commits).
- A#94/A#95 independent from each other and from the stacks (base = main).

## Merge sequence (depends on the actual DAG)

1. A#94 → 2. A#95 (fold the three shared manifests) → 3. C#69 (with stack) →
4. D#90 (with stack) → 5. B#102 (with stack) → 6. Owner integration PR.
