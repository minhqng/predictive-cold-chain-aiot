# Branch fuse commissioning note — A-W04-03

Status: **NOT FROZEN.** The installed fuse is recorded, the electrical demand is
measured, and one input to the selection is still missing. Freezing a rating
here would be a guess, and `docs/01` §16.2 forbids guessing branch protection.

## 1. What is installed and reported

| Item | Value | Basis |
|---|---|---|
| Branch fuse, holder slot 3 | **15 A, currently installed** | operator confirmation 2026-11-02; a photo of the label is pending and is not in this repository |
| Fuse box | ATO 4-way blade holder (HW-14) | `evidence/A/W01/bom-audit.csv:15` |
| Spare ratings owned | 10 A / 15 A / 20 A set (HW-15) | `evidence/A/W01/bom-audit.csv:16` |
| Other slots | 1 = 5 A (XL4015 logic rail), 2 = 1 A (PZEM), 4 = 1 A (fan) | operator-reported, `g0-electrical-verification.md:111` |
| Markings actually read off the body | **none** | `evidence/A/W01/photos/07-fusebox.jpg` and `photo-inventory.csv:8` state that no ATO text and no current rating are legible; no 250 V, dielectric (glass/ceramic) or blade-size record exists |
| History | slot 3 was removed for the unpowered G0 inspection and reinserted before the H6 run | `g0-electrical-verification.md:345`, `h6/09-pzem-gate-pass.md:8` |

## 2. Measured electrical demand on this branch

| Session | Duty | Duration | Current | Voltage | Power |
|---|---|---|---|---|---|
| H6, 2026-10-29 (`h6/first-tec-trace.csv`) | 10 % | 60 s | 0.97 A peak, 0.96 A mean | 11.71 V | 11.3 W peak |
| H8 box run, 2026-11-01 (`tec-cooling-response-600s.csv`) | 100 % | 600 s | 9.99 A peak, 7.24 A mean over the 600 COOLING frames | 11.76–11.95 V | 117.4 W peak |

The 15 A figure is **not** derived from the TEC part number `TEC1-12715`; that
inference is explicitly prohibited (`docs/01` §16.2), and this note does not
make it.

## 3. The conductor is the weak element, and its rating is the missing input

A branch fuse protects the **weakest** element in the branch, which is the
cable, not the TEC and not the driver.

| Element | Record |
|---|---|
| Branch conductor | **1.75 mm²**, operator-confirmed 2026-11-02; no marking photographed, no measurement recorded. The canonical ask is `2 × 2.5 mm²` (`docs/05A` A-W04-02, `docs/01` PHY-SAFE-004) and `evidence/A/W01/bom-audit.csv:20` still carries HW-19 as `UNVERIFIED` |
| Termination on the branch | FDD2-250 faston, rated 1.5–2.5 mm² → **in range** for a 1.75 mm² conductor |
| Termination previously flagged | the same FDD2-250 used on 0.75 mm² auxiliary wire (`evidence/A/W01/bom-audit.csv:21`, HW-20) → out of range there; that is a different circuit and must not be conflated with the TEC branch |
| Insulation temperature class, routing, bundling | not recorded anywhere |

Without the installed current-carrying capacity of a 1.75 mm² conductor at its
actual insulation class and routing, no rating below or above 15 A can be
justified. Publishing a number here would be exactly the "improvise silently"
failure `docs/05A` A-W08-02 warns about.

## 4. Decision table

| Available fact | Consequence for the fuse |
|---|---|
| Conductor is 1.75 mm² PVC, free-air single run, ≤ 60 °C insulation, short run | a 10 A fuse is the conservative choice; 15 A becomes arguable only with a stated ampacity table |
| Conductor is 1.75 mm² bundled or routed through a warm region | 10 A or lower; 15 A not defensible |
| Conductor is replaced by documented `2 × 2.5 mm²` with photo + marking | the canonical class is met and 15 A becomes defensible against the measured 9.99 A peak |
| No conductor evidence at all (today) | **no freeze**; branch stays as-is with no powered test beyond what the operator authorizes case by case |

## 5. What closes this note

1. A photograph of the installed fuse body showing its rating (and ideally
   `250 V` + glass/ceramic), plus one of the spare 10 A fuse.
2. Either a marking or a measurement of the branch conductor cross-section
   (photo of the print on the insulation, or caliper measurement of the bare
   conductor with the strand count), **or** a recorded decision to rewire the
   branch to `2 × 2.5 mm²`.
3. One sentence of installed condition for the ampacity basis: insulation
   temperature rating and how the cable is routed.

With (1) and (2) this file gets a `Selected rating / Basis / Verification`
block and A-W04-03 becomes VERIFIED. Until then A-W04-03 is **NEED_USER_INPUT**
and the conductor item is a hardware deviation needing change review
(`change-review-request-CR-A-W04-02.md`).

## 6. What this note does not claim

It does not claim 15 A is safe, it does not claim the branch is protected to a
standard, and it does not approve any powered test. The measured 9.99 A peak is
reported as a measurement of a past supervised session, not as a duty cycle this
fuse may be exercised at.
