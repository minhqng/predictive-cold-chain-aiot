# ColdGuard Member A — Demo Runbook (A-W23-01)

**Status:** DRAFT prepared from existing verified protocols — PENDING OPERATOR CONFIRMATION.
This document is a preparation deliverable, NOT an executed rehearsal or handover.
It does not by itself satisfy A-W23-01; the operator must confirm each step and
attach this runbook during the documentary acceptance run.

**Authority:** docs/05A A-W23-01. Sources: W19/campaign-wave1-runbook.md,
W24/final-hil-smoke-protocol.md, W18/pre-run-safety-checklist.json,
HANDOFF/supervised-session-plan.md, W18/abort-criteria.yaml.

**Verified configuration referenced:** firmware cg-w06-0.1.0; ROM map
T1=287088CA00000051 (chamber), T2=28AEBF2200000006 (TEC hot side),
T3=28CBE9CA00000072 (chamber), SPARE=283BE5C9000000A9 (near door);
DS18B20 data GPIO33, BME280 I2C SDA21/SCL34, MC-38 GPIO35, PZEM RS-485 GPIO36/37,
IBT-2 RPWM=GPIO5/R_EN=GPIO6/L_EN=GPIO10. Output stage default-OFF.

## Safety posture (always)
- TEC output stage energization forbidden while hardware gates H-GATE-1..10 open,
  slot-3 15 A fuse removed, or PSU 12 V OFF. No script asserts non-zero PWM.
- Abort on: new abnormal current (>10 A provisional), unexpected heating
  (hot side >55 °C provisional), repeated verification failure, physical drift
  (W18/abort-criteria.yaml). Stop, do not retry to force a success.

## Eight-step demo sequence
1. **Visual inspection** — fixtures, V1 mounting, terminals, fuse holder, cable
   positions unchanged; no damage/drift. (Ref W12 mechanical audit; operator.)
2. **Power-on** — PSU 12 V ON via validated arrangement; ESP32 boots; verify
   boot log identity (boot_id, firmware_version, hardware_config_id).
3. **Sensor check** — DS18B20 T1/T3/SPARE valid; T2 hot-side plausible; BME280
   ambient/humidity valid (if fitted); MC-38 door transitions. thermal_quality VALID.
4. **PZEM check** — PZEM-017 Modbus RTU responds; voltage ~12 V, current 0 A at
   idle; electrical_quality VALID; no stale samples.
5. **Broker/device check** — local console responsive (USB-Serial/JTAG); telemetry
   stream present; (NETWORK transport is Member C-owned — verify only if integrated).
6. **Short legal actuation check** — BLOCKED pending H-GATE resolution + fuse +
   explicit two-step operator authorization. Until then verify default-OFF only
   (pwm_applied=0, output_stage DISABLED). Do NOT energize TEC unattended.
7. **Demo scene** — present live dashboard/telemetry; demonstrate sensor acquisition
   and safe default-OFF; narrate the fault-injection capability (W21) without
   actuating TEC.
8. **Safe shutdown** — TEC OFF, PSU 12 V OFF in validated order; confirm output
   stage disabled; record final state.

## Operator confirmation required
The documentary evaluator (handler_documentary) requires the operator to confirm
each of the eight steps, record inspection notes (operator/date/deviations), and
attach this runbook. Until then A-W23-01 remains NOT_RUN.