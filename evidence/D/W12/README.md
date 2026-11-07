# Week 12 – Controller A benchmark and Gate G3 control readiness

## Status summary

| Item | Status | Owner | Evidence needed |
|------|--------|-------|-----------------|
| D‑W12‑01 Controller A configuration v1 | **OPEN** | D / A | `PolicyConfig` supports versioning, but no measured threshold, persistence or action state has been frozen |
| D‑W12‑02 Replay benchmark | **INPUT CONTRACT DEFINED; RESULT OPEN** | D / A / B | `replay-benchmark-contract.md` pins admissibility and metrics; qualified recorded A/B runs are still needed |
| D‑W12‑03 Real benchmark | **BLOCKED** | A / B / C | Physical S2 runs with full command‑to‑actuation latency; requires qualified electrical channel and post‑freeze inspection |
| D‑W12‑04 Command lifecycle proof | **SYNTHETIC WIRING TEST; PHYSICAL PROOF OPEN** | A / D | `test_synthetic_lifecycle.py` exercises the pure chain only; device command → ACK → electrical → thermal trace remains required |
| D‑W12‑05 Gate G3 signoff | **OPEN** | A | Open blockers listed in `evidence/A/W12/gate-g3-input.json` (no host‑only sign‑off) |

A's `evidence/A/W12/gate-g3-input.json` says electrical qualification, post-freeze inspection and fuse/conductor evidence remain open. This week is a readiness inventory, not a G3 pass.
