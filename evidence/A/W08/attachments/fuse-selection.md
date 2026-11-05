# A-W08-02 fuse selection - measured basis (derived; no decision recorded)

Generated offline from genuine captures only. This file supplies the **measured basis**.
The rating choice, the steady/transient figures entered at the prompt, the rationale text and
the fuse photo remain operator inputs and are deliberately NOT pre-filled here.

## Measured TEC branch current (PZEM-004T, 12 V PSU, supervised bench image 73968c19)

| Source | Duration / applied duty | Mean current (A) | Peak current (A) | Mean power (W) |
|---|---|---|---|---|
| A-W07-03 trial 1 | 180 s / 500 permille | 4.270 | 4.94 | 50.55 |
| A-W07-03 trial 2 | 180 s / 500 permille | 4.292 | 5.03 | 50.81 |
| A-W04-05 (60 s) | 60 s / 500 permille | 4.424 | 4.99 | 52.38 |

Worst-case measured peak: **5.03 A**. Highest measured mean: **4.424 A**.
Verifier rule (`final_fuse_above_measured_peak`): rating >= 1.25 x measured peak -> **>= 6.29 A**.

## Candidate ratings from the purchased set (10 A / 15 A / 20 A)

| Rating | Clears 1.25 x measured peak | Headroom vs peak | Clears 1.25 x highest mean |
|---|---|---|---|
| 10 A | yes | 1.99x | yes |
| 15 A | yes | 2.98x | yes |
| 20 A | yes | 3.98x | yes |

All three purchased ratings clear the measured electrical basis. The deciding factors are
therefore physical: TEC inrush/transient behaviour, wiring gauge, and terminal heating observed
by the operator - none of which is derivable from telemetry alone.

Bench ceilings for this image: duty_max_permille 500, on_time_max_ms 190000, current_max_a 6.0,
hot_side_max_c 45.0, supply 11-13 V. The peaks above are therefore the ceiling for this image.

## Verifier sequencing

`handler_fuse_final` (tools/member_a_app/evaluators_extra.py:334) only accepts current sources
whose recorded outcome is PASS, so A-W08-02 must be recorded after A-W07-03 is recorded PASS.
A-W08-02 is in turn the prerequisite for A-W18-01 (pre-run safety audit) and for the A-W24-01
final configuration freeze (`FINAL_FUSE_NOT_RECORDED` block at evaluators.py:1234).

---

## Revision 2026-11-05 - actual inventory and conductor/terminal/holder assessment

Operator-confirmed inventory (2026-11-05): **2 x 1 A, 1 x 5 A, 1 x 15 A. No 10 A and no 20 A
fuses exist.** The "purchased set" table above is therefore superseded for the decision: of the
three ratings the verifier accepts, only **15 A** is physically available.

### Electrical basis, both operating points

| Basis | Mean (A) | Peak (A) | 1.25 x peak | 1 A | 5 A | 15 A |
|---|---|---|---|---|---|---|
| Bench profile (500 permille cap, A-W04-05 + A-W07-03 x3) | 4.270-4.424 | 5.03 | 6.29 | fails | fails | clears |
| Historical full duty (imported A-W04-03, W01-W04 evidence) | 9.35 | 9.35 | 11.69 | fails | fails | clears |

15 A is the unique rating consistent with both the measured bench envelope and the historical
full-duty record, and it is the rating recorded as installed in the imported W01-W04 evidence
(`fuse_a = 15.0`, `steady_a = 9.35`, `transient_a = 9.35`). That record is historical: it is not
by itself proof of what is in the holder today.

### Conductor, terminal and holder suitability from documented evidence

- **Conductor:** BOM audit HW-19 lists the power leads as "2 x 2.5 mm2, ~2 m" with status
  **UNVERIFIED** - "no photo in the 25-photo set shows a readable cable cross-section marking".
  2.5 mm2 copper would carry roughly 20-24 A in free air, so a 15 A fuse sits inside conductor
  ampacity *if* the claim holds. Unverified means the protection coordination is unproven, not
  disproven; a smaller actual cross-section would invert the conclusion.
- **Terminal block:** TB4506 was substituted for the frozen TB4504 45 A 4P; its rating is
  **UNVERIFIED** (CR-A-W01-02, DEVIATION MAJOR in the BOM audit). The positions carrying the TEC
  branch are not individually rated in any record.
- **Ferrules/crimps:** the risk ledger R12 (OPEN) records FDD2-250 ferrules (1.5-2.5 mm2 range)
  used on 0.75 mm2 wire on the 5 V/aux branch. The ferrule type on the TEC branch conductors is
  not documented at all.
- **Holder:** photo `attachments/A-W08-02/fuse-block-holder-20261105.png` shows a 4-position
  blade block with the sockets in view and no blade markings legible. The G0 record states slot 3
  (15 A) was deliberately removed on 2026-10-29 and the operator later stated a fuse was installed
  for Stage F, so the **currently installed rating is not evidenced by any record**.

### Exact missing evidence (one consolidated de-energized visual inspection, after all captures)

1. Photo of the installed TEC-branch fuse showing its rating marking - or an explicit statement
   that the slot is empty, which would itself be a safety finding because the branch has carried
   current in powered tests.
2. Photo of the TEC-branch cable jacket marking (cross-section) plus measured length.
3. Photo or datasheet giving the rating of the terminal-block positions carrying the TEC branch.
4. Which ferrules/crimps are on the TEC branch conductors and their wire range.

### Verdict logic

With 15 A as the only inventory-consistent rating and every measured peak far below it, A-W08-02
can PASS only after items 1-4 confirm conductor, terminal and holder suitability. If the conductor
proves smaller than 2.5 mm2, or the block/ferrule rating proves below the load with margin, the
canonical gate FAILS rather than improvising: no other rating exists in inventory and a fuse above
conductor ampacity is not protection. No purchase and no live wiring inspection is requested.

