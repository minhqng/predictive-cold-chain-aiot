"""One-shot read-only acceptance for the live demo XGBoost score.

Calls the SAME production demo functions as the dashboard endpoint, twice on
the same captured current-boot rows, and records the real feature vector,
artifact SHA-256, score, anchor time and boot. It never writes the database,
never registers a model, and never sends a device command.

A stale anchor, missing feature, unavailable database/model, or non-repeatable
score is reported as BLOCKED. No predictive physical accuracy is asserted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND))

from integration.leader_live_inference import (  # noqa: E402
    DEFAULT_FORECAST_DIR, fetch_current_boot_rows, live_prediction, model_metadata, row_from_mapping,
)

DEFAULT_REPORT_DIR = REPO_ROOT / "runtime" / "leader" / "xgb-acceptance"


def _write_report(report: dict, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"xgb-acceptance-{stamp}.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    checks = report.get("checks") or {}
    model = report.get("model") or {}
    lines = [
        "# XGBoost demo acceptance",
        "",
        f"- status: `{report.get('status')}`",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- source: `{report.get('source') or 'n/a'}`",
        f"- model: `{model.get('model_version') or 'n/a'}`",
        f"- artifact SHA-256: `{model.get('artifact_sha256') or 'n/a'}`",
        f"- training class: `{model.get('training_class') or 'n/a'}`",
        f"- release eligibility: `{model.get('release_eligibility') or 'n/a'}`",
        f"- current boot: `{report.get('current_boot') or 'n/a'}`",
        f"- anchor UTC: `{report.get('anchor_utc') or 'n/a'}`",
        f"- frame age: `{report.get('frame_age_s') if report.get('frame_age_s') is not None else 'n/a'} s`",
        f"- feature vector: `{report.get('feature_count') if report.get('feature_count') is not None else 'n/a'}"
        f"/{report.get('feature_total') if report.get('feature_total') is not None else 'n/a'}`",
        f"- missing features: `{', '.join(report.get('missing_features') or []) or 'none'}`",
        f"- score: `{report.get('score')}`",
        f"- feature vector SHA-256: `{report.get('feature_vector_sha256') or 'n/a'}`",
        f"- deterministic repeat: `{checks.get('deterministic_same_vector')}`",
        f"- finite output: `{checks.get('output_finite')}`",
        f"- fresh current data: `{checks.get('anchor_fresh')}`",
        f"- source class REAL_SERIAL: `{checks.get('source_real_serial')}`",
    ]
    if report.get("model_task") == "temperature_forecast":
        lines.extend([
            f"- current chamber mean: `{report.get('current_chamber_mean_c')}` °C",
            f"- predicted delta: `{report.get('predicted_delta_c')}` °C",
            f"- predicted +{report.get('horizon_s')}s: `{report.get('predicted_temperature_c')}` °C",
        ])
    if report.get("error"):
        lines.append(f"- error: `{report['error']}`")
    if report.get("api"):
        lines.append(f"- API cross-check: `{report['api'].get('status')}`")
    lines.extend([
        "",
        "Demo-only, read-only shadow score. Separate from any manual TEC1000",
        "actuation. No field accuracy, calibration, early-warning or",
        "control-causality claim is made.",
    ])
    if report.get("notes"):
        lines.extend(["", "## Notes", ""] + [f"- {note}" for note in report["notes"]])
    md_path = report_dir / f"xgb-acceptance-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot live XGBoost demo acceptance")
    parser.add_argument("--device-id", default=os.environ.get("CG_DEVICE_ID", "coldguard-001"))
    parser.add_argument("--model-dir", default=os.environ.get("COLDGUARD_DEMO_MODEL_DIR", str(DEFAULT_FORECAST_DIR)),
                        help="demo model directory (default: environment or bundled experimental forecast)")
    parser.add_argument("--model-version", default=os.environ.get("COLDGUARD_DEMO_MODEL_VERSION"))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--api-url", default=None,
                        help="optional running dashboard base URL for an API cross-check")
    args = parser.parse_args(argv)

    report_dir = Path(args.report_dir)
    generated = datetime.now(timezone.utc)
    report: dict = {
        "schema": "coldguard.leader.xgb_demo_acceptance.v1",
        "generated_at": generated.isoformat(),
        "device_id": args.device_id,
        "mode": "DEMO_ONLY_SHADOW",
        "actuation": "NOT_PART_OF_THIS_ACCEPTANCE",
        "status": None,
        "notes": [
            "Read-only one-shot; no DB writes, no model registration, no device command.",
            "The model's training class and release eligibility are reported as declared; "
            "no predictive physical accuracy is asserted.",
        ],
    }

    try:
        raw_rows = fetch_current_boot_rows(args.device_id)
    except Exception as exc:  # noqa: BLE001 - report the read-only refusal
        report.update({
            "status": "BLOCKED_DATABASE_UNAVAILABLE",
            "error": type(exc).__name__,
            "checks": {"database_readable": False},
        })
        json_path, md_path = _write_report(report, report_dir)
        print(json.dumps({"status": report["status"], "report": str(json_path),
                          "markdown": str(md_path), "error": type(exc).__name__}, indent=2))
        return 2

    rows = [row_from_mapping(m) for m in raw_rows]
    now = datetime.now(timezone.utc)
    try:
        first = live_prediction(
            args.device_id, args.model_version, args.model_dir,
            rows=rows, now=now, source="REAL_SERIAL")
        second = live_prediction(
            args.device_id, args.model_version, args.model_dir,
            rows=rows, now=now, source="REAL_SERIAL")
    except Exception as exc:  # noqa: BLE001 - report, never fake a pass
        report.update({
            "status": "BLOCKED_SCORER_ERROR",
            "error": type(exc).__name__,
            "checks": {"database_readable": True, "scorer_callable": False},
        })
        json_path, md_path = _write_report(report, report_dir)
        print(json.dumps({"status": report["status"], "report": str(json_path),
                          "markdown": str(md_path), "error": report["error"]}, indent=2))
        return 2

    try:
        model = model_metadata(args.model_dir)
        artifact_sha = hashlib.sha256(
            (Path(model["model_dir"]) / "model.ubj").read_bytes()).hexdigest()
    except Exception as exc:  # noqa: BLE001 - report the refusal, never fake a pass
        report.update({
            "status": "BLOCKED_MODEL_UNAVAILABLE",
            "error": type(exc).__name__,
            "checks": {"database_readable": True, "model_contract_readable": False},
        })
        json_path, md_path = _write_report(report, report_dir)
        print(json.dumps({"status": report["status"], "report": str(json_path),
                          "markdown": str(md_path), "error": report["error"]}, indent=2))
        return 2

    required = model["feature_names"]
    is_forecast = model.get("model_task") == "temperature_forecast"
    score = first.get("score")
    if is_forecast:
        forecast_value = first.get("predicted_temperature_c")
        finite = (isinstance(forecast_value, (int, float))
                  and math.isfinite(forecast_value))
        deterministic = (
            first.get("feature_vector_sha256") == second.get("feature_vector_sha256")
            and first.get("predicted_temperature_c") == second.get("predicted_temperature_c")
            and first.get("predicted_delta_c") == second.get("predicted_delta_c")
            and list(first.get("features") or {}) == required
            and list(second.get("features") or {}) == required
            and first.get("feature_vector_sha256") is not None
        )
        status_ok = first.get("forecast_status") == "OK_EXPERIMENTAL_DEMO"
    else:
        finite = (isinstance(score, (int, float)) and math.isfinite(score)
                  and 0.0 <= score <= 1.0)
        deterministic = (
            first.get("feature_vector_sha256") == second.get("feature_vector_sha256")
            and first.get("score") == second.get("score")
            and list(first.get("features") or {}) == required
            and list(second.get("features") or {}) == required
            and first.get("feature_vector_sha256") is not None
        )
        status_ok = first.get("score_status") == "OK_DEMO_ONLY"
    checks = {
        "database_readable": True,
        "score_status_ok": status_ok,
        "output_finite": finite,
        "deterministic_same_vector": bool(deterministic),
        "anchor_fresh": bool(first.get("fresh")),
        "source_real_serial": first.get("source") == "REAL_SERIAL",
        "artifact_sha_matches_manifest": artifact_sha == model["artifact_sha256"],
        "feature_order_matches_manifest": list(first.get("features") or {}) == required,
        "all_required_features_present": not first.get("missing_features"),
    }
    if is_forecast:
        current = first.get("current_chamber_mean_c")
        delta = first.get("predicted_delta_c")
        predicted = first.get("predicted_temperature_c")
        checks["forecast_equals_current_plus_delta"] = (
            isinstance(current, (int, float)) and isinstance(delta, (int, float))
            and isinstance(predicted, (int, float))
            and abs(predicted - (current + delta)) <= 1e-9)
        checks["forecast_unit_degc"] = first.get("unit") == "degC"
    passed = all(checks.values())
    if passed:
        status = "ACCEPTED_EXPERIMENTAL_DEMO" if is_forecast else "ACCEPTED_DEMO_ONLY"
    elif first.get("score_status") == "BLOCKED_FEATURES_INCOMPLETE":
        status = "BLOCKED_FEATURES_INCOMPLETE"
    elif str(first.get("score_status") or "").startswith("STALE_"):
        status = "BLOCKED_STALE_ANCHOR"
    else:
        raw_status = str(first.get("score_status") or "UNKNOWN")
        status = raw_status if raw_status.startswith("BLOCKED_") else "BLOCKED_" + raw_status

    report.update({
        "status": status,
        "source": first.get("source"),
        "model": {
            "model_dir": model["model_dir"],
            "model_version": model.get("model_version"),
            "artifact_sha256": model.get("artifact_sha256"),
            "artifact_sha256_recomputed": artifact_sha,
            "feature_version": model.get("feature_version"),
            "feature_schema_sha256": model.get("feature_schema_sha256"),
            "training_class": model.get("training_class"),
            "training_data_class": model.get("training_data_class"),
            "release_eligibility": model.get("release_eligibility"),
            "target": model.get("target"),
            "horizon_s": model.get("horizon_s"),
            "horizon_status": model.get("horizon_status"),
            "model_selection": model.get("model_selection"),
            "model_task": model.get("model_task"),
            "objective": model.get("objective"),
            "target_transform": model.get("target_transform"),
            "baseline_feature_id": model.get("baseline_feature_id"),
        },
        "model_task": model.get("model_task"),
        "current_boot": first.get("current_boot"),
        "anchor_utc": first.get("anchor_utc"),
        "anchor_seq": first.get("anchor_seq"),
        "frame_age_s": first.get("frame_age_s"),
        "feature_count": first.get("feature_count"),
        "feature_total": first.get("feature_total"),
        "missing_features": first.get("missing_features"),
        "feature_names_in_order": required,
        "features": first.get("features"),
        "feature_vector_sha256": first.get("feature_vector_sha256"),
        "score": score,
        "score_status": first.get("score_status"),
        "forecast_status": first.get("forecast_status"),
        "unit": first.get("unit"),
        "horizon_s": first.get("horizon_s"),
        "current_chamber_mean_c": first.get("current_chamber_mean_c"),
        "predicted_delta_c": first.get("predicted_delta_c"),
        "predicted_temperature_c": first.get("predicted_temperature_c"),
        "repeat_run": {
            "score": second.get("score"),
            "forecast_status": second.get("forecast_status"),
            "predicted_temperature_c": second.get("predicted_temperature_c"),
            "predicted_delta_c": second.get("predicted_delta_c"),
            "feature_vector_sha256": second.get("feature_vector_sha256"),
            "score_status": second.get("score_status"),
        },
        "checks": checks,
    })
    if args.api_url:
        import urllib.request

        def api_call() -> tuple[int, dict]:
            with urllib.request.urlopen(
                    args.api_url.rstrip("/") + "/api/leader/xgb", timeout=20) as response:
                return response.status, json.loads(response.read())

        try:
            status1, api1 = api_call()
            _status2, api2 = api_call()
            report["api"] = {
                "status": "OK" if status1 == 200 else f"HTTP_{status1}",
                "score": api1.get("score"),
                "repeat_score": api2.get("score"),
                "score_status": api1.get("score_status"),
                "repeat_score_status": api2.get("score_status"),
                "predicted_temperature_c": api1.get("predicted_temperature_c"),
                "repeat_predicted_temperature_c": api2.get("predicted_temperature_c"),
                "feature_vector_sha256": api1.get("feature_vector_sha256"),
                "repeat_feature_vector_sha256": api2.get("feature_vector_sha256"),
                "anchor_utc": api1.get("anchor_utc"),
                "artifact_sha256": api1.get("artifact_sha256"),
                "same_anchor": api1.get("anchor_utc") == first.get("anchor_utc"),
                "repeat_same_anchor": api1.get("anchor_utc") == api2.get("anchor_utc"),
                "repeat_same_score": api1.get("score") == api2.get("score"),
                "repeat_same_vector": (
                    api1.get("feature_vector_sha256") == api2.get("feature_vector_sha256")),
            }
        except Exception as exc:  # noqa: BLE001 - cross-check is evidence, not a gate
            report["api"] = {"status": "UNAVAILABLE", "error": type(exc).__name__}

    json_path, md_path = _write_report(report, report_dir)
    print(json.dumps({
        "status": status,
        "score": score,
        "model_version": model.get("model_version"),
        "artifact_sha256": model.get("artifact_sha256"),
        "feature_vector_sha256": first.get("feature_vector_sha256"),
        "current_boot": first.get("current_boot"),
        "anchor_utc": first.get("anchor_utc"),
        "checks": checks,
        "report": str(json_path),
        "markdown": str(md_path),
    }, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
