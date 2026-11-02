# A-W07 handoff — what W07 gives B/C/D, and what only a session can give

Week-scoped slice of the docs/05A §5 / §6.1–§6.3 handover. Requirement-level status for all
44 items lives in each week's own dossier; this file covers A-W07-01..05 only.

## Consumable now (delivered on this branch, PR #18)

| Handoff field (docs/05A) | W07 artifact | Honest state |
|---|---|---|
| sensor identity / placement (§6.1) | `geometry-v1.md` §1, `probe-identification-v0.md` + 6 raw captures | Position mapping is operator-frozen and re-derivable from 233 frames: **T1 centre, T2 TEC hot side, T3 bottom, T4 near door**. ROM ids are *by source* (`coldguard_config.h:229-235`), never read back from the devices. The in-frame `t1..t4_role` fields remain `UNASSIGNED` except `t2_role=HOT_SIDE` |
| quality flags (§6.1) | `repeatability-*.json`, `repeatability-report.md` | Probe quality is real (`t*_status` OK in 957/957); **electrical values are unqualified at the source** — `current_status`/`voltage_status` empty in all 957 rows and `power_w`/`energy_wh` have no status column at all. Absence is not verification, and tooling now refuses to infer it |
| applied cooling (§6.1) | `warmup-runs.jsonl`, `cooling-step-runs.jsonl`, `recovery-runs.jsonl` | `pwm_applied_permille` separates intent from application; per-phase exclusions are counted, not hidden |
| thermal response windows (§6.3) | `repeatability-report.md`, overlay CSV (3 828 rows, 4 representations) | **One session only**: cooling −8.7083 C over 9.98 min, 1 C at 0.85 min. A single observation, never a window |
| sensor degraded behaviour (§6.3) | `reset-criterion-v0.yaml` `sensor_quality_required: VALID` | Enforced: the evaluator refuses a state whose quality is not `VALID`, and `UNKNOWN` is not `CLOSED`/`VALID`/known |
| reset / readiness criterion (§6.3, A-W07-05) | `cg_reset_criterion.py`, `reset-criterion-evaluation.json` | Shipped candidate answers **UNKNOWN**, never READY. Three state gates are frozen; `tmean_band_c` and `gradient_bound_c_per_min` stay UNRESOLVED until measured. D owns the threshold values |
| representation choice (blocks B feature design) | `REPRESENTATIONS` + `includes_hot_side` | Four named means published side by side. On this rig the canonical literal `mean(T1,T2,T3)` measures −2.5627 C where the as-built air mean measures −8.7083 C — a **3.40×** disagreement. Choosing between them is a project decision, not W07's |

## Not deliverable by W07 software

- **A-W07-02 / A-W07-03**: needs ≥3 valid passive and ≥3 valid cooling-step runs. Today there
  is one session (`boot_id 56044b74`) whose passive, cooling and recovery segments share that
  boot, so they are three phases of one run, not three runs. `independent_session: false` on
  every registry entry, and the validator fails if a segment is ever filed as independent.
- **A-W07-04 repeatability verdict**: `NOT ESTABLISHED` / `CANNOT BE JUDGED` by design. The
  pass criterion — plant variation small enough to separate a deliberate S2 disturbance from
  setup drift — cannot be evaluated with n=1.
- **A-W07-01 freeze**: positions are frozen; mounting method/height/clearance, V1, cable
  routing, door alignment, internal load, conductor marking and the configuration photo are
  not, and no host test can close them.

## Session requirement this week actually needs (S-1)

Three independent passive warm-up runs, TEC never enabled:

- **Independence is by boot, not by window.** Opening the serial port resets the board and
  changes `boot_id`, so a new session must be a new `boot_id`. Three windows inside one boot
  reproduce exactly today's defect.
- **It must be a genuine warm-up, not a stable room baseline.** A chamber already at room
  temperature produces a flat series that can set no band. Each run must start **below** room
  conditions (cold-soaked from a prior cooling step or a door event) and show a monotonic rise
  toward equilibrium, so the measured drift is the parameter `gradient_bound_c_per_min` is
  waiting for. A run that never departs from ambient is a baseline capture and must be logged
  as invalid for A-W07-02, never deleted.
- Minimum 10 minutes of untouched record per run (today's passive segment is 226 samples /
  224.99 s, which is both too short and not a warm-up).
- Invalidators, all logged with reason: any applied duty above 0, any hand-touch, door not
  attested CLOSED, any probe status other than the valid state, a shared `boot_id`.

When those three runs exist, `reset-criterion-v0.yaml` can stop carrying UNRESOLVED numbers
and the gate that depends on it can answer something other than UNKNOWN. Until then no
threshold in this dossier may be quoted as a project limit — including the 31.5 C / 0.50
C/min pair that appears only inside a labelled test injection.
