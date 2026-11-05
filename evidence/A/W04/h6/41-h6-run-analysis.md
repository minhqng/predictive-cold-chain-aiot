# H6 one-shot run — real measurements (2026-10-29)

Status: **H6 RUN EXECUTED ONCE — automatic OFF at 60.000 s, all 60 live samples
valid, final outputs off. Awaiting operator touch observation.**

Operator authorization: explicit ARM/START authorization received before the
run. PWM 10 %, one run, no retry, no firmware change.

## 1. Sequence (`40-h6-run.log`, host UTC)

```
15:40:06.221 H6 CMD ARM accepted state=ARMED duty_permille=0 next=START
15:40:08.245 H6 PRECHECK pzem=OK vbus_mv=11950 current_ma=0 power_mw=0
15:40:08.245 H6 CMD START accepted state=RUNNING_10_PERCENT max_on_ms=60000
15:40:08.245 H6 ON duty_permille=100 duty_count=819 pwm_freq_hz=1000 freq_reconstructed=1
...
15:41:08.217 H6 OFF source=guard_timer reason=TIMEOUT elapsed_ms=60000 duty_permille=0 ren=0 len=0 rpwm_level=0
15:41:08.217 H6 END state=COMPLETE elapsed_ms=60000 duty_permille=0 ren=0 len=0 rpwm_level=0 start_rejected_until_reboot=1
```

- Device-measured ON time: **60 000 ms exactly** (esp_timer guard one-shot).
- Host-side span from START accept to OFF line: 59.972 s (USB CDC print latency).
- No `STOP` was sent; no `H6 OFF source=operator_stop` line; no fault,
  telemetry-invalid or implausible line.

## 2. Live telemetry — 60 samples at 1 Hz, every one `pzem=OK`

First sample (elapsed_ms=2) is the pre-ramp reading; from 1 s onward:

| quantity | min | max | mean |
|---|---:|---:|---:|
| bus voltage | 11.71 V | 11.71 V | 11.710 V |
| current | 0.96 A | 0.97 A | 0.960 A |
| power | 11.2 W | 11.3 W | 11.20 W |

Representative lines:

```
elapsed_ms=2     vbus_mv=11760 current_ma=0   power_mw=0
elapsed_ms=1015  vbus_mv=11710 current_ma=970 power_mw=11300
elapsed_ms=30015 vbus_mv=11710 current_ma=960 power_mw=11200
elapsed_ms=59015 vbus_mv=11710 current_ma=960 power_mw=11200
```

Consistency: 11.71 V × 0.96 A = 11.24 W, matching the reported 11.2–11.3 W.
Bus drop from 11.95 V (idle) to 11.71 V at ~1 A is consistent with the branch
resistance. 0.96 A at 10 % duty is in line with the earlier ≈0.98 A bench
observation; this run did not exceed it.

Raw frames: 62 `H6 PZEM_TRACE` lines for 60 samples — 60 `class=OK` plus 2
`ECHO_ONLY` first attempts that were retried successfully inside the same
sample. No sample was delivered from a retry-free attempt without a CRC-valid
reply.

## 3. Final state

Captured at the end of the run: `state=COMPLETE`, `elapsed_ms=60000`,
`duty_permille=0`, `ren=0`, `len=0`, `rpwm_level=0`,
`start_rejected_until_reboot=1`.

A `STATUS` issued 30 s later (`42-status-after-run.log`) reports
`state=WAIT_FOR_MANUAL_ARM reason=NONE run_consumed=0` with
`pzem=OK vbus_mv=11950 current_ma=0 power_mw=0`. That is the MCU's boot state,
so the board reset between the end of the run (15:41:08.217) and that query.
No firmware path returns to `WAIT_FOR_MANUAL_ARM`, and a reset at port open is
ruled out by timing (the first `STATUS` was answered 110 ms after the port
opened). The two remaining candidates are the USB-Serial/JTAG DTR/RTS
transition when the console port was closed at `H6 END`, or an autonomous
reset. The reset cause was not recorded because no reader was attached at that
moment, so it is stated as unresolved rather than asserted.

Either way the safety outcome is unchanged: boot goes through `SAFE_OFF` with
RPWM/EN low, no TEC drive is possible without operator ARM + START, and the
PZEM confirms 0.00 A at 11.95 V afterwards. `run_consumed=0` reflects that
post-reset boot, not a missing one-shot latch — the latch was observed active
(`start_rejected_until_reboot=1`) at the end of the run. Any future run would
still require a new explicit ARM + START authorization.

## 4. What the run proves / does not prove

Proves: command path, 10 % PWM application, current actually flowing, live
telemetry throughout, exact 60 s bound, automatic OFF, no restart, outputs at 0
afterwards.

Does not prove: thermal performance, continuous-operation safety, or the
polarity itself — polarity is the operator's qualitative touch observation.

## 5. Next

Operator observes the small aluminum block by touch (not terminals, not the
fan, not the heatsink). Result classes: colder → H6_POLARITY_CORRECT, warmer →
H6_POLARITY_REVERSED_SUSPECTED, no difference → H6_INCONCLUSIVE. W04 restore is
held until the observation and this evidence are recorded.

---

## Correction (2026-11-01, delivery review)

Recomputed against `40-h6-run.log`: the file holds 62 `H6 PZEM_TRACE` lines =
61 `class=OK` plus 1 `class=ECHO_ONLY`, and those 62 include the pre-check poll
issued before START. §2's "60 `class=OK` plus 2 `ECHO_ONLY`" is therefore wrong.
The 60 `H6 T` samples, 60/60 `pzem=OK`, min/max/mean table and the OFF/END lines
all reproduce as written. The text above is left intact as the dated record of
2026-10-29; this block is the correction.
