# Week 12 – Controller A benchmark and Gate G3 control readiness

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W12‑01 Controller A configuration v1 | **OPEN** | D / A | `PolicyConfig` supports versioning, but no measured threshold, persistence or action state has been frozen |
| D‑W12‑02 Replay benchmark | **INPUT CONTRACT DEFINED; SOURCE DATA AVAILABLE; RESULT OPEN** | D / A / B | Current main has accepted S1/S2 datasets, but no frozen Controller A representation or admitted controller-run set |
| D‑W12‑03 Real benchmark | **PARTIAL INPUTS; BENCHMARK OPEN** | A / B / C | A-W12-03 inspection passed and qualified S2 data exists; full Controller A command-to-applied/electrical/thermal runs are still absent |
| D‑W12‑04 Command lifecycle proof | **SYNTHETIC WIRING TEST; PHYSICAL PROOF OPEN** | A / D | `test_synthetic_lifecycle.py` exercises the pure chain only; device command → ACK → electrical → thermal trace remains required |
| D‑W12‑05 Gate G3 signoff | **OPEN** | Whole-team gate owners | The older A gate input is partly stale after A-W12-03, but fuse/conductor, Controller A, lifecycle and whole-team signoffs remain open |

A's `evidence/A/W12/gate-g3-input.json` predates the main handoff and the
A-W12-03 inspection result. Its post-freeze-inspection and blanket electrical
blockers are no longer a current inventory, while its fuse/conductor concern
remains. This week is a readiness inventory, not a G3 pass.

`g3-evidence-matrix.json` is rebuilt from the legacy A gate input, the current
A-W12-03 inspection result, and the normalized run index/measurement summary.
It also records PR #95's one supplementary S1 run without admitting it into
the frozen package.
It records which legacy blockers are superseded and retains `NOT_VERIFIED` for
the remaining Controller A, lifecycle, fuse/conductor and team-signoff gaps.
Only designated owners can provide physical evidence and a whole-team G3
decision.
