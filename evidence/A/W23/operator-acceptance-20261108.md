# Operator acceptance / deviation record — 2026-11-08

Operator present and deciding. Hardware CG-HW-001. These are operator acceptance
decisions, recorded verbatim in intent; they are NOT agent-fabricated confirmations.

## A-W23-03 (branch labels) — OPERATOR-ACCEPTED DEVIATION
- Canonical criterion: apply labels 12 V / 5 V / sensor bus / RS-485 / TEC branch / shunt.
- Operator decision (2026-11-08): "6 nhãn nhánh ... ko cần vì linh kiện có ghi
  thông số và để ngoài hết rồi cho dễ nhìn" — components carry inherent markings
  and are laid out exposed; no additional labels applied.
- Recorded as: operator-accepted deviation. Evidence = existing component-marking
  photos (W01 overview / PSU label / fan label / shunt marking / TEC marking) and
  the exposed as-built layout (W07 geometry). NOT applied-branch-label photos.
- Acceptance: INCOMPLETE — physical branch labeling deferred by operator
  (2026-11-08); not a hardware fault. The canonical applied-label criterion
  (6 labels) is not met and remains unchanged. The operator-accepted deviation
  above is recorded as provenance, NOT a PASS: no waiver clause exists in the
  governing procedure to convert an operator-accepted deviation into PASS.
- Evaluation history: an earlier "PASS with deviation note (operator authority)"
  conclusion was incorrect and is superseded by this line; a FAIL attempt was
  archived in the results store, then corrected to INCOMPLETE once labeling was
  confirmed as deferred work. See results/A-W23-03.json (outcome INCOMPLETE,
  "Prior FAIL attempt archived. Not a PASS."). Labeling pending.

## A-W12-03 (mechanical inspection, fuse item) — OPERATOR ACCEPTANCE
- Operator decision (2026-11-08): fuse ratings read by ATO color code
  (khe: cam 5 A / 1 A / 15 A / 1 A, matching runbook v2); "cầu chì chỉ có màu
  như thế thôi" → color code accepted as the rating identification.
- Mechanical items (fixtures / V1 mounting / terminals / cable positions) supported
  by W07 geometry interior+exterior and W01 08-terminal-block.jpg.
- LIMITATION (kept open, not waived): fuse-to-conductor ampacity suitability is NOT
  certified (runbook v2: 15 A not certified; core 1.75 mm → 2.405 mm² conditional).
  This remains an open engineering deviation cross-referenced to the deferred
  hardware FAILs A-W01-01 / A-W03-02. The PASS covers the mechanical inspection and
  rating identification, not an ampacity certification.

## Still pending (not accepted here)
- A-W23-01 runbook 8-step confirmation; A-W18-05 abort-rule confirmation;
  A-W04-06 cold-face confirmation; A-W23-04 rehearsals; A-W24-03 second-person handover.