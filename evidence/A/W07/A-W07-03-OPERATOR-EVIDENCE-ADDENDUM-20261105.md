# A-W07-03 — operator evidence addendum (2026-11-05)

Status: **CANONICAL CRITERION MET BY THE THREE RECORDED TRIALS; THE AUXILIARY
TWO-WINDOW WITNESS REMAINS NOT_REUSABLE AND IS NOT RELIED UPON.**

This addendum closes the publication limitation for A-W07-03 without changing any
recorded measurement, threshold or verdict. It adds no new hardware experiment and
does not convert the separate witness into a PASS.

## 1. Canonical criterion

From the acceptance registry:

> Perform at least three valid cooling-step runs with the same core action; measure
> current/power, command-to-electrical delay, thermal response and recovery.

Canonical checks: **3 valid runs**, **current present**, **no fault**, **cooling
response**. The criterion does not require a separate two-window stabilization
artifact.

## 2. Recorded trials (already published)

Each trial is a 180 s, 50 % START on the bench profile, with a pre-START
stabilization gate evaluated by the trial runner on the trial's own boot.

| trial | boot | current max | chamber drop | electrical delay | thermal delay | pre-START gate slope / spread | gate |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | `6d7dd125` | 4.94 A | 2.2708 °C | 1.02 s | 37.04 s | −0.012434 °C/min / 0.041667 °C | STABLE |
| 2 | `be89bf4a` | 5.03 A | 2.2688 °C | 1.02 s | 35.00 s | −0.000486 °C/min / 0.041667 °C | STABLE |
| 3 | `f44c9bed` | 4.99 A | 2.2688 °C | 1.02 s | 36.02 s | −0.002119 °C/min / 0.020833 °C | STABLE |

The runner's gate is |slope| ≤ 0.02 °C/min and Tmean spread ≤ 0.05 °C over the
last 60 frames (≥ 50 samples), evaluated immediately before START on the same boot.
All three trials passed it. The trial records and the raw trial captures are
published in `evidence/A/W07/registry/bench/` and
`evidence/A/W07/registry/trials/`.

## 3. Operator confirmation

On 2026-11-05 the operator confirmed that thermal testing was performed
repeatedly and observed to stabilize, and accepts the three recorded cooling-step
trials. This is an operator statement about the recorded trials; it is not a new
measurement and it does not backdate any record.

## 4. Auxiliary witness

`evidence/A/W07/registry/bench/stabilization-witness-a-w07-03-run3.json` was
captured on boot `82b2d6b6`, a different boot from run 3 (`f44c9bed`). It is
**NOT_REUSABLE** and its verdict is preserved. Its own windows were NOT_STABLE
(spread 0.0625 °C > 0.05 °C). No 90 s two-window PASS is claimed anywhere.

## 5. Disposition

- A-W07-03 canonical criterion: **MET** by the three recorded valid cooling-step
  runs and their same-boot pre-START gates.
- Publication limitation: **closed for the criterion**; the auxiliary witness
  limitation is retained verbatim as a documented caveat.
- Acceptance verdict: unchanged (`PASS`); this addendum is not a physical
  re-certification of the whole campaign.
