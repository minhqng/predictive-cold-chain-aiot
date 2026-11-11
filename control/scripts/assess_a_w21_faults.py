"""Cross-check A-W21 on-device fault evidence against D's W10 oracles."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


CONTROL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROL_ROOT / "src"))

from coldguard_control.faults import (  # noqa: E402
    InjectionVerdict,
    check_injection,
    get_protocol,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path, root: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}


def assess(root: Path) -> dict[str, object]:
    manifest_path = root / "evidence/A/W21/fault-injection-session-20261108/manifest.json"
    sensor_path = root / "evidence/A/W21/results/A-W21-02.json"
    pzem_path = root / "evidence/A/W21/results/A-W21-03.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sensor = json.loads(sensor_path.read_text(encoding="utf-8"))
    pzem = json.loads(pzem_path.read_text(encoding="utf-8"))

    if manifest.get("evidence_mode") != "ON_DEVICE_SOFTWARE_INJECTION":
        raise ValueError("A-W21 evidence mode changed; reassess manually")
    if sensor.get("outcome") != "PASS" or pzem.get("outcome") != "PASS":
        raise ValueError("A-W21 source result is not PASS; reassess manually")
    if manifest["raw_log_sha256"] not in sensor["notes"]:
        raise ValueError("A-W21-02 raw-log lineage mismatch")
    if manifest["raw_log_sha256"] not in pzem["notes"]:
        raise ValueError("A-W21-03 raw-log lineage mismatch")

    sensor_check = check_injection("SENSOR-DEGRADED", "SW-SENSOR-ROLE-INVALID")
    pzem_check = check_injection("PZEM-UNAVAILABLE", "SW-PZEM-TRANSPORT-DISABLE")
    if sensor_check.verdict is not InjectionVerdict.PROTOCOL_ALLOWED:
        raise ValueError("D sensor protocol does not admit A-W21-02 technique")
    if pzem_check.verdict is not InjectionVerdict.PROTOCOL_ALLOWED:
        raise ValueError("D PZEM protocol does not admit A-W21-03 technique")

    sensor_measurements = sensor["measurements"]
    sensor_match = (
        sensor_measurements["thermal_invalid_frames"] > 0
        and sensor_measurements["recovery_valid_frames"] > 0
        and sensor_measurements["invalid_roles"] == ["T1"]
        and sensor_measurements["cooling_on_frames"] == 0
    )
    pzem_measurements = pzem["measurements"]
    pzem_match = (
        pzem_measurements["electrical_invalid_frames"] > 0
        and pzem_measurements["current_none_frames"] > 0
        and pzem_measurements["recovery_valid_frames"] > 0
        and pzem_measurements["cooling_on_frames"] == 0
    )
    if not sensor_match or not pzem_match:
        raise ValueError("A-W21 observations no longer match the D source oracle")

    cases = []
    for protocol_id, technique_id, result, observed in (
        (
            "SENSOR-DEGRADED",
            "SW-SENSOR-ROLE-INVALID",
            sensor,
            {
                "invalid_roles": sensor_measurements["invalid_roles"],
                "thermal_invalid_frames": sensor_measurements["thermal_invalid_frames"],
                "recovery_valid_frames": sensor_measurements["recovery_valid_frames"],
                "cooling_on_frames": sensor_measurements["cooling_on_frames"],
            },
        ),
        (
            "PZEM-UNAVAILABLE",
            "SW-PZEM-TRANSPORT-DISABLE",
            pzem,
            {
                "electrical_invalid_frames": pzem_measurements["electrical_invalid_frames"],
                "current_none_frames": pzem_measurements["current_none_frames"],
                "recovery_valid_frames": pzem_measurements["recovery_valid_frames"],
                "cooling_on_frames": pzem_measurements["cooling_on_frames"],
            },
        ),
    ):
        protocol = get_protocol(protocol_id)
        cases.append(
            {
                "source_test_id": result["test_id"],
                "protocol_id": protocol_id,
                "fault_id": protocol.fault_id,
                "technique_id": technique_id,
                "source_outcome": result["outcome"],
                "observed": observed,
                "expected_state": protocol.oracle.expected_state,
                "expected_policy": protocol.oracle.expected_policy,
                "expected_event": protocol.oracle.expected_event,
                "source_oracle_verdict": "MATCHED_NON_ENERGIZED_SOURCE_CASE",
            }
        )

    return {
        "scope": "D_W10_READ_ONLY_A_W21_ORACLE_CROSSCHECK",
        "sources": [
            _source(manifest_path, root),
            _source(sensor_path, root),
            _source(pzem_path, root),
        ],
        "device_identity": manifest["identity"],
        "evidence_mode": manifest["evidence_mode"],
        "raw_log_sha256": manifest["raw_log_sha256"],
        "cases": cases,
        "aggregate": "2_SOURCE_CASES_MATCH_D_ORACLES",
        "physical_enablement": False,
        "remaining": [
            "runtime D diagnosis events were not captured",
            "C persistence of reason/evidence window/incident state is absent",
            "output stage was disabled and fuse removed, so energized fail-safe is unproven",
            "S4 electrical-response-missing, thermal-ineffective and unexpected-current-while-OFF cases remain open",
        ],
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = assess(root)
    target = root / "evidence/D/W10/a-w21-oracle-crosscheck.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
