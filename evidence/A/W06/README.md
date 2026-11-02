# A-W06 — Device command/ACK + physical actuation state (Member A)

Week: **W06** · Branch: `feat/a-w06-command-ack` · Stacked on
`feat/a-w05-telemetry` (PR #16, OPEN) which is stacked on
`feat/a-w04-tec-commissioning` (PR #13, OPEN)
Owner: Member A · Compiled: ESP-IDF v6.1, esp32s3
Status: **SOFTWARE DELIVERED · NO TRANSPORT · NO ACTUATION · PHYSICAL TRACE OPEN**

This dossier proves the device-side rules of the `docs/02` §28-§32 command
contract. It contains no real command round trip, because this firmware has no
transport, no backend issuer, and no authorized energized session.

## 1. What W06 changed

| Requirement | Delivered | Where |
|---|---|---|
| **A-W06-01** parser | `cg_command.c/.h`: the §28.1 field set, a strict record parser that refuses unknown fields and non-canonical vocabularies, and the §29 validation chain in the contract's own order | `firmware/main/cg_command.c` |
| **A-W06-02** idempotency | Volatile 8-entry `command_id -> canonical result` store; a replay returns the **original** verdict before freshness/range/safety are re-decided; hits and retention evictions are counted | same |
| **A-W06-03** expiry | **Fail closed on unverifiable absolute expiry.** No receive-time TTL substitution anywhere; `expiry_evaluable` states which of the two cases a line is | same |
| **A-W06-04** applied state | ACK carries `desired_*` and `applied_*` separately, the applied pair read only from the device context; telemetry gained `command_id`, `desired_cooling`, `desired_duty_permille`, `last_ack_status`, `last_ack_reason` | `cg_command.c`, `cg_telemetry.c` |
| **A-W06-05** physical trace | `cg_command_trace.py` with five non-promoting stages, plus the honest empty trace over a committed real capture | `firmware/tools/`, `physical-command-trace.md` |
| **A-W06-06** reset with a command present | Store is RAM-only and re-initialised at start; nothing in the command path or the commissioning file persists to NVS; the scenario log shows the post-reset verdict | `cg_commission.c`, harness |

Serial telemetry schema **2 → 3**. Schemas 1 and 2 still parse — the committed W04
capture and the W05 fixture are both re-parsed by the test suite. The command
envelope stays `schema=1` (docs/02 §28.1) and the ACK line says so, so the two
version numbers cannot be confused.

## 2. Files

| File | What it is |
|---|---|
| `README.md` | this file |
| `command-parser-tests.md` | the 36-scenario matrix, the freshness decision table, retention/reset semantics, and the W04 parser defect found here |
| `physical-command-trace.md` | stage rules, the two generated traces, what a real trace requires |
| `ack-fixture.json` | five labelled `#CG CMDACK` lines emitted by the delivered formatter, with parsed field maps |
| `duplicate-command-log.jsonl` | the same `command_id` submitted three times: `ACCEPTED`, then two `DUPLICATE_CANONICAL` with `reapplied=0` |
| `expired-command-log.jsonl` | the synchronized-clock expiry case |
| `reset-command-log.jsonl` | accepted before a reset, not remembered and re-validated after it |
| `demo-command-capture.log` | the input for the trace tool, generated not typed |
| `trace-host-demo.json`, `trace-committed-w04-capture.json` | the two trace reports |
| `build_contract_artifacts.py` | regenerates every artifact above from the sources; `--check` compares |
| `handoff-w06.md` | what Members C and D can build on, and the open contract items |
| `acceptance.md` | requirement-by-requirement status with the gaps named |
| `build/` | ESP-IDF v6.1 compile log, image hash, source pins |
| `SHA256SUMS.txt`, `validate_w06.py` | byte pins and the re-checker, which also asserts the honest verdict is still present |

## 3. Reproduce

```bash
py firmware/tools/run_all_checks_w06.py              # whole suite, 12 layers
py firmware/tools/cg_check_firmware_w06.py           # 93 static checks
py firmware/tools/tests/test_cg_w06_harness.py       # 36 C scenarios on the real sources
py evidence/A/W06/build_contract_artifacts.py --check # artifacts reproduce byte-for-byte
py evidence/A/W06/validate_w06.py
```

## 4. Limits of this dossier

* **Host evidence only.** Every command here is synthetic and every verdict comes
  from the delivered validator running on a host. No device received a command.
* **No actuation is possible in this build**, and the command path adds no route
  to it: `cg_command.c` calls no start/enable/duty/GPIO function (checked), the
  console's `START` verb remains the only controller start call site (checked),
  the output stage is compiled out, requested duty is 0, and all six operating
  limits (`CG_LIMIT_COUNT`) are still `UNRESOLVED`. Every fixture ACK reports `applied_cooling=OFF`,
  and the artifact generator refuses to write the file if that ever stops being
  true.
* **The device-side encoding is provisional.** `docs/02` shows a JSON envelope;
  parsing JSON in firmware is not warranted before a transport exists, so the
  record form here is `key=value` with the §28.1 field names and the rules are
  transport-independent. C owns the envelope; see `handoff-w06.md`.
* **An `ACCEPTED` verdict is unreachable on the shipped board**, by design: the
  clock is unsynchronized, so freshness is unverifiable. The permissive contexts
  that reach it are harness fixtures, the same kind of injection the W04 harness
  uses for its resolved limit table.
* **`device_mode` carries the controller state, not a policy mode** — policy
  states in `docs/02` §23 belong to Member D and this firmware runs none.
* **W05's physical gap is unchanged.** No 30-minute telemetry capture exists; the
  W06 image has not been flashed either. Both remain NEED_USER_ACTION in
  `acceptance.md` and in the W05 record.
* **Read `acceptance.md` §6 before quoting any image hash from this branch**, and
  §7 for the two dated corrections this slice owes the W04 and W05 records (the
  six-vs-seven limit count and the superseded serial-line budget).
