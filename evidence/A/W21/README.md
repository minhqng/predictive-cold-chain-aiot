# A-W21 delivery evidence — degraded-sensor & PZEM transport fault acceptance

Accepted: A-W21-02 (single DS18B20 software injection) and A-W21-03 (PZEM
transport-boundary injection), both PASS on real ESP32-S3 device evidence.
(A-W21-01 passive soak and A-W21-04 SAFE_LOCAL were accepted separately.)

## Provenance
- Firmware branch feat/a-w21-transport-fault, HEAD a54ba24 (base main b5e5cbf).
- Flashed test image SHA-256:
  e1073935168c01be029c23a87f6f012d852016deac0afb672437f234a269206b
- Boot ID 4cf9be5f; hardware CG-HW-001; device coldguard-001; firmware cg-w06-0.1.0.
- Evidence mode: ON_DEVICE_SOFTWARE_INJECTION (real device, NOT host simulation,
  NOT physical cable disconnection).
- fault-injection-session-20261108/: raw.log (SHA-256
  faf008eb6c7e250c8b8f98385e6eb3817b1084771a56d800a3735c576c7106fa), manifest.json,
  events.json, SHA256SUMS.txt. Independent phases per scenario:
  W21-02 (A_baseline/B_ds_t1_on/B_ds_t1_off), W21-03 (C_pzem_baseline/C_pzem_on/
  C_pzem_off), plus D_clear. Single boot, one ROM map (no remap).
- results/A-W21-02.json, results/A-W21-03.json with attachments/ (integrity-verified).

## Safety / limitation (must accompany any reuse)
- TEC output stage compiled out; fuse OUT. tec_state=OFF, cooling_applied=OFF,
  output_stage=DISABLED in all frames. OFF / 0 A is the safe test configuration,
  NOT proof of an enabled actuator's fail-safe logic.
- PZEM fault is a deliberate software transport disable (status=INJECT_DISABLED,
  attempts=0, RX empty), not a physical PZEM failure or a natural timeout.

## Validation dependency (transparency)
- The acceptance evaluators that produced these records live in the unpublished
  Member A acceptance application (feat/a-w21-evidence-final, HEAD 5fd89fb). They
  are NOT on main. This PR is therefore reviewable for source + evidence, but full
  independent re-evaluation requires that evaluator lineage (separate infrastructure
  PR chain). Do not treat this PR as fully independently reproducible on main alone.
- To re-validate: run handler_degraded_sensor / handler_degraded_pzem from the
  evaluator lineage against fault-injection-session-20261108/raw.log (replay), or
  re-run the on-device session with the test image and explicit authorization.

## Firmware source in this branch (vs main)
cg_fault_inject.{c,h} (reversible test-only injection), cg_ds18b20.c (single-ROM hook),
cg_power.c (PZEM transport-boundary injection), cg_pzem.{c,h} (INJECT_DISABLED),
cg_console.c (USB-Serial/JTAG console read), coldguard_config.h (CG_FAULT_INJECTION
default 0), CMakeLists.txt (gate + esp_driver_usb_serial_jtag), host tools/tests.