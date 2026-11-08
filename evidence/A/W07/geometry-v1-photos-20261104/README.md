# W07 geometry-v1 photographs — canonical source (published once)

Genuine operator photographs of the assembled chamber geometry, 2026-11-04
(CG-HW-001). Published here ONCE as the canonical source; other requirements
reference these files by relative path instead of storing per-requirement copies.

| File | SHA-256 | Bytes |
|---|---|---|
| geometry-v1-interior-20261104.png | f19531a1703604c8c5bcd0aee78f6347d67c024c9d8962520d816e030f8cfe7d | 1081314 |
| geometry-v1-exterior-20261104.png | ae96a96fa55fb4b92a4bf0cdc7754d74fcac5caa8ce3f2fc4d0dac015cf54ab2 | 3808646 |

Checksums: `SHA256SUMS.txt` (`sha256sum -c SHA256SUMS.txt`).

## Referencing requirements (no copies)
- A-W04-06 (TEC polarity/orientation): `evidence/A/W04/results/A-W04-06.json`
  references `../W07/geometry-v1-photos-20261104/…` (interior + exterior).
- A-W12-03 (mechanical inspection): `evidence/A/W12/results/A-W12-03.json`
  references the same canonical files.

The acceptance store resolves each reference as `<store-root>/<stored>` and
verifies the SHA-256, so a referencing requirement must be reviewed on a base
that contains this canonical directory (its own PR diff or a stacked base).
These photographs support orientation/mechanical layout; they are not a
substitute for requirement-specific attestation and do not by themselves prove
probe ROM placement (see A-W04-06 disclosures).