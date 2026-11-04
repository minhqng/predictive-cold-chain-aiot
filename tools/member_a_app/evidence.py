"""Evidence store: raw lines, per-test results, attachments and reports.

Raw device lines are written before any derived value, and derived results
live in separate files. Every copied attachment is hashed so the report can
name the exact bytes it accepted.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import threading
import uuid
from typing import Any, Iterable

from .model import Outcome, TestDefinition, TestResult, now_iso

APP_VERSION = "1.0.0"
SESSION_SCHEMA = 1
_SAFE_ID_RE = re.compile(r"^A-W[0-9]{2}-[0-9]{2}$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_ALLOWED_PASS_SOURCES = {
    "HARDWARE",
    "DOCUMENTARY",
    "OPERATOR_MEASUREMENT",
    "DERIVED",
    "TEAM_EVIDENCE",
}


class EvidenceError(RuntimeError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, pathlib.Path):
        return str(value)
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _write_json_atomic(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class SessionStore:
    def __init__(self, root: pathlib.Path | str, operator: str = "", create: bool = True):
        self.root = pathlib.Path(root)
        self._lock = threading.RLock()
        self._raw_lock = threading.Lock()
        self.session_file = self.root / "session.json"
        self.raw_dir = self.root / "raw"
        self.results_dir = self.root / "results"
        self.measure_dir = self.root / "measurements"
        self.attach_dir = self.root / "attachments"
        existing = _read_json(self.session_file, None)
        if existing is None:
            if not create:
                raise EvidenceError(f"no session at {self.root}")
            self.root.mkdir(parents=True, exist_ok=True)
            for folder in (self.raw_dir, self.results_dir, self.measure_dir, self.attach_dir):
                folder.mkdir(parents=True, exist_ok=True)
            self.session = {
                "schema": SESSION_SCHEMA,
                "app_version": APP_VERSION,
                "session_id": _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "operator": operator,
                "device_identity": {},
                "port": None,
                "firmware_kind": None,
                "results": {},
                "config": {},
            }
            self._save_session()
        else:
            self.session = existing
            for folder in (self.raw_dir, self.results_dir, self.measure_dir, self.attach_dir):
                folder.mkdir(parents=True, exist_ok=True)
        self._raw_handle = (self.raw_dir / "serial.jsonl").open("a", encoding="utf-8")
        self._telemetry_handle = (self.raw_dir / "telemetry.jsonl").open("a", encoding="utf-8")

    @property
    def session_id(self) -> str:
        return str(self.session.get("session_id", "unknown"))

    @property
    def operator(self) -> str:
        return str(self.session.get("operator", ""))

    def set_operator(self, operator: str) -> None:
        with self._lock:
            self.session["operator"] = operator
            self._save_session()

    def set_device(self, port: str | None, identity: dict[str, Any], firmware_kind: str | None) -> None:
        with self._lock:
            self.session["port"] = port
            self.session["device_identity"] = _jsonable(identity)
            self.session["firmware_kind"] = firmware_kind
            self._save_session()

    def set_config(self, key: str, value: Any) -> None:
        with self._lock:
            self.session.setdefault("config", {})[key] = _jsonable(value)
            self._save_session()

    def config(self, key: str, default: Any = None) -> Any:
        return self.session.get("config", {}).get(key, default)

    def _save_session(self) -> None:
        with self._lock:
            self.session["updated_at"] = now_iso()
            _write_json_atomic(self.session_file, self.session)

    def close(self) -> None:
        for handle in (self._raw_handle, self._telemetry_handle):
            try:
                handle.flush()
                handle.close()
            except Exception:
                pass

    def append_raw(self, direction: str, text: str, host_time: str | None = None) -> None:
        record = {
            "host_time": host_time or now_iso(),
            "direction": direction,
            "line": text.rstrip("\r\n"),
        }
        with self._raw_lock:
            self._raw_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._raw_handle.flush()

    def append_telemetry(self, frame: Any) -> None:
        record = {
            "host_time": frame.host_time.isoformat() if hasattr(frame.host_time, "isoformat") else str(frame.host_time),
            "kind": frame.kind,
            "schema": frame.schema,
            "device_id": frame.device_id,
            "boot_id": frame.boot_id,
            "seq": frame.seq,
            "uptime_ms": frame.uptime_ms,
            "t": frame.t,
            "chamber_c": frame.chamber_c,
            "hot_side_c": frame.hot_side_c,
            "ambient_c": frame.ambient_c,
            "humidity_pct": frame.humidity_pct,
            "door_open": frame.door_open,
            "voltage_v": frame.voltage_v,
            "current_a": frame.current_a,
            "power_w": frame.power_w,
            "pwm_duty": frame.pwm_duty,
            "pwm_applied": frame.pwm_applied,
            "state": frame.state,
            "quality": frame.quality,
            "cooling_applied": frame.cooling_applied,
            "warnings": list(frame.warnings),
            "raw": frame.raw,
        }
        with self._raw_lock:
            self._telemetry_handle.write(
                json.dumps(_jsonable(record), ensure_ascii=False) + "\n")
            self._telemetry_handle.flush()
    def results(self) -> dict[str, TestResult]:
        out: dict[str, TestResult] = {}
        for path in sorted(self.results_dir.glob("*.json")):
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                continue
            try:
                result = TestResult.from_dict(payload)
            except (TypeError, ValueError):
                continue
            out[result.test_id] = result
        return out

    def result(self, test_id: str) -> TestResult | None:
        return self.results().get(test_id)

    def record_result(self, result: TestResult) -> None:
        if not _SAFE_ID_RE.match(result.test_id):
            raise EvidenceError(f"refusing result for non-canonical id {result.test_id!r}")
        if result.outcome is Outcome.PASS and result.source not in _ALLOWED_PASS_SOURCES:
            raise EvidenceError(
                f"{result.test_id}: a {result.source} result may not be reported as PASS"
            )
        with self._lock:
            target = self.results_dir / f"{result.test_id}.json"
            if target.exists():
                history = self.results_dir / "history"
                history.mkdir(parents=True, exist_ok=True)
                stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                target.replace(history / f"{result.test_id}-{stamp}.json")
            _write_json_atomic(target, result.to_dict())
            self.session.setdefault("results", {})[result.test_id] = {
                "outcome": result.outcome.value,
                "ended_at": result.ended_at,
                "failure_reason": result.failure_reason,
                "source": result.source,
            }
            self._save_session()

    def attempt_count(self, test_id: str) -> int:
        current = 1 if (self.results_dir / f"{test_id}.json").is_file() else 0
        history = self.results_dir / "history"
        archived = len(list(history.glob(f"{test_id}-*.json"))) if history.is_dir() else 0
        return current + archived

    def save_measurements(self, test_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not _SAFE_ID_RE.match(test_id):
            raise EvidenceError(f"bad test id {test_id!r}")
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = self.measure_dir / f"{test_id}-{stamp}-{uuid.uuid4().hex[:6]}.json"
        _write_json_atomic(path, payload)
        return {"original": test_id, "stored": str(path.relative_to(self.root)),
                "path": str(path), "sha256": sha256_file(path),
                "size": path.stat().st_size, "captured_at": now_iso()}

    def update_measurements(self, record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        stored = record.get("stored")
        if not stored:
            raise EvidenceError("measurement record has no stored path")
        path = self.root / stored
        _write_json_atomic(path, payload)
        record["sha256"] = sha256_file(path)
        record["size"] = path.stat().st_size
        record["captured_at"] = now_iso()
        return record

    def attach(self, test_id: str, source: str | pathlib.Path) -> dict[str, Any]:
        if not _SAFE_ID_RE.match(test_id):
            raise EvidenceError(f"bad test id {test_id!r}")
        src = pathlib.Path(source)
        if not src.is_file():
            raise EvidenceError(f"evidence file not found: {src}")
        if src.stat().st_size == 0:
            raise EvidenceError(f"evidence file is empty: {src}")
        digest = sha256_file(src)
        safe_name = _SAFE_NAME_RE.sub("_", src.name)[:120] or "evidence"
        folder = self.attach_dir / test_id
        folder.mkdir(parents=True, exist_ok=True)
        stored = folder / f"{digest[:12]}-{safe_name}"
        if not stored.exists():
            shutil.copy2(src, stored)
        return {
            "original": str(src),
            "stored": str(stored.relative_to(self.root)),
            "sha256": digest,
            "size": stored.stat().st_size,
            "captured_at": now_iso(),
        }

    def verify_attachments(self) -> list[dict[str, Any]]:
        problems: list[dict[str, Any]] = []
        for result in self.results().values():
            for item in result.evidence:
                stored = item.get("stored")
                expected = item.get("sha256")
                if not stored or not expected:
                    problems.append({"test_id": result.test_id,
                                     "path": str(item.get("stored") or item.get("original")),
                                     "problem": "MALFORMED_RECORD"})
                    continue
                path = self.root / stored
                if not path.is_file():
                    problems.append({"test_id": result.test_id, "path": stored,
                                     "problem": "MISSING"})
                    continue
                actual = sha256_file(path)
                if actual != expected:
                    problems.append({"test_id": result.test_id, "path": stored,
                                     "problem": "HASH_MISMATCH", "expected": expected,
                                     "actual": actual})
        return problems

    def session_digest(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.name.endswith(".tmp"):
                continue
            if path.name.startswith("acceptance-report") or path.name == "telemetry.csv":
                continue
            digest.update(str(path.relative_to(self.root)).encode("utf-8"))
            digest.update(sha256_file(path).encode("ascii"))
        return digest.hexdigest()

    def export_telemetry_csv(self, folder: pathlib.Path | None = None) -> dict[str, Any]:
        import csv
        target = (folder or self.root) / "telemetry.csv"
        rows: list[dict[str, Any]] = []
        source = self.raw_dir / "telemetry.jsonl"
        if source.is_file():
            for line in source.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                temps = record.get("t") or {}
                rows.append({
                    "host_time": record.get("host_time"),
                    "kind": record.get("kind"),
                    "schema": record.get("schema"),
                    "device_id": record.get("device_id"),
                    "boot_id": record.get("boot_id"),
                    "seq": record.get("seq"),
                    "uptime_ms": record.get("uptime_ms"),
                    "t1_c": temps.get("T1"),
                    "t2_c": temps.get("T2"),
                    "t3_c": temps.get("T3"),
                    "spare_c": temps.get("SPARE"),
                    "chamber_c": record.get("chamber_c"),
                    "hot_side_c": record.get("hot_side_c"),
                    "ambient_c": record.get("ambient_c"),
                    "humidity_pct": record.get("humidity_pct"),
                    "door_open": record.get("door_open"),
                    "voltage_v": record.get("voltage_v"),
                    "current_a": record.get("current_a"),
                    "power_w": record.get("power_w"),
                    "pwm_duty": record.get("pwm_duty"),
                    "pwm_applied": record.get("pwm_applied"),
                    "state": record.get("state"),
                    "quality": record.get("quality"),
                    "cooling_applied": record.get("cooling_applied"),
                    "warnings": ";".join(record.get("warnings") or []),
                    "raw": record.get("raw"),
                })
        fieldnames = list(rows[0].keys()) if rows else ["host_time", "kind", "raw"]
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return {"path": str(target), "rows": len(rows), "sha256": sha256_file(target)}

    def export_report(self, definitions: Iterable[TestDefinition],
                      target: pathlib.Path | None = None) -> dict[str, str]:
        defs = sorted(definitions, key=lambda item: item.test_id)
        results = self.results()
        rows = []
        counts = {outcome.value: 0 for outcome in Outcome}
        for definition in defs:
            result = results.get(definition.test_id)
            outcome = result.outcome.value if result else Outcome.NOT_RUN.value
            counts[outcome] = counts.get(outcome, 0) + 1
            checks = result.checks if result else []
            rows.append({
                "test_id": definition.test_id,
                "week": definition.week,
                "title": definition.title,
                "mode": definition.mode.value,
                "safety": definition.safety.value,
                "outcome": outcome,
                "failure_reason": result.failure_reason if result else "",
                "checks_passed": sum(1 for item in checks if item.passed),
                "checks_total": len(checks),
                "evidence_count": len(result.evidence) if result else 0,
                "attempts": self.attempt_count(definition.test_id),
                "source": result.source if result else "",
                "started_at": result.started_at if result else "",
                "ended_at": result.ended_at if result else "",
                "criterion": definition.criterion,
            })

        folder = self.root
        if target is not None:
            folder = pathlib.Path(target)
            folder.mkdir(parents=True, exist_ok=True)
        json_path = folder / "acceptance-report.json"
        csv_path = folder / "acceptance-report.csv"
        md_path = folder / "acceptance-report.md"
        verification = self.verify_attachments()
        payload = {
            "schema": 1,
            "app_version": APP_VERSION,
            "session_id": self.session_id,
            "generated_at": now_iso(),
            "operator": self.operator,
            "device_identity": self.session.get("device_identity", {}),
            "firmware_kind": self.session.get("firmware_kind"),
            "coverage": {"canonical": len(defs), "reported": len(rows)},
            "summary": counts,
            "evidence_integrity": {"ok": not verification, "problems": verification},
            "session_digest": self.session_digest(),
            "results": rows,
        }
        _write_json_atomic(json_path, payload)
        import csv
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["test_id"])
            writer.writeheader()
            writer.writerows(rows)
        md_path.write_text(self._markdown(payload), encoding="utf-8")
        return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}

    def _markdown(self, payload: dict[str, Any]) -> str:
        counts = payload["summary"]
        lines = [
            "# ColdGuard Member A acceptance report",
            "",
            f"- Session: `{payload['session_id']}`",
            f"- Generated: {payload['generated_at']}",
            f"- App version: {payload['app_version']}",
            f"- Operator: {payload['operator'] or 'UNRECORDED'}",
            f"- Firmware kind: {payload.get('firmware_kind') or 'UNRECORDED'}",
            f"- Hardware: `{payload.get('device_identity', {}).get('hardware_config_id', 'UNRECORDED')}`",
            f"- Session digest: `{payload['session_digest']}`",
            f"- Evidence integrity: {'OK' if payload['evidence_integrity']['ok'] else 'PROBLEMS'}",
            "",
            "## Summary",
            "",
            "| Outcome | Count |",
            "|---|---:|",
        ]
        for outcome in Outcome:
            lines.append(f"| {outcome.value} | {counts.get(outcome.value, 0)} |")
        lines += [
            f"| **Total** | **{payload['coverage']['canonical']}** |",
            "",
        ]
        problems = payload["evidence_integrity"]["problems"]
        if problems:
            lines += ["## Evidence integrity problems", ""]
            for problem in problems:
                lines.append(f"- `{problem['test_id']}` `{problem['path']}`: {problem['problem']}")
            lines.append("")
        lines += [
            "## Requirement results",
            "",
            "| ID | Wk | Requirement | Outcome | Checks | Evidence | Attempts | Reason |",
            "|---|---:|---|---|---|---:|---:|---|",
        ]
        for row in payload["results"]:
            reason = (row["failure_reason"] or "").replace("|", "\\|")
            title = row["title"].replace("|", "\\|")
            lines.append(
                f"| {row['test_id']} | {row['week']} | {title} | {row['outcome']} | "
                f"{row['checks_passed']}/{row['checks_total']} | {row['evidence_count']} | "
                f"{row.get('attempts', 1)} | {reason} |"
            )
        lines += ["", "## Canonical criteria", ""]
        for row in payload["results"]:
            lines.append(f"### {row['test_id']} — {row['title']}")
            lines.append("")
            lines.append(row["criterion"])
            lines.append("")
        return "\n".join(lines) + "\n"
