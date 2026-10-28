"""B-W02-01 verification: deterministic synthetic runs.

Focus (05B §30, Doc `04` §17-B):
* same seed ⇒ byte-identical replay; different seed ⇒ different values;
* self-labeled fixture provenance (``synthetic: true`` + note, B7);
* canonical sample identity is unique corpus-wide and boot-scoped;
* prescribed (never curve-derived) critical-event series;
* canonical scenario vocabulary behaviors (Doc `03` §31);
* absence is preserved (never zero-filled), UNKNOWN door stays UNKNOWN.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from coldguard_ml import (
    DataContractError,
    SyntheticRunSpec,
    build_synthetic_dataset,
    build_synthetic_run,
    build_synthetic_runs,
    validate_observation,
)
from coldguard_ml.observations import event_time_to_rfc3339

UTC = _dt.timezone.utc
START = _dt.datetime(2026, 1, 1, tzinfo=UTC)
FIXTURE_COMMIT = "0" * 40
FIXTURE_CREATED = _dt.datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def _spec(**overrides) -> SyntheticRunSpec:
    base: dict = dict(run_id="CG-S1-A-001", scenario_id="S1", seed=7)
    base.update(overrides)
    return SyntheticRunSpec(**base)


def test_same_seed_replay_is_identical():
    first = build_synthetic_run(_spec(critical_event_offset_s=40.0))
    second = build_synthetic_run(_spec(critical_event_offset_s=40.0))
    assert first.observations == second.observations
    assert first.run_manifest == second.run_manifest
    assert first.critical_series == second.critical_series
    assert first == second


def test_seed_change_varies_values_but_keeps_structure():
    base = build_synthetic_run(_spec(seed=7))
    other = build_synthetic_run(_spec(seed=8))
    assert base.observations != other.observations
    assert len(other.observations) == len(base.observations)
    assert [o.seq for o in other.observations] == [o.seq for o in base.observations]
    assert [o.boot_id for o in other.observations] == [o.boot_id for o in base.observations]


def test_run_manifest_declares_fixture_provenance_and_metadata():
    run = build_synthetic_run(_spec())
    manifest = run.run_manifest
    assert manifest["synthetic"] is True
    assert manifest["seed"] == 7
    assert manifest["note"].startswith("SYNTHETIC")
    assert manifest["is_valid"] is True
    assert manifest["invalid_reason"] is None
    assert manifest["run_id"] == "CG-S1-A-001"
    assert manifest["scenario_id"] == "S1"
    assert manifest["hardware_config_id"] == "CG-HW-001"
    assert manifest["firmware_version"].startswith("fw-synthetic")
    assert manifest["start_time"] == event_time_to_rfc3339(run.observations[0].time)
    assert manifest["end_time"] == event_time_to_rfc3339(run.observations[-1].time)
    assert manifest["boots"][0]["n_observations"] == len(run.observations)


def test_sample_identity_is_corpus_wide_unique_and_boot_scoped():
    run = build_synthetic_run(_spec(boot_sessions=3))
    identities = [o.identity for o in run.observations]
    assert len(set(identities)) == len(identities), "identities must be unique"
    boots = sorted({o.boot_id for o in run.observations})
    assert len(boots) == 3
    for boot in boots:
        seqs = [o.seq for o in run.observations if o.boot_id == boot]
        assert seqs == list(range(len(seqs))), "seq restarts per boot"
    # Wall gaps between boot sessions are preserved — no fabricated time fill.
    times = sorted(o.time for o in run.observations)
    gaps = [
        (times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)
    ]
    assert max(gaps) >= 5.0, "boot gaps must survive (no interpolation)"


def test_critical_series_is_prescribed_not_curve_derived():
    run = build_synthetic_run(
        _spec(critical_event_offset_s=40.0, untrusted_event_offset_s=20.0)
    )
    events = run.critical_series.events
    assert len(events) == 2
    trusted = [e for e in events if e.trusted]
    untrusted = [e for e in events if not e.trusted]
    assert trusted and trusted[0].time == START + _dt.timedelta(seconds=40.0)
    assert untrusted and untrusted[0].time == START + _dt.timedelta(seconds=20.0)
    assert all(e.ref is not None and e.ref.startswith("prescribed") for e in events)
    # Coverage reaching the last sample makes complete-horizon evaluation possible.
    assert run.critical_series.coverage_end == run.observations[-1].time


def test_no_series_events_when_none_prescribed():
    run = build_synthetic_run(_spec())
    assert run.critical_series.events == ()
    assert run.critical_series.series_id == "synthetic-prescribed-series:CG-S1-A-001:v0"
    assert run.critical_series.coverage_end == run.observations[-1].time


def test_s2_door_disturbance_window():
    run = build_synthetic_run(_spec(run_id="CG-S2-A-001", scenario_id="S2"))
    opens = [
        o
        for o in run.observations
        if o.time == START + _dt.timedelta(seconds=30.0)
    ]
    assert opens and opens[0].door_state == "OPEN"
    closed_after = [
        o
        for o in run.observations
        if o.time == START + _dt.timedelta(seconds=50.0)
    ]
    assert closed_after and closed_after[0].door_state == "CLOSED"
    assert all(o.door_state in ("OPEN", "CLOSED", "UNKNOWN") for o in run.observations)


def test_s6_degradation_keeps_absence_and_unknown_door():
    run = build_synthetic_run(_spec(run_id="CG-S6-A-001", scenario_id="S6"))
    degraded = [o for o in run.observations if o.thermal_quality == "DEGRADED"]
    assert degraded and all(o.t2_c is None for o in degraded)  # LRK-14: absent ≠ 0
    late = [
        o for o in run.observations if o.time >= START + _dt.timedelta(seconds=50.0)
    ]
    assert late and all(o.door_state == "UNKNOWN" for o in late)
    absent_electrical = [
        o for o in run.observations if o.electrical_quality == "INVALID"
    ]
    assert absent_electrical and all(
        o.cooling_voltage_v is None
        and o.cooling_current_a is None
        and o.cooling_power_w is None
        and o.cooling_energy_counter_wh is None
        for o in absent_electrical
    )


def test_s5_connectivity_loss_is_recorded_absence():
    run = build_synthetic_run(_spec(run_id="CG-S5-A-001", scenario_id="S5"))
    times = [o.time for o in run.observations]
    gaps = [
        (times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)
    ]
    # The loss span 40s..71.5s (default) removes samples — a recorded gap,
    # never bridged with fabricated rows.
    assert max(gaps) >= 30.0
    assert len(run.observations) == 58  # 90 nominal minus 32 loss-span slots
    assert all(o.overall_quality in ("VALID", "DEGRADED") for o in run.observations)


def test_s4_actuation_fault_is_visible_in_electrical_branch():
    fault = build_synthetic_run(_spec(run_id="CG-S4-A-001", scenario_id="S4"))
    healthy = build_synthetic_run(
        _spec(run_id="CG-S1-A-002", scenario_id="S1", seed=47)
    )
    cut = START + _dt.timedelta(seconds=45.0)
    fault_late = [o for o in fault.observations if o.time >= cut]
    healthy_late = [o for o in healthy.observations if o.time >= cut]
    assert fault_late and healthy_late
    assert all(o.cooling_current_a is not None and o.cooling_current_a < 0.2 for o in fault_late)
    assert all(o.cooling_current_a is not None and o.cooling_current_a > 3.0 for o in healthy_late)
    assert all(o.applied_cooling == "ON" for o in fault_late)


def test_every_generated_row_passes_dictionary_validation():
    for scenario in ("S1", "S2", "S3", "S4", "S5", "S6"):
        run = build_synthetic_run(
            _spec(run_id=f"CG-S{scenario[1]}-A-001", scenario_id=scenario, seed=13)
        )
        for row in run.observations:
            validate_observation(row)


def test_spec_rejects_out_of_bounds_and_implicit_values():
    with pytest.raises(DataContractError, match="seed must be an explicit integer"):
        SyntheticRunSpec(run_id="CG-S1-A-003", scenario_id="S1", seed="7")  # type: ignore[arg-type]
    with pytest.raises(DataContractError, match="scenario_id"):
        SyntheticRunSpec(run_id="CG-S1-A-004", scenario_id="S9", seed=1)
    with pytest.raises(DataContractError, match="beyond the recorded trajectory"):
        SyntheticRunSpec(
            run_id="CG-S1-A-005", scenario_id="S1", seed=1, critical_event_offset_s=91.0
        )
    with pytest.raises(DataContractError, match="door_offset_s and door_duration_s"):
        SyntheticRunSpec(run_id="CG-S2-A-009", scenario_id="S2", seed=1, door_offset_s=10.0)
    with pytest.raises(DataContractError, match="zero observations"):
        build_synthetic_run(
            SyntheticRunSpec(
                run_id="CG-S5-A-008",
                scenario_id="S5",
                seed=1,
                duration_s=10.0,
                connectivity_loss_after_s=0.0,
                connectivity_loss_until_s=10.0,
            )
        )


def test_build_runs_sorts_by_run_id_deterministically():
    specs = [
        _spec(run_id="CG-S2-A-001", scenario_id="S2", seed=2),
        _spec(run_id="CG-S1-A-001", scenario_id="S1", seed=1),
        _spec(run_id="CG-S4-A-001", scenario_id="S4", seed=4),
    ]
    runs = build_synthetic_runs(specs)
    assert [r.run_id for r in runs] == ["CG-S1-A-001", "CG-S2-A-001", "CG-S4-A-001"]
    # Canonical order does not depend on input order.
    assert build_synthetic_runs(reversed(list(specs))) == runs


def test_dataset_manifest_propagates_synthetic_flag():
    run = build_synthetic_run(_spec(seed=21))
    payload, runs = build_synthetic_dataset(
        [run],
        "CG-DATA-001",
        git_commit=FIXTURE_COMMIT,
        created_at=FIXTURE_CREATED,
    )
    assert payload["synthetic"] is True
    assert payload["source_runs"] == ["CG-S1-A-001"]
    assert payload["hardware_configs"] == ["CG-HW-001"]
    assert payload["schema_version"] == 1
    assert payload["status"] == "draft"
    assert payload["content_sha256"] is None  # hash is minted at lock time (§4)
    assert payload["git_commit"] == FIXTURE_COMMIT
    with pytest.raises(DataContractError, match="git_commit"):
        build_synthetic_dataset([run], "CG-DATA-001", git_commit="", created_at=FIXTURE_CREATED)
