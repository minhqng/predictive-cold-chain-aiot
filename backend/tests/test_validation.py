"""Strict runtime validation + topic/device identity (C-W03-01/02).

Pure contract tests: no database, no broker. Each test names the
invariant, the realistic bug that would violate it, and the cheapest
layer that proves it (here: the validation module directly).

Defects detected: lax-coercion rescue (seq/t1 as strings, bool seq),
naive timestamps, unsupported schema parsed as compatible, missing
identity, wrong field types, broken nesting, quality-contract
violations, topic/payload device disagreement, malformed telemetry
namespaces, and any trust in self-declared payload identity as proof
of broker authentication (no such field exists by design).
"""

import copy
import json
from pathlib import Path

from coldguard_backend.validation import (
    looks_like_telemetry_topic,
    topic_device_id,
    validate_telemetry_payload,
    validate_topic_identity,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TOPIC = "coldguard/coldguard-001/telemetry"


def _payload() -> dict:
    return json.loads((FIXTURES / "telemetry_v0.json").read_text())


def _valid() -> tuple[dict, object]:
    payload = _payload()
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is not None, errors
    assert errors == []
    return payload, telemetry


def test_happy_path_validates_with_agreement():
    payload, telemetry = _valid()
    assert validate_topic_identity(TOPIC, telemetry) == []
    assert telemetry.message_identity == ("coldguard-001", "boot-w01-fixture-001", 12345)


def test_seq_as_string_rejected_not_coerced():
    payload = _payload()
    payload["seq"] = "12345"
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None
    assert any(err["loc"] == "seq" for err in errors)


def test_measurement_as_string_rejected_not_coerced():
    payload = _payload()
    payload["thermal"]["t1"] = "7.1"
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None
    assert any(err["loc"] == "thermal.t1" for err in errors)


def test_bool_seq_rejected():
    payload = _payload()
    payload["seq"] = True
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None
    assert any(err["loc"] == "seq" for err in errors)


def test_bool_measurement_rejected():
    payload = _payload()
    payload["electrical"]["current_a"] = True
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_int_for_float_measurement_accepted():
    # Numeric widening (int where float is expected) is semantically
    # safe: no information is invented, unlike string parsing.
    payload = _payload()
    payload["thermal"]["t1"] = 7
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is not None, errors
    assert telemetry.thermal.t1 == 7.0


def test_naive_timestamp_rejected():
    payload = _payload()
    payload["captured_at"] = "2026-10-14T07:00:00"
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None
    assert any(err["code"] == "NAIVE_TIMESTAMP" for err in errors)


def test_unsupported_schema_rejected_never_parsed_as_compatible():
    payload = _payload()
    payload["schema_version"] = 2
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None
    assert any(err["code"] == "UNSUPPORTED_SCHEMA" for err in errors)


def test_zero_schema_rejected():
    payload = _payload()
    payload["schema_version"] = 0
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_missing_identity_rejected():
    payload = _payload()
    del payload["boot_id"]
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None
    assert errors, "missing identity needs diagnostics"


def test_empty_device_id_rejected():
    payload = _payload()
    payload["device_id"] = "   "
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_wrong_nesting_rejected():
    payload = _payload()
    payload["thermal"] = [7.1, 7.4, 7.8]
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_missing_section_rejected():
    payload = _payload()
    del payload["quality"]
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_none_under_valid_quality_rejected():
    payload = _payload()
    payload["thermal"]["t3"] = None
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_degraded_missing_still_validates():
    # DEGRADED is reduced trust, not absence: usable readings survive
    # and the quality flag stays honest.
    payload = _payload()
    payload["thermal"]["t3"] = None
    payload["quality"]["thermal"] = "DEGRADED"
    payload["quality"]["overall"] = "DEGRADED"
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is not None, errors
    assert telemetry.thermal.t3 is None
    assert telemetry.quality.thermal == "DEGRADED"


def test_non_finite_measurement_rejected():
    # Python's json parser accepts NaN/Infinity literals; they are
    # impossible physical readings and NaN would poison duplicate
    # comparison (NaN != NaN), so both are rejected.
    import math

    for bad in (float("nan"), float("inf"), float("-inf")):
        payload = _payload()
        payload["thermal"]["t1"] = bad
        telemetry, errors = validate_telemetry_payload(payload)
        assert telemetry is None, bad
        assert any(err["code"] == "NON_FINITE" for err in errors), bad
    assert not math.isnan(7.0)  # sanity: finiteness gate itself is sound


def test_zero_measurement_is_not_missing():    # Zero is a reading; None is missing. They must not be equated.
    payload = _payload()
    payload["electrical"]["current_a"] = 0.0
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is not None, errors
    assert telemetry.electrical.current_a == 0.0


def test_unknown_quality_value_rejected():
    payload = _payload()
    payload["quality"]["overall"] = "PROBABLY_FINE"
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_legacy_dual_branch_rejected():
    payload = _payload()
    payload["electrical"]["power_1"] = 10.0
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_negative_energy_counter_rejected():
    payload = _payload()
    payload["electrical"]["energy_wh"] = -1.0
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is None


def test_topic_mismatch_rejected():
    _, telemetry = _valid()
    errors = validate_topic_identity("coldguard/other-device/telemetry", telemetry)
    assert len(errors) == 1
    assert errors[0]["code"] == "TOPIC_MISMATCH"


def test_malformed_topic_rejected():
    _, telemetry = _valid()
    for bad in (
        "coldguard//telemetry",
        "coldguard/+/telemetry",
        "coldguard/#/telemetry",
        "wrongprefix/coldguard-001/telemetry",
        "coldguard/coldguard-001/telemetry/extra",
        "coldguard/coldguard-001/state",
    ):
        errors = validate_topic_identity(bad, telemetry)
        assert errors, f"topic {bad!r} should not validate"
        assert errors[0]["code"] == "MALFORMED_TOPIC"


def test_topic_device_extraction():
    assert topic_device_id(TOPIC) == "coldguard-001"
    assert topic_device_id("coldguard//telemetry") is None
    assert topic_device_id("coldguard/coldguard-001/state") is None
    assert topic_device_id("other/coldguard-001/telemetry") is None


def test_looks_like_telemetry_topic():
    assert looks_like_telemetry_topic(TOPIC)
    assert looks_like_telemetry_topic("coldguard//telemetry")
    assert not looks_like_telemetry_topic("coldguard/coldguard-001/state")


def test_no_publisher_identity_field_trusted():
    # The trust boundary: no field in the payload may pose as broker
    # authentication proof. A payload claiming an owner/username must
    # not change the validation verdict (extras are ignored).
    payload = _payload()
    payload["mqtt_username"] = "device-coldguard-001"
    payload["authenticated"] = True
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is not None, errors
    # Agreement still comes from topic/payload device comparison only.
    assert validate_topic_identity(TOPIC, telemetry) == []
    assert validate_topic_identity("coldguard/attacker/telemetry", telemetry) != []


def test_non_dict_payload_rejected():
    telemetry, errors = validate_telemetry_payload([1, 2, 3])
    assert telemetry is None
    assert errors


def test_deep_copy_variant_still_validates():
    payload = copy.deepcopy(_payload())
    telemetry, errors = validate_telemetry_payload(payload)
    assert telemetry is not None, errors
