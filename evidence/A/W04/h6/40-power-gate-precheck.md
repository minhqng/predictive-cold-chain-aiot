# H6 power gate PASS — precheck BLOCKED on PZEM telemetry

Session date: 2026-10-29
Gate: **PASS** (operator confirmed: fuse inserted with PSU disconnected, wiring
and shunt secure, V1 fan running, ESP32 connected, no abnormal heat/smell/
noise/wiring).
Precheck result: **FAIL — PZEM telemetry invalid.**
Run status: **NOT STARTED.** No `ARM`, no `START`, no TEC drive, no restart,
no repeated test. Result class so far: **H6_BLOCKED** (precheck).

## 1. SAFE_OFF status with PSU ON (verified)

`30-precheck-pzem-on.log`, `STATUS` at 15:14:58Z:

```
state=WAIT_FOR_MANUAL_ARM reason=NONE run_consumed=0 elapsed_ms=0
duty_permille=0 ren=0 len=0 rpwm_level=0 pzem_ready=1
pzem=BAD_LENGTH
```

`31-precheck-retries.log`, three further `STATUS` at 15:15:12Z:

```
STATUS 1: pzem=BAD_LENGTH
STATUS 2: pzem=BAD_LENGTH
STATUS 3: pzem=BAD_LENGTH
```

Ignition-relevant state is correct and safe with the PSU live:

- state `WAIT_FOR_MANUAL_ARM`, `run_consumed=0` (the one-shot run has not been
  latched);
- duty 0, R_EN 0, L_EN 0, RPWM 0 — no drive to the IBT-2;
- LEDC and UART drivers initialised (`pzem_ready=1`);
- no fault, no unexpected output.

## 2. Why the run did not start

`cmd_start()` refuses to start unless the live precheck sample is valid:

```c
const h6_pzem_sample_t pre = h6_pzem_poll();
if (!pre.valid) {
    H6_LOG("H6 CMD START rejected reason=PZEM_INVALID state=ARMED\n");
    return 1;
}
```

With `pzem=BAD_LENGTH` the START gate can never pass, and starting without
voltage/current telemetry would violate the prepared test (PZEM is the
current anomaly detector). No ARM was sent, so the device remains in
`WAIT_FOR_MANUAL_ARM` with `run_consumed=0`.

## 3. What BAD_LENGTH means in this firmware

The poller sends `01 04 00 00 00 06 <crc>` (read 6 input registers, READ
ONLY), then reads up to 32 bytes with a 250 ms window and a 10 ms idle
terminator. A status of `BAD_LENGTH` is returned when:

1. no frame candidate (0x04 response or 5-byte exception) ends exactly at the
   RX tail, or
2. more than one CRC-valid candidate ends at the tail, or
3. a CRC-valid 0x04 response ends at the tail but its length/byte count is not
   the 17-byte / 12-data-byte profile (`parse_input`), or
4. an exception frame has the wrong length.

`CRC_ERR` would indicate a candidate with a bad CRC. The observed
`BAD_LENGTH` therefore points at a *framing or length mismatch*, not at a
CRC-only corruption. Two causes are consistent with the evidence and cannot
be separated with the current image, because the H6 poller does not log raw
RX bytes:

- **Echo / turnaround:** an 8-byte echo of our own request arrives first; the
  10 ms idle terminator ends the read after the echo, so the real response is
  never seen. The echoed prefix cannot form a tail-anchored candidate, which
  yields exactly `BAD_LENGTH`.
- **Response length different from the 6-register profile:** e.g. a module
  returning 8 or 10 input registers (21/25-byte frame) with a valid CRC.
  `extract_response()` accepts it, `parse_input()` rejects the length and
  returns `BAD_LENGTH`.

Less likely and not supported by the status: A/B polarity inversion or baud
mismatch (usually `CRC_ERR` or `TIMEOUT`), or a dead module (would be
`TIMEOUT`; with the PSU off it was `TIMEOUT`, with the PSU on bytes arrive).

No successful live PZEM read exists anywhere in the preserved evidence: the
W04 boot log before the flash also shows `status=TIMEOUT` (PSU off), and the
G1 evidence contains only the protocol tooling and fixtures. The PZEM path
has therefore never been proven end-to-end on this bench.

## 4. Why diagnosis was not improvised

- Rebuilding H6 to add raw RX logging would change the verified image
  (`573f9181…`) that is currently flashed, against the instruction not to
  recreate the firmware.
- Reflashing W04 (which logs `tx=`/`rx=` hex) would discard the H6 image and
  alter the prepared run state.
- Changing baud, slave address, wiring or the RS-485 module is a hardware/
  configuration change and was not authorized.
- Sending `START` anyway is impossible (precheck rejects it) and would be
  unsafe.

## 5. Current physical state

- TEC 15 A fuse: inserted (gate).
- PSU: ON per operator.
- TEC drive: OFF — duty 0, R_EN 0, L_EN 0. Nothing is heating or cooling.
- Firmware state: `WAIT_FOR_MANUAL_ARM`, one-shot latch still unused.
- No auto-repeat path exists; the guard timer is not running.

Recommended: power the PSU down again if the bench will be left unattended.

## 6. Options for the operator (no action taken)

1. **Inspect the PZEM/RS-485 link** (unpowered): confirm the module is a
   PZEM-017, its slave address and baud label, A/B polarity, and that the
   auto-direction TTL485 module releases the bus after TX. This is visual/
   unpowered only and does not repeat G0/G1 electrical tests.
2. **Authorize a diagnostic H6 rebuild** that dumps raw RX hex and/or accepts
   the module's full register set, then reflash and repeat the precheck only.
   This changes the image identity and must be explicitly authorized.
3. **Restore W04** (its PZEM line logs `tx=`/`rx=`) to capture the raw frame,
   then decide. This ends the H6 session state.

The one-shot test remains unstarted and can still be executed unchanged once
valid PZEM telemetry is available.

## 7. Evidence files

| File | Content |
|---|---|
| `30-precheck-pzem-on.log` | first STATUS with PSU on |
| `31-precheck-retries.log` | three retry STATUS polls |
