# ColdGuard Member A — W22 Evidence Gap Catalog & Physical Reconciliation

**Requirement Authority:** `docs/05A §31: A-W22-01`, `docs/03`, `evidence/A/RC/remaining-hardware-gates.md`  
**Status:** **HONEST_DISCLOSURE / CURRENT_BENCH_STATE**

---

## 1. Conductor Sizing Reconciliation: Diameter vs Cross-Section

A historical documentation discrepancy exists between early notes and verified measurements:
- **Early W04 Notes:** Stated conductor sizing as `"1.75 mm²"`.
- **Verified W01 / W12 / As-Built Audit:** Physical caliper measurement established a **1.75 mm diameter** solid round copper conductor (`as-built-pinmap-2026-10-27.md`).
- **Mathematical Reconciliation:** For a solid round copper conductor with diameter $d = 1.75\text{ mm}$, the actual cross-sectional area is:
  $$A = \pi \left(\frac{1.75}{2}\right)^2 = \pi \times 0.875^2 \approx 2.405\text{ mm}^2$$
  This corresponds roughly to AWG 13–14 wire, capable of safely handling the 9.99 A observed peak current.
- **Protocol Directive:** Both values are formally documented here to resolve team confusion without silently erasing historical notes.

---

## 2. Comprehensive Census of Open Evidence Gaps (W04–W16 & Hardware Gates)

| ID | Description | Source / Requirement | Current Status | Required Action / Closing Evidence |
|---|---|---|---|---|
| **GAP-01 (H-GATE-1)** | Unflashed Production Image | A-W04/W05/W06, docs/05A §20 | Bench runs H8 image (`01cedce3...`); RC image is un-flashed | Backup app partition, flash RC image, record boot banner and SHA-256 |
| **GAP-02 (H-GATE-2)** | Continuous 1 Hz Cadence on Silicon | A-W05-03, docs/05A §17 | Timing pilot derived from 60s committed capture | ≥30 min continuous on-device capture with zero sequence gaps |
| **GAP-03 (H-GATE-3)** | Door Polarity per Boot | A-W02-07, docs/05A §14 | Firmware holds door `UNVERIFIED` until attested | Physical open/close cycle observation per boot with raw level logged |
| **GAP-04 (H-GATE-4)** | Hot-Side Limit Unestablished | A-W08-03, docs/05A §20 | `HOT_SIDE_LIMIT_NOT_ESTABLISHED` in `cg_tec_limits.c` | Sustained energized run reconciling 55.0 °C provisional limit with 39.9 °C observed |
| **GAP-05 (H-GATE-5)** | Slot-3 Fuse & Resistance Under Load | A-W03-01, A-W08-02 | 15 A blade fuse currently REMOVED; holder resistance unmeasured | Under-load contact resistance measurement, or derating with written basis |
| **GAP-06 (H-GATE-6)** | Ground-Loop & USB Backfeed Mitigation | D22 (P1, HIGH) | PC USB connected to logic while 12 V PSU energized | USB isolator or isolated logic rail before slot-3 fuse reinsertion |
| **GAP-07 (H-GATE-7)** | True Cold POWERON Attestation | A-W04-04, docs/05A §16 | Native USB loses COM on reset; `rst:0x15` is not `rst:0x1 POWERON` | Dedicated UART console capture of cold power-on default-off state |
| **GAP-08 (H-GATE-8)** | Multi-Run Physical Repetitions | A-W07, A-W10, A-W19, A-W20 | Only one 600s cooling run committed; 0 certified S1, 0 valid S2 | ≥3 independent cooling sessions and paired door protocol on hardware |
| **GAP-09 (H-GATE-9)** | Physical Command Trace & ACK Execution | A-W06-05/06, docs/05A §18 | No network stack in build; backend command execution pending | Energized session with real applied PWM transition and matching ACK |
| **GAP-10 (H-GATE-10)**| Current Headroom Margin | A-W03-05, A-W08-01 | Observed peak 9.99 A vs 10.0 A provisional ceiling (narrow margin) | Inrush/steady-state load measurement or duty limit reduction |
| **GAP-11 (W16)** | Comparability Refusal Dataset | A-W16-04, docs/05A §25 | Comparability framework ready, but unlabelled refusal dataset uncommitted | Commit unlabelled physical refusal capture for drift baseline |
