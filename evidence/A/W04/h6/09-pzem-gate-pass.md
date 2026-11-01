# H6 PZEM gate — live verification with PSU on (2026-10-29)

Status: **H6_PZEM_GATE_PASS.** Five consecutive CRC-valid samples, decoded and
plausible. TEC OFF throughout, `run_consumed=0`, no ARM/START sent.

## 1. Operator state

PSU 12 V ON, 15 A TEC fuse reinserted while unpowered, V1 fan running, ESP32-S3
on USB, wiring unchanged, no abnormal heat/smell/noise. No rebuild/reflash.

## 2. Device state (`30-pzem-gate.log`)

```
H6 STATUS state=WAIT_FOR_MANUAL_ARM reason=NONE run_consumed=0 elapsed_ms=0 duty_permille=0 ren=0 len=0 rpwm_level=0 pzem_ready=1
```

State, duty and both enable levels are exactly the required pre-arm condition.

## 3. Five consecutive samples, 1.6 s apart (`31-pzem-1hz.log`)

Every poll succeeded on **attempt 1** with the same raw stream:

```
tx  01 04 00 00 00 06 70 08
rx  01 04 00 00 00 06 70 08 | 01 04 0C 04 AB 00 00 00 00 00 00 00 00 00 00 43 5E
    ^ 8-byte echo @10-19 ms  | ^ 17-byte reply, complete @88-94 ms
```

| # | utc | rx_len | chunks | echo | frame_off | count | crc | class | vbus_mv | current_ma | power_mw |
|---:|---|---:|---|---:|---:|---:|---|---|---:|---:|---:|
| 1 | 15:38:45.951 | 25 | 8@10ms,17@90ms | 8 | 8 | 12 | ok | OK | 11950 | 0 | 0 |
| 2 | 15:38:47.502 | 25 | 8@18ms,17@88ms | 8 | 8 | 12 | ok | OK | 11950 | 0 | 0 |
| 3 | 15:38:49.079 | 25 | 8@11ms,17@91ms | 8 | 8 | 12 | ok | OK | 11950 | 0 | 0 |
| 4 | 15:38:50.819 | 25 | 8@14ms,17@94ms | 8 | 8 | 12 | ok | OK | 11950 | 0 | 0 |
| 5 | 15:38:52.380 | 25 | 8@19ms,17@89ms | 8 | 8 | 12 | ok | OK | 11950 | 0 | 0 |

Independent host-side CRC check of the reply (not using device code):

```
frame 01 04 0c 04 ab 00 00 00 00 00 00 00 00 00 00 43 5e
CRC16/MODBUS over first 15 bytes = 43 5e  -> match
regs [0x04AB, 0, 0, 0, 0, 0]
V = 11.95 V   I = 0.00 A   P = 0.0 W   E = 0.0 Wh
```

## 4. Plausibility (not merely "frame valid")

- **Voltage 11.95 V** on a nominal 12 V bench branch — within 0.5 % of nominal,
  inside the test window 6–16 V, and consistent with the 11.96 V recorded in
  the W03 off-state runs on this same branch.
- **Current 0.00 A** with TEC OFF — no commanded drive, and well below the
  START precheck threshold of 0.2 A. The shunt branch is live (the module is
  powered and reports the bus), so this is a real zero, not a missing reading.
- **Power 0.0 W**, **energy 0.0 Wh** — consistent with zero current; the
  zero-energy counter also matches the absence of any commanded drive since
  boot.
- Register map in use (V, I, P low/high, E low/high) matches the production
  driver, so the decoded fields are the intended ones.

## 5. Note on back-to-back polling

When four `STATUS` commands were queued within ~1 s, polls 2–4 had their first
attempt end as `ECHO_ONLY` (echo at 13–19 ms, no reply inside the attempt
window) and the second attempt returned the frame at 88–108 ms:

```
attempt=1 ... rx_len=8 ... class=ECHO_ONLY
attempt=2 ... rx_len=25 ... class=OK
```

At the operating cadence (1.6 s and 1 Hz during the run) every first attempt
succeeded, as shown in §3. The retry path is the designed behaviour and no
setting was changed: this is evidence that the fix handles both the normal
case and a missed reply without ever reusing a stale reading.

## 6. Verdict

H6_PZEM_GATE_PASS. All prerequisites for START are satisfied: state
`WAIT_FOR_MANUAL_ARM`, duty 0, outputs off, one run unconsumed, and live
telemetry valid, CRC-checked and physically plausible. No ARM or START has
been sent; the next step requires a separate explicit operator authorization.
