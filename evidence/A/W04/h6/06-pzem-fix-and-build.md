# H6 PZEM fix and build (2026-10-29)

Status: **source fix built and statically checked; reflash blocked on operator
power isolation.** No TEC drive in this step. See `05-pzem-root-cause.md` for
the evidence trail.

## 1. Files changed (H6 only)

| File | Change |
|---|---|
| `firmware/h6-bench/main/h6_pzem.c` | read policy rewritten: accumulate until a usable frame or the attempt deadline; line idle no longer ends a read; whole-buffer frame scan; per-attempt classification |
| `firmware/h6-bench/main/h6_pzem.h` | trace struct/callback, frame/class API for the poller and the self-test |
| `firmware/h6-bench/main/h6_main.c` | `H6 PZEM_TRACE` printer, trace registration after a successful init, init line now states framing and read-only |
| `firmware/h6-bench/main/h6_selftest.c` | `test_pzem_framing()`: synthetic RX streams for every classification |

Not touched: `firmware/main/**` (production W04), `h6_config.h` transport or
safety constants, `h6_state.c/h`, `h6_selftest.h`, GPIO map, PWM setup.

## 2. Exact fix

`h6_pzem.c:275` `poll_attempt()`:

1. flush RX **before** the write only; write `01 04 00 00 00 06 70 08`;
   wait for TX done (50 ms);
2. start a 250 ms window (`esp_timer_get_time()`, not tick granularity);
3. collect **every** available chunk, remembering length and arrival time;
4. after each chunk run `h6_pzem_classify()`; end early **only** when a
   CRC-valid FC04 reply from slave 1 with ≥ 6 data registers is present;
5. never end on inter-byte idle; a short read is not a short response;
6. at the deadline, classify the whole 32-byte capture and map the class to the
   existing status vocabulary.

`h6_pzem.c:91` `h6_pzem_classify()` detects, in this order:

- a usable reply (CRC-valid, slave 1, FC04, even count ≥ 12) anywhere in the
  buffer — echo prefix and trailing byte allowed;
- two differing usable replies → `AMBIGUOUS`;
- CRC-valid FC84 exception;
- CRC-valid reply from another slave;
- CRC-valid reply with < 12 data bytes (`FULL_WRONG_COUNT`);
- full-shape reply with bad CRC (`CRC_INVALID`);
- echo only (7–8 byte prefix of the request);
- otherwise `PARTIAL`; empty buffer → `NO_RESPONSE`.

`h6_pzem.c:247` `h6_pzem_parse_registers()` decodes the first six registers
with an independent CRC and length check.

`h6_pzem.c:394` `h6_pzem_init()` now uses the production order
(`param_config`, `set_pin`, `driver_install`). No parameter changed.

## 3. Diagnostic output (Step 2 requirement)

Every attempt prints one line (wrapped here with `\` only for readability):

```
H6 PZEM_TRACE attempt=1 tx=0104000000067008 rx_len=25 \
rx=010400000006700801040C04AC00000000000000000000592A \
chunk_count=2 chunks=8@10ms,17@78ms first_ms=10 last_ms=78 echo=8 \
frame_off=8 frame_len=17 slave=1 fc=4 count=12 crc_ok=1 usable=1 early=1 \
uart_err=0 class=OK
```

(field values illustrative of the expected bench pattern; the bytes shown are
the real request, echo and a 0 V/11.96 V reply).
Fields: exact TX bytes, exact RX bytes, RX total, each chunk’s length and time
relative to TX-done, first/last byte time, detected echo length, frame offset
and length, parsed slave/function/byte count, CRC status, final class.

The six required distinctions map to `class=`:

| Case | `class=` |
|---|---|
| request echo only | `ECHO_ONLY` |
| echo followed by valid reply | `OK` with `echo=8 frame_off=8` |
| partial reply | `PARTIAL` |
| full reply with unexpected count | `FULL_WRONG_COUNT` (count < 12) or `OK` with `count=` ≠ 12 |
| CRC-invalid reply | `CRC_INVALID` |
| no reply | `NO_RESPONSE` |

## 4. Unit checks (on-device self-test)

`test_pzem_framing()` (`h6_selftest.c:227`) runs at every boot against the
linked code; a failure blocks arming. Vectors are real Modbus bytes:

- `01 04 0C 04 AC 00…59 2A` (clean 17-byte reply) → `OK`
- echo + reply (offset 8) → `OK`, `echo=8`
- 7-byte echo + reply (first echoed byte lost) → `OK`, `offset=7`
- reply + trailing byte → `OK`
- echo only → `ECHO_ONLY`
- echo + truncated reply → `PARTIAL`
- 21-byte / count-16 reply → `OK`
- reply with corrupted CRC → `CRC_INVALID`
- CRC-valid reply from slave 2 → `BAD_SLAVE`
- CRC-valid count-8 reply → `FULL_WRONG_COUNT`
- FC84 exception → `EXCEPTION`
- empty buffer → `NO_RESPONSE`
- two replies → `AMBIGUOUS`
- register decoding and CRC rejection of the corrupted frame

Static checks: `07-static-checks.txt` (one FC04 builder, no idle termination,
flush-before-write, one TEC enable site, one `h6_sm_start` site, START still
rejects `PZEM_INVALID`, PWM/ON-bound constants unchanged, W04 gates unchanged).

## 5. Build result

| Item | Value |
|---|---|
| ESP-IDF | v6.1 (`C:\Espressif\v6.1\esp-idf`), target `esp32s3` |
| Build dir | `C:/Users/dlbac/Downloads/coldguard-repo/_h6-build` |
| Result | success, 0 warnings, 0 errors |
| App size | 0x3CB10 bytes, 76 % of the 1 MB slot free |
| `coldguard_h6_bench.bin` | `963f3cd623b8c8fade910adda723c0f178e7bc303528b63ed6520fd12110858d` |
| `bootloader.bin` | `764792967f1a0910d20290c9c2a51611a7a6d3cb0441d2c175b4200d0f3ff10d` (unchanged) |
| `partition-table.bin` | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` (unchanged) |

The new class names (`PZEM_TRACE`, `ECHO_ONLY`, `FULL_WRONG_COUNT`,
`AMBIGUOUS`, `NO_RESPONSE`) are present in the linked image.

## 6. Reflash plan (requires operator isolation first)

Mandatory before flashing, per plan §8 and the operator’s Step 4:

1. PSU 12 V switched off and disconnected from AC;
2. TEC 15 A fuse removed while unpowered;
3. confirm no abnormal heat/smell; ESP32 stays on USB.

Then, without chip erase and without touching the pre-flash backup:

```
esptool --chip esp32s3 -p COM4 -b 460800 --before default-reset --after hard-reset \
  write-flash --flash-mode dio --flash-freq 80m --flash-size 2MB \
  0x0     _h6-build/bootloader/bootloader.bin \
  0x8000  _h6-build/partition_table/partition-table.bin \
  0x10000 _h6-build/coldguard_h6_bench.bin
```

`w04-flash-backup.bin` (4 MB, SHA-256 `9ac21e78…`) and the region files are
left untouched; no new full-chip backup is needed.

Boot acceptance after flashing: `H6 SELFTEST result=PASS` (expected ~172
checks, 0 failures), `H6 SAFE_OFF`, `WAIT_FOR_MANUAL_ARM`, duty 0, no
spontaneous output. With the PSU still off, PZEM `TIMEOUT`/`NO_RESPONSE` is
expected and is not a link failure.

Then the operator restores PSU power (fan running, fuse in), and the bench
check is at least three consecutive valid samples with raw trace, plus an
OFF-state current consistent with no commanded drive. Only after that will a
new explicit ARM/START authorization be requested.
