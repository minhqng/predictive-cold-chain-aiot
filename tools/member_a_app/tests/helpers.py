"""Shared test helpers and deterministic protocol fixtures."""

from __future__ import annotations

import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8").strip()


def _set(line: str, key: str, value: object) -> str:
    return re.sub(rf"(?<![A-Za-z0-9_]){re.escape(key)}=\S+", f"{key}={value}", line)


def telem_line(seq: int = 1, uptime_ms: int = 1_000_000,
               t1: float = 25.0, t2: float = 25.0, t3: float = 25.0,
               spare: float = 25.0, door: int = 0, current: float = 0.0,
               voltage: float = 11.9, power: float | None = None,
               quality: str = "VALID", thermal_quality: str = "VALID",
               output_stage: str = "DISABLED", state: str = "OFF",
               cooling: str = "OFF", boot: str = "abcd0123",
               fault: str = "0x00000000", humidity: float | None = None,
               ambient: float | None = None, supervised: int = 0,
               interlock: str = "ABSENT", bench_policy: str = "NORMAL") -> str:
    line = fixture("telem_schema3.txt")
    line = _set(line, "seq", seq)
    line = _set(line, "uptime_ms", uptime_ms)
    line = _set(line, "elapsed_ms", uptime_ms)
    line = _set(line, "boot_id", boot)
    line = _set(line, "t_inside_c", f"{t1:.4f}")
    line = _set(line, "t_hot_side_c", f"{t2:.4f}")
    line = _set(line, "raw_t1_c", f"{t1:.4f}")
    line = _set(line, "raw_t2_c", f"{t2:.4f}")
    line = _set(line, "raw_t3_c", f"{t3:.4f}")
    line = _set(line, "raw_spare_c", f"{spare:.4f}")
    line = _set(line, "door_open", door)
    line = _set(line, "door_raw", 1 if door else 0)
    line = _set(line, "door_status", "OK")
    line = _set(line, "voltage_v", f"{voltage:.4f}")
    line = _set(line, "current_a", f"{current:.4f}")
    line = _set(line, "power_w", f"{(voltage * current if power is None else power):.4f}")
    line = _set(line, "quality", quality)
    line = _set(line, "thermal_quality", thermal_quality)
    line = _set(line, "output_stage", output_stage)
    line = _set(line, "tec_state", state)
    line = _set(line, "cooling_applied", cooling)
    line = _set(line, "fault_code", fault)
    line = _set(line, "probes_valid", 4)
    line = _set(line, "probes_expected", 4)
    if humidity is not None:
        line = _set(line, "relative_humidity_pct", f"{humidity:.2f}")
        line = _set(line, "relative_humidity_status", "OK")
    if ambient is not None:
        line = _set(line, "t_ambient_c", f"{ambient:.2f}")
        line = _set(line, "t_ambient_status", "OK")
    line += (f" supervised_bench={supervised} supervised_authorized=0"
             f" interlock={interlock} bench_policy={bench_policy}")
    return line


def telemetry_series(count: int = 30, interval_ms: int = 1000,
                     t1: float = 25.0, t2: float = 25.0, t3: float = 25.0,
                     spare: float = 25.0, door: int = 0, current: float = 0.0,
                     **kwargs: object) -> list[str]:
    return [telem_line(seq=index + 1, uptime_ms=1_000_000 + index * interval_ms,
                       t1=t1 + (kwargs.get("t1_step", 0) * index),  # type: ignore[operator]
                       t2=t2, t3=t3, spare=spare, door=door, current=current,
                       **{key: value for key, value in kwargs.items() if key != "t1_step"})
            for index in range(count)]


def boot_lines(boot_id: str = "abcd0123", boot_count: int = 7) -> list[str]:
    return [
        "#CG LOG v=2 fw=cg-w06-0.1.0 hw=CG-HW-001 device=coldguard-001 pin_map=2 grammar=2",
        f"#CG BOOT boot_id={boot_id} boot_count={boot_count}",
        "#CG BOOT event=IDENTITY device_id=coldguard-001 "
        f"boot_id={boot_id} boot_count={boot_count} firmware_version=cg-w06-0.1.0 "
        "hardware_config_id=CG-HW-001 calibration_id=UNRECORDED schema=3 seq_start=1",
    ]


def rom_lines() -> list[str]:
    return [
        "#CG ROM role=T1 rom=287088CA00000051 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING",
        "#CG ROM role=T2 rom=28AEBF2200000006 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING",
        "#CG ROM role=T3 rom=28CBE9CA00000072 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING",
        "#CG ROM role=SPARE rom=283BE5C9000000A9 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING",
    ]


def h8_boot_lines(token: str = "DEADBEEF", boot_id: str = "b45af2ff") -> list[str]:
    return [
        f"#CG H8 BOOT boot_id={boot_id} token={token} schema=3 firmware=h8-bench "
        "test_mode=BENCH_ENDURANCE mandatory_roles=HOT_SIDE "
        "mandatory_probes=T1,T2,T3,T4 supervised=1 reset_cause=USB sim_cooling=0",
        "#CG H8 BOOT_POLICY limits=SHIPPED actuator=REAL physical_output=ENABLED "
        "stages=A:180,B:420,C:600,D:900,E:1800,F:30 pwm=100 check_pwm=20 "
        "interlock=NOT_INSTALLED snapshot_ms=1000 host_ack_timeout_ms=3000 reset_marker=1",
        "#CG H8 BOOT_OFF_CURRENT off_current_limit_a=0.200 off_current_approved=1 "
        "off_current_test_enforce=0",
        "#CG TEC_LIMITS test_mode=BENCH_ENDURANCE operator_approved=1 "
        "simulated_enforcement=0 policy_enabled=1 required_mask=0x4f "
        "required_resolved=1 all_resolved=0 stage_f_guard=1 endurance_stages=0",
    ]


def h8s_line(seq: int = 1, run_id: str = "run-00000000", state: str = "OFF",
             stage: str = "NONE", current: float = 0.0, voltage: float = 11.9,
             power: float | None = None, t1: float = 29.0, t2: float = 30.0,
             t3: float = 29.0, t4: float = 29.0, fault: str = "0x0",
             pwm: int = 0, fan: str = "UNCONFIRMED",
             door_polarity: str = "UNCONFIRMED", door: int = 1,
             supervised: str = "1", supervised_authorized: str = "0") -> str:
    line = fixture("h8s_sample.txt")
    line = _set(line, "seq", seq)
    line = _set(line, "run_id", run_id)
    line = _set(line, "state", state)
    line = _set(line, "stage", stage)
    line = _set(line, "snapshot", "VALID")
    line = _set(line, "fault_bits", fault)
    line = _set(line, "voltage_v", f"{voltage:.3f}")
    line = _set(line, "voltage_v_status", "OK")
    line = _set(line, "current_a", f"{current:.3f}")
    line = _set(line, "current_a_status", "OK")
    line = _set(line, "power_w", f"{(voltage * current if power is None else power):.3f}")
    line = _set(line, "power_w_status", "OK")
    line = _set(line, "t1", f"{t1:.3f}")
    line = _set(line, "t2", f"{t2:.3f}")
    line = _set(line, "t3", f"{t3:.3f}")
    line = _set(line, "t4", f"{t4:.3f}")
    line = _set(line, "pwm_req_permille", pwm)
    line = _set(line, "pwm_applied_permille", pwm)
    line = _set(line, "pwm_readback_permille", pwm)
    line = _set(line, "fan", fan)
    line = _set(line, "door_polarity", door_polarity)
    line = _set(line, "door_open", door)
    line = _set(line, "door_status", "OK")
    line = _set(line, "supervised_bench", supervised)
    line = _set(line, "supervised_authorized", supervised_authorized)
    line = _set(line, "test_mode", "BENCH_ENDURANCE")
    line = _set(line, "mandatory_roles", "HOT_SIDE")
    line = _set(line, "limits_operator_approved", 1)
    line = _set(line, "limits_enforced", 1)
    line = _set(line, "off_current_approved", 1)
    return line


def h8_cmd(result: str, **fields: object) -> str:
    body = " ".join(f"{key}={value}" for key, value in fields.items())
    return f"#CG H8 CMD result={result}" + (f" {body}" if body else "")
