# ColdGuard Member A — W20 Frozen Campaign Manifest Specification

**Requirement Authority:** `docs/05A §29: A-W20-04`  
**Status:** **SPECIFIED / PENDING_PHYSICAL_RUNS**

---

## 1. Manifest Contents

The frozen campaign manifest requires signing:
1. `hardware_unchanged`: Boolean (`true` / `false`).
2. `exceptions`: List of approved deviations or non-destructive adjustments.
3. `invalid_attempts`: Full count of discarded/invalidated runs with linked reason codes.
4. `dataset_hashes`: SHA-256 digests of all raw CSV and JSON telemetry captures.
5. `manifest_signature`: SHA-256 seal computed by `cg_w20_campaign_freeze.py`.
