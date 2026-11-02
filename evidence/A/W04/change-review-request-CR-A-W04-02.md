# Change review request CR-A-W04-02 — TEC branch conductor class

Raised by Member A on 2026-11-02. Records a hardware deviation from the frozen
physical contract. **Nothing in this PR accepts, approves or works around it.**

## 1. The requirement and the as-built fact

| Item | Record |
|---|---|
| Canonical ask | `docs/05A` A-W04-02 with `docs/01` PHY-SAFE-004: the TEC branch conductor class is `2 × 2.5 mm²`, and no primary TEC current may run through a PCT-218 or Dupont path |
| As-built, operator-confirmed 2026-11-02 | the branch runs on **1.75 mm²** conductor |
| Repository state before that statement | `evidence/A/W01/bom-audit.csv:20` HW-19 = `UNVERIFIED`, `photo_ref NONE`: no photo or marking anywhere has ever established the class |
| Termination | FDD2-250 faston, rated 1.5–2.5 mm² — in range for 1.75 mm²; the separate out-of-range case is the same terminal type on 0.75 mm² auxiliary wire (HW-20), a different circuit |
| Measured demand on the branch | 0.97 A peak at 10 % duty (H6, 2026-10-29); 9.99 A peak and 7.24 A mean at 100 % duty for 600 s (2026-11-01) |

## 2. Why it is a change-review item, not a Member A decision

The conductor class is part of the frozen physical contract, and the branch
fuse selection depends on it (`fuse-commissioning-note.md` §3): a fuse protects
the cable, so the cable's installed ampacity sets the maximum rating. Changing
or accepting a smaller conductor therefore changes a safety parameter and must
be reviewed at project level, recorded in `docs/01`, and reflected in the
hardware configuration identity — not quietly accepted inside a W04 dossier.

## 3. Options

| Option | Action | Consequence |
|---|---|---|
| **A. Rebuild the branch to spec** | replace with documented `2 × 2.5 mm²`, photograph the marking, re-crimp in range | A-W04-02 becomes VERIFIED, 15 A fuse becomes defensible against the measured 9.99 A peak, no contract change needed |
| **B. Amend the contract to 1.75 mm²** | record the class, its insulation temperature rating and routing, derive the ampacity, then set the fuse below it | requires `docs/01` PHY-SAFE-004 change review and a new `hardware_config_id` revision; the fuse must most likely drop to 10 A |
| **C. Leave it undocumented** | do nothing | rejected: it leaves the branch protection basis undefined and blocks W08's measured envelope |

Member A recommends **Option A**, because it removes the deviation instead of
documenting a weaker branch, and it is the only option that makes the existing
15 A fuse defensible.

## 4. What Member A will not do

- Not approve the out-of-spec conductor as adequate.
- Not freeze a fuse rating against an unknown ampacity.
- Not run additional high-current tests to "characterise" the difference while
  the conductor basis is unresolved. The 2026-11-01 600 s run is reported as
  history, not as a licence to repeat it.

## 5. Requested decision owners

Project-level review with the `docs/01` owner and Member D as reviewer of record
for Member A's power/PZEM/IBT-2 work (`docs/04`).

## 6. Status

OPEN. Until it is decided, A-W04-02 stays **NOT VERIFIED / deviation** in
`acceptance.md`, and W08's safe-operating-envelope work is blocked behind it.
