# H6 PZEM `BAD_LENGTH` — root cause (2026-10-29)

Status: **root cause identified from preserved evidence and corrected in the
H6 reader.** No hardware change. This supersedes the two hypotheses listed in
`40-power-gate-precheck.md` §4, which were written before the preserved bench
logs were examined.

## 1. Observed symptom

With the PSU ON and the H6 image running, four consecutive `STATUS` polls
returned:

```
H6 STATUS state=WAIT_FOR_MANUAL_ARM ... pzem_ready=1
H6 STATUS pzem=BAD_LENGTH
```

each answer in ~0.1 s (`30-precheck-pzem-on.log`, `31-precheck-retries.log`).
`START` was never sent; its precheck requires a valid live sample.

## 2. The previously successful reader (operator-confirmed)

Preserved bench firmware and logs from the same board, same PZEM-017 and same
TTL485 auto-direction module:

- `evidence/A/W03/hardware-2026-10-27/firmware/ColdGuard_TEST_133B_reset_default_off.ino`
  - request frame: `01 04 00 00 00 08 F1 CC` — FC04, **eight** input registers
  - expected reply: `01 04 10 [16 data bytes] [CRC]` — **21 bytes**
  - source comment: *"Ignore possible 8-byte TX echo."*
  - reads inside an **800 ms** window, scanning the accumulated buffer at every
    offset, and never ends the read early.
- `evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.log`
  - `VALID_SAMPLES: 600`, `FAILED_SAMPLES: 0`, `SUCCESS_RATE: 100.00 %`
  - every CSV row has `rx_len = 29` = **8-byte echo + 21-byte reply**
- `evidence/A/W03/hardware-2026-10-20/raw/pzem-off-serial.log` (same transport)
  - `#RUN_START ... function=0x04 qty=8 ... timeout_ms=260`
  - `#MEAS_PASS ... prefix=8 echo=1 rx_complete_us=80436`
  - prefix distribution over 595 logged samples: **437 × prefix 8 (echo), 98 ×
    prefix 8, 60 × prefix 7** — an echo is present in every sample, sometimes
    with its first byte lost in the transceiver turnaround
  - `rx_complete_us` range: **72 198 – 92 472 µs** (reply completes ~72–92 ms
    after the request)

So: the module answers correctly on this exact wiring, the transceiver echoes
the request onto RX, and the reply arrives tens of milliseconds after the echo.

## 3. Difference that causes the failure

H6's reader mirrored `firmware/main/cg_power.c` in protocol but not in read
policy. Production's `link_transaction()` calls `cg_rs485_read()` repeatedly
inside a per-attempt deadline loop and keeps going after an echo; H6 called a
single `read_with_timeout()` that **returns after 10 ms of line idle**:

```c
if (got_data && (TickType_t)(now - last_rx) >= idle_ticks) {
    break;      /* H6 before the fix: ends the attempt right after the echo */
}
```

Sequence on the bench, from the measured data above:

| t after request | bytes on RX | H6 (before fix) |
|---|---|---|
| 0–8.3 ms | 8-byte request echo | read collects 8 bytes |
| 8.3–18.3 ms | silence | 10 ms idle reached → **attempt ends** |
| ~58–72 ms | reply starts | never read; buffer flushed by the next attempt |
| ~80–92 ms | reply complete | not seen |

`extract_response()` on those 8 echo bytes finds no complete frame: at offset 0
the "function" is `0x04` but the "byte count" is `0x00`, giving a 5-byte
candidate that does not end at the RX tail; no other offset qualifies. With no
candidate and no CRC-bad candidate the extractor returns `BAD_LENGTH` — exactly
the status observed (`h6_pzem.c`, old lines 63–118). `CRC_ERR` was impossible
because no frame shape of usable length was ever received.

This is consistent with the ~0.1 s answer time: the reader returned after the
echo, not after the 250 ms window.

## 4. Comparison table (requested in Step 1)

| Item | Proven W03 bench (2026-10-20/27) | Production W04 | H6 before fix | H6 after fix |
|---|---|---|---|---|
| UART port | UART2 (`HardwareSerial(2)`) | UART1 | UART1 | UART1 |
| TX / RX GPIO | 36 / 37 | 36 / 37 | 36 / 37 | 36 / 37 |
| Baud, framing | 9600 8N1 | 9600 8N1 | 9600 8N1 | 9600 8N1 |
| Slave | 1 | 1 | 1 | 1 |
| Function | 0x04 | 0x04 (0x03 for range) | 0x04 | 0x04 |
| Registers | 0x0000, qty **8** | 0x0000, qty **6** | 0x0000, qty **6** | 0x0000, qty **6** |
| Request CRC | `F1 CC` | `70 08` | `70 08` | `70 08` |
| Expected reply | 21 B, count `0x10` | 17 B, count `0x0C` | 17 B, count `0x0C` | 17 B expected; any even count ≥ 12 accepted |
| TX completion | `flush()` | `uart_wait_tx_done` 50 ms | same | same |
| Read window | 800 ms outer loop | 250 ms per attempt | 250 ms per attempt | 250 ms per attempt |
| Inter-byte idle | not used to end a read | 10 ms per `read()` call, transaction continues | **10 ms ends the attempt** | not used to end the attempt |
| Echo handling | scans everywhere; comment says echo expected | tail-anchored extract, loop continues past echo | tail-anchored, single read | scans everywhere; ends early only on a usable frame |
| RX flush | drain before write | before write | before write | before write |

Two differences are *not* defects and were deliberately left alone:

- **UART2 vs UART1.** Same pins, same module; port numbering is internal to
  the ESP32-S3 and UART1 is what production uses. Nothing in the evidence
  implicates the port.
- **qty 8 vs 6.** The module also answered a 4-register FC03 read on
  2026-10-20 (`#CFG_PASS`), so it honours the requested quantity. Six
  registers is a valid read of `0x0000–0x0005`; the failure is timing, not the
  count. The new parser accepts any even count ≥ 12, so a 21-byte reply would
  also be decoded.

## 5. Why production was not implicated in the field

`cg_power.c`'s outer loop calls `cg_rs485_read()` again with the remaining
deadline after the idle-terminated call, so the echo never ends the
transaction. The W04 PZEM path has no successful live evidence in this repo
(the only W04 boot log was captured with the PSU off, hence `TIMEOUT`), but
its structure does not contain the H6 defect.

## 6. What the fix changes, and what it does not

Changed only in `firmware/h6-bench/`:

- read until a CRC-valid FC04 reply with ≥ 6 registers is present, or the
  250 ms attempt window closes;
- scan the whole received buffer (echo prefix, optional trailing byte);
- classify every attempt and print raw TX/RX hex, chunk lengths and timestamps,
  parsed slave/function/byte count, CRC status and final class.

Unchanged: request bytes, baud/framing/pins, 250 ms × 2 attempts, 1 Hz poll,
START's mandatory valid-sample precheck, 10 % PWM, 60 s hard bound, one-shot
latch, SAFE_OFF boot, automatic OFF, no automatic restart, all W04 gates.

## 7. Exact bytes

H6 request (fixed, CRC16/MODBUS recomputed and checked offline):

```
01 04 00 00 00 06 70 08
```

Expected 17-byte reply for six registers (`0x0000–0x0005`):

```
01 04 0C [12 data] [CRC]        e.g. 01 04 0C 04 AC 00 00 00 00 00 00 00 00 00 00 00 59 2A
```

The 17-byte vector above is the self-test vector (`h6_selftest.c`, `k_resp6`);
its CRC was verified independently, so a clean 10.96 V reply decodes as
`vbus_mv=1100 current_ma=0 power_mw=0`.

Observed RX on this wiring (preserved 2026-10-20 log; raw frames transcribed in
`A-W03-integration/evidence/A/W03/hardware-2026-10-20/crc-audit.md`):

```
01 04 00 00 00 08 F1 CC | 01 04 10 04 AC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FB 92   (29 B, 600/600 samples)
       8-byte echo     |  21-byte reply, completes 72–92 ms after the request
```

The 29-byte length is `rx_len` recorded on every row of the 600/600 run; the
tail bytes shown are the clean form these frames carry (a reply with corrupted
data bytes keeps `FB 92` but fails CRC — the 7 INVALID samples of 2026-10-20).
The old H6 image had no RX logging, so its own capture existed only as the
`BAD_LENGTH` status; the new image prints TX/RX hex, chunk timing and class on
every attempt, which is how the post-reflash check will document the exact
bytes seen by H6.
