# ColdGuard Member A — W20 Frozen Campaign Manifest Specification

**Requirement Authority:** `docs/05A §29: A-W20-04`, `docs/03`  
**Status:** **SPECIFIED / PENDING_PHYSICAL_RUNS**

---

## 1. Manifest Contents & Integrity Model

The frozen campaign manifest establishes cryptographic and provenance integrity for all physical A/B campaign runs:
1. `campaign_id`: Unique identifier for the execution wave.
2. `target_pairs`: Frozen target quota per Doc 03 protocol.
3. `completed_pairs`: Number of valid, matched A/B pairs (matching same `pair_id` under identical scenario/hardware).
4. `hardware_unchanged`: Post-campaign hardware inspection signoff (`true` / `false`).
5. `exceptions`: Exhaustive list of documented deviations, including all invalid attempts and exceptions.
6. `invalid_attempts`: Full count and logs of discarded runs with structured taxonomy reason codes.
7. `dataset_hashes`: Verified SHA-256 digests of all raw CSV and JSON telemetry captures.
8. `manifest_digest_sha256`: Cryptographic digest of canonical serialized payload computed by `cg_w20_campaign_freeze.py`.
9. `operator_signature`: **Separate human signoff record** (`status = PENDING_OPERATOR_PHYSICAL_SIGNATURE`). An automated SHA-256 digest is never equated with human approval.
