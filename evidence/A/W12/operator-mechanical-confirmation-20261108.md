# A-W12-03 mechanical inspection — operator confirmation (2026-11-08)

Operator present and deciding. Hardware CG-HW-001. This records the operator's
physical confirmation of the W12 mechanical-inspection items. It is an
operator-confirmed DOCUMENTARY acceptance, not a host-derived PASS.

## Relationship to the host drift-audit dossier (already on main)
The merged W12 host dossier (`acceptance.md`, `mechanical-audit-checklist.csv`,
`drift-audit.json`, PR #22) records A-W12-03 as `NEED_USER_ACTION /
BLOCKED_HARDWARE` because a host audit cannot perform physical checks. That
host-only perspective is unchanged and remains valid. This follow-up adds the
operator's physical confirmation on top; it does not edit the hash-pinned host
artifacts or claim the host dossier proved a physical PASS.

## Confirmed items (operator, 2026-11-08)
| Item | Confirmation | Supporting evidence (canonical reference) |
|---|---|---|
| Sensor fixtures unchanged | Confirmed | W07 geometry interior/exterior |
| V1 mounting unchanged | Confirmed | W07 geometry interior/exterior |
| All terminals secure | Confirmed | W07 geometry + W01 08-terminal-block.jpg |
| Fuse and holder unchanged | Confirmed | W23 fuse-block-installed.png (PR #75) |
| Cable positions unchanged | Confirmed | W07 geometry interior/exterior |

## Fuse rating identification (operator assertion)
- Operator decision (2026-11-08): fuse ratings read by ATO color code
  (khe: cam 5 A / 1 A / 15 A / 1 A, matching runbook v2); "cầu chì chỉ có màu
  như thế thôi" → color code accepted as the rating identification.
- LIMITATION (kept open, not waived): fuse-to-conductor ampacity suitability is
  NOT certified (runbook v2: 15 A not certified; observed conductor 1.75 mm
  copper-core diameter → ≈2.405 mm² only IF solid round, unconfirmed; canonical
  ask 2 × 2.5 mm²; W01 HW-19 UNVERIFIED). This open engineering deviation is
  cross-referenced to the deferred hardware FAILs A-W01-01 / A-W03-02. The PASS
  covers the mechanical inspection and rating identification, NOT an ampacity
  certification. The installed-photo colors do not independently corroborate the
  two 1 A slots (open verification).

## Scope
- Accepted: A-W12-03 (mechanical inspection), source DOCUMENTARY.
- Not accepted here: A-W12-01/02/04/05 (host dossier unchanged); whole-week W12
  is NOT GREEN; G3 is not set by this slice.