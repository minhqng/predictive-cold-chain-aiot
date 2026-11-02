# W04 evidence manifest — committed set and local-only artifacts

W04 dossier for Member A (H4 default-OFF, H5 power branch, H6 conservative TEC
commissioning). This file states exactly what is in git and what stayed on the
bench machine, so a reviewer can tell committed proof from local proof.

Generated 2026-11-01. Nothing in this directory was produced by a simulator.

## 1. Layout

| Path | Content |
|---|---|
| `README.md` | Session metadata block required by `docs/05A` (date, operator, hardware_config_id, firmware identity, test IDs, result). |
| `acceptance.md` | Per-requirement status for A-W04-01…07, H4/H5/H6, and the canonical deliverable list. |
| `SHA256SUMS.txt` | SHA-256 of every committed file in this dossier; verified by `validate_w04.py`. |
| `g0-electrical-verification.md` | G0 electrical verification pass (continuity, shunt, fuse slot, conductor). |
| `h6-tec-polarity-test-plan.md` | Polarity test plan. The polarity verdict itself was never recorded — see `acceptance.md` A-W04-06. |
| `h6/` | H6 conservative TEC bench session 2026-10-29: build logs, static checks, flash/readback reports, the 60 s run capture and its analysis. |
| `g1/` | G1 production-firmware gate session 2026-10-29: git identity, source hashes, host unit tests, static checks, ESP-IDF build logs, chip identity, flash log, boot/reset captures, telemetry CSV/JSONL. |
| `g2a/` | G2a probe-identification and six-limit audit reports and the capture script. |
| `build-2026-11-01/` | ESP-IDF v6.1 compile-only build of the tree this PR delivers, with artifact and source hashes. |
| `power-topology-v1.png`, `fuse-commissioning-note.md`, `boot-default-off.csv`, `boot-default-off-note.md`, `polarity-photo.md`, `h6/first-tec-trace.csv`, `h6/first-tec-plot.png` | the six canonical W04 deliverables; the CSV and PNG files are generated from pinned raw captures by the tools in `tools/` and `firmware/tools/` |
| `tec-cooling-response-600s.csv`, `tec-cooling-response-600s.png` | cross-week thermal response derived from the 2026-11-01 monitor stream, labelled as 100 % duty later-week data, not a conservative W04 trace |
| `change-review-request-CR-A-W04-01.md`, `change-review-request-CR-A-W04-02.md` | the two contract questions Member A cannot decide alone (T2 semantics, conductor class) |
| `tools/` | the Windows renderers that regenerate the figures; edit their node/edge and series lists, not the PNGs |

## 2. Local-only artifacts (deliberately not committed)

Flash images and bulk bench captures stay outside git. The largest blob the
team has ever committed under `evidence/` is 534 KB and no `.bin` exists in the
repository history, so this dossier keeps the same rule: hashes here, bytes on
the bench machine.

Paths below are relative to Member A's local checkout area
(`coldguard-repo/`): the W04 bench worktree `A-W04-tec-commissioning/` holds the
`evidence/A/W04/**` and `firmware/*-bench/**` entries, and the scratch folders
`_w04-g1-evidence/` and `_w04-g2a-evidence/` hold the G1 and G2a session
worktrees. All three stay on the bench machine and are not part of this PR.
Some committed reports (`g0-electrical-verification.md`, `g1/SUMMARY.md`,
`g2a/`) still name `_w04-g1-evidence/...` paths in their prose: those files were
copied into `evidence/A/W04/g1/` unchanged, so the content is in git under the
dossier path and the original scratch path is kept as its provenance.

### 2.1 Flash images and region readbacks (`*.bin`)

| SHA-256 | bytes | path |
|---|---|---|
| `b9118aa3840f7c042a4dea8dae339d07a6e69f3716102174cc87b18046276295` | 4096 | `evidence/A/W04/h6/02-partition-table-read.bin` |
| `971d8e7855b936f4f4577dd7cb7a1601e6113fac933344b1981114fd9d9eb6cb` | 311296 | `evidence/A/W04/h6/11-h6-readback.bin` |
| `051f1e06c094380bee46bc2b771983377d21dfc6a24c4f5ed0436a6b1028ba5f` | 315392 | `evidence/A/W04/h6/13-h6-readback-fix.bin` |
| `41dd8e27540a744b34f2bb934ec1811d6ff32874d089aea32ddec06eac4e4033` | 4194304 | `evidence/A/W04/h6/w04-flash-backup-reread.bin` |
| `9ac21e7863ae2f4072655c8bf9788dae337b001a908efcd22b2eb677140595cf` | 4194304 | `evidence/A/W04/h6/w04-flash-backup.bin` |
| `f06b47007558c1fe0ef905c138a2d3c3048c903dec12816f8c7016d7d5431b62` | 65536 | `evidence/A/W04/h6/w04-region-0x00000-0x10000.bin` |
| `15e640fff7dec8ab733d8f5d1cc1cba48748d1a85f3f2302289a1c2996acbfda` | 244352 | `evidence/A/W04/h6/w04-region-app.bin` |
| `7ecc0a972abba338ea85a30ee0932581deeac4cd4ad2048d394523ad6d1864bb` | 32768 | `evidence/A/W04/h6/w04-region-bootloader.bin` |
| `b9118aa3840f7c042a4dea8dae339d07a6e69f3716102174cc87b18046276295` | 4096 | `evidence/A/W04/h6/w04-region-parttable.bin` |
| `9a840958796d215c6c710674cef21fe45c9624ea709edcf80e699ee3a07eccf0` | 4194304 | `evidence/A/W04/h7/pre-h8-h7-backup-2026-10-31.bin` |
| `9a840958796d215c6c710674cef21fe45c9624ea709edcf80e699ee3a07eccf0` | 4194304 | `evidence/A/W04/h7/pre-h8-h7-backup-2026-10-31-reread.bin` |
| `3b9e092dd0167cb27765b451ed8ba446fdcb1cacff5debdc81bb6e5fe47c0b34` | 254128 | `evidence/A/W04/h8/phase4d/00-current-device-app-v4.bin` |
| `d5e6464ce4418242a51fc449de4e68e5857e0e1eb17af9f06230a70bf51c1dbc` | 257392 | `evidence/A/W04/h8/phase4d/04-sim-readback.bin` |
| `f864911c6d9084f5b14ac12fee1f3201fb599ed761fa28ac691097798c1cade4` | 258448 | `evidence/A/W04/h8/phase4d/ondevice/23-sim-readback.bin` |

`02-partition-table-read.bin` and `w04-region-parttable.bin` share one hash:
the same partition table read back twice. The two `pre-h8-h7-backup` files also
share one hash for the same reason.

### 2.2 Bulk raw captures kept local

| SHA-256 | bytes | path | why local |
|---|---|---|---|
| `6815214d170a2c0efc9812384d80cfad29cf58ca6ea63f95d0eb42379cc6a439` | 641834 | `_w04-g2a-evidence/10-probe-warm-session.log` | raw probe-warm capture behind the committed `g2a/` reports |
| `5e8bb1918b90c392bea2cdca9e227a91886a4ac6f7f4d4e3db74d705d1ca1414` | 321879 | `_w04-g2a-evidence/11-probe-warm-session-2.log` | second pass of the same capture |
| `07ecfd7211a9089bb588539f664bc7eb851bb5a016a0c985ff80e0d6b9063c01` | 957 lines | `A-W04-tec-commissioning/evidence/A/W04/h8/box-cooling-600s-2026-11-01/monitor-final/samples.jsonl` | raw source of the committed `tec-cooling-response-600s.csv`; the CSV is in git, the JSONL stays local, so the derivation is checkable only against this hash |

### 2.3 H7 and H8 trees (later weeks, preserved locally)

H7 (electrical ladder) and H8 (endurance/box cooling) belong to W05+ scope and
are excluded from this PR on purpose. They are recorded here so their absence is
visible and so the local copies cannot be silently replaced.

Aggregate digest = SHA-256 of the concatenated `sha256sum` output of every
file in that tree, with the file list sorted by path:

```bash
cd A-W04-tec-commissioning
find <tree> -type f | sort | xargs sha256sum | sha256sum
```

| tree | files | bytes | aggregate SHA-256 |
|---|---|---|---|
| `evidence/A/W04/h7/` | 124 | 9,860,615 | `8b7ffc632a2ad70161124bf0f121264889a0328b5bca8be0fbb6a6c6013eebf5` |
| `evidence/A/W04/h8/` | 586 | 82,426,477 | `c9077c69896374a8e4e489528b9d8dc6897178de7fc8663a27797ad451dc48a7` |
| `firmware/h7-bench/main/` | 15 | 116,314 | `3e1e392a41b1c43c4652e1abc85bb743fc4ca54c2de930c50ec9b3a86c3bcd67` |
| `firmware/h7-bench/tools/` | 1 | 3,930 | `d9817f8d3139ea550ca7a70ae7db5702db5ba17dd167b0ba11fffb5182132a1d` |
| `firmware/h8-bench/main/` | 30 | 179,418 | `b7d0a60768f14b343dd7a8abb2fc095d3b64cc73d8f3cd58b439aa72372a56ba` |
| `firmware/h8-bench/tools/` | 18 | 321,473 | `ff94c8ea6636692409baf3d41ddb24645351ef2cf08df59f5a56a1ee0851366a` |

Two identities worth pinning because later weeks cite them:

- H8 final T2 HOT_SIDE image: `01cedce3b794638f25ae4c7f1e2dfdcb4b00555fdc81a0bcf4d35ed4187f6c9f`, 258,544 bytes, locally at `firmware/h8-bench/build-t2-hot-side/coldguard_h8_bench.bin` (recomputed 2026-11-01, matches the value recorded in the H8 report).
- Nine configured ESP-IDF build trees under `firmware/h8-bench/build*` total ≈ 1.39 GB and are regenerable output, not evidence. `.gitignore` now refuses them.

#### 2.4 Where the delivered image hashes live

The compile-only build of the tree this PR delivers is pinned in
`build-2026-11-01/21-artifact-hashes.txt` (app `0acd230c…`, 244,496 bytes) with
its source pins in `build-2026-11-01/22-source-hashes.txt`; those files are in
git, not local-only. `sdkconfig` is regenerated by `idf.py set-target`, so that
image is compile-proven but not bit-reproducible from git alone.

## 2.5 Reproducibility statement

The `h6/` and `g1/` logs are the actual serial and build output of the sessions
they describe, byte-pinned in `SHA256SUMS.txt`. The local-only files above are
pinned by hash but their bytes are not in this repository: a reviewer who needs
them must ask Member A for the worktree copy. Nothing here claims an independent
reviewer can reproduce a measurement from git alone.
