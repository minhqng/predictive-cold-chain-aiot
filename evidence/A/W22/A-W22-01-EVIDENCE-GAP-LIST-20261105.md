# A-W22-01 evidence gap ledger (machine-derived from the live store)

Session `capture-20261104T092140Z`; registry totals {"FAIL": 2, "PASS": 38, "NOT_RUN": 69, "INCOMPLETE": 5} of 114.
Owner and disposition columns are intentionally blank: the canonical criterion is a joint
leader/B identification, so this ledger supplies the factual inventory only.

## Per-requirement ledger

| Requirement | Title | Outcome | Recorded reason | Owner | Disposition |
|---|---|---|---|---|---|
| A-W01-01 | BOM reconciliation | FAIL | UNAPPROVED_SUBSTITUTION | | |
| A-W02-06 | BME280 check | NOT_RUN |  | | |
| A-W03-02 | RS-485 transceiver power and pin map | FAIL | vcc_3v3_ABOVE_MAXIMUM | | |
| A-W03-07 | IBT-2 logic only | NOT_RUN |  | | |
| A-W04-04 | Boot/reset default-off | NOT_RUN |  | | |
| A-W04-06 | Polarity freeze | NOT_RUN |  | | |
| A-W05-05 | Quality flags | NOT_RUN |  | | |
| A-W06-01 | Command parser | INCOMPLETE | NETWORK_TRANSPORT_UNAVAILABLE: the local source gate precedes field-level validation, so canonical d | | |
| A-W06-02 | Idempotency | INCOMPLETE | NETWORK_COMMAND_TRANSPORT_UNAVAILABLE: duplicate-canonical requires the docs/02 NETWORK source; the  | | |
| A-W06-03 | Expiry | NOT_RUN |  | | |
| A-W06-05 | Physical trace | NOT_RUN |  | | |
| A-W06-06 | Reset while a command exists | NOT_RUN |  | | |
| A-W07-02 | Passive warm-up repetitions | INCOMPLETE | START_CONDITION_SIMILARITY_AND_INDEPENDENCE_NOT_VERIFIED: three valid 300 s trials are contiguous (~ | | |
| A-W07-04 | Repeatability summary | INCOMPLETE | PREREQUISITE_INCOMPLETE A-W07-02: START_CONDITION_SIMILARITY_AND_INDEPENDENCE_NOT_VERIFIED: three va | | |
| A-W07-05 | Initial/reset criterion candidate | NOT_RUN |  | | |
| A-W08-03 | Hot-side sustainability | NOT_RUN |  | | |
| A-W08-05 | Gate A package | NOT_RUN |  | | |
| A-W09-01 | Run checklist | NOT_RUN |  | | |
| A-W09-02 | S1 baseline | NOT_RUN |  | | |
| A-W09-04 | Healthy response reference | NOT_RUN |  | | |
| A-W10-01 | Door protocol candidates | NOT_RUN |  | | |
| A-W10-02 | Timing method | NOT_RUN |  | | |
| A-W10-03 | Repeated S2 pilot | NOT_RUN |  | | |
| A-W10-04 | Pair tolerance evidence | NOT_RUN |  | | |
| A-W10-05 | Horizon support | NOT_RUN |  | | |
| A-W11-01 | S4 method | NOT_RUN |  | | |
| A-W11-02 | S4 evidence | NOT_RUN |  | | |
| A-W11-03 | Dataset expansion | NOT_RUN |  | | |
| A-W11-04 | Conditional S3 feasibility | NOT_RUN |  | | |
| A-W12-03 | Mechanical audit | NOT_RUN |  | | |
| A-W12-04 | Hardware config signoff | NOT_RUN |  | | |
| A-W12-05 | Gate G3 input | NOT_RUN |  | | |
| A-W13-03 | Door-to-critical time | NOT_RUN |  | | |
| A-W14-03 | Spatial statistics | NOT_RUN |  | | |
| A-W14-04 | Pairing criterion refinement | NOT_RUN |  | | |
| A-W15-01 | Electrical feature integrity | NOT_RUN |  | | |
| A-W15-02 | A3 dataset support | NOT_RUN |  | | |
| A-W15-03 | PZEM reference check | NOT_RUN |  | | |
| A-W15-04 | PWM Go/No-Go | NOT_RUN |  | | |
| A-W16-01 | Re-run short characterization | NOT_RUN |  | | |
| A-W16-02 | Compare W7/W8 versus W16 | NOT_RUN |  | | |
| A-W16-03 | Final pair tolerances | NOT_RUN |  | | |
| A-W16-04 | Controller B physical readiness | NOT_RUN |  | | |
| A-W17-01 | Shadow S2 runs | NOT_RUN |  | | |
| A-W17-02 | No predictive physical path | NOT_RUN |  | | |
| A-W17-03 | Online/offline physical alignment | NOT_RUN |  | | |
| A-W17-04 | Plant anomaly monitoring | NOT_RUN |  | | |
| A-W18-01 | Pre-run safety audit | NOT_RUN |  | | |
| A-W18-02 | Controlled predictive dry runs | NOT_RUN |  | | |
| A-W18-03 | Electrical verification | NOT_RUN |  | | |
| A-W18-04 | Thermal verification | NOT_RUN |  | | |
| A-W18-05 | Abort criteria | NOT_RUN |  | | |
| A-W19-01 | Run preparation | NOT_RUN |  | | |
| A-W19-02 | Physical execution | NOT_RUN |  | | |
| A-W19-03 | Invalid attempt logging | NOT_RUN |  | | |
| A-W19-04 | Reset | NOT_RUN |  | | |
| A-W20-01 | Continue exact protocol | NOT_RUN |  | | |
| A-W20-02 | Valid-pair completion | NOT_RUN |  | | |
| A-W20-03 | Campaign close physical audit | NOT_RUN |  | | |
| A-W20-04 | Freeze physical campaign data | NOT_RUN |  | | |
| A-W21-01 | Physical reliability soak | NOT_RUN |  | | |
| A-W21-02 | One-sensor degraded case | NOT_RUN |  | | |
| A-W21-03 | PZEM unavailable | NOT_RUN |  | | |
| A-W21-04 | SAFE_LOCAL final test | NOT_RUN |  | | |
| A-W22-01 | Evidence gap list | NOT_RUN |  | | |
| A-W22-02 | Execute approved reruns | NOT_RUN |  | | |
| A-W22-03 | Physical limitation summary | NOT_RUN |  | | |
| A-W23-01 | Physical demo runbook | NOT_RUN |  | | |
| A-W23-02 | Recovery kit | NOT_RUN |  | | |
| A-W23-03 | Cable/label hardening | NOT_RUN |  | | |
| A-W23-04 | Demo rehearsals | NOT_RUN |  | | |
| A-W23-05 | Evidence package | NOT_RUN |  | | |
| A-W24-01 | Final configuration record | INCOMPLETE | FINAL_FUSE_NOT_RECORDED: run A-W08-02 before freezing the configuration | | |
| A-W24-02 | Final HIL smoke | NOT_RUN |  | | |
| A-W24-03 | Handover run | NOT_RUN |  | | |
| A-W24-04 | Final acceptance | NOT_RUN |  | | |

## Grouped causes

- **Run-3 derived, now closed:** none outstanding
- **Door observation dependent (observed 2026-11-05; re-run chain pending):** A-W07-02, A-W07-04, A-W07-05, A-W09-01, A-W10-01, A-W10-02
- **S1/S2 campaign dependent (long captures, operator door events):** A-W09-02, A-W09-04, A-W10-03, A-W10-04, A-W10-05, A-W11-03, A-W13-03, A-W14-03, A-W14-04, A-W15-01, A-W15-02, A-W16-01, A-W16-02, A-W16-03
- **BME280 + trim reference evidence dependent:** A-W02-06, A-W05-05
- **Firmware profile / capture-limit dependent (needs authorized profile change):** A-W08-03, A-W21-01
- **Degraded-input tests needing a fault-injection test image:** A-W21-02, A-W21-03, A-W21-04
- **Reset/boot series needing operator USB cold boots:** A-W04-04, A-W08-05
- **Operator documentary statements (one batched request):** A-W12-03, A-W12-04, A-W12-05, A-W22-01, A-W22-03, A-W18-05, A-W20-03, A-W20-04, A-W23-01, A-W23-02, A-W23-03, A-W23-04
- **Genuine B/C/D ownership (A halves proven where applicable):** A-W06-01, A-W06-02, A-W06-03, A-W06-05, A-W16-04, A-W17-01, A-W17-02, A-W17-03, A-W17-04, A-W18-02, A-W18-03, A-W18-04, A-W19-02, A-W20-02
- **Proven hardware noncompliance (FAIL, excluded from sprint):** A-W01-01, A-W03-02

Unassigned non-PASS IDs (should be empty):
A-W03-07, A-W04-06, A-W06-06, A-W11-01, A-W11-02, A-W11-04, A-W15-03, A-W15-04, A-W18-01, A-W19-01, A-W19-03, A-W19-04, A-W20-01, A-W22-02, A-W23-05, A-W24-01, A-W24-02, A-W24-03, A-W24-04
