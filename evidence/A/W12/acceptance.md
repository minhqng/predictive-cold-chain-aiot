# A-W12 acceptance

Slice: W12 drift audit + Month-3 physical/data signoff inputs · Branch
`feat/a-w12-physical-readiness` · Owner: Member A
Hardware touched: **NO** · Flashed: **NO** · Serial opened: **NO** · Physical signoff issued: **NO**

W12 is **not** a GREEN week. It is a host drift audit that keeps the datasets
defensible per configuration and names, precisely, the physical and qualification
gaps that block an A-side signoff. It never marks anything PHYSICALLY_VERIFIED
from host bytes and never declares G3 GREEN.

## 1. Requirement matrix (docs/05A §21)

| ID | Canonical ask | Status | Evidence / gap |
|---|---|---|---|
| **A-W12-01** | Sensor consistency recheck, compare offsets/drift (W2 method) | **REAL_DATA_ANALYZED** (host) | `drift-audit.json`: per-slot mean offset and chamber-air agreement grouped to the one committed configuration (bench image `01cedce3…`). Per-slot means over all valid frames: T1 24.90 °C, T3 25.30 °C, T4 25.20 °C (chamber air) vs T2 35.42 °C (TEC hot side, kept a separate population under the authored versioned deviation `chamber-air-trio-v1` and never folded into the air trio; docs/01 §6.4/§20.1 treat T1-T3 as chamber air and do **not** forbid a hot-side mean, so this exclusion is Member A's deliberate choice, not a canonical ban). Chamber-air agreement = mean per-frame trio spread **0.654 °C** (max **1.126 °C**, population stdev **of that per-frame spread** 0.289 °C) over all 957 frames; the mean of the per-frame trio population stdev is a **separate** figure, **0.2773 °C**. Every mean is taken only over frames whose device-side quality token is valid (all 957 carry `OK` today; non-valid terms would be skipped and counted, never averaged, per docs/01 §19/§20.1). **Intra-configuration drift between sessions is NOT COMPUTABLE** — only one distinct physical session of this configuration is committed on this branch. |
| **A-W12-02** | PZEM zero/active check vs W3/W8 envelope | **REAL_DATA_ANALYZED (host), electrical UNQUALIFIED** | `drift-audit.json.pzem_audit`: 12 duty-0-with-current frames; the standout is `seq 827` (state COOLDOWN) reporting **7.15 A** at applied duty 0 — the documented PZEM register-latency last-loaded-current artifact, listed individually. The rest sit at the **0.02 A** fan idle floor. `current_status`/`voltage_status` are empty in all 957 rows, so every V/I/P figure is labelled `UNQUALIFIED`. Peak driven current **9.99 A**. Envelope comparison to W3/W8 is a `TEAM_DEPENDENCY` (those dossiers are sibling workstreams). |
| **A-W12-03** | Mechanical audit: sensor fixtures, V1 mounting, terminals, fuse, cable positions | **NEED_USER_ACTION / BLOCKED_HARDWARE** | `mechanical-audit-checklist.csv`. Each item has a status and what closes it. The fuse item is `BLOCKED_HARDWARE`: fuse reported **15 A**, its marking was never photographed (`evidence/A/W04/fuse-commissioning-note.md` ~:36), observed conductor is a **1.75 mm copper-core diameter** (operator-measured 2026-11-02; ≈2.405 mm² *if* solid round — that assumption is unconfirmed, no marking photographed, no cross-section measured), canonical ask `2 × 2.5 mm²`, W01 `bom-audit.csv` HW-19 `UNVERIFIED`; note ~:53 says *no conductor evidence today → no freeze*. This audit does **not** certify compliance and keeps observed vs recommended apart. |
| **A-W12-04** | Hardware config signoff: list runs under `CG-HW-001`; identify what must not be pooled | **HOST_VERIFIED** | `dataset-validity.csv`: all committed captures under `CG-HW-001`; the validity table groups by installed image/limits posture and marks must-not-pool rules (probe-id captures, role disagreements, different images). The cooling capture stamps T1/T3/T4 role `UNASSIGNED` (predates the operator role freeze) — a label gap, not a contradiction; T2 is stamped `HOT_SIDE`, consistent with the freeze. |
| **A-W12-05** | Gate G3 input: A's "plant stable enough for predictive development" or blockers | **NEED_USER_ACTION** | `gate-g3-input.json`: A cannot sign off from host evidence alone. Blockers named (electrical qualification, mechanical inspection, fuse deviation). The slice does **not** declare a whole-team G3 GREEN, which is out of this slice's scope. |

## 2. Frozen geometry honoured (never re-tested, never questioned)

T1 = chamber **CENTER** (`287088CA00000051`) · T2 = TEC **HOT_SIDE**
(`28AEBF2200000006`) · T3 = chamber **BOTTOM** (`28CBE9CA00000072`) · T4/SPARE =
**NEAR_DOOR** (`283BE5C9000000A9`). T3 is BOTTOM — it is *not* relabelled
"far/opposite"; no measured geometry proves that wording. The TEC hot side is
kept as a separate population and never folded into a chamber-air statistic
(asserted in `sensor_consistency`; the exclusion is the authored `chamber-air-trio-v1`
deviation, not a docs/01 ban — docs/01 §6.4/§20.1 treat T1-T3 as chamber air and
do not forbid a hot-side mean). Probe-identification touch captures are
`PROBE_IDENTIFICATION` events and are excluded from every drift and timing
statistic — asserted in code (`is_probe_identification`, which reads the path
**and** the session content, `audit_capture`) and pinned by
`tests/test_cg_w12_drift_audit.py`. The committed role-identification support on
this branch is `evidence/A/W04/g2a/20-probe-identification.md`; the raw W07 touch
captures live on the sibling `feat/a-w07-*` branch and are a `TEAM_DEPENDENCY`
reference, not read from this branch's bytes.

## 3. Numbers published (each with its source and status)

| Figure | Source | Status |
|---|---|---|
| 957 rows @1 Hz, one `boot_id=56044b74`, driven block = 600 frames at applied duty 999 | `evidence/A/W04/tec-cooling-response-600s.csv` | REAL_DATA_ANALYZED |
| `current_status`/`voltage_status` empty in all 957 rows; no `power_status`/`door_status` columns | same | REAL_DATA_ANALYZED → electrical **UNQUALIFIED** |
| 12 duty-0-with-current frames; `seq 827` COOLDOWN = 7.15 A (stale register); floor 0.02 A | same | REAL_DATA_ANALYZED (listed individually) |
| Peak driven current 9.99 A | same | REAL_DATA_ANALYZED, UNQUALIFIED |
| Chamber-air trio whole-window cooling slope −0.8548 °C/min; 1 °C reached at 0.85 min after applied-on | same | REAL_DATA_ANALYZED |
| fuse 15 A (unproven), conductor 1.75 mm core **diameter** ≈2.405 mm² if solid round (canonical 2×2.5 mm²), HW-19 UNVERIFIED | `evidence/A/W04/fuse-commissioning-note.md`, `evidence/A/W01/bom-audit.csv` | NEED_USER_ACTION / BLOCKED_HARDWARE (not certified) |

## 4. What could NOT be computed, and why

* **Intra-configuration drift between sessions** — only one thermal capture of the
  `01cedce3…` configuration is committed on this branch; the W07/W08-era captures
  are sibling workstreams. Reported as a gap, no number invented.
* **Fuse suitability / conductor ampacity** — no marking photographed, no
  insulation class/routing recorded (`fuse-commissioning-note.md` ~:53). The
  deviation stays open; not certified.
* **W3/W8 envelope comparison** — a `TEAM_DEPENDENCY`: those dossiers are owned by
  sibling workstreams and are referenced, not re-derived.

## 5. OPERATOR_ACTION_QUEUE (W12)

Consolidated into the minimum supervised sessions; required repetitions are not
skipped. Nothing here authorises a flash or energize by itself — those keep their
own two-step gate.

| # | Requirement | Exact physical action | Existing valid evidence | Safety prerequisites | Expected capture | Downstream unlock |
|---|---|---|---|---|---|---|
| 1 | A-W12-03 sensor fixtures | Inspect + photograph each of the 4 DS18B20 fixtures at their frozen positions; record each ROM beside the photo | frozen geometry (this §2); `g2a/20-probe-identification.md` baseline | board unpowered; no wiring change | photo set + ROM/position table | enables role freeze to be treated as measured, not assumed |
| 2 | A-W12-03 V1 mounting + cable positions | Photograph TEC cold/hot mounting and probe/power cable routing; confirm unchanged since H8 | H8 T2 hot-side result (`01cedce3…` image) | board unpowered; supervision | dated mounting/routing photo set | closes the "geometry unchanged since freeze" A-W14 dependency |
| 3 | A-W12-03 terminals + fuse | Photograph installed fuse body rating + branch terminals; record conductor insulation class, run length, bundling | `fuse-commissioning-note.md` ~:36, ~:53 | board unpowered; do not deshoot/energize | fuse photo + conductor data | lets the fuse deviation move from BLOCKED_HARDWARE toward a defensible rating |
| 4 | A-W12-02 electrical qualification | One supervised idle (duty-0) OFF-envelope capture that also emits a qualified `current_status` | current OFF data is UNQUALIFIED | two-step flash/energize gate if a build change is needed to emit status; else capture-only on the installed image | OFF frames with non-empty current_status/voltage_status | upgrades A-W12-02 electrical figures from UNQUALIFIED to qualified |
| 5 | A-W12-01 intra-configuration drift | A second short characterization run on the *same* installed image (`01cedce3…`), no config change | one committed session | supervised bench; stop on zero/abnormal current | a second cooling CSV of the same configuration | computes session-to-session drift within one configuration |

Item 5 must not pool a different image: it is repeatable only under `01cedce3…`.
Items 1–3 are unpowered inspections and can share a single bench visit. Items 4–5
each need their own supervised energized session (with the standing stop-on-zero
rule), and item 4 must not skip its idle-window requirement.
