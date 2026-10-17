"""B-W02-05 verification: manifest parsing and cross-bindings.

Focus (artifact-convention §§2–5, §9):
* the §3.1 dataset / §3.2 split / run-record shapes accept conforming
  payloads via dict, YAML text, and file path (parse→dump→parse is
  deterministic — §5 canonical key order);
* duplicate YAML keys, unknown fields, wrong CG-* identifier patterns,
  wrong statuses, missing provenance and lock/hash contradictions fail
  with an actionable ManifestError naming field + value + anchor;
* binding B1 (dataset_id resolution + partition union == source_runs),
  B5 (single hardware lineage value), B7 (synthetic flag propagation),
  plus split↔run-record resolution with pair lineage and excluded-run
  ledger consistency.
"""

from __future__ import annotations

import datetime as _dt

import pytest
import yaml

from coldguard_ml import (
    ManifestError,
    bind_dataset_to_run_records,
    bind_split_to_dataset,
    bind_split_to_run_records,
    canonical_manifest_yaml,
    manifest_content_sha256,
    parse_dataset_manifest,
    parse_run_manifest,
    parse_run_manifests,
    parse_split_manifest,
)
from coldguard_ml.observations import event_time_to_rfc3339

UTC = _dt.timezone.utc
WHEN = _dt.datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
LATER = _dt.datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC)
GIT = "a" * 64
SHA = "b" * 64
NOTE = "SYNTHETIC synthetic-harness fixture — not a physical measurement."


def _dataset_payload(**overrides):
    payload = {
        "dataset_id": "CG-DATA-001",
        "source_runs": ["CG-S1-A-001", "CG-S2-A-001", "CG-S4-A-001"],
        "hardware_configs": ["CG-HW-001"],
        "schema_version": 1,
        "calibration_ids": ["CG-CAL-001"],
        "export_query_hash": None,
        "created_at": event_time_to_rfc3339(WHEN),
        "created_by": "member-b",
        "git_commit": GIT,
        "status": "draft",
        "content_sha256": None,
        "synthetic": False,
    }
    payload.update(overrides)
    return payload


def _split_payload(**overrides):
    payload = {
        "split_id": "CG-SPLIT-001",
        "dataset_id": "CG-DATA-001",
        "train_runs": ["CG-S1-A-001"],
        "validation_runs": ["CG-S2-A-001"],
        "test_runs": ["CG-S4-A-001"],
        "grouping": {"key": "run_id"},
        "hardware_lineage": {"hardware_config_id": "CG-HW-001"},
        "locked_test": {"frozen_at": None, "opened_at": None},
        "controller_context": "all-reactive-or-observational",
        "pair_lineage": [],
        "excluded_runs": [],
        "split_seed": 11,
        "created_at": event_time_to_rfc3339(WHEN),
        "created_by": "member-b",
        "git_commit": GIT,
        "status": "draft",
        "content_sha256": None,
    }
    payload.update(overrides)
    return payload


def _run_payload(**overrides):
    payload = {
        "run_id": "CG-S1-A-001",
        "scenario_id": "S1",
        "controller_id": "CONTROLLER-A",
        "pair_id": None,
        "device_id": "coldguard-001",
        "hardware_config_id": "CG-HW-001",
        "firmware_version": "fw-synthetic-v0",
        "calibration_id": None,
        "schema_version": 1,
        "is_valid": True,
        "invalid_reason": None,
        "synthetic": True,
        "seed": 7,
        "boots": [],
        "start_time": "2026-01-01T00:00:00.000000Z",
        "end_time": "2026-01-01T00:01:29.000000Z",
        "note": NOTE,
    }
    payload.update(overrides)
    return payload


def _run_records():
    return parse_run_manifests(
        [
            _run_payload(run_id="CG-S1-A-001"),
            _run_payload(
                run_id="CG-S2-A-001",
                scenario_id="S2",
                synthetic=False,
                seed=None,
                note=None,
            ),
            _run_payload(run_id="CG-S4-A-001", scenario_id="S4", synthetic=False, seed=None, note=None),
        ],
    )


def _synthetic_run_records():
    """All-synthetic record set (B7-chain proof)."""
    return parse_run_manifests(
        [
            _run_payload(run_id="CG-S1-A-001"),
            _run_payload(run_id="CG-S2-A-001", scenario_id="S2"),
            _run_payload(run_id="CG-S4-A-001", scenario_id="S4"),
        ],
    )


def _yaml_text(payload) -> str:
    return yaml.safe_dump(payload, sort_keys=True)


# -- parsing inputs -----------------------------------------------------------


def test_parse_accepts_dict_text_and_file(tmp_path):
    payload = _dataset_payload()
    from_text = parse_dataset_manifest(_yaml_text(payload))
    from_dict = parse_dataset_manifest(payload)
    path = tmp_path / "dataset-CG-DATA-001-manifest.yaml"
    path.write_text(_yaml_text(payload), encoding="utf-8")
    from_file = parse_dataset_manifest(path)
    assert from_text == from_dict == from_file
    assert from_dict.dataset_id == "CG-DATA-001"
    assert from_dict.source_runs == ("CG-S1-A-001", "CG-S2-A-001", "CG-S4-A-001")
    assert from_dict.hardware_configs == ("CG-HW-001",)
    assert from_dict.calibration_ids == ("CG-CAL-001",)
    assert from_dict.created_at == WHEN
    assert from_dict.status == "draft"
    assert from_dict.synthetic is False
    assert from_dict.content_sha256 is None


def test_duplicate_yaml_keys_are_rejected():
    text = (
        "dataset_id: CG-DATA-001\n"
        "dataset_id: CG-DATA-002\n"
        "source_runs: [CG-S1-A-001]\n"
    )
    with pytest.raises(ManifestError, match="duplicate YAML key"):
        parse_dataset_manifest(text)


def test_unknown_fields_are_rejected_with_allowlist():
    payload = _dataset_payload(some_new_thing=1)
    with pytest.raises(ManifestError, match="unknown fields"):
        parse_dataset_manifest(payload)


def test_required_fields_must_be_present():
    payload = _dataset_payload()
    del payload["source_runs"]
    with pytest.raises(ManifestError, match="missing required field 'source_runs'"):
        parse_dataset_manifest(payload)


def test_identifier_patterns_are_enforced():
    with pytest.raises(ManifestError, match="dataset_id"):
        parse_dataset_manifest(_dataset_payload(dataset_id="DATA-001"))
    with pytest.raises(ManifestError, match="source_runs"):
        parse_dataset_manifest(_dataset_payload(source_runs=["CG-SX-1"]))
    with pytest.raises(ManifestError, match="hardware_configs"):
        parse_dataset_manifest(_dataset_payload(hardware_configs=["HW-01"]))
    with pytest.raises(ManifestError, match="split_id"):
        parse_split_manifest(_split_payload(split_id="CG-SPL-01"))


def test_scenario_and_status_domains_are_enforced():
    with pytest.raises(ManifestError, match="scenario_id"):
        parse_run_manifest(_run_payload(scenario_id="S7"))
    with pytest.raises(ManifestError, match="status"):
        parse_dataset_manifest(_dataset_payload(status="published"))
    with pytest.raises(ManifestError, match="status"):
        parse_split_manifest(_split_payload(status="published"))


def test_run_record_validation():
    # synthetic runs self-label via note and record their seed (§11)
    with pytest.raises(ManifestError, match="note"):
        parse_run_manifest(_run_payload(note=None))
    with pytest.raises(ManifestError, match="seed"):
        parse_run_manifest(_run_payload(seed=None))
    with pytest.raises(ManifestError, match="invalid_reason"):
        parse_run_manifest(_run_payload(is_valid=False, invalid_reason=None))
    # invalid run with a reason parses
    record = parse_run_manifest(
        _run_payload(is_valid=False, invalid_reason="thermal-contradiction")
    )
    assert record.is_valid is False
    assert record.invalid_reason == "thermal-contradiction"
    # temporal span contradictions are rejected
    with pytest.raises(ManifestError, match="end_time"):
        parse_run_manifest(
            _run_payload(start_time="2026-01-02T00:00:00Z", end_time="2026-01-01T00:00:00Z")
        )


def test_run_manifest_list_parsing_requires_unique_ids_and_list_form():
    records = parse_run_manifests([
        _run_payload(),
        _run_payload(run_id="CG-S2-A-001", seed=None, synthetic=False, note=None),
    ])
    assert len(records) == 2
    with pytest.raises(ManifestError, match="duplicate run manifests"):
        parse_run_manifests([_run_payload(), _run_payload()])
    with pytest.raises(ManifestError, match="must be a YAML list"):
        parse_run_manifests(_run_payload(run_id="CG-S2-A-002"))


def test_lock_discipline_and_lifecycle():
    locked = parse_dataset_manifest(_dataset_payload(status="locked", content_sha256=SHA))
    assert locked.content_sha256 == SHA
    # locked/final without content identity is a hard contradiction
    with pytest.raises(ManifestError, match="content_sha256"):
        parse_dataset_manifest(_dataset_payload(status="locked"))
    with pytest.raises(ManifestError, match="content_sha256"):
        parse_split_manifest(_split_payload(status="final"))
    # a hash-looking value is validated as sha256 hex
    with pytest.raises(ManifestError, match="content_sha256"):
        parse_dataset_manifest(_dataset_payload(status="locked", content_sha256="deadbeef"))
    # locked_test contradictions (§3.2)
    with pytest.raises(ManifestError, match="frozen"):
        parse_split_manifest(_split_payload(locked_test={"frozen_at": None, "opened_at": event_time_to_rfc3339(LATER)}))
    with pytest.raises(ManifestError, match="precedes"):
        parse_split_manifest(
            _split_payload(
                locked_test={
                    "frozen_at": event_time_to_rfc3339(LATER),
                    "opened_at": event_time_to_rfc3339(WHEN),
                }
            )
        )
    opening = parse_split_manifest(
        _split_payload(
            locked_test={
                "frozen_at": event_time_to_rfc3339(WHEN),
                "opened_at": event_time_to_rfc3339(LATER),
            }
        )
    )
    assert opening.frozen_at == WHEN and opening.opened_at == LATER


def test_split_grouping_and_seed_discipline():
    with pytest.raises(ManifestError, match="run_id"):
        parse_split_manifest(_split_payload(grouping={"key": "boot_id"}))
    with pytest.raises(ManifestError, match="split_seed"):
        parse_split_manifest(_split_payload(split_seed=None))
    with pytest.raises(ManifestError, match="split_seed"):
        parse_split_manifest(_split_payload(split_seed=True))
    # empty partition lists are legal (floors are a splitting-time contract)
    parsed = parse_split_manifest(
        _split_payload(train_runs=[], validation_runs=[], test_runs=["CG-S4-A-001"])
    )
    assert parsed.partitioned_runs == ("CG-S4-A-001",)


def test_split_excluded_runs_and_pair_lineage_validation():
    excluded_payloads = _split_payload(
        test_runs=[],
        excluded_runs=[{"run_id": "CG-S4-A-001", "reason": "thermal-contradiction"}],
    )
    parsed = parse_split_manifest(excluded_payloads)
    assert parsed.excluded_run_ids == frozenset({"CG-S4-A-001"})
    # an excluded run may not also live in a partition
    with pytest.raises(ManifestError, match="excluded and also assigned"):
        parse_split_manifest(
            _split_payload(excluded_runs=[{"run_id": "CG-S1-A-001", "reason": "x"}])
        )
    # pair lineage arms must sit inside the recorded partition
    with pytest.raises(ManifestError, match="arms must live in one partition"):
        parse_split_manifest(
            _split_payload(
                pair_lineage=[
                    {
                        "pair_id": "CG-S1-A-001",
                        "run_ids": ["CG-S1-A-001"],
                        "partition": "validation",
                    }
                ]
            )
        )
    ok = parse_split_manifest(
        _split_payload(
            train_runs=["CG-S1-A-001", "CG-S2-A-001"],
            validation_runs=[],
            pair_lineage=[
                {
                    "pair_id": "CG-S1-A-001",
                    "run_ids": ["CG-S1-A-001", "CG-S2-A-001"],
                    "partition": "train",
                }
            ],
        )
    )
    assert ok.pair_lineage == (
        {
            "pair_id": "CG-S1-A-001",
            "run_ids": ("CG-S1-A-001", "CG-S2-A-001"),
            "partition": "train",
        },
    )


# -- cross-bindings -----------------------------------------------------------


def test_b1_binding_union_equals_source_runs():
    dataset = parse_dataset_manifest(_dataset_payload())
    split = parse_split_manifest(_split_payload())
    bind_split_to_dataset(split, dataset)
    with pytest.raises(ManifestError, match="B1"):
        bind_split_to_dataset(
            parse_split_manifest(_split_payload(dataset_id="CG-DATA-002")), dataset
        )
    with pytest.raises(ManifestError, match="not equal"):
        bind_split_to_dataset(
            parse_split_manifest(
                _split_payload(test_runs=["CG-S9-A-001"])
            ),
            dataset,
        )
    with pytest.raises(ManifestError, match="not equal"):
        bind_split_to_dataset(
            parse_split_manifest(_split_payload(test_runs=[])),
            dataset,
        )
    # B5 support: the split lineage must sit inside the dataset's configs
    with pytest.raises(ManifestError, match="hardware lineage"):
        bind_split_to_dataset(
            parse_split_manifest(
                _split_payload(hardware_lineage={"hardware_config_id": "CG-HW-999"})
            ),
            dataset,
        )


def test_b7_synthetic_flag_must_propagate_consistently():
    records = _run_records()  # CG-S1 is synthetic; CG-S2/CG-S4 are not
    mixed = parse_dataset_manifest(_dataset_payload())
    with pytest.raises(ManifestError, match="B7"):
        bind_dataset_to_run_records(mixed, records)
    # the true synthetic chain binds cleanly
    synthetic_dataset = parse_dataset_manifest(_dataset_payload(synthetic=True))
    bind_dataset_to_run_records(synthetic_dataset, _synthetic_run_records())
    # invalid runs must never appear as dataset sources
    with pytest.raises(ManifestError, match="invalid-run ledger"):
        bind_dataset_to_run_records(
            synthetic_dataset,
            [
                parse_run_manifest(
                    _run_payload(
                        run_id="CG-S1-A-001",
                        is_valid=False,
                        invalid_reason="thermal-contradiction",
                    )
                ),
                *_synthetic_run_records()[1:],
            ],
        )


def test_split_to_run_record_bindings():
    dataset = parse_dataset_manifest(_dataset_payload())
    split = parse_split_manifest(_split_payload())
    bind_split_to_dataset(split, dataset)
    records = _run_records()
    bind_split_to_run_records(split, records)

    # partitioned invalid run = contradiction
    bad_records = [
        parse_run_manifest(
            _run_payload(
                run_id="CG-S1-A-001",
                is_valid=False,
                invalid_reason="thermal-contradiction",
            )
        ),
        *_run_records()[1:],
    ]
    with pytest.raises(ManifestError, match="never partitioned"):
        bind_split_to_run_records(split, bad_records)

    # missing run records fail loudly
    with pytest.raises(ManifestError, match="without manifests"):
        bind_split_to_run_records(split, records[2:])

    # excluded valid run with a non-predictive reason = audit failure
    excluded_split = parse_split_manifest(
        _split_payload(
            test_runs=[],
            excluded_runs=[{"run_id": "CG-S4-A-001", "reason": "invented-reason"}],
        )
    )
    bind_split_to_dataset(excluded_split, parse_dataset_manifest(
        _dataset_payload(source_runs=["CG-S1-A-001", "CG-S2-A-001"])
    ))
    with pytest.raises(ManifestError, match="excluded with reason"):
        bind_split_to_run_records(excluded_split, records)
    # predictive-closed-loop exclusion of a valid run is the legal path
    predictive_excluded = parse_split_manifest(
        _split_payload(
            test_runs=[],
            excluded_runs=[{"run_id": "CG-S4-A-001", "reason": "predictive-closed-loop"}],
        )
    )
    bind_split_to_run_records(predictive_excluded, records)

    # pair lineage contradicting the recorded partitions fails at parse time
    # (self-consistency gate); the binding keeps a defensive re-check too.
    with pytest.raises(ManifestError, match="arms must live in one partition"):
        parse_split_manifest(
            _split_payload(
                train_runs=["CG-S1-A-001"],
                pair_lineage=[
                    {
                        "pair_id": "CG-S1-A-001",
                        "run_ids": ["CG-S1-A-001"],
                        "partition": "test",
                    }
                ],
            )
        )


# -- canonical serialization --------------------------------------------------


def test_round_trip_is_deterministic_and_sha_stable():
    payload = _split_payload(
        status="locked",
        content_sha256=SHA,
        locked_test={
            "frozen_at": event_time_to_rfc3339(WHEN),
            "opened_at": None,
        },
        pair_lineage=[
            {
                "pair_id": "CG-S1-A-001",
                "run_ids": ["CG-S1-A-001"],
                "partition": "train",
            }
        ],
    )
    text = _yaml_text(payload)
    first = parse_split_manifest(text)
    second = parse_split_manifest(canonical_manifest_yaml(first.raw))
    # canonical key-sorted YAML (§5): identical bytes across parse/dump cycles
    assert canonical_manifest_yaml(first.raw) == canonical_manifest_yaml(second.raw)
    assert manifest_content_sha256(first.raw) == manifest_content_sha256(second.raw)
    # typed fields survive the round trip (datetimes parse back identically)
    assert first.frozen_at == second.frozen_at == WHEN
    assert first.split_id == second.split_id == "CG-SPLIT-001"
    assert first.pair_lineage == second.pair_lineage
    # hash format is a real sha256 hex digest
    assert len(manifest_content_sha256(first.raw)) == 64
