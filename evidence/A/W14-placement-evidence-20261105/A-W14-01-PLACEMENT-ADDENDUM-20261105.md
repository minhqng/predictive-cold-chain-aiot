# A-W14-01 — placement evidence addendum (2026-11-05)

Status: **AS-BUILT PLACEMENT VERIFIED BY DATED OPERATOR PHOTOGRAPHS AND ROM
MAPPING; CONTINUOUS UNCHANGED PLACEMENT AT THE EXACT QA INSTANT IS LIMITED.**

This addendum adds evidence references only. It does not change the recorded
A-W14-01 verdict, checks, measurements or timestamps, and it does not invent a
historical photograph or backdate an attestation.

## 1. Canonical criterion

> Verify no sensor has moved since the geometry freeze.

Canonical checks: **ROM map matches**, **four unique ROMs**, **photo evidence**.

## 2. Authentic evidence

| Evidence | SHA-256 | Notes |
|---|---|---|
| `geometry-v1-frozen-20261104.md` | `e5a3a2fb298456dbd02697557715af80d9cee69a8c39675df3e408b8661e3717` | operator-frozen mapping; dated 2026-11-04 |
| `geometry-v1-20261104-SHA256SUMS.txt` | `92233ce4864e3d1d57d2b4012a0c81b8a80a97861fd061a2277c9b040a3ce1ca` | pins the two original photographs |
| `geometry-v1-interior-20261104.png` | `f19531a1703604c8c5bcd0aee78f6347d67c024c9d8962520d816e030f8cfe7d` | original operator photo, 1 081 314 bytes; bytes excluded from Git (size policy) |
| `geometry-v1-exterior-20261104.png` | `ae96a96fa55fb4b92a4bf0cdc7754d74fcac5caa8ce3f2fc4d0dac015cf54ab2` | original operator photo, 3 808 646 bytes; bytes excluded from Git (size policy) |

The frozen record maps the slots as follows, from the operator-frozen geometry and
the probe-identification record:

| slot | ROM | position |
|---|---|---|
| T1 | `287088CA00000051` | CHAMBER_CENTER |
| T2 | `28AEBF2200000006` | TEC_HOT_SIDE |
| T3 | `28CBE9CA00000072` | CHAMBER_BOTTOM |
| T4 / SPARE | `283BE5C9000000A9` | CHAMBER_NEAR_DOOR |

A-W14-01 itself (`2026-11-04T14:29Z`, boot `0b8ad797`) reports exactly this ROM
map and four unique ROMs.

## 3. Operator confirmation

On 2026-11-05 the operator confirmed the mapping above (T1 centre, T2 hot side,
T3 bottom, T4/SPARE near the door) and that no sensor has been moved. This is an
operator statement about the installed as-built configuration; it is not a new
measurement and it is not dated to the QA window.

## 4. What is verified and what remains limited

- **Verified (as-built):** the installed placement matches the frozen ROM-to-position
  mapping, supported by the two original operator photographs and the operator's
  2026-11-05 confirmation.
- **Limited (continuity):** the photographs were supplied and assembled on
  2026-11-04 before the A-W14-01 run, but no photograph is timestamped at the exact
  QA instant. Continuous unchanged placement across that interval rests on the
  operator's confirmation, not on a contemporaneous dated inspection. This specific
  limitation is retained; no "unchanged since H0" claim is made.
- The geometry record itself states that it makes no H0 continuity or dimensional
  claim.

## 5. Disposition

- A-W14-01 acceptance verdict: unchanged (`PASS` on ROM identity).
- Publication limitation: **closed for as-built placement**; the exact QA-instant
  continuity limitation is retained and documented.
- Photograph bytes remain outside Git under the repository size policy; their
  original SHA-256 values are pinned here and in the frozen geometry record.
