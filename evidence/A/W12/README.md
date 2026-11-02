# A-W12 — Drift audit and Month-3 physical/data signoff inputs (Member A)

Week: **W12** · Branch: `feat/a-w12-physical-readiness` · Owner: Member A
Status: **HOST DRIFT AUDIT ONLY · NO HARDWARE · NO PHYSICAL SIGNOFF · G3 INPUT IS AN A-SIDE BLOCKED STATE**

This dossier answers the Week-12 objective — *do the datasets collected so far
still belong to one defensible physical configuration?* — from already-committed
captures only. It touches no hardware, opens no serial port, flashes nothing, and
declares no whole-team gate. Where a quantity cannot be computed from committed
evidence it is recorded as a named gap; it is never substituted with a number.

W12 is **not** a GREEN week.

## 1. What W12 delivered

| Requirement | Delivered | Where |
|---|---|---|
| **A-W12-01** sensor consistency recheck | Per-slot probe offset (mean) and chamber-air agreement grouped strictly by configuration; the TEC hot side is never folded into a chamber-air statistic | `cg_w12_drift_audit.py`, `drift-audit.json` |
| **A-W12-02** PZEM zero/active audit | duty-0-with-current frames listed **individually** (never averaged), electrical figures labelled `UNQUALIFIED`, OFF/ON separation compared to the envelope | same |
| **A-W12-03** mechanical audit | Machine-readable checklist: sensor fixtures, V1 mounting, terminals, fuse, cable positions — each with a status and the exact evidence that closes it | `mechanical-audit-checklist.csv` |
| **A-W12-04** hardware-config signoff | Runs grouped under `CG-HW-001` with a configuration-grouped **dataset validity table** showing which captures may not be pooled | `dataset-validity.csv`, `drift-audit.json` |
| **A-W12-05** gate G3 input | Member-A signoff input with named blockers; explicitly does **not** declare G3 GREEN | `gate-g3-input.json` |

## 2. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `drift-audit.json` | full machine-readable audit (sensor consistency, role geometry, PZEM, cross-session drift) |
| `mechanical-audit-checklist.csv` | A-W12-03 checklist table |
| `dataset-validity.csv` | A-W12-04 configuration-grouped pool/refuse table |
| `gate-g3-input.json` | A-W12-05 A-side signoff input |
| `build_w12_artifacts.py` | regenerates every artifact from the committed capture; `--check` compares byte-for-byte |
| `validate_w12.py` | verifies SHA256SUMS pins, LF-only, and re-asserts the honesty (no physical PASS, no G3 GREEN) |
| `SHA256SUMS.txt` | byte pins (LF-only), produced by `build_w12_artifacts.py --pins` |
| `handoff.md` | this week's part of the docs/05A section 5 / 6.1-6.3 handover: what B, C and D may use from W12, what must not be inferred from one session, and what only an inspection can give |

## 3. Reproduce

```bash
py firmware/tools/cg_w12_drift_audit.py                 # run on the committed W04 cooling capture
py firmware/tools/run_all_checks_w12.py                 # full W12 check chain
py evidence/A/W12/build_w12_artifacts.py --check        # artifacts reproduce byte-for-byte
py evidence/A/W12/validate_w12.py                       # hash pins + honesty re-assert
```

## 4. Limits of this dossier

* **Host evidence only.** The only capture committed on this branch compatible
  with the thermal/electrical audit is the W04 H8-C cooling run
  (`evidence/A/W04/tec-cooling-response-600s.csv`, `boot_id=56044b74`, installed
  bench image `01cedce3…`, `physical_output` column empty, `current_status` and
  `voltage_status` empty in all 957 rows). H7/H8 raw sessions and the W07/W08
  dossiers live in sibling worktrees; this slice references their documented
  numbers and does **not** copy their originals or re-derive them here.
* **Nothing here is PHYSICALLY_VERIFIED.** The mechanical items (fixtures, V1
  mounting, terminals, fuse, routing) are physical checks the host cannot
  perform; they are `NEED_USER_ACTION` or `BLOCKED_HARDWARE`.
* **G3 is not this slice's to set.** `gate-g3-input.json` states Member A's
  position and blockers; a whole-team G3 GREEN is explicitly out of scope.
* **Electrical figures are UNQUALIFIED.** Because `current_status`/`voltage_status`
  are empty in the capture, V/I/P are reported but not device-qualified, and the
  duty-0 stale-current frames (PZEM register latency) are listed one by one,
  never averaged.
