"""Owner-owned cross-team path adapters (W01-W13 integration, additive only).

Each adapter composes two immutable member implementations and records the
provenance it was given — never inventing a value no member produced:

- Path 1  A → C   physical telemetry to gateway/backend: exercised by driving
  Member C's real ``serial_gateway.translate``/``pump`` offline over Member A's
  committed harness captures (tests/test_cross_team_paths.py).
- Path 2  C → B   normalized store row → Member B ``Observation`` admission.
  Event time is required: B refuses inferred times, so a clockless row is
  *refused and counted*, never given a manufactured timestamp.
- Path 3  B → D   horizon label records → Member D ``PredictionView``. Member B
  owns no trained model at W13 (no model fitting exists in the package), so the
  mapping is ``ModelHealth.UNAVAILABLE`` with no invented risk score and D's
  own AI-unavailable fallback decides. The owner-frozen horizon set
  (30/60/120/300 s) is the W13 evaluation vocabulary, not a member constant.
- Path 4  A → D   measured door-response envelope → Member D policy input.
  The committed W13 sidecar deliberately does NOT freeze the critical-Tmean
  threshold (``NOT_FROZEN_PENDING_MEMBER_D``); the adapter feeds only the
  measured values and D's own frozen policy thresholds decide.
- Path 5  D → C → A command: ``command_path_runner`` (bridge-integrated).
- Path 6  A → C → D ACK lifecycle: ``command_path_runner`` + Member A's
  ``cg_command_trace`` stage promotion (bridge-integrated).

Import layout mirrors ``backend/scripts/serial_gateway.py``: the checkout root
and ``ml/src``/``control/src`` are added to ``sys.path`` so the committed member
packages are used directly, unmodified.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Mapping
from datetime import datetime
from typing import Any

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_ML_SRC = _ROOT / "ml" / "src"
if _ML_SRC.is_dir() and str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))
_CONTROL_SRC = _ROOT / "control" / "src"
if _CONTROL_SRC.is_dir() and str(_CONTROL_SRC) not in sys.path:
    sys.path.insert(0, str(_CONTROL_SRC))

from coldguard_ml.observations import (  # noqa: E402
    DEVICE_MODES,
    Observation,
)
from coldguard_ml.errors import DataContractError  # noqa: E402
from coldguard_ml.labels import (  # noqa: E402
    LabelRecord,
    LabelSpec,
    generate_label_records,
)
from coldguard_control.types import ModelHealth, QualityState  # noqa: E402

#: Owner-frozen W13 horizon evaluation set (30/60/120/300 s). The member
#: packages deliberately leave the horizon to the caller (``LabelSpec`` is
#: "the values the caller freezes into this spec object"); this set is the
#: W13 evaluation vocabulary and is recorded on every produced label.
W13_HORIZONS_S = (30.0, 60.0, 120.0, 300.0)
W13_SPEC_VERSION = "owner-w13-horizons-v1"

#: A: the S1 encoding carries no device identity; this sentinel is not one.
_NO_DEVICE_ID = "NOT_CARRIED_BY_THIS_ENCODING"


class ObservationAdmissionRefused(ValueError):
    """One normalized row cannot become a Member B observation honestly."""


def normalized_row_to_observation(
    row: Mapping[str, Any],
    *,
    time_source: str = "HOST_STAMP",
) -> Observation:
    """Map one Member C normalized telemetry row to Member B's Observation.

    Refuses (never repairs) rows without a tz-aware event time or without a
    real device identity; the dataset's declared ``time_source`` is kept in the
    caller's provenance, not silently mixed into the row semantics.
    """
    raw_time = row.get("time")
    if not isinstance(raw_time, datetime) or raw_time.tzinfo is None:
        raise ObservationAdmissionRefused(
            f"NO_EVENT_TIME[{row.get('seq')!r}]: time_source={time_source}; "
            "B forbids inferred event times — refusing instead of inventing one"
        )
    device_id = row.get("device_id")
    if not device_id or device_id == _NO_DEVICE_ID:
        raise ObservationAdmissionRefused(
            f"NO_DEVICE_IDENTITY[{row.get('seq')!r}]: the encoding carries no "
            "device identity; a placeholder is not admission identity"
        )

    door_open = row.get("door_open")
    door_status_ok = row.get("door_status") in ("OK", "")
    if door_status_ok and door_open is not None and door_open != "":
        door_state = "OPEN" if str(door_open) in ("1", "1.0", "OPEN") else "CLOSED"
    else:
        door_state = "UNKNOWN"

    for section in ("thermal_quality", "environment_quality", "electrical_quality"):
        if row.get(section) in ("", None):
            raise ObservationAdmissionRefused(
                f"MISSING_SECTION_QUALITY[{row.get('seq')!r}]: {section}; "
                "B's vocabulary has no silent default — refusal over coercion"
            )

    uptime = row.get("uptime_ms")
    uptime_ms = int(uptime) if isinstance(uptime, (int, float)) and not isinstance(uptime, bool) else None
    state = row.get("device_mode") or None
    if state is not None and state not in DEVICE_MODES:
        state = None  # an unmappable lifecycle string is carried as absent

    pwm = row.get("applied_duty")
    applied_duty = float(pwm) if pwm not in ("", None) else None

    return Observation(
        device_id=device_id,
        boot_id=row["boot_id"],
        seq=int(row["seq"]),
        time=raw_time,
        uptime_ms=uptime_ms,
        run_id=row["run_id"],
        t1_c=_or_none(row.get("t1_c")),
        t2_c=_or_none(row.get("t2_c")),
        t3_c=_or_none(row.get("t3_c")),
        t_air_c=_or_none(row.get("t_air_c")),
        rh_pct=_or_none(row.get("rh_pct")),
        door_state=door_state,
        cooling_voltage_v=_or_none(row.get("cooling_voltage_v")),
        cooling_current_a=_or_none(row.get("cooling_current_a")),
        cooling_power_w=_or_none(row.get("cooling_power_w")),
        cooling_energy_counter_wh=_or_none(row.get("cooling_energy_counter_wh")),
        applied_cooling=row["applied_cooling"],
        applied_duty=applied_duty,
        thermal_quality=row["thermal_quality"],
        environment_quality=row["environment_quality"],
        electrical_quality=row["electrical_quality"],
        overall_quality=row["overall_quality"],
        device_mode=state,
        schema_version=1,
        hardware_config_id=row["hardware_config_id"],
        firmware_version=row["firmware_version"],
        calibration_id=row.get("calibration_id"),
        backend_received_at=row.get("backend_received_at"),
    )


def _or_none(value: Any) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def admit_rows(
    raw_rows: list[Mapping[str, Any]], *, time_source: str = "HOST_STAMP"
) -> dict:
    """Adapt and validate rows, classifying every refusal by reason.

    Refusals are the honest C→B answer for clockless/identity-less encodings:
    they are counted, not silently repaired or silently dropped.
    """
    from coldguard_ml.observations import (
        canonical_order,
        deduplicate_by_identity,
        validate_observation,
    )

    admitted: list[Observation] = []
    refused: list[dict] = []
    for row in raw_rows:
        try:
            observation = normalized_row_to_observation(row, time_source=time_source)
            validate_observation(observation)
        except ObservationAdmissionRefused as exc:
            refused.append({"seq": row.get("seq"), "reason_code": str(exc).split(":", 1)[0],
                            "reason": str(exc)})
            continue
        except (DataContractError, KeyError) as exc:
            refused.append({"seq": row.get("seq"), "reason_code": "B_REFUSED",
                            "reason": str(exc)})
            continue
        admitted.append(observation)
    ordering = canonical_order(admitted)
    deduped = deduplicate_by_identity(admitted)
    return {
        "admitted": admitted,
        "refused": refused,
        "canonical_count": len(ordering),
        "deduplicated_count": len(deduped),
        "refused_by_reason": {
            code: sum(1 for r in refused if r["reason_code"] == code)
            for code in sorted({r["reason_code"] for r in refused})
        },
        "time_source": time_source,
    }


def owner_horizon_specs() -> tuple[LabelSpec, ...]:
    """The owner-frozen W13 horizon set as Member B ``LabelSpec`` objects."""
    return tuple(
        LabelSpec(horizon_s=h, spec_version=W13_SPEC_VERSION) for h in W13_HORIZONS_S
    )


def labels_at_horizons(
    anchors, series, coverage_end: datetime | None = None
) -> dict[float, list[dict]]:
    """Evaluate y_t(H) with Member B's real label machinery at W13 horizons.

    Anchors and the critical-event series come from the caller (data-owned).
    No label verdict is invented here: statuses are Member B's
    (EVALUABLE / CENSORED / UNTRUSTED_INFO).
    """
    out: dict[float, list[dict]] = {}
    for spec in owner_horizon_specs():
        records: tuple[LabelRecord, ...] = generate_label_records(
            series.run_id,
            anchors,
            series,
            spec,
            coverage_end=coverage_end,
        )
        out[spec.horizon_s] = [
            {
                "status": record.status.value,
                "y": record.y,
                "prediction_time": record.prediction_time.isoformat(),
                "matched_event": None
                if record.matched_event is None
                else {"time": record.matched_event.time.isoformat(),
                      "trusted": record.matched_event.trusted},
            }
            for record in records
        ]
    return out


def label_records_to_prediction_view(series_run_id: str, horizon_s: float) -> dict:
    """Member B's W13-honest model statement as Member D ``PredictionView`` input.

    Member B owns no trained model at W13 (no model fitting exists in
    ``coldguard_ml``), so the only honest predictive hand-off is explicit
    unavailability with the frozen horizon recorded — never an invented risk
    score. Member D's AI-unavailable fallback is the deciding semantics.
    """
    if horizon_s not in W13_HORIZONS_S:
        raise ValueError(f"horizon {horizon_s!r} is not in the W13 frozen set")
    return {
        "health": ModelHealth.UNAVAILABLE,
        "model_version": "NONE_MEMBER_B_W13",
        "feature_version": "NONE_MEMBER_B_W13",
        "risk_score": None,
        "age_s": None,
        "horizon_s": horizon_s,
        "above_preemptive_s": None,
        "series_run_id": series_run_id,
    }


def door_critical_sidecar_to_policy_views(sidecar: Mapping[str, Any]) -> list[dict]:
    """Map the committed W13 door-critical sidecar to Member D policy inputs.

    Only measured values move (``tmean_min/max``, ``baseline_mean_c_30s``,
    final ``tmean``), each marked ``replay``: the measurement keeps its
    capture-time validity and is never presented as live freshness. The
    sidecar's ``critical_tmean_c`` is
    ``NOT_FROZEN_PENDING_MEMBER_D`` — Member D's frozen policy thresholds do
    the deciding, exactly as the sidecar requires.
    """
    if sidecar.get("critical_tmean_status") != "NOT_FROZEN_PENDING_MEMBER_D":
        raise ValueError(
            "sidecar critical-Tmean freeze state changed; re-review this "
            f"adapter before reuse: {sidecar.get('critical_tmean_status')!r}"
        )
    views: list[dict] = []
    for run_tag, envelope in sorted(sidecar["per_run_envelope"].items()):
        final_tmean = envelope.get("final_tmean_c")
        if final_tmean is None:
            continue
        views.append({
            "run_tag": run_tag,
            "replay": True,  # evaluated capture evidence, never a live reading
            "thermal": {
                "quality": QualityState.VALID,
                "t_representative_c": final_tmean,
                "age_s": 0.0,
            },
            "baseline_mean_c_30s": envelope.get("baseline_mean_c_30s"),
            "tmean_max_c": envelope.get("tmean_max_c"),
            "frames": envelope.get("frames"),
            "first_sustained_rise_0p125C_delay_s":
                envelope.get("first_sustained_rise_0p125C_delay_s"),
        })
    return views


# ---------------------------------------------------------------------------
# Path 3 closure (Phase 2B): the committed 18-run / 9,293-frame physical
# dataset through Member B's real pipeline order (admit -> split -> windows
# -> labels, LRK-02) with the honest W13 ground-truth verdict, mapped into
# Member D's PredictionView. No value is invented at any step.
# ---------------------------------------------------------------------------

DATASET_ROOT = _ROOT / "evidence" / "A" / "SOURCES" / "20261107" / "datasets"
RUN_INDEX_CSV = DATASET_ROOT / "run_index.csv"
#: The single physically characterized rig of the committed evidence chain
#: (hardware_config_id CG-HW-001); caller-supplied, recorded as provenance.
ACCEPTED_RIG_DEVICE_ID = "coldguard-001"
CLOSURE_SEED = 20261110
#: Observational capture runs: no controller was in the loop (W10 horizon
#: sidecar: "no controller in the loop and no S2 capture").
OBSERVATIONAL_CONTROLLER_ID = "REACTIVE"


def load_accepted_runs() -> list[dict]:
    """Load the verified accepted runs from the committed dataset run index.

    Only ``DATASET_ACCEPTED_*`` classifications are admitted-run candidates;
    each run's committed SHA-256 is re-verified against the CSV bytes before
    the run is returned. A mismatch raises — stale data is never silently
    processed.
    """
    import csv
    import hashlib

    runs: list[dict] = []
    with RUN_INDEX_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row["classification"].startswith("DATASET_ACCEPTED_"):
                continue
            csv_path = DATASET_ROOT / "datasets" / f"{row['run_tag']}-normalized.csv"
            digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            if digest != row["dataset_sha256"]:
                raise ValueError(
                    f"DATASET_HASH_MISMATCH: {csv_path.name} sha256 {digest} "
                    f"!= committed {row['dataset_sha256']}"
                )
            runs.append({
                "run_tag": row["run_tag"],
                "scenario": row["scenario"],
                "classification": row["classification"],
                "boot_id": row["boot_id"],
                "timebase": row["timebase"],
                "device_timestamp_utc_source": row["device_timestamp_utc_source"],
                "hardware_config_id": row["hardware_config_id"],
                "frames": int(row["frames"]),
                "csv_path": csv_path,
                "dataset_sha256": row["dataset_sha256"],
            })
    if not runs:
        raise ValueError("NO_ACCEPTED_RUNS: the committed run index lists none")
    return runs


def run_csv_to_c_rows(csv_path: pathlib.Path, run_tag: str) -> list[dict]:
    """Map one committed normalized export onto Member C's normalized row shape.

    Declared provenance carried on every row: ``time`` is the dataset's
    HOST_STAMP axis (the device has no wall clock —
    ``device_timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK``), a genuinely
    declared timebase that is NOT a device-verified EVENT_UTC; downstream
    consumers keep seeing that caveat through ``admit_rows``/the sidecar.
    """
    import csv
    from datetime import datetime as _dt

    rows: list[dict] = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            time = _dt.fromisoformat(r["host_time_utc"])
            if time.tzinfo is None:
                raise ObservationAdmissionRefused(
                    f"NAIVE_HOST_STAMP[{r['seq']!r}]: the committed export "
                    "carries a naive host stamp; refusing rather than guessing UTC"
                )
            pwm = r["pwm_applied_permille"]
            rows.append({
                "seq": int(r["seq"]),
                "run_id": run_tag,
                "device_id": ACCEPTED_RIG_DEVICE_ID,
                "boot_id": r["boot_id"],
                "time": time,
                "uptime_ms": int(float(r["uptime_ms"])),
                "t1_c": r["t1_c"], "t2_c": r["t2_c"], "t3_c": r["t3_c"],
                "t_air_c": r["air_c_reported"], "rh_pct": r["rh_pct"],
                "door_open": r["door_open"], "door_status": r["door_status"],
                "thermal_quality": r["quality"] if r["t1_status"] == "OK" else "INVALID",
                "environment_quality": "INVALID",
                "electrical_quality": "VALID" if r["current_status"] == "OK" else "INVALID",
                "overall_quality": r["quality"],
                "device_mode": r["state"] or None,
                "applied_cooling": r["tec_state"],
                "applied_duty": (float(pwm) / 1000.0) if pwm else None,
                "cooling_voltage_v": r["voltage_v"],
                "cooling_current_a": r["current_a"],
                "cooling_power_w": r["power_w"],
                "cooling_energy_counter_wh": r["energy_wh"],
                "hardware_config_id": r["hardware_config_id"],
                "firmware_version": r["firmware_version"],
                "calibration_id": None,
            })
    return rows


def unattested_door_series(run_id: str, admitted: list) -> tuple[Any, dict] | None:
    """Build the honest critical-state series for one run, or refuse.

    The committed W10 semantics mark door transitions
    ``REPORTED_BY_FRAME_ONLY_NOT_PHYSICALLY_NAMED``: present but physically
    unattested, so every event stays ``trusted=False``. The critical-Tmean
    threshold is NOT_FROZEN_PENDING_MEMBER_D, which means the *decidable*
    critical-state coverage of the run is unknown — so ``coverage_end`` is
    deliberately left undeclared: Member B's own label evaluator refuses
    (LabelError: "label coverage is unknown") instead of emitting a
    fabricated y=0. Refusing here is the closure, not a gap.
    """
    from coldguard_ml.labels import CriticalEvent, CriticalEventSeries

    # Only OPEN rows carry the (framing-only) door claim; Member B's closed
    # vocabulary (`DOOR_STATES`) leaves CLOSED as a rest state and UNKNOWN as
    # a refusal, so neither may enter an unattested critical state series.
    door_events = [o for o in admitted if o.door_state == "OPEN"]
    if not door_events:
        return None, {
            "run_id": run_id,
            "verdict": "NO_CRITICAL_STATE_INFO",
            "note": "no unattested door/critical-state events in the run",
        }
    events = tuple(
        CriticalEvent(time=o.time, trusted=False, ref=f"{o.boot_id}:{o.seq}")
        for o in door_events
    )
    series = CriticalEventSeries(
        run_id=run_id,
        events=events,
        series_id=f"committed-{run_id}-door-unattested",
        coverage_end=None,  # unfrozen threshold -> decidable coverage unknown
    )
    return series, {
        "run_id": run_id,
        "verdict": "GROUND_TRUTH_UNKNOWN",
        "unattested_events": len(events),
        "note": (
            "series carries only untrusted (framing-only) door transitions; "
            "critical-Tmean threshold is NOT_FROZEN_PENDING_MEMBER_D so "
            "decidable coverage is unknown"
        ),
    }


def evaluate_b_to_d_closure(*, seed: int = CLOSURE_SEED) -> dict:
    """Run the canonical Member B order over the committed accepted dataset.

    admit (B validator) → grouped split (LRK-02 leakage order, deterministic
    seed) → windows (B's causal generator) → per-horizon label verdicts with
    the honest ground-truth gate → Member D PredictionView mapping. Nothing
    here is a model fit or a prediction: it is the executable data-dependency
    closure for W13, with every unavailable input kept honestly unavailable.
    """
    from coldguard_ml.labels import LabelError, labels_and_windows
    from coldguard_ml.observations import deduplicate_by_identity
    from coldguard_ml.splitting import (
        PARTITIONS,
        RunInfo,
        SplitConfig,
        SplitProportions,
        split_runs,
    )
    from coldguard_ml.windows import WindowConfig, generate_windows

    runs = load_accepted_runs()
    admitted_by_run: dict[str, list] = {}
    admission_rows: list[dict] = []
    all_admitted: list = []
    for run in runs:
        c_rows = run_csv_to_c_rows(run["csv_path"], run["run_tag"])
        report = admit_rows(
            c_rows,
            time_source=run["timebase"],
        )
        admitted_by_run[run["run_tag"]] = report["admitted"]
        all_admitted.extend(report["admitted"])
        admission_rows.append({
            "run_tag": run["run_tag"],
            "classification": run["classification"],
            "boot_id": run["boot_id"],
            "timebase": run["timebase"],
            "event_time_trust": "HOST_STAMP_DECLARED_NOT_DEVICE_VERIFIED",
            "rows": len(c_rows),
            "admitted": len(report["admitted"]),
            "deduplicated": report["deduplicated_count"],
            "refused": len(report["refused"]),
            "refused_by_reason": report["refused_by_reason"],
            "sha256_verified": True,
        })

    # Deterministic grouped split; every accepted run is one observational
    # group (no pair lineage is committed for them, LRK-08/03 §47).
    run_infos = [
        RunInfo(
            run_id=run["run_tag"],
            scenario_id=run["scenario"],
            controller_id=OBSERVATIONAL_CONTROLLER_ID,
            hardware_config_id=run["hardware_config_id"],
        )
        for run in runs
    ]
    split = split_runs(
        run_infos,
        SplitConfig(
            proportions=SplitProportions(train=1 / 3, validation=1 / 3, test=1 / 3),
            seed=seed,
            controller_context="observational-capture-no-controller-in-loop",
            hardware_lineage=runs[0]["hardware_config_id"],
            min_groups_per_partition=3,
        ),
    )

    horizon_specs = owner_horizon_specs()
    per_run_labels: dict[str, dict] = {}
    window_counts: dict[str, int] = {}
    for partition in PARTITIONS:
        partition_rows = [
            o for o in all_admitted if split.partition_of(o.run_id) == partition
        ]
        windows = generate_windows(partition_rows, split, partition, WindowConfig())
        window_counts[partition] = len(windows)
        for run_tag in split.runs_in(partition):
            admitted = admitted_by_run[run_tag]
            series, series_verdict = unattested_door_series(run_tag, admitted)
            run_labels: dict[float, dict] = {}
            for spec in horizon_specs:
                if series is None:
                    run_labels[spec.horizon_s] = {
                        "verdict": series_verdict["verdict"],
                        "windows_labeled": 0,
                    }
                    continue
                run_windows = [w for w in windows if w.run_id == run_tag]
                try:
                    pairs = labels_and_windows(
                        run_windows,
                        {run_tag: series},
                        spec,
                        # coverage declared unknown -> B must refuse labels
                        coverage_ends={},
                    )
                    statuses: dict[str, int] = {}
                    for _, record in pairs:
                        statuses[record.status.value] = (
                            statuses.get(record.status.value, 0) + 1
                        )
                    run_labels[spec.horizon_s] = {
                        "verdict": "EVALUATED",
                        "windows_labeled": len(pairs),
                        "statuses": statuses,
                        "positive_labels": sum(1 for _, r in pairs if r.y == 1),
                    }
                except LabelError as exc:
                    run_labels[spec.horizon_s] = {
                        "verdict": "REFUSED_GROUND_TRUTH_UNKNOWN",
                        "windows_labeled": 0,
                        "reason": str(exc),
                    }
            previous = per_run_labels.setdefault(run_tag, {})
            previous.update(run_labels)

    # Member D receives one PredictionView per frozen horizon: honest
    # unavailability (B owns no model at W13), never an invented score.
    d_views = {
        h: label_records_to_prediction_view("committed-dataset", h)
        for h in W13_HORIZONS_S
    }
    return {
        "closure": "B->D W13 data-dependency closure (Phase 2B)",
        "seed": seed,
        "runs": admission_rows,
        "totals": {
            "runs": len(runs),
            "admitted": len(deduplicate_by_identity(all_admitted)),
            "windows": dict(window_counts),
        },
        "split": split.to_manifest_dict(
            "owner-w01-w13-closure-split",
            dataset_id="committed-20261107-accepted",
            created_at=None,  # a sidecar stamps its own provenance, not a data time
            created_by="owner",
            status="draft",
        ),
        "labels": per_run_labels,
        "prediction_views": d_views,
        "honesty": [
            "no critical-Tmean threshold is frozen; D decides",
            "every event in a constructed series is trusted=False",
            "B refused label evaluation where decidable coverage is unknown",
            "no y=1 label exists in this closure; none was fabricated",
            "HOST_STAMP is a declared dataset timebase, not device EVENT_UTC",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write the deterministic B→D closure sidecar report."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    parser.add_argument("--seed", type=int, default=CLOSURE_SEED)
    args = parser.parse_args(argv)
    report = evaluate_b_to_d_closure(seed=args.seed)
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
