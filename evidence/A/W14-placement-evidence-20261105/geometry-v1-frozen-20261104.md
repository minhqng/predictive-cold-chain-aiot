# geometry-v1 — A-W07-01 freeze record (2026-11-04)

Status: **FROZEN — current as-built geometry documented by operator-supplied
photographs; no TEC run; no dimensions invented**

This record supersedes the PENDING prefill `geometry-v1-prefill-20261104.md` for
the A-W07-01 decision. It preserves the existing sensor-position baseline and
adds the current configuration photographs. It does not claim an H0 dimension
baseline: H0 mechanical was deferred, no `sensor-placement.png` exists, and the
only capacity statement is the operator's verbal 6 L claim in the W01 photo
inventory.

## 1. Frozen slot-to-position mapping (unchanged)

| slot | ROM | physical position | source |
|---|---|---|---|
| T1 | `287088CA00000051` | chamber CENTER | `probe-identification-v0.md` §Official mapping; `geometry-v1.md` §1 |
| T2 | `28AEBF2200000006` | TEC HOT_SIDE, not moved | same |
| T3 | `28CBE9CA00000072` | chamber BOTTOM | same |
| T4 / SPARE | `283BE5C9000000A9` | NEAR the chamber DOOR | same |

The 2026-11-04 photographs corroborate the mounting, not a new role mapping.
No role is reassigned from an image.

## 2. Seven A-W07-01 fields

| # | Field | Frozen value / evidence | Limitation |
|---|---|---|---|
| 1 | Sensor mounts fixed | Interior photo shows four probe pass-throughs fixed in the chamber walls; exterior photo shows the V1/TEC assembly mounted through the chamber wall. Existing 2026-11-02 mapping retained. | Mounting height and clearance are not measured. |
| 2 | V1 position fixed | Exterior photo: V1 fan and heatsink on the chamber exterior, IBT-2 above it. Interior photo: inner fan at the TEC cold side. | No coordinates; position is photographic, not measured. |
| 3 | Cable paths fixed | Exterior photo: probe leads exit the chamber wall at the upper right; power/signal wiring runs loose (not taped) across the bench to the IBT-2, terminal blocks, PZEM and controller. This is the frozen current routing. | Loose, not strain-relieved; no route length or tie points recorded. |
| 4 | Door alignment fixed | 2026-11-04 live test: raw 0→1→0 transition, `door_status=VALID`, polarity CONFIRMED, cycles incrementing (`capture-20261104T094423Z`). Exterior photo shows the lid in place. | Rest gap and alignment method are not measured. |
| 5 | Chamber internal state fixed | Interior photo: four probes, BME280 module, inner fan and cold-side heatsink inside the foam chamber; no product or internal load. | No internal dimensions or load mass measured. |
| 6 | Dimensions / change since H0 | No dimensions recorded; no H0 mechanical baseline (W02 acceptance lines 56, 62, 103); 6 L is an operator verbal claim only (W01 photo inventory row 27). The freeze starts 2026-11-04. | No claim of "unchanged since H0"; no dimensions invented. |
| 7 | Configuration photo/drawing | Two current photographs supplied by the operator on 2026-11-04: `geometry-v1-interior-20261104.png` and `geometry-v1-exterior-20261104.png`. The wrapped-package photo is not used. | Photographs, not a measured drawing. |

## 3. Photo provenance

| File | SHA-256 |
|---|---|
| `geometry-v1-photos-20261104/geometry-v1-interior-20261104.png` | `f19531a1703604c8c5bcd0aee78f6347d67c024c9d8962520d816e030f8cfe7d` |
| `geometry-v1-photos-20261104/geometry-v1-exterior-20261104.png` | `ae96a96fa55fb4b92a4bf0cdc7754d74fcac5caa8ce3f2fc4d0dac015cf54ab2` |

Source: operator-supplied image attachments, 2026-11-04, current installed
setup. No cropping or editing was applied.

## 4. Existing evidence retained

- `evidence/A/W07/probe-identification-v0.md` — accepted slot-to-position record
  (233 frames, state OFF, applied duty 0).
- `evidence/A/W07/geometry-v1.md` §1–§3 — prior PARTIAL record and its open list.
- `evidence/A/W04/h8/mc38-2026-11-01/COLDGUARD_MC38_DOOR_ALIGNMENT_RESULT.md` —
  the earlier alignment failure and adjustment recommendation.
- `evidence/A/h8-captures/capture-20261104T094423Z/` — the successful
  2026-11-04 door transition and polarity confirmation.
- `evidence/A/W02/acceptance.md` lines 56, 62, 75, 103 — H0 deferred and
  `sensor-placement.png` missing.
- `evidence/A/W01/photo-inventory.csv` row 27 — wrapped-package photo; proves
  receipt only.

## 5. What this freeze does not assert

- No H0 dimension baseline and no "unchanged since H0" claim.
- No measured mounting height, clearance, door gap or cable length.
- No claim that a probe's physical label is present; ROM labels remain
  by-source per `probe-identification-v0.md`.
- No change to the docs/01 logical T1/T2/T3 naming discrepancy recorded in
  `geometry-v1.md` §4.

A-W07-01 can be evaluated from this record plus the two photographs; the
limitations above remain visible in the evidence rather than being hidden.
