"""Shared test fixtures for the W09/W10/W11 tooling (HOST-SYNTHESISED, not data).

Everything here is a *tooling input*: frames assembled in the exact wire shapes
the shipped encodings use, so the parsers and analysers are tested against real
field spellings. No file in this module represents a run, and the markers say
so: ``FIXTURE_RUN_LABEL_PREFIX`` and ``is_physical_measurement=False`` travel
with every fixture frame, which is what lets the tests assert that the analysis
layer refuses them.

The line templates are transcribed from real captured lines - the committed W04
``#CG TELEM`` capture and the H8 ``#CG H8S`` wire form - with the values changed
to the ones each test needs.
"""

from __future__ import annotations

import cg_w09_capture_parser as capture_parser

FIXTURE_RUN_LABEL_PREFIX = "FIXTURE_"
FIXTURE_NOTE = "host-synthesised tooling fixture; is_physical_measurement=False; never a run"

H8S_TEMPLATE = (
    "#CG H8S schema=3 seq={seq} timestamp_utc=UNAVAILABLE "
    "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK device_ms={device_ms} boot_id={boot_id} "
    "reset_cause=USB run_id={run_id} stage={stage} state={state} fault_bits=0x0 fault=NONE "
    "stop_reason={stop_reason} test_mode=BENCH_ENDURANCE mandatory_roles=HOT_SIDE "
    "pressure_required=1 snapshot={snapshot} missing={missing} invalid={invalid} stale={stale} "
    "pwm_req_permille={pwm_req} pwm_applied_permille={pwm_applied} "
    "pwm_readback_permille={pwm_readback} pwm_freq_hz=1000 pwm_freq_rb_hz=1000 ren_command=0 "
    "len_command=0 enable_readback=ren:0,len:0 stage_elapsed_ms=0 stage_remaining_ms=0 "
    "run_count=0 host_ack_seq=0 host_ack_age_ms=-1 host_ack_count=0 host_ack_reject=0 "
    "host_ack_awaiting=0 fault_latency_us=-1 off_current_limit_a=0.200 "
    "off_current_approved=1 off_current_test_enforce=0 off_verify=NONE "
    "limits_operator_approved=1 limits_simulated_enforcement=0 limits_enforced=1 "
    "limits_policy=APPROVED supervised_bench=1 supervised_authorized=0 "
    "interlock_state=NOT_INSTALLED t1={t1} t1_status={t1_status} t1_age_ms=46 t1_role=UNASSIGNED "
    "t2={t2} t2_status={t2_status} t2_age_ms=46 t2_role=HOT_SIDE "
    "t3={t3} t3_status={t3_status} t3_age_ms=46 t3_role=UNASSIGNED "
    "t4={t4} t4_status={t4_status} t4_age_ms=46 t4_role=UNASSIGNED "
    "air_c={air_c} air_c_status=OK air_c_age_ms=775 rh_pct=70.124 rh_pct_status=OK "
    "rh_pct_age_ms=775 pressure_hpa=1015.39 pressure_status=OK door_open={door_open} "
    "door_raw={door_raw} door_status={door_status} door_age_ms=1 door_cycles={door_cycles} "
    "door_polarity={door_polarity} voltage_v={voltage_v} voltage_v_status={voltage_status} "
    "voltage_v_age_ms=656 current_a={current_a} current_a_status={current_status} "
    "current_a_age_ms=656 power_w={power_w} power_w_status={power_status} power_w_age_ms=656 "
    "energy_wh=24.000 fan=OPERATOR_CONFIRMED fan_readback=NOT_ELECTRONICALLY_VERIFIED "
    "cloud=NOT_PROVISIONED"
)


def h8s_line(seq=1, device_ms=None, boot_id="fixtureboot", run_id="run-00000000",
             stage="NONE", state="OFF", stop_reason="NONE", snapshot="VALID",
             missing="0x0", invalid="0x0", stale="0x0", pwm_req=0, pwm_applied=0,
             pwm_readback=0, t1=25.0, t2=30.0, t3=25.0, t4=25.0, air_c=25.5,
             t1_status="OK", t2_status="OK", t3_status="OK", t4_status="OK",
             door_open="0", door_raw="0", door_status="VALID", door_cycles="0",
             door_polarity="CONFIRMED", voltage_v="11.940", current_a="0.000",
             power_w="0.000", voltage_status="OK", current_status="OK",
             power_status="OK") -> str:
    """One complete real-shaped ``#CG H8S`` line."""
    return H8S_TEMPLATE.format(
        seq=seq, device_ms=device_ms if device_ms is not None else (seq - 1) * 1000 + 904,
        boot_id=boot_id, run_id=run_id, stage=stage, state=state, stop_reason=stop_reason,
        snapshot=snapshot, missing=missing, invalid=invalid, stale=stale, pwm_req=pwm_req,
        pwm_applied=pwm_applied, pwm_readback=pwm_readback, t1=t1, t2=t2, t3=t3, t4=t4,
        air_c=air_c, t1_status=t1_status, t2_status=t2_status, t3_status=t3_status,
        t4_status=t4_status, door_open=door_open, door_raw=door_raw, door_status=door_status,
        door_cycles=door_cycles, door_polarity=door_polarity, voltage_v=voltage_v,
        current_a=current_a, power_w=power_w, voltage_status=voltage_status,
        current_status=current_status, power_status=power_status,
    )


def _build(count, *, physical: bool, seqs=None, run_label: str, note: str = "",
           host_time: bool = False, **overrides) -> list[capture_parser.Frame]:
    """One builder for both fixture kinds, so they cannot drift apart.

    ``seqs`` lets a test name the exact sequence it needs - a gap, a duplicate,
    a run that continues where the previous block stopped.
    """
    wanted = list(seqs) if seqs is not None else list(range(1, count + 1))
    frames = []
    for position, seq in enumerate(wanted):
        line = h8s_line(seq=seq, **overrides)
        if host_time:
            line = f"2026-11-02T00:00:{(position + 1) % 60:02d}Z {line}"
        provenance = capture_parser.SourceProvenance(
            source_kind="h8s_jsonl" if physical else "h8s_fixture",
            source_path=(
                "evidence/A/W04/h8/example/monitor/samples.jsonl"
                if physical else "tests/cg_w09_fixtures.py"
            ),
            source_sha256="0" * 64 if physical else None,
            line_index=position + 1,
            is_physical_measurement=physical,
            run_label=run_label,
            note=note if note else ("" if physical else FIXTURE_NOTE),
        )
        frames.append(capture_parser.parse_frame_line(line, provenance))
    return frames


def fixture_frames(count=5, run_label=FIXTURE_RUN_LABEL_PREFIX + "H8S", note="",
                   seqs=None, **overrides) -> list[capture_parser.Frame]:
    """H8S frames tagged as host fixtures (is_physical_measurement=False)."""
    host_time = overrides.pop("host_time", False)
    return _build(count, physical=False, seqs=seqs, run_label=run_label, note=note,
                  host_time=host_time, **overrides)


def physical_frames(count=5, run_label="SOME_REAL_RUN", note="", seqs=None,
                    **overrides) -> list[capture_parser.Frame]:
    """H8S frames carrying a physical-provenance flag, for the positive paths."""
    host_time = overrides.pop("host_time", False)
    return _build(count, physical=True, seqs=seqs, run_label=run_label, note=note,
                  host_time=host_time, **overrides)
