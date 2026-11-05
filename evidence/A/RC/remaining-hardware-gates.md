# Member A — remaining hardware acceptance gates (RC, 2026-11-03)

This is the complete list of Member A acceptance items that **cannot** be closed
by any offline run. Every one of them needs an operator action on the assembled
box, and each states the minimum evidence that would close it. Nothing here is
claimed as passed.

Standing physical state at the time of writing (operator-confirmed): PSU 12 V
OFF; fuse slot 3 (15 A, IBT-2 B+ / TEC supply) REMOVED, so the TEC branch is
isolated; the four DS18B20 probes are not to be heated, moved or re-identified.

| Gate | Requirement | Why offline work cannot close it | Minimum closing evidence | Blocking dependency |
|---|---|---|---|---|
| H-GATE-1 production flash | A-W04/W05/W06 on real silicon | The box runs the H8 bench image (`01cedce3b794…6c9f`), not this release candidate. An H8 result is never proof of an unflashed production build | Backup the running app partition first, flash the RC, capture the boot banner and `#CG TELEM` line, record the new image SHA-256 | explicit operator authorization (two-step, no auto-retry) |
| H-GATE-2 1 Hz telemetry | A-W05-03 | The timing pilot is derived from a committed 60 s W04 capture, so it measures a window, not a continuous rating | ≥30 min on-device capture with published/elapsed jitter, zero sequence gaps | H-GATE-1 |
| H-GATE-3 door polarity per boot | A-W02-07, D25 | A compile-time constant cannot prove the wiring still matches after reset, and the firmware now holds the door `UNVERIFIED` until attested | One physical open/close observation per boot, recorded as `DOOR_POLARITY` with the raw committed level | H-GATE-1 |
| H-GATE-4 hot-side limit | A-W08-03 | `HOT_SIDE_LIMIT_NOT_ESTABLISHED` is an unmeasured quantity; the start-admission gate is deliberately left unwired rather than bound to an invented threshold | Sustained hot-side temperature at the tested duty, with the provisional 55 °C cutoff and the observed 39.938 °C maximum reconciled | supervised energized session |
| H-GATE-5 fuse finalisation | A-W03-01, A-W08-02, D13 | Slot-3 contact resistance under load, holder rated current and the branch overcurrent strategy are physical measurements. The only recorded holder reading is an unquantified bench OL | Under-load holder reading, or a written substitution/derating with its basis | slot 3 reinsertion, therefore H-GATE-6 first |
| H-GATE-6 ground-loop mitigation | D22 (P1, HIGH) | USB backfeed into a powered 12 V branch is observed history; its loop current needs an instrument this bench does not have | USB isolator, or an isolated 5 V logic rail with the PC disconnected, or an explicit operator acceptance naming the load hazard | none — must be resolved **before** any stage that reinserts the fuse |
| H-GATE-7 true POWERON attestation | A-W04-04, D24 | The native USB console loses its own COM enumeration at reset, so it cannot capture the first boot bytes; `rst:0x15` is not `rst:0x1 POWERON` | A cold-boot capture from a console that stays up, or an equivalent independent observation of default-OFF at power-on | CH343G console path proven operational, or a second observer |
| H-GATE-8 plant repetitions | A-W07-02/03, A-W10-02/03, A-W19/W20 | Repeatability, paired-door disturbances and the A/B campaign are physical runs; one run is not three experiments | ≥3 independent cooling sessions and the paired door protocol, each with its own run id and reset-criterion outcome | H-GATE-1, H-GATE-4, supervised sessions |
| H-GATE-9 physical command trace | A-W06-05/06 | There is no network stack in this build and `CG_CMD_SOURCE_NETWORK` is reserved, so no command can reach the device from the backend | An energized session with a real applied-state transition and its ACK, or a documented local-source equivalent clearly labelled non-canonical | H-GATE-1, transport implementation |
| H-GATE-10 current headroom | A-W03-05, A-W08-01 | The best observed loaded peak is 9.990 A against a provisional 10 A ceiling — margin, not a rating | Either a measured inrush/peak with the real load, or a written reduction of the permitted duty ceiling | supervised session |

## What the release candidate can already prove without any of the above

- The production image compiles for ESP32-S3 with ESP-IDF v6.1 and its bytes are
  reproducible from committed sources plus `firmware/sdkconfig.defaults`.
- Every host-side contract, parser, idempotency, expiry, quality-flag and
  telemetry-schema check passes, including the mutation tests that prove the
  hot-side probe cannot be folded into the chamber-air value.
- The B/C/D interface mismatch is characterised field by field, so Members C and
  D know exactly what their gateway must change.

## Non-negotiables carried forward

- No unattended energization: any stage that touches 12 V requires an attended
  session with named abort conditions.
- Never send `ARM`, `STAGE` or `START` outside a supervised stage that permits it.
- Never treat software `OFF` as proof of physical isolation; slot 3 is the
  isolation.
- Do not re-run the measurements already frozen in `evidence/A/IHA-01/` —
  G0 resistance checks, TEST109/110, H6/H7/H8 capability runs, ROM
  re-identification, and TEST-01B are all closed as evidence and must not be
  repeated to satisfy a new document.
