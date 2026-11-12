"""W21 diagnosis/resilience evidence audit driver (B-W21-01..04).

Canonical anchors: Doc 01 sections 1.10-1.17, 6.5-6.8, 9, 19, 26; Doc 02
sections 37-44; Doc 03 sections 66, 103-107, 115, 137; Doc 04 W21-W22;
Doc 05B section 49.

The driver reads a fixed allowlist of metadata, a pinned source register and
two B-owned report inputs.  It never opens a W16 locked-test file, a W20
paired-outcome payload, a physical device interface or a broker client.  The
recorded Member A evidence stays outside the B branch; only extracted fields
and SHA-256 bindings are carried into the generated inventory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from coldguard_ml.w21_diagnosis import (
    CLASS_DEGRADED_OR_UNKNOWN,
    CLASS_DEGRADED_THERMAL_EFFECTIVENESS,
    CLASS_ELECTRICAL_RESPONSE_MISSING,
    CLASS_HEALTHY_RESPONSE,
    CLASS_NOT_ESTIMABLE,
    CLASS_UNEXPECTED_OFF_CURRENT,
    CONCORDANCE_CONCORDANT,
    CONCORDANCE_NOT_ESTIMABLE,
    COMMAND_OFF,
    COMMAND_ON,
    CURRENT_MEASURED_NONZERO,
    CURRENT_MEASURED_ZERO,
    CURRENT_MISSING,
    CURRENT_UNKNOWN,
    DIAG_01,
    DIAG_02,
    DIAG_03,
    DIAG_04,
    GROUND_TRUTH_CONTROLLED_INJECTION,
    GROUND_TRUTH_NONE,
    LEVEL_ELECTRICAL_RESPONSE_VERIFICATION,
    LEVEL_RECORDED_CONDITION,
    LEVEL_SOFTWARE_DIAGNOSTIC_CLASSIFICATION,
    LEVEL_THERMAL_RESPONSE_VERIFICATION,
    LEVEL_TRUSTED_CHANNEL_OBSERVATION,
    METRIC_NOT_ESTIMABLE,
    OUTPUT_STAGE_DISABLED,
    OUTPUT_STAGE_ENABLED,
    QUALITY_DEGRADED,
    QUALITY_INVALID,
    QUALITY_UNKNOWN,
    QUALITY_VALID,
    REFUSAL_ACK_NOT_EVIDENCE,
    REFUSAL_ELECTRICAL_UNAVAILABLE,
    REFUSAL_MISSING_PZEM_NOT_ZERO,
    REFUSAL_OUTPUT_STAGE_DISABLED,
    REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE,
    THERMAL_ABSENT,
    THERMAL_PRESENT,
    THERMAL_UNKNOWN,
    DiagnosisCase,
    assess_diagnosis_table,
    classify_case,
    population_metrics,
    required_negative_cases,
)
from coldguard_ml.w21_evidence import (
    EVIDENCE_CONTRACT_REFERENCE,
    EVIDENCE_HOST_SOFTWARE_SIMULATION,
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
    GATE_BOUNDED_ON_DEVICE_EVIDENCE,
    GATE_CONTRACT_REFERENCE_ONLY,
    GATE_F_NOT_OPENED,
    GATE_F_OPEN,
    GATE_NOT_ESTABLISHED,
    GATE_PHYSICALLY_VERIFIED,
    GATE_SOFTWARE_TEST_ONLY,
    PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED,
    PROVENANCE_MEASUREMENT_INTERPRETATION_SUPPORTED,
    PROVENANCE_RECORDED_CHECK_PASSED,
    PROVENANCE_SOURCE_BYTES_VERIFIED,
    SourceRecord,
    W21_EVIDENCE_LAYER_VERSION,
    admit_source,
    assess_class_promotion,
    assess_gate_f,
    audit_capabilities,
    build_source_inventory,
    canonical_sha256,
    count_independent_sessions,
    degraded_model_inference_allowed,
    electrical_measurement,
    energy_delta,
    normalize_door_state,
    normalize_temperature,
    predictive_training_eligible,
    recovery_supported,
    require_no_capability,
    sha256_bytes,
    source_bytes_match,
    source_register_identity,
)
from coldguard_ml.w21_resilience import (
    DURATION_ON_DEVICE_OBSERVED,
    DURATION_SOFTWARE_SIMULATION,
    EXIT_REQUIREMENTS,
    MODEL_HEALTH_READY,
    PHYSICAL_STATE_NOT_VERIFIED,
    PHYSICAL_STATE_VERIFIED,
    STATUS_DETECTION_NOT_OBSERVED,
    STATUS_OUTAGE_NOT_OBSERVED,
    STATUS_PHYSICAL_CONTROL_NOT_VERIFIED,
    STATUS_RESYNC_NOT_VERIFIED,
    STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED,
    STATUS_TIME_DOMAIN_INSUFFICIENT,
    TIME_BACKEND_RECEIVED_AT,
    TIME_DEVICE_CAPTURED_AT,
    TIME_SOFTWARE_SIMULATION_CLOCK,
    TelemetryRecord,
    ResilienceTimeline,
    assess_ai_fallback,
    assess_replay,
    assess_safe_local_exit,
    assess_stale_command,
    assess_timeline,
    population_distribution_status,
)

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
REPORTS_DIR = ML_ROOT / "reports" / "W21"

W21_LAYER_VERSION = W21_EVIDENCE_LAYER_VERSION
W21_BASE_REVISION = "127a79b96f4ebb89b20cbc8826ada1dd813bb5df"
W21_BASE_REVISION_SEMANTICS = "W20_STACK_HEAD_BASE_NOT_W21_DELIVERY_COMMIT"
REV_A_EVIDENCE = "cd1b40e08456a0a088f131cbdd2e1ef3b92052cc"
REV_MAIN_VERIFIED = "d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85"
REV_C_W21 = "72a5861c0dd47b69a9f326312e3e1b523c1bcaee"
REV_C_W16 = "e31d30bce7b6aedb4116385a86dcaaace4f6b142"
REV_D_W13 = "da821094985006945d0306dd7b16be576378bc18"

A_SESSION_KEY = "coldguard-001/4cf9be5f"
W15_MODEL_STATUS = "SYNTHETIC_NONDEPLOYABLE"

A_SESSION = {
    "session": "W21-02_W21-03_combined",
    "evidence_mode": EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
    "device_id": "coldguard-001",
    "boot_id": "4cf9be5f",
    "boot_count": "181",
    "hardware_config_id": "CG-HW-001",
    "firmware_version": "cg-w06-0.1.0",
    "firmware_binary_sha256": (
        "e1073935168c01be029c23a87f6f012d852016deac0afb672437f234a269206b"
    ),
    "raw_log_sha256": (
        "faf008eb6c7e250c8b8f98385e6eb3817b1084771a56d800a3735c576c7106fa"
    ),
    "raw_log_bytes": 371291,
    "test_ids": ("A-W21-02", "A-W21-03"),
    "record_count": 50,
    "fault_window_frames": 50,
    "recovery_frames": 50,
    "total_recorded_frames": 100,
    "independent_session_count": 1,
    "tec_actuation": "NONE",
    "output_stage": "COMPILED_OUT",
    "fuse": "OUT",
    "physical_disconnection": "NONE",
    "role_map_provenance": (
        "A_W07_AS_BUILT_ROLE_RECORD_CONSUMED_BY_ML_FEATURE_REGISTRY_V1; "
        "PHYSICAL_POSITION_VERIFICATION_REMAINS_A_OWNED"
    ),
    "rom_map_unchanged": True,
    "rom_map": {
        "T1": "287088CA00000051",
        "T2": "28AEBF2200000006",
        "T3": "28CBE9CA00000072",
        "SPARE": "283BE5C9000000A9",
    },
    "evaluator_lineage": "feat/a-w21-evidence-final @ 5fd89fb (NOT_ON_MAIN)",
    "independent_evaluator_replay": "INDEPENDENT_EVALUATOR_REPLAY_PENDING",
}

SENSOR_ROLE_MAP = {
    "t1": {
        "physical_position": "CHAMBER_CENTER",
        "rom": "287088CA00000051",
        "chamber_air": True,
    },
    "t2": {
        "physical_position": "TEC_HOT_SIDE",
        "rom": "28AEBF2200000006",
        "chamber_air": False,
    },
    "t3": {
        "physical_position": "CHAMBER_BOTTOM",
        "rom": "28CBE9CA00000072",
        "chamber_air": True,
    },
    "t4": {
        "physical_position": "CHAMBER_NEAR_DOOR",
        "rom": "283BE5C9000000A9",
        "chamber_air": True,
    },
}

EXTERNAL_DEPENDENCIES = {
    "a_w21_evaluator": {
        "state": "NOT_ON_MAIN",
        "lineage": A_SESSION["evaluator_lineage"],
        "independent_replay": A_SESSION["independent_evaluator_replay"],
        "physical_acceptance": "NOT_ISSUED",
    },
    "c_w21": {
        "pr": 98,
        "head": REV_C_W21,
        "base": "feat/c-w20-evidence-freeze @ 659512f91c41deadef036da71544ffa8b6245d93",
        "state": "OPEN_UNMERGED",
        "evidence_class": EVIDENCE_HOST_SOFTWARE_SIMULATION,
        "physical_safe_local": "REFUSED",
        "committed_evidence_artifacts": False,
        "role": "backend/twin/replay implementation; read-only contract reference",
    },
    "c_w16": {
        "pr": 72,
        "head": REV_C_W16,
        "state": "OPEN_UNMERGED",
        "evidence_class": EVIDENCE_HOST_SOFTWARE_SIMULATION,
        "physical_safe_local": "REFUSED",
        "committed_evidence_artifacts": False,
        "role": "outage/reconnect implementation; read-only contract reference",
    },
    "d_policy": {
        "pr": 90,
        "head": REV_D_W13,
        "state": "OPEN_UNMERGED",
        "policy_version": "NOT_FROZEN",
        "evidence_class": EVIDENCE_CONTRACT_REFERENCE,
        "physical_execution": "NOT_VERIFIED",
        "role": "SAFE_LOCAL policy and control authority contract",
    },
}

W21_SOURCE_FILES = (
    ML_ROOT / "src" / "coldguard_ml" / "w21_evidence.py",
    ML_ROOT / "src" / "coldguard_ml" / "w21_diagnosis.py",
    ML_ROOT / "src" / "coldguard_ml" / "w21_resilience.py",
    ML_ROOT / "scripts" / "w21-resilience-audit-W21.py",
    ML_ROOT / "tests" / "test_w21_evidence.py",
    ML_ROOT / "tests" / "test_w21_diagnosis.py",
    ML_ROOT / "tests" / "test_w21_resilience.py",
    ML_ROOT / "tests" / "test_w21_delivery.py",
)

EXPECTED_REPORTS = (
    "diagnosis-table-W21.md",
    "safe-local-summary-W21.md",
    "degraded-sensor-pzem-W21.md",
    "optional-energy-gate-W21.md",
)

PINNED_EARLIER_ARTIFACTS = {
    "reports/W11/benchmark-manifest-W11.json": "855c5beb55f15c6e5bcd38640ff3a6ff02a41a525bf3f1601722abdeca2d47f0",
    "reports/W12/w12-manifest.json": "ef06f9712203b39c01351ad89a17368574e98a0db6436f842e926b68418073a7",
    "reports/W13/horizon-manifest-W13.json": "02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404",
    "reports/W14/w14-manifest.json": "e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d",
    "reports/W15/model/model.ubj": "25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f",
    "reports/W15/model/model-manifest-W15.json": "85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e",
    "reports/W16/locked-test-manifest-W16.json": "6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165",
    "reports/W17/w17-manifest.json": "8b2e92e7c70134e5ab0c6ac796c900b681bc7d66f79eddb48ecc939ddcc33532",
    "reports/W18/w18-manifest.json": "bd1391d72d030af5e0ca99540059424fbf45ca1ccced255e8d41ca374799c9ab",
    "reports/W18/freeze-baseline-W18.json": "d1bcc8ff26ed28ed998fb2c43d7fa57ab928d6c4d90c1af801289016dd446581",
    "reports/W19/w19-manifest.json": "f3bbae932743b4b71c8e8ed7bbbb5334836353080361aa2746c3950cb989db82",
    "reports/W19/campaign-readiness-W19.md": "f554788a441a2eebfc622d3731effc5fa93b010e06ba73a3cb699c6790a7187a",
    "reports/W19/pair-ledger-contract-W19.md": "1cc99bfcf99e2a95e74437c85c28c2c59e37979e272072c52e2f3add4af879df",
    "reports/W19/validity-discipline-W19.md": "e4514e709be0785fefe8da2f8e2f127d607f16a4040c2fdadc309e78e2f62fcf",
    "reports/W19/no-significance-peeking-W19.md": "20cf96565ab478d97e45196768465e6bf808e799c4eb4bccd28c6b22634eb996",
    "reports/W20/w20-manifest.json": "0d8c2ad1cb846599d3535a74ade65186b388702da59eb4bfb0271dcb5a849ece",
    "reports/W20/campaign-metadata-W20.json": "b0c49699036752c8707e650bb4f3b58a3389c12c94ae80106d38b8db94b3076b",
    "reports/W20/campaign-integrity.md": "89c02aa88a77f4b02eac12db92410a2bec84d0d51cd9750a91f5749a1ab9eae5",
    "reports/W20/paired-outcome-contract-W20.md": "2768273d029dc3f0894867e85df3de52a44093bb745e86efdbc6077f61cf08c1",
    "reports/W20/analysis-unlock-W20.md": "cea11179f2d58487dbc2cea5bba610c27bd4a84574b7278a3cfcd6ae43b19376",
}


def _a_records() -> tuple[SourceRecord, ...]:
    identity = {
        "device_id": A_SESSION["device_id"],
        "boot_id": A_SESSION["boot_id"],
        "session_key": A_SESSION_KEY,
    }
    common_session = dict(identity, session=A_SESSION["session"])
    return (
        SourceRecord(
            source_id="A-W21-02-RESULT",
            source_path="evidence/A/W21/results/A-W21-02.json",
            source_revision=REV_A_EVIDENCE,
            source_sha256="4fbc22d3150d3e67a8e1c2556543c454e68e835426d8fd66a3bc0f6949b1682b",
            size_bytes=3785,
            producer="Member A acceptance evaluator (unpublished lineage)",
            identity=dict(common_session, test_id="A-W21-02"),
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            scenario="single DS18B20 role T1 software injection",
            observed_outcome=(
                "T1 explicitly invalid; overall UNKNOWN; thermal DEGRADED; "
                "ROM map unchanged; 25/25 fresh recovery frames; output OFF"
            ),
            admissible_inference=(
                "degraded/unknown quality was represented explicitly",
                "no silent sensor ROM remap",
                "valid acquisition returned from fresh samples",
                "the output stayed OFF in this test configuration",
            ),
            unsupported_inference=(
                "physical DS18B20 cable failure",
                "enabled-actuator fail-safe behaviour",
                "model accuracy under real sensor loss",
                "fault-detection accuracy across independent runs",
            ),
            review_state="RECORDED_PASS_EVALUATOR_NOT_ON_MAIN",
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            in_w20_ancestry=False,
            verified_at_authoring=True,
        ),
        SourceRecord(
            source_id="A-W21-03-RESULT",
            source_path="evidence/A/W21/results/A-W21-03.json",
            source_revision=REV_A_EVIDENCE,
            source_sha256="b8bb30ba309bd90a555bb99d8c30dca289a15fd1559628937bf069142e8c8cdc",
            size_bytes=3273,
            producer="Member A acceptance evaluator (unpublished lineage)",
            identity=dict(common_session, test_id="A-W21-03"),
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            scenario="PZEM transport-boundary software disable",
            observed_outcome=(
                "electrical quality INVALID 24 / VALID 1; overall quality "
                "INVALID 24 / UNKNOWN 1; current missing, never carried "
                "forward; 24/25 fresh recovery frames; output OFF"
            ),
            admissible_inference=(
                "PZEM unavailability was represented explicitly",
                "missing current was not converted into a fresh or zero value",
                "fresh electrical data returned after injection was cleared",
            ),
            unsupported_inference=(
                "physical PZEM or cable disconnection",
                "verified zero current",
                "commanded TEC failing to draw current under an enabled actuator",
                "whole-system power",
                "fault-detection accuracy",
            ),
            review_state="RECORDED_PASS_EVALUATOR_NOT_ON_MAIN",
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            in_w20_ancestry=False,
            verified_at_authoring=True,
        ),
        SourceRecord(
            source_id="A-W21-SESSION-RAW",
            source_path="evidence/A/W21/fault-injection-session-20261108/raw.log",
            source_revision=REV_A_EVIDENCE,
            source_sha256=A_SESSION["raw_log_sha256"],
            size_bytes=A_SESSION["raw_log_bytes"],
            producer="Member A ESP32-S3 UART log",
            identity=common_session,
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            scenario="combined W21-02/W21-03 session in one boot",
            observed_outcome="phase-ordered device log for injection, hold and clear",
            admissible_inference=(
                "raw session bytes and phase order",
                "one boot shared by both test IDs",
            ),
            unsupported_inference=(
                "independent experiments per test ID",
                "physical disconnection",
                "physical thermal recovery",
            ),
            review_state="SOURCE_BYTES_HASH_PINNED",
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            in_w20_ancestry=False,
            verified_at_authoring=True,
        ),
        SourceRecord(
            source_id="A-W21-SESSION-MANIFEST",
            source_path="evidence/A/W21/fault-injection-session-20261108/manifest.json",
            source_revision=REV_A_EVIDENCE,
            source_sha256="1f37024afd676a42970d68ca12250fa37f04836bb4d3b2b77a09e73e1cf514ca",
            size_bytes=1865,
            producer="Member A session recorder",
            identity=common_session,
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            scenario="session identity, firmware image and phase map",
            observed_outcome="boot/hardware/firmware/ROM identity and raw hash declared",
            admissible_inference=("manifest-to-result identity coherence",),
            unsupported_inference=("independent evaluator approval",),
            review_state="MANIFEST_COHERENT_WITH_RESULTS",
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            in_w20_ancestry=False,
            verified_at_authoring=True,
        ),
        SourceRecord(
            source_id="A-W21-SESSION-EVENTS",
            source_path="evidence/A/W21/fault-injection-session-20261108/events.json",
            source_revision=REV_A_EVIDENCE,
            source_sha256="57494aa95d21dc31dd38fd5d372caa4addeb8734aaf635b3663c66408024ce3b",
            size_bytes=656,
            producer="Member A session recorder",
            identity=common_session,
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            scenario="fault injection phase markers",
            observed_outcome="five declared injection/clear events across two scenarios",
            admissible_inference=("phase ordering", "single shared boot"),
            unsupported_inference=("physical fault injection",),
            review_state="EVENT_LIST_BOUND_TO_MANIFEST",
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            in_w20_ancestry=False,
            verified_at_authoring=True,
        ),
        SourceRecord(
            source_id="A-W21-SESSION-SHA256SUMS",
            source_path="evidence/A/W21/fault-injection-session-20261108/SHA256SUMS.txt",
            source_revision=REV_A_EVIDENCE,
            source_sha256="b8f22398e24e21ea5dd2ab8ad93aee006bccc9acd5b5035f083234a3edd9289f",
            size_bytes=235,
            producer="Member A session recorder",
            identity=common_session,
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            scenario="session checksum listing",
            observed_outcome="events/manifest/raw hashes listed",
            admissible_inference=("checksum listing format",),
            unsupported_inference=("independent evaluator approval",),
            review_state="CHECKSUM_LISTING_VERIFIED",
            gate=GATE_BOUNDED_ON_DEVICE_EVIDENCE,
            in_w20_ancestry=False,
            verified_at_authoring=True,
        ),
        SourceRecord(
            source_id="A-W21-README",
            source_path="evidence/A/W21/README.md",
            source_revision=REV_A_EVIDENCE,
            source_sha256="471e6e63f28aed69b0777a11688efc9a9f0711c2a3dd744df518b5dd3a0c03bb",
            size_bytes=2631,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="A-W21 delivery notes and limitation statement",
            observed_outcome="safety limitation and evaluator dependency declared",
            admissible_inference=("author-declared limitations",),
            unsupported_inference=("physical acceptance",),
            review_state="DOCUMENT_REFERENCE",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=False,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
        SourceRecord(
            source_id="A-W21-TOP-SHA256SUMS",
            source_path="evidence/A/W21/SHA256SUMS.txt",
            source_revision=W21_BASE_REVISION,
            source_sha256="3cd6b19b30f1885e555f6171b51cd48986037aa8adbcf752cf8b0c8c0565701b",
            size_bytes=447,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="top-level A-W21 checksum listing",
            observed_outcome="five top-level files hashed",
            admissible_inference=("document checksum listing",),
            unsupported_inference=("physical acceptance",),
            review_state="DOCUMENT_REFERENCE",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=True,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
        SourceRecord(
            source_id="A-W21-SAFE-LOCAL-AUDIT",
            source_path="evidence/A/W21/safe-local-audit.md",
            source_revision=REV_A_EVIDENCE,
            source_sha256="5f77e382b7d1b6ccce706816951e17b0cde42fc75ec32d0df97b3c56e4acc189",
            size_bytes=None,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="SAFE_LOCAL integration support note",
            observed_outcome="status READY_FOR_INTEGRATION; no physical SAFE_LOCAL run",
            admissible_inference=("declared design responsibilities",),
            unsupported_inference=("observed physical SAFE_LOCAL",),
            review_state="READY_FOR_INTEGRATION_ONLY",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=True,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
        SourceRecord(
            source_id="A-W21-DEGRADED-SENSOR-VERIFICATION",
            source_path="evidence/A/W21/degraded-sensor-verification.json",
            source_revision=W21_BASE_REVISION,
            source_sha256="f93d58fca3887c48485a6d717f0113ecf25a78b79c82696dec70f045329b14da",
            size_bytes=None,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="declared degraded-sensor fallback rules",
            observed_outcome="status SOFTWARE_VERIFIED; design rules only",
            admissible_inference=("declared fallback rules",),
            unsupported_inference=("physical measurement", "model robustness"),
            review_state="DESIGN_CONTRACT_ONLY",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=True,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
        SourceRecord(
            source_id="A-W21-PZEM-FAULT-RESPONSE",
            source_path="evidence/A/W21/pzem-fault-response.json",
            source_revision=W21_BASE_REVISION,
            source_sha256="c0c05f412b32192532fd282732476b7af3f3ca37f536587ccd92677c439efdd7",
            size_bytes=None,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="declared PZEM fault response",
            observed_outcome="status SOFTWARE_VERIFIED; design actions only",
            admissible_inference=("declared fault actions",),
            unsupported_inference=("physical actuator response",),
            review_state="DESIGN_CONTRACT_ONLY",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=True,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
        SourceRecord(
            source_id="A-W21-SOAK-PROTOCOL",
            source_path="evidence/A/W21/soak-protocol.md",
            source_revision=W21_BASE_REVISION,
            source_sha256="7c34bbc59d752a81468545f5ad9b247347b9e2343da317666eeab5d4ee346ff5",
            size_bytes=None,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="soak protocol description",
            observed_outcome="protocol only",
            admissible_inference=("protocol description",),
            unsupported_inference=("executed soak result",),
            review_state="PROTOCOL_ONLY",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=True,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
        SourceRecord(
            source_id="A-W21-VALIDATE-SCRIPT",
            source_path="evidence/A/W21/validate_w21.py",
            source_revision=W21_BASE_REVISION,
            source_sha256="e63198127dc38b24796af926a07706dcad8ad2c94fb6a0cb601df94a4a1d6bbb",
            size_bytes=None,
            producer="Member A",
            identity={"session_key": "a-w21-documents"},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario="A-W21 validation helper",
            observed_outcome="tooling reference",
            admissible_inference=("validation tooling exists",),
            unsupported_inference=("independent evaluator approval",),
            review_state="TOOLING_REFERENCE",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=True,
            verified_at_authoring=True,
            measurement_bearing=False,
        ),
    )


def _reference_records() -> tuple[SourceRecord, ...]:
    def ref(
        source_id: str,
        path: str,
        revision: str,
        digest: str,
        producer: str,
        scenario: str,
        outcome: str,
        admissible: tuple[str, ...],
        unsupported: tuple[str, ...],
    ) -> SourceRecord:
        return SourceRecord(
            source_id=source_id,
            source_path=path,
            source_revision=revision,
            source_sha256=digest,
            size_bytes=None,
            producer=producer,
            identity={"session_key": source_id.lower()},
            evidence_class=EVIDENCE_CONTRACT_REFERENCE,
            scenario=scenario,
            observed_outcome=outcome,
            admissible_inference=admissible,
            unsupported_inference=unsupported,
            review_state="PINNED_CONTRACT_REFERENCE",
            gate=GATE_CONTRACT_REFERENCE_ONLY,
            in_w20_ancestry=False,
            verified_at_authoring=True,
            measurement_bearing=False,
        )

    return (
        ref(
            "C-W21-INCIDENT-AUDIT",
            "backend/src/coldguard_backend/incident_audit.py",
            REV_C_W21,
            "5bff7345c22f4aae95fe8638a2f0ebd43591f2e521efa492214ac78396852033",
            "Member C",
            "read-only incident package builder",
            "software implementation; no committed evidence artifact",
            ("event/incident field mapping", "duplicate/replay semantics"),
            ("physical SAFE_LOCAL", "accepted physical resilience"),
        ),
        ref(
            "C-W21-RESILIENCE-DOC",
            "backend/RESILIENCE.md",
            REV_C_W21,
            "c93dd7fcf4eb0caae692ffc67281d212d612eba41044b004340e39f12e9ea4a0",
            "Member C",
            "W21 resilience/security audit notes",
            "declares SOFTWARE_SIMULATION and BLOCKED_EXTERNAL",
            ("software evidence boundary",),
            ("physical SAFE_LOCAL",),
        ),
        ref(
            "C-W21-INCIDENT-TEST",
            "backend/tests/test_incident_audit.py",
            REV_C_W21,
            "ba8133728568574684a0f2faeeba1cdaf68acc8c0dc87475dbf14a6bc4f6211e",
            "Member C",
            "software incident audit tests",
            "software assertions only",
            ("declared software checks",),
            ("physical acceptance",),
        ),
        ref(
            "C-W16-RECOVERY",
            "backend/src/coldguard_backend/recovery.py",
            REV_C_W16,
            "76dd7ef0dabaa32212c2e2b3f587f82f665f78617903ab5d51e78196e4cc0adc",
            "Member C",
            "outage/reconnect backend recovery",
            "software implementation; unmerged",
            ("resync contract fields",),
            ("physical SAFE_LOCAL",),
        ),
        ref(
            "C-W16-RECOVERY-DOC",
            "backend/PLATFORM_RECOVERY.md",
            REV_C_W16,
            "de8138e0a57efcd1c94de958cb6b34cf316726ed45dfac651eef8f8f4815e52d",
            "Member C",
            "platform recovery notes",
            "software contract",
            ("reconnect discipline",),
            ("physical resilience result",),
        ),
        ref(
            "C-W16-OUTAGE-TEST",
            "backend/tests/test_outage_recovery.py",
            REV_C_W16,
            "b7fdcd85c7450772dc78f440b21a2a2b55dbc1af87bf6d0137ce97bc5b5eb18d",
            "Member C",
            "software outage recovery tests",
            "software assertions only",
            ("command expiry/reconnect checks",),
            ("physical acceptance",),
        ),
        ref(
            "D-POLICY",
            "control/src/coldguard_control/policy.py",
            REV_D_W13,
            "b6db9d2bcee057372d2c60dacc4f093af37493af17a54a291446070bbe747d8f",
            "Member D",
            "pure policy and safety gate",
            "declared policy contract; thresholds not frozen",
            ("reason/state vocabulary", "SAFE_LOCAL exit gate"),
            ("observed physical execution",),
        ),
        ref(
            "D-SAFE-LOCAL",
            "control/src/coldguard_control/safe_local.py",
            REV_D_W13,
            "9e039d58ab2acd22fdbddb17b4da94b95aacda061ad86fe3dbda0882abf0a693",
            "Member D",
            "SAFE_LOCAL session semantics",
            "declared session contract",
            ("entry/exit bookkeeping semantics",),
            ("physical thermal protection",),
        ),
        ref(
            "D-TYPES",
            "control/src/coldguard_control/types.py",
            REV_D_W13,
            "787febc8f108466c7f4c806446bfe89845aec939f519cb82af30c307042c5f47",
            "Member D",
            "quality/state/model-health vocabulary",
            "declared vocabulary",
            ("UNKNOWN semantics", "model health fallback"),
            ("observed execution",),
        ),
        ref(
            "D-CONFIG",
            "control/src/coldguard_control/config.py",
            REV_D_W13,
            "d821ee231b57b1151bc0185aca77c9520c9336e109eb67a9aa40c71b92248505",
            "Member D",
            "versioned policy configuration",
            "no frozen final policy version",
            ("policy_version requirement",),
            ("frozen threshold values",),
        ),
        ref(
            "D-W02-POLICY-STATES",
            "evidence/D/W02/policy-states.md",
            REV_D_W13,
            "1787eace821d78c43f12d42a2d7098ed25ce165bb58a58b0ef08741b5c0a532f",
            "Member D",
            "policy-state design contract",
            "design contract only",
            ("state precedence",),
            ("physical result",),
        ),
        ref(
            "D-W03-FAILURE-TAXONOMY",
            "evidence/D/W03/failure-taxonomy.md",
            REV_D_W13,
            "e88848d5b50228b3123045c96c0f825f07f8b6a75bc6d58a006b2fb5eaf42c7d",
            "Member D",
            "failure disposition taxonomy",
            "declared dispositions; NOT_CONTRACTED rules explicit",
            ("failure dispositions",),
            ("automatic policy action for NOT_CONTRACTED"),
        ),
        ref(
            "D-W11-DIAGNOSIS-HANDOFF",
            "evidence/D/W11/diagnosis-event-handoff.md",
            REV_D_W13,
            "6286ec9c56ad7eaa038853e2449c6384a5ef58c2a32f0a0a60fddec8fe493aaa",
            "Member D",
            "diagnosis event handoff contract",
            "contract proposed; C persistence OPEN",
            ("event field contract", "ACK is not physical proof"),
            ("end-to-end persisted event",),
        ),
    )


def source_register() -> tuple[SourceRecord, ...]:
    return _a_records() + _reference_records()


def _a_cases() -> tuple[DiagnosisCase, ...]:
    return (
        DiagnosisCase(
            case_id="A-W21-02",
            condition=(
                "single DS18B20 chamber-air role T1 software injection on the "
                "real ESP32-S3"
            ),
            ground_truth_source=GROUND_TRUTH_CONTROLLED_INJECTION,
            injection_ref=(
                "evidence/A/W21/fault-injection-session-20261108/events.json"
                "::B_ds_t1_on"
            ),
            command_state=COMMAND_OFF,
            ack_observed=False,
            output_stage=OUTPUT_STAGE_DISABLED,
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
            current_value_a=None,
            thermal_quality=QUALITY_DEGRADED,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            observed_invalid_channels=("T1",),
            recovery_observed=True,
            frames=25,
            source_sha256=(
                "4fbc22d3150d3e67a8e1c2556543c454e68e835426d8fd66a3bc0f6949b1682b"
            ),
            device_id=A_SESSION["device_id"],
            boot_id=A_SESSION["boot_id"],
            session_id=A_SESSION["session"],
            expected_classification=CLASS_DEGRADED_OR_UNKNOWN,
            unsupported_conclusions=(
                "PHYSICAL_DS18B20_FAILURE",
                "MODEL_ROBUSTNESS_UNDER_SENSOR_LOSS",
                "FAULT_DETECTION_ACCURACY",
                "ENABLED_ACTUATOR_FAIL_SAFE",
            ),
            notes=(
                "TEC OFF; output stage compiled out; fuse OUT; no physical "
                "disconnection; one boot shared with A-W21-03."
            ),
        ),
        DiagnosisCase(
            case_id="A-W21-03",
            condition="PZEM transport-boundary software disable",
            ground_truth_source=GROUND_TRUTH_CONTROLLED_INJECTION,
            injection_ref=(
                "evidence/A/W21/fault-injection-session-20261108/events.json"
                "::C_pzem_on"
            ),
            command_state=COMMAND_OFF,
            ack_observed=False,
            output_stage=OUTPUT_STAGE_DISABLED,
            electrical_quality=QUALITY_INVALID,
            current_measurement=CURRENT_MISSING,
            current_value_a=None,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_INVALID,
            observed_invalid_channels=(),
            recovery_observed=True,
            frames=25,
            source_sha256=(
                "b8bb30ba309bd90a555bb99d8c30dca289a15fd1559628937bf069142e8c8cdc"
            ),
            device_id=A_SESSION["device_id"],
            boot_id=A_SESSION["boot_id"],
            session_id=A_SESSION["session"],
            expected_classification=CLASS_DEGRADED_OR_UNKNOWN,
            unsupported_conclusions=(
                "PHYSICAL_PZEM_DISCONNECTION",
                "VERIFIED_ZERO_CURRENT",
                "WHOLE_SYSTEM_POWER",
                "ENABLED_ACTUATOR_ELECTRICAL_RESPONSE",
                "FAULT_DETECTION_ACCURACY",
            ),
            notes=(
                "TEC OFF; output stage compiled out; fuse OUT; electrical "
                "INVALID 24 / VALID 1, overall INVALID 24 / UNKNOWN 1; the "
                "PZEM fault is a software transport disable, not a physical "
                "failure."
            ),
        ),
    )


def canonical_diag_rows() -> tuple[dict[str, str], ...]:
    return (
        {
            "case_id": DIAG_01,
            "condition": "healthy",
            "expected": CLASS_HEALTHY_RESPONSE,
            "status": METRIC_NOT_ESTIMABLE,
            "reason": "NO_ENABLED_ACTUATOR_OBSERVATION",
        },
        {
            "case_id": DIAG_02,
            "condition": "electrical response missing",
            "expected": CLASS_ELECTRICAL_RESPONSE_MISSING,
            "status": METRIC_NOT_ESTIMABLE,
            "reason": (
                "NO_ENABLED_ACTUATOR_OBSERVATION; A-W21-03 IS A PZEM TRANSPORT "
                "DISABLE, NOT A COMMANDED TEC FAILING TO DRAW CURRENT"
            ),
        },
        {
            "case_id": DIAG_03,
            "condition": "unexpected current while OFF",
            "expected": CLASS_UNEXPECTED_OFF_CURRENT,
            "status": METRIC_NOT_ESTIMABLE,
            "reason": "NO_OBSERVED_OFF_WITH_CURRENT",
        },
        {
            "case_id": DIAG_04,
            "condition": "degraded thermal effectiveness",
            "expected": CLASS_DEGRADED_THERMAL_EFFECTIVENESS,
            "status": METRIC_NOT_ESTIMABLE,
            "reason": "NO_SAFE_PHYSICAL_DEGRADATION_OBSERVATION",
        },
    )


def a_w21_timeline() -> ResilienceTimeline:
    return ResilienceTimeline(
        scenario_id="A-W21-02_03-SESSION",
        source_id="A-W21-SESSION-RAW",
        device_id=A_SESSION["device_id"],
        boot_id=A_SESSION["boot_id"],
        time_domain=TIME_DEVICE_CAPTURED_AT,
        source_hash=A_SESSION["raw_log_sha256"],
        evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
        local_control_state="NOT_RECORDED",
        physical_electrical_state=PHYSICAL_STATE_NOT_VERIFIED,
        physical_thermal_state=PHYSICAL_STATE_NOT_VERIFIED,
    )


def software_fixture_timeline() -> ResilienceTimeline:
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ResilienceTimeline(
        scenario_id="TEST_ONLY_TIMELINE_FIXTURE",
        source_id="W21-SOFTWARE-FIXTURE",
        device_id="fixture-device",
        boot_id="fixture-boot",
        time_domain=TIME_SOFTWARE_SIMULATION_CLOCK,
        source_hash=sha256_bytes(b"w21-software-fixture-timeline"),
        evidence_class=EVIDENCE_HOST_SOFTWARE_SIMULATION,
        outage_start=origin,
        outage_end=origin.replace(minute=2),
        outage_detection=origin.replace(second=10),
        safe_local_entered=origin.replace(second=10),
        safe_local_exited=origin.replace(minute=1, second=50),
        local_control_state="REACTIVE_HYSTERESIS",
        physical_electrical_state=PHYSICAL_STATE_NOT_VERIFIED,
        physical_thermal_state=PHYSICAL_STATE_NOT_VERIFIED,
        reconnect_observed=origin.replace(minute=1, second=50),
        fresh_state_confirmed=True,
        resync_completed=origin.replace(minute=2, second=10),
        stale_command_rejected=True,
    )


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"expected an object: {path}")
    return payload


def _input_record(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(ML_ROOT).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _analysis_code_sha256() -> str:
    digest = hashlib.sha256()
    for path in W21_SOURCE_FILES:
        digest.update(path.relative_to(ML_ROOT).as_posix().encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"ABSENT")
    return digest.hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _evidence_rows(table) -> list[dict[str, Any]]:
    return [assessment.to_dict() for assessment in table.cases]


def _diagnosis_report(
    table,
    canonical_rows: Sequence[Mapping[str, str]],
    admissions: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# W21 Diagnosis Table (B-W21-01)",
        "",
        "Evidence class: `ON_DEVICE_SOFTWARE_INJECTION` for the two recorded cases; "
        "`SOFTWARE_TEST_ONLY` for the contract controls. The actuator output stage "
        "was compiled out, the fuse was OUT and the TEC was OFF throughout.",
        "",
        "Scope: non-primary diagnosis evidence only. No model retraining, no "
        "threshold/horizon/persistence change and no physical acceptance.",
        "",
        "## Source-bound recorded cases",
        "",
        "| Case | Condition | Ground truth | Measurement evidence | Quality | Expected | Observed | Concordance | Independent sessions | Source SHA-256 |",
        "|---|---|---|---|---|---|---|---|---:|---|",
    ]
    case_notes = {
        "A-W21-02": (
            "25 frames; T1 explicitly invalid; overall UNKNOWN; thermal DEGRADED; "
            "ROM map unchanged; 25/25 valid recovery frames"
        ),
        "A-W21-03": (
            "25 frames; electrical INVALID 24 / VALID 1; overall INVALID 24 / "
            "UNKNOWN 1; current missing; never carried forward; 24/25 valid "
            "recovery frames"
        ),
    }
    for assessment, case in zip(table.cases, _a_cases()):
        lines.append(
            "| {case_id} | {condition} | {truth} ({ref}) | {evidence} | {quality} | "
            "{expected} | {observed} | {concordance} | {sessions} | `{sha}` |".format(
                case_id=assessment.case_id,
                condition=case.condition,
                truth=case.ground_truth_source,
                ref=case.injection_ref or "NONE",
                evidence=case_notes[assessment.case_id],
                quality=(
                    f"overall={case.overall_quality}; thermal={case.thermal_quality}; "
                    f"electrical={case.electrical_quality}; current={case.current_measurement}"
                ),
                expected=assessment.expected_classification,
                observed=assessment.classification,
                concordance=assessment.concordance,
                sessions=assessment.independent_session_count,
                sha=case.source_sha256,
            )
        )
    lines.extend(
        [
            "",
            "Expected classifications are derived from the recorded injection "
            "condition and the canonical DIAG mapping; they are not an "
            "independent external evaluator label. Concordance is bounded to "
            "these two controlled cases and is not a population accuracy estimate.",
            "",
            "## Canonical DIAG-01..04 comparison",
            "",
        ]
    )
    lines.extend(
        [
            "| Case | Condition | Expected | Status | Reason |",
            "|---|---|---|---|---|",
        ]
    )
    for row in canonical_rows:
        lines.append(
            "| {case_id} | {condition} | {expected} | {status} | {reason} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "The recorded session contains no healthy enabled-actuator observation. "
            "The DIAG-01/02 actuator-response comparison is therefore left "
            "unestimated; A-W21-03 is a PZEM transport disable under an "
            "output-disabled configuration, not a commanded TEC failing to draw "
            "current.",
            "",
            "## Evidence levels",
            "",
            "| Case | Levels supported |",
            "|---|---|",
        ]
    )
    for assessment in table.cases:
        lines.append(
            "| {case_id} | {levels} |".format(
                case_id=assessment.case_id,
                levels=", ".join(assessment.evidence_levels),
            )
        )
    lines.extend(
        [
            "",
            "`ROOT_CAUSE_IDENTIFICATION` is never supported by a single observation.",
            "",
            "## Refusal and control catalogue",
            "",
            "Classifier-emitted refusals are listed first; rows marked "
            "`(control)` are driver-level probes, not classifier outputs.",
            "",
            "| Refusal | Applied to |",
            "|---|---|",
        ]
    )
    refusal_sources: dict[str, list[str]] = {}
    for assessment in table.cases:
        for refusal in assessment.refusals:
            refusal_sources.setdefault(refusal, []).append(assessment.case_id)
    for refusal, cases in sorted(refusal_sources.items()):
        lines.append(f"| `{refusal}` | {', '.join(cases)} |")
    for name, refusal in required_negative_cases():
        if refusal not in refusal_sources:
            lines.append(f"| `{refusal}` | {name} (control) |")
    lines.extend(
        [
            "",
            "## Unsupported conclusions",
            "",
        ]
    )
    unsupported: set[str] = set()
    for case in _a_cases():
        unsupported.update(case.unsupported_conclusions)
    for item in sorted(unsupported):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Population metrics",
            "",
            "| Metric | Value | Reason |",
            "|---|---|---|",
        ]
    )
    for name, reason in table.metric_reasons.items():
        lines.append(f"| {name} | {table.metrics[name]} | `{reason}` |")
    lines.extend(
        [
            "",
            "## Independence",
            "",
            f"- Recorded injection-window frames: {table.record_count} (25 + 25).",
            f"- Recorded recovery frames: {A_SESSION['recovery_frames']} (25 + 25).",
            f"- Total recorded frames: {A_SESSION['total_recorded_frames']}.",
            f"- Independent on-device session count: {table.independent_session_count}.",
            "- A-W21-02 and A-W21-03 share boot `4cf9be5f`, one raw log and one "
            "combined session; they are not two independent physical experiments.",
            "- The acceptance evaluator lineage is not on main; independent "
            "evaluator replay remains pending.",
            "",
        ]
    )
    return "\n".join(lines)


def _safe_local_report(a_assessment, fixture_assessment) -> str:
    lines = [
        "# W21 SAFE_LOCAL Outcome Summary (B-W21-02)",
        "",
        "Scope: outage interval, physical state, recovery and resynchronization "
        "for admitted resilience evidence. Software-state transitions are not "
        "physical thermal protection.",
        "",
        "## A-W21 recorded session",
        "",
        "| Timeline field | Status |",
        "|---|---|",
        "| outage_start | MISSING |",
        "| outage_end | MISSING |",
        "| outage_detection | MISSING |",
        "| SAFE_LOCAL_entered | MISSING |",
        "| local_control_state | RECORDED AS NOT_RECORDED |",
        "| physical_electrical_state | NOT_VERIFIED |",
        "| physical_thermal_state | NOT_VERIFIED |",
        "| reconnect_observed | MISSING |",
        "| fresh_state_confirmed | MISSING |",
        "| resync_completed | MISSING |",
        "| stale_command_rejected | MISSING |",
        "",
        "Assessment statuses: {}.".format(
            ", ".join(f"`{status}`" for status in a_assessment.statuses)
        ),
        "",
        "No outage, detection, SAFE_LOCAL or resync duration is computed for the "
        "recorded session. A missing event is not assigned a time value.",
        "",
        "## Software fixture control (TEST_ONLY)",
        "",
        "The fixture exercises the timeline contract in a host process. It is "
        "permanently labelled `HOST_SOFTWARE_SIMULATION` and is not device "
        "evidence.",
        "",
        "| Duration | Seconds | Class |",
        "|---|---:|---|",
    ]
    for name, value in fixture_assessment.durations.items():
        lines.append(
            f"| {name} | {value['value_s']:.0f} | `{value['duration_class']}` |"
        )
    lines.extend(
        [
            "",
            "Fixture statuses: {}.".format(
                ", ".join(f"`{status}`" for status in fixture_assessment.statuses)
            ),
            "",
            "The fixture cannot claim physical thermal protection: "
            f"{fixture_assessment.physical_thermal_protection}.",
            "",
            "## External dependencies",
            "",
            "| Member | Source | State | Permitted use | Refused claim |",
            "|---|---|---|---|---|",
            "| C | PR #98 `feat/c-w21-resilience-security` | OPEN / UNMERGED | "
            "event/incident field mapping; software replay assertions | physical "
            "SAFE_LOCAL |",
            "| C | PR #72 `feat/c-w16-outage-resynchronization` | OPEN / UNMERGED | "
            "command expiry and resync contract | physical SAFE_LOCAL |",
            "| D | PR #90 `feat/d-w13-aiw-readiness` | OPEN / UNMERGED | SAFE_LOCAL "
            "policy contract | observed physical execution |",
            "| A | `safe-local-audit.md` | READY_FOR_INTEGRATION | declared design "
            "responsibilities | physical SAFE_LOCAL run |",
            "",
            "D's final policy version is NOT_FROZEN. C's W21/W16 evidence is host "
            "software simulation and is not committed as an evidence artifact.",
            "",
            "## Replay and recovery checks",
            "",
            "| Check | Required semantics |",
            "|---|---|",
            "| duplicate telemetry | one normalized sample; duplicate count retained |",
            "| out-of-order sequence | order violation visible; no silent reordering |",
            "| boot change | new stream identity; no cross-boot sequence merge |",
            "| reconnect replay | historical records do not regress the current twin |",
            "| stale command | expired/duplicate desired state is not applied |",
            "| receipt time | never substituted for device event time |",
            "| AI unavailable | Controller A/local fallback; no indefinite old score |",
            "| SAFE_LOCAL exit | requires fresh state, synced backend and no stale command |",
            "",
            "## Physical conclusion",
            "",
            "```text",
            "A_W21_OUTAGE = OUTAGE_NOT_OBSERVED",
            "A_W21_SAFE_LOCAL = SAFE_LOCAL_STATE_NOT_VERIFIED",
            "A_W21_PHYSICAL_CONTROL = PHYSICAL_CONTROL_NOT_VERIFIED",
            "A_W21_RESYNC = RESYNC_NOT_VERIFIED",
            "PHYSICAL_SAFE_LOCAL = NOT_ESTABLISHED",
            "COMBINED_LATENCY_DISTRIBUTION = NOT_CREATED",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _degraded_report(table) -> str:
    lines = [
        "# W21 Degraded Sensor and PZEM Assessment (B-W21-03)",
        "",
        "## Current sensor role map",
        "",
        "| Slot | Physical position | ROM | Chamber-air aggregate |",
        "|---|---|---|---|",
    ]
    for slot, info in SENSOR_ROLE_MAP.items():
        lines.append(
            f"| {slot} | {info['physical_position']} | `{info['rom']}` | "
            f"{info['chamber_air']} |"
        )
    lines.extend(
        [
            "",
            "`T2` is `TEC_HOT_SIDE`. It is never substituted for a missing "
            "chamber-air role.",
            "",
            "Provenance: this is the as-built A W07 role record consumed by "
            "`ml/feature-registry-v1.yaml`. It is a role record, not an "
            "independently measured calibration; physical position verification "
            "remains A-owned. An earlier A W02 assignment listed T1/T2/T3 "
            "positions differently and is superseded by the as-built record. "
            "The W21 refusal uses only the current registry: a missing "
            "chamber-air role is not replaced by the hot-side role.",
            "",
            "## Recorded observations",
            "",
            "| Item | A-W21-02 | A-W21-03 |",
            "|---|---|---|",
            "| Injected condition | DS18B20 T1 software injection | PZEM transport "
            "software disable |",
            "| Frames | 25 | 25 |",
            "| Explicit invalid role/channel | T1 | electrical quality |",
            "| Overall quality | UNKNOWN 25 | INVALID 24, UNKNOWN 1 |",
            "| Thermal / electrical | DEGRADED 25 | electrical INVALID 24, "
            "VALID 1; thermal not recorded |",
            "| Current | UNKNOWN | MISSING 24 |",
            "| Recovery | 25/25 valid frames | 24/25 valid frames |",
            "| Output state | OFF, stage compiled out | OFF, stage compiled out |",
            "| ROM map | unchanged | unchanged |",
            "",
            "## Missingness and quality rules",
            "",
            "| Prohibited conversion | Enforced behaviour |",
            "|---|---|",
            "| missing chamber-air sensor replaced by T2 | refused; T2 is hot-side |",
            "| hidden ROM remap | refused; role map must remain stable |",
            "| UNKNOWN door converted to CLOSED | normalized to UNKNOWN |",
            "| invalid temperature converted to a number | normalized to null |",
            "| stale PZEM carried forward | measurement missing |",
            "| missing current converted to 0 A | measurement missing |",
            "| missing power integrated as zero energy | energy missing |",
            "| energy counter reset hidden | reset detected; no negative delta |",
            "| recovery inferred without fresh samples | refused |",
            "| degraded-model inference without validation | refused |",
            "| W21 fault evidence used as training data | refused |",
            "",
            "## Model and feature consequence",
            "",
            "The W15 model is a synthetic, nondeployable candidate; no "
            "degraded-feature validation exists and the final policy version is "
            "NOT_FROZEN. Under a missing required chamber-air channel or an "
            "invalid electrical channel, predictive inference must be refused or "
            "disabled and Controller A/local semantics apply. W21 does not claim "
            "positive model robustness under real sensor loss.",
            "",
            "## Source binding",
            "",
            "| Binding | Value |",
            "|---|---|",
            f"| Firmware image SHA-256 | `{A_SESSION['firmware_binary_sha256']}` |",
            f"| Device / boot | `{A_SESSION['device_id']}` / `{A_SESSION['boot_id']}` |",
            f"| Hardware config | `{A_SESSION['hardware_config_id']}` |",
            f"| Firmware version | `{A_SESSION['firmware_version']}` |",
            f"| Raw log SHA-256 | `{A_SESSION['raw_log_sha256']}` |",
            "| Test mechanism | on-device software injection |",
            "| Output-stage limitation | compiled out; fuse OUT; TEC OFF |",
            "| Physical disconnection | NONE |",
            "",
            "## Descriptive counts",
            "",
            f"- Fault-window frames: {A_SESSION['fault_window_frames']} "
            "(25 + 25).",
            f"- Recovery frames: {A_SESSION['recovery_frames']} (25 + 25).",
            f"- Total recorded frames: {A_SESSION['total_recorded_frames']}.",
            f"- Independent on-device sessions: {table.independent_session_count}.",
            "- Explicit degraded/unknown states: 50 frames across two test IDs.",
            "- Documented fresh recoveries: 2 (25/25 and 24/25 valid frames).",
            "- These are descriptive source-bound counts, not physical reliability rates.",
            "",
            "```text",
            "diagnostic_accuracy = NOT_ESTIMABLE",
            "fault_recall = NOT_ESTIMABLE",
            "real_model_robustness = NOT_ESTABLISHED",
            "physical_cooling_response = NOT_ESTABLISHED",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _gate_f_report(gate_f) -> str:
    lines = [
        "# W21 Optional Energy Gate (B-W21-04)",
        "",
        "```text",
        f"GATE_F = {gate_f.status}",
        f"B_W21_04 = {gate_f.optional_deliverable}",
        "ENERGY_ANALYSIS = NOT_PERFORMED",
        "PWM_CHARACTERIZATION = NOT_PERFORMED",
        "DUTY_CYCLE_SEARCH = NOT_PERFORMED",
        "ENERGY_SAVINGS_CLAIM = NONE",
        "```",
        "",
        "## Why the optional scope is closed",
        "",
    ]
    for reason in gate_f.reasons:
        lines.append(f"- `{reason}`")
    lines.extend(
        [
            "",
            "The canonical condition is an authorized optional scope after core "
            "evidence is complete (Doc 03 Gate F; Doc 04 W21 optional opening; "
            "Doc 05B B-W21-04). No authoritative authorization artifact bound to "
            "bytes exists, and core evidence is incomplete.",
            "",
            "## Measurement boundary",
            "",
            "```text",
            "PZEM_ENERGY_SCOPE = COOLING_BRANCH_ONLY",
            "WHOLE_SYSTEM_ENERGY = NOT_MEASURED",
            "PWM_POWER_STATUS = CHARACTERIZATION_REQUIRED",
            "```",
            "",
            "No synthetic branch-power example is reported as measured energy.",
            "",
        ]
    )
    return "\n".join(lines)


def _cross_check_a_session(root: Path) -> bool:
    """Cross-check the pinned result/manifest identities from actual bytes."""
    base = Path(root) / "evidence" / "A" / "W21"
    try:
        result_02 = json.loads(
            (base / "results" / "A-W21-02.json").read_text(encoding="utf-8")
        )
        result_03 = json.loads(
            (base / "results" / "A-W21-03.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (
                base
                / "fault-injection-session-20261108"
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return False
    identity = manifest.get("identity", {})
    expected_roms = {
        "T1": identity.get("t1_rom"),
        "T2": identity.get("t2_rom"),
        "T3": identity.get("t3_rom"),
        "SPARE": identity.get("spare_rom"),
    }
    if not all(expected_roms.values()):
        return False
    for result in (result_02, result_03):
        device = result.get("device_identity", {})
        if device.get("boot_id") != identity.get("boot_id"):
            return False
        if device.get("device_id") != identity.get("device_id"):
            return False
        if device.get("hardware_config_id") != identity.get("hardware_config_id"):
            return False
        if device.get("firmware_version") != identity.get("firmware_version"):
            return False
        evidence = result.get("evidence", [])
        raw = [
            entry
            for entry in evidence
            if str(entry.get("stored", "")).replace("\\", "/").endswith("raw.log")
        ]
        if len(raw) != 1 or raw[0].get("sha256") != manifest.get("raw_log_sha256"):
            return False
        if result.get("measurements", {}).get("evidence_mode") != manifest.get(
            "evidence_mode"
        ):
            return False
    if result_02.get("started_at") != result_03.get("started_at"):
        return False
    if result_02.get("ended_at") != result_03.get("ended_at"):
        return False
    measurements = result_02.get("measurements", {})
    return measurements.get("baseline_rom_map") == expected_roms and (
        measurements.get("rom_roles") == expected_roms
    )


def _admission_rows(
    records, verify_root: Path | None
) -> list[dict[str, Any]]:
    cross_checked = (
        _cross_check_a_session(verify_root) if verify_root is not None else None
    )
    rows = []
    for record in records:
        root = None
        if record.in_w20_ancestry:
            root = REPO_ROOT
        elif record.source_path.startswith("evidence/A/W21/") and verify_root:
            root = verify_root
        coherent = None
        recorded = None
        if cross_checked is not None and record.measurement_bearing and (
            record.source_id.startswith("A-W21")
        ):
            coherent = cross_checked
            if record.source_id.endswith("-RESULT"):
                recorded = cross_checked
        admission = admit_source(
            record,
            root=root,
            manifest_coherent=coherent,
            recorded_check_passed=recorded,
        )
        rows.append(admission.to_dict())
    return rows


def _session_identity_matches(boot_id: str, manifest_boot_id: str) -> bool:
    return bool(boot_id) and boot_id == manifest_boot_id


def run_adversarial_controls(
    table,
    records,
    admissions,
    fixture_assessment,
    diagnosis_cases,
    *,
    g4: str,
    g5: str,
    w16: str,
    w20_analysis: str,
    w15_synthetic: bool,
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []

    def check(name: str, expectation: str, passed: bool) -> None:
        probes.append(
            {"name": name, "expectation": expectation, "passed": bool(passed)}
        )

    by_id = {row["source_id"]: row for row in admissions}
    a_result = by_id["A-W21-02-RESULT"]
    a03_result = by_id["A-W21-03-RESULT"]
    case_02, case_03 = diagnosis_cases

    check(
        "authentic_on_device_injection_classified",
        "the A-W21 result remains ON_DEVICE_SOFTWARE_INJECTION",
        next(r for r in records if r.source_id == "A-W21-02-RESULT").evidence_class
        == EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
    )
    check(
        "host_simulation_not_on_device",
        "host simulation cannot be promoted to on-device evidence",
        assess_class_promotion(
            EVIDENCE_HOST_SOFTWARE_SIMULATION,
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
        )
        == "EVIDENCE_CLASS_PROMOTION_REFUSED",
    )
    check(
        "injection_not_physical_disconnect",
        "on-device injection cannot be promoted to physical response",
        assess_class_promotion(
            EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
        )
        == "EVIDENCE_CLASS_PROMOTION_REFUSED",
    )
    disabled_claim = classify_case(
        replace(
            case_03,
            case_id="PROBE-OUTPUT-DISABLED",
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=0.0,
        )
    )
    check(
        "output_disabled_not_enabled_validation",
        "an output-disabled case cannot become a missing electrical response",
        disabled_claim.classification != CLASS_ELECTRICAL_RESPONSE_MISSING
        and REFUSAL_OUTPUT_STAGE_DISABLED in disabled_claim.refusals,
    )
    check(
        "shared_boot_not_independent",
        "two test IDs from one boot count as one independent session",
        table.independent_session_count == 1
        and A_SESSION["independent_session_count"] == 1,
    )
    raw_record = next(r for r in records if r.source_id == "A-W21-SESSION-RAW")
    check(
        "raw_log_hash_mismatch_refused",
        "tampered bytes fail the pinned raw-log hash",
        not source_bytes_match(raw_record, b"tampered-w21-log"),
    )
    check(
        "manifest_result_identity_mismatch_refused",
        "a mismatched boot identity fails the manifest/result check",
        not _session_identity_matches("deadbeef", A_SESSION["boot_id"]),
    )
    check(
        "unmerged_c_not_physical",
        "unmerged C software evidence cannot be reported as physical",
        assess_class_promotion(
            EVIDENCE_HOST_SOFTWARE_SIMULATION,
            EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
        )
        == "EVIDENCE_CLASS_PROMOTION_REFUSED",
    )
    check(
        "pass_field_not_authority",
        "a recorded PASS does not verify evaluator authority",
        a_result["checks"][PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED]
        != "VERIFIED",
    )
    check(
        "missing_physical_not_negative",
        "missing resilience fields yield NOT_VERIFIED, not a negative result",
        STATUS_OUTAGE_NOT_OBSERVED
        in assess_timeline(a_w21_timeline()).statuses,
    )

    on_without_current = classify_case(
        replace(
            case_03,
            case_id="PROBE-ON-NO-CURRENT",
            command_state=COMMAND_ON,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
        )
    )
    check(
        "command_on_not_current",
        "a command ON alone is not measured current",
        on_without_current.classification != CLASS_HEALTHY_RESPONSE
        and REFUSAL_ELECTRICAL_UNAVAILABLE in on_without_current.refusals,
    )
    ack_case = classify_case(
        replace(
            case_03,
            case_id="PROBE-ACK",
            command_state=COMMAND_ON,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
            ack_observed=True,
        )
    )
    check(
        "ack_not_physical_response",
        "an ACK is not an applied-power observation",
        REFUSAL_ACK_NOT_EVIDENCE in ack_case.refusals,
    )
    current_thermal = classify_case(
        replace(
            case_02,
            case_id="PROBE-CURRENT-NO-THERMAL",
            command_state=COMMAND_ON,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_NONZERO,
            current_value_a=1.0,
            thermal_quality=QUALITY_VALID,
            thermal_response=THERMAL_ABSENT,
            overall_quality=QUALITY_VALID,
            observed_invalid_channels=(),
        )
    )
    check(
        "current_without_thermal",
        "current flow with absent thermal response is degraded effectiveness",
        current_thermal.classification == CLASS_DEGRADED_THERMAL_EFFECTIVENESS,
    )
    unknown_healthy = classify_case(
        replace(
            case_02,
            case_id="PROBE-UNKNOWN",
            command_state=COMMAND_ON,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_UNKNOWN,
            current_measurement=CURRENT_UNKNOWN,
            thermal_quality=QUALITY_UNKNOWN,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_UNKNOWN,
            observed_invalid_channels=(),
        )
    )
    check(
        "unknown_not_healthy",
        "UNKNOWN quality never becomes HEALTHY_RESPONSE",
        unknown_healthy.classification != CLASS_HEALTHY_RESPONSE,
    )
    check(
        "missing_pzem_not_zero",
        "missing PZEM data stays MISSING, never a verified zero",
        case_03.current_measurement == CURRENT_MISSING
        and REFUSAL_MISSING_PZEM_NOT_ZERO in classify_case(case_03).refusals,
    )
    check(
        "disabled_stage_not_electrical_failure",
        "a compiled-out stage is not a real electrical failure",
        disabled_claim.classification != CLASS_ELECTRICAL_RESPONSE_MISSING,
    )
    check(
        "weak_thermal_not_component",
        "weak thermal response is not a component root cause",
        REFUSAL_WEAK_THERMAL_NOT_ROOT_CAUSE in current_thermal.refusals
        and "COMPONENT_LEVEL_ROOT_CAUSE"
        in current_thermal.unsupported_conclusions,
    )
    check(
        "software_detection_accuracy_refused",
        "software-only scenarios do not produce detection accuracy",
        population_metrics([case_03])["diagnostic_accuracy"]
        == METRIC_NOT_ESTIMABLE,
    )
    no_truth = classify_case(
        replace(
            case_03,
            case_id="PROBE-NO-TRUTH",
            ground_truth_source=GROUND_TRUTH_NONE,
            expected_classification=None,
        )
    )
    check(
        "no_ground_truth_not_concordant",
        "concordance requires authoritative ground truth",
        no_truth.concordance == CONCORDANCE_NOT_ESTIMABLE,
    )
    check(
        "synthetic_not_physical_reliability",
        "synthetic diagnosis cannot be promoted to physical reliability",
        assess_class_promotion(
            EVIDENCE_HOST_SOFTWARE_SIMULATION,
            EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
        )
        == "EVIDENCE_CLASS_PROMOTION_REFUSED",
    )

    a_timeline = assess_timeline(a_w21_timeline())
    check(
        "outage_duration_without_endpoints",
        "outage duration is absent when start/end are missing",
        STATUS_OUTAGE_NOT_OBSERVED in a_timeline.statuses
        and "outage_duration_s" not in a_timeline.durations,
    )
    receipt_timeline = assess_timeline(
        replace(a_w21_timeline(), time_domain=TIME_BACKEND_RECEIVED_AT)
    )
    check(
        "receipt_time_not_event_time",
        "receipt timestamps cannot stand in for device event time",
        STATUS_TIME_DOMAIN_INSUFFICIENT in receipt_timeline.statuses
        and not receipt_timeline.durations,
    )
    reconnect = assess_safe_local_exit(
        {
            "network_stable": False,
            "broker_connected": True,
            "backend_synchronized": True,
            "fresh_telemetry": True,
            "no_stale_command": True,
            "ai_healthy_if_predictive": True,
            "no_critical_fault": True,
        },
        reconnect_observed=True,
    )
    check(
        "reconnect_not_safe_local_exit",
        "a backend reconnect alone does not exit SAFE_LOCAL",
        not reconnect.ready and "RECONNECT_IS_NOT_SAFE_LOCAL_EXIT" in reconnect.refusals,
    )
    replay = assess_replay(
        [
            TelemetryRecord(
                "d1",
                "b1",
                5,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                sha256_bytes(b"old"),
            )
        ],
        current_twin_seq={"b1": 10},
    )
    check(
        "twin_regression_refused",
        "historical replay does not regress the current twin",
        replay.twin_regressions == 1 and replay.status == "FAILED",
    )
    stale = assess_stale_command(
        issued_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evaluated_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        ttl_s=10,
        fresh_state_confirmed=True,
        applied=True,
    )
    check(
        "stale_command_not_applied",
        "an applied expired command is reported FAILED, never as fresh control",
        stale.status == "FAILED" and stale.expired is True,
    )
    dup_replay = assess_replay(
        [
            TelemetryRecord(
                "d1",
                "b1",
                1,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                sha256_bytes(b"x"),
            ),
            TelemetryRecord(
                "d1",
                "b1",
                1,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                sha256_bytes(b"x"),
            ),
        ]
    )
    check(
        "duplicate_not_inflate_sample",
        "duplicate telemetry does not inflate normalized sample counts",
        dup_replay.normalized_sample_count == 1
        and dup_replay.duplicate_count == 1,
    )
    resync = assess_timeline(
        replace(
            software_fixture_timeline(),
            fresh_state_confirmed=False,
        )
    )
    check(
        "resync_without_fresh_state",
        "resync cannot complete without fresh state evidence",
        STATUS_RESYNC_NOT_VERIFIED in resync.statuses,
    )
    ai = assess_ai_fallback(
        model_health="UNAVAILABLE", risk_score_age_s=0.0, maximum_score_age_s=60.0
    )
    check(
        "ai_unavailable_score_not_trusted",
        "an unavailable model does not keep trusting an old score",
        not ai.score_usable and ai.status == "FALLBACK_REQUIRED",
    )
    check(
        "safe_local_not_physical_protection",
        "a software SAFE_LOCAL transition is not physical thermal protection",
        a_timeline.physical_thermal_protection is False
        and STATUS_PHYSICAL_CONTROL_NOT_VERIFIED in a_timeline.statuses,
    )
    check(
        "single_session_not_distribution",
        "one session is not a population resilience distribution",
        population_distribution_status(1) == "SINGLE_SESSION_IS_NOT_A_DISTRIBUTION",
    )

    chamber_positions = {
        info["physical_position"] for info in SENSOR_ROLE_MAP.values() if info["chamber_air"]
    }
    check(
        "hot_side_not_chamber_substitute",
        "TEC_HOT_SIDE is never a chamber-air substitute",
        "TEC_HOT_SIDE" not in chamber_positions
        and SENSOR_ROLE_MAP["t2"]["chamber_air"] is False,
    )
    check(
        "rom_remap_not_concealed",
        "the pinned extraction records an unchanged, distinct ROM map",
        A_SESSION["rom_map_unchanged"] is True
        and len(set(A_SESSION["rom_map"].values())) == 4,
    )
    check(
        "unknown_door_not_closed",
        "UNKNOWN door state stays UNKNOWN",
        normalize_door_state("UNKNOWN") == "UNKNOWN",
    )
    check(
        "invalid_temperature_not_numeric",
        "an invalid temperature does not become a plausible number",
        normalize_temperature(QUALITY_INVALID, 4.0) is None,
    )
    check(
        "stale_pzem_not_current",
        "stale PZEM data is not carried forward",
        electrical_measurement(QUALITY_VALID, 1.2, stale=True)["status"]
        == "MISSING",
    )
    check(
        "missing_current_not_zero",
        "missing current is not converted to 0 A",
        electrical_measurement(QUALITY_INVALID, None, stale=False)["value"] is None,
    )
    check(
        "energy_reset_not_hidden",
        "a counter reset is not hidden as a negative delta",
        energy_delta(10.0, 5.0)["status"] == "COUNTER_RESET_DETECTED",
    )
    check(
        "recovery_requires_fresh_samples",
        "recovery requires newly valid samples",
        recovery_supported(True, 0) is False,
    )
    check(
        "degraded_model_inference_refused",
        "degraded-feature inference requires explicit model validation",
        degraded_model_inference_allowed(False) is False,
    )
    check(
        "test_fault_not_training_data",
        "W21 fault evidence never becomes predictive training data",
        predictive_training_eligible(EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION)
        is False,
    )

    gate_f = assess_gate_f(None)
    check(
        "gate_f_closed_no_energy_analysis",
        "absent Gate F means no energy analysis runs",
        gate_f.status == GATE_F_NOT_OPENED and gate_f.energy_analysis_run is False,
    )
    check(
        "pwm_not_claimed",
        "PWM characterization is not claimed under a closed gate",
        gate_f.status == GATE_F_NOT_OPENED and gate_f.pwm_search_run is False,
    )
    check(
        "cooling_branch_not_whole_system",
        "PZEM energy stays cooling-branch energy",
        gate_f.cooling_branch_boundary == "COOLING_BRANCH_ONLY",
    )
    check(
        "w20_outcome_not_opened",
        "W21 code never opens a W20 paired-outcome payload",
        w20_analysis == "NOT_RUN"
        and not any(
            token in path.as_posix()
            for path in W21_SOURCE_FILES
            for token in ("paired-outcome", "pair-outcomes")
        ),
    )
    inputs = ("reports/W18/w18-manifest.json", "reports/W20/w20-manifest.json")
    check(
        "w16_locked_test_not_opened",
        "no W16 locked-test file is an input and the holdout stays unopened",
        w16 == "NOT_OPENED"
        and all("W16" not in path for path in inputs),
    )
    check(
        "w15_model_not_deployable",
        "the W15 report is synthetic and the model remains nondeployable",
        W15_MODEL_STATUS == "SYNTHETIC_NONDEPLOYABLE" and w15_synthetic,
    )
    check(
        "g4_g5_not_upgraded",
        "G4/G5 read as their actual observed states from prior manifests",
        g4 == "NOT_READY" and g5 == "NOT_ESTABLISHED",
    )
    check(
        "c_d_code_not_modified",
        "W21 code is confined to the ml/ tree",
        all(str(path).replace("\\", "/").find("/ml/") >= 0 for path in W21_SOURCE_FILES),
    )
    capability = audit_capabilities(
        [path for path in W21_SOURCE_FILES if "tests" not in path.parts],
        base=ML_ROOT,
    )
    check(
        "no_physical_fault_injection",
        "W21 code has no physical fault-injection capability",
        all(value is False for value in capability["capabilities"].values()),
    )
    check(
        "unknown_not_numeric_zero",
        "the diagnosis table keeps MISSING/UNKNOWN states instead of zero",
        case_03.current_measurement == CURRENT_MISSING
        and a03_result["gate"] == GATE_BOUNDED_ON_DEVICE_EVIDENCE,
    )

    check(
        "positive_valid_source_admitted",
        "an authentic source reaches the bounded on-device gate",
        a_result["gate"] == GATE_BOUNDED_ON_DEVICE_EVIDENCE,
    )
    check(
        "positive_bounded_evidence_limited_gate",
        "bounded on-device evidence passes the limited gate without physical acceptance",
        a03_result["gate"] == GATE_BOUNDED_ON_DEVICE_EVIDENCE
        and a03_result["checks"][PROVENANCE_ACCEPTANCE_AUTHORITY_VERIFIED]
        != "VERIFIED",
    )
    check(
        "positive_fixture_timeline_durations",
        "the software fixture computes the declared durations",
        set(fixture_assessment.durations)
        == {
            "outage_duration_s",
            "detection_delay_s",
            "safe_local_interval_s",
            "reconnect_to_resync_s",
        }
        and all(
            value["duration_class"] == DURATION_SOFTWARE_SIMULATION
            for value in fixture_assessment.durations.values()
        ),
    )
    valid_replay = assess_replay(
        [
            TelemetryRecord(
                "d1",
                "b1",
                1,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                sha256_bytes(b"a"),
            ),
            TelemetryRecord(
                "d1",
                "b1",
                2,
                datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
                sha256_bytes(b"b"),
            ),
        ]
    )
    check(
        "positive_replay_clean",
        "ordered unique telemetry produces a clean replay assessment",
        valid_replay.status == "VERIFIED"
        and valid_replay.normalized_sample_count == 2,
    )
    exit_ready = assess_safe_local_exit({name: True for name in EXIT_REQUIREMENTS})
    check(
        "positive_exit_gate_ready",
        "a fully satisfied exit gate is ready",
        exit_ready.ready and not exit_ready.missing,
    )
    healthy_case = classify_case(
        replace(
            case_02,
            case_id="PROBE-HEALTHY",
            command_state=COMMAND_ON,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_NONZERO,
            current_value_a=1.0,
            thermal_quality=QUALITY_VALID,
            thermal_response=THERMAL_PRESENT,
            overall_quality=QUALITY_VALID,
            observed_invalid_channels=(),
        )
    )
    check(
        "positive_healthy_enabled_case",
        "a complete enabled-actuator fixture can reach HEALTHY_RESPONSE",
        healthy_case.classification == CLASS_HEALTHY_RESPONSE
        and LEVEL_ELECTRICAL_RESPONSE_VERIFICATION in healthy_case.evidence_levels
        and LEVEL_THERMAL_RESPONSE_VERIFICATION in healthy_case.evidence_levels,
    )
    missing_case = classify_case(
        replace(
            case_02,
            case_id="PROBE-ELECTRICAL-MISSING",
            command_state=COMMAND_ON,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_ZERO,
            current_value_a=0.0,
            thermal_quality=QUALITY_VALID,
            thermal_response=THERMAL_ABSENT,
            overall_quality=QUALITY_VALID,
            observed_invalid_channels=(),
        )
    )
    check(
        "positive_electrical_missing_case",
        "a valid measured zero current reaches ELECTRICAL_RESPONSE_MISSING",
        missing_case.classification == CLASS_ELECTRICAL_RESPONSE_MISSING,
    )
    off_current = classify_case(
        replace(
            case_02,
            case_id="PROBE-OFF-CURRENT",
            command_state=COMMAND_OFF,
            output_stage=OUTPUT_STAGE_ENABLED,
            electrical_quality=QUALITY_VALID,
            current_measurement=CURRENT_MEASURED_NONZERO,
            current_value_a=1.0,
            thermal_quality=QUALITY_VALID,
            thermal_response=THERMAL_UNKNOWN,
            overall_quality=QUALITY_VALID,
            observed_invalid_channels=(),
        )
    )
    check(
        "positive_unexpected_off_current",
        "measured current while OFF reaches UNEXPECTED_OFF_CURRENT",
        off_current.classification == CLASS_UNEXPECTED_OFF_CURRENT,
    )

    return probes


def generate(
    out_dir: Path,
    *,
    source_revision: str = W21_BASE_REVISION,
    verify_sources_root: Path | None = None,
    gate_f_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    records = source_register()
    for record in records:
        record.validate()
    admissions = _admission_rows(records, verify_sources_root)
    for row in admissions:
        if row["gate"] == GATE_NOT_ESTABLISHED:
            # Contract references never reach this branch; a physical claim without
            # acceptance authority stays visibly unestablished.
            row["refusal_reasons"] = list(row["refusal_reasons"])

    cases = _a_cases()
    table = assess_diagnosis_table(cases)
    diag_rows = canonical_diag_rows()
    a_assessment = assess_timeline(a_w21_timeline())
    fixture_assessment = assess_timeline(software_fixture_timeline())
    gate_f = assess_gate_f(gate_f_authorization, core_evidence_complete=False)
    capability = audit_capabilities(
        [path for path in W21_SOURCE_FILES if "tests" not in path.parts],
        base=ML_ROOT,
    )
    require_no_capability(capability)

    w18 = _read_json(ML_ROOT / "reports" / "W18" / "w18-manifest.json")
    w20 = _read_json(ML_ROOT / "reports" / "W20" / "w20-manifest.json")
    w18_verdicts = w18.get("verdicts", {}) if isinstance(w18.get("verdicts"), Mapping) else {}
    w20_verdicts = w20.get("verdicts", {}) if isinstance(w20.get("verdicts"), Mapping) else {}
    g4 = str(w20_verdicts.get("G4", w18_verdicts.get("G4", "NOT_READY")))
    g5 = str(w20_verdicts.get("G5", "NOT_ESTABLISHED"))
    w16 = str(w20_verdicts.get("W16_HOLDOUT", w18_verdicts.get("W16_HOLDOUT", "NOT_OPENED")))
    w20_analysis = str(w20_verdicts.get("W20_FINAL_ANALYSIS", "NOT_RUN"))

    w15_text = (
        ML_ROOT / "reports" / "W15" / "A3-report.md"
    ).read_text(encoding="utf-8")
    w15_synthetic = "synthetic" in w15_text.lower()

    probes = run_adversarial_controls(
        table,
        records,
        admissions,
        fixture_assessment,
        cases,
        g4=g4,
        g5=g5,
        w16=w16,
        w20_analysis=w20_analysis,
        w15_synthetic=w15_synthetic,
    )
    probes_passed = sum(1 for probe in probes if probe["passed"])
    if probes_passed != len(probes):
        failed = [probe["name"] for probe in probes if not probe["passed"]]
        raise RuntimeError(f"adversarial controls failed: {failed}")

    reports = {
        "diagnosis-table-W21.md": _diagnosis_report(table, diag_rows, admissions),
        "safe-local-summary-W21.md": _safe_local_report(
            a_assessment, fixture_assessment
        ),
        "degraded-sensor-pzem-W21.md": _degraded_report(table),
        "optional-energy-gate-W21.md": _gate_f_report(gate_f),
    }
    report_hashes: dict[str, str] = {}
    for name, text in reports.items():
        _write(out_dir / name, text)
        report_hashes[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    manifest = {
        "schema": "coldguard-w21-resilience-diagnosis-evidence-v1",
        "layer_version": W21_LAYER_VERSION,
        "scientific_evidence_class": (
            "BOUNDED_ON_DEVICE_SOFTWARE_INJECTION_PLUS_SOFTWARE_CONTRACTS"
        ),
        "source_revision": source_revision,
        "revision_semantics": W21_BASE_REVISION_SEMANTICS,
        "analysis_code_sha256": _analysis_code_sha256(),
        "external_evidence": {
            "a_result_commit": REV_A_EVIDENCE,
            "a_bytes_observed_at_main": REV_MAIN_VERIFIED,
            "a_bytes_verified_live": verify_sources_root is not None,
            "a_evaluator_lineage": A_SESSION["evaluator_lineage"],
            "a_independent_replay": A_SESSION["independent_evaluator_replay"],
        },
        "source_register_identity": source_register_identity(records),
        "source_inventory": build_source_inventory(records),
        "source_admissions": admissions,
        "session_identity": dict(A_SESSION),
        "sensor_role_map": SENSOR_ROLE_MAP,
        "diagnosis_table": table.to_dict(),
        "canonical_diagnosis_rows": [dict(row) for row in diag_rows],
        "resilience": {
            "a_w21_session": a_assessment.to_dict(),
            "software_fixture": fixture_assessment.to_dict(),
            "external_dependencies": EXTERNAL_DEPENDENCIES,
            "physical_safe_local": "NOT_ESTABLISHED",
            "combined_latency_distribution": "NOT_CREATED",
        },
        "degraded_sensor_pzem": {
            "recorded_device_evidence": "BOUNDED_ON_DEVICE_EVIDENCE",
            "model_robustness": "NOT_ESTABLISHED",
            "model_status": "SYNTHETIC_NONDEPLOYABLE",
            "missingness_rules": {
                "missing_current_as_zero": False,
                "missing_power_as_zero_energy": False,
                "stale_value_as_fresh": False,
                "chamber_sensor_replaced_by_hot_side": False,
                "invalid_temperature_as_number": False,
                "unknown_door_as_closed": False,
                "energy_counter_reset_hidden": False,
            },
        },
        "gate_f": gate_f.to_dict(),
        "verdicts": {
            "SOFTWARE": "COMPLETE",
            "B_W21_01_DIAGNOSIS_TABLE": "SOFTWARE_VERIFIED",
            "B_W21_01_REAL_DIAGNOSIS_EVIDENCE": "BOUNDED_ON_DEVICE_EVIDENCE",
            "B_W21_02_SAFE_LOCAL_SUMMARY": "SOFTWARE_VERIFIED",
            "B_W21_02_PHYSICAL_SAFE_LOCAL": "NOT_ESTABLISHED",
            "B_W21_03_DEGRADED_SENSOR_PZEM": "SOFTWARE_VERIFIED",
            "B_W21_03_RECORDED_DEVICE_EVIDENCE": "BOUNDED_ON_DEVICE_EVIDENCE",
            "B_W21_04_OPTIONAL_ENERGY": (
                "GATE_F_OPEN" if gate_f.status == GATE_F_OPEN else "GATE_F_NOT_OPENED"
            ),
            "REAL_MODEL_ROBUSTNESS": "NOT_ESTABLISHED",
            "W15_MODEL": "SYNTHETIC_NONDEPLOYABLE",
            "G4": g4,
            "G5": g5,
            "W16_HOLDOUT": w16,
            "W20_FINAL_ANALYSIS": w20_analysis,
            "CONTROLLER_B_SIGNOFF": "WITHHELD",
            "DELIVERY": "PENDING_PUBLICATION",
        },
        "scientific_integrity": {
            "W13_PRIMARY_HORIZON": "UNFROZEN",
            "W15_MODEL": "SYNTHETIC_NONDEPLOYABLE",
            "W16_HOLDOUT": "NOT_OPENED",
            "W20_FINAL_ANALYSIS": "LOCKED",
            "G4": "NOT_READY",
            "G5": "NOT_ESTABLISHED",
            "PHYSICAL_ACCEPTANCE": "NOT_ISSUED",
        },
        "generation_inputs": {
            "w18_manifest": _input_record(
                ML_ROOT / "reports" / "W18" / "w18-manifest.json"
            ),
            "w20_manifest": _input_record(
                ML_ROOT / "reports" / "W20" / "w20-manifest.json"
            ),
            "w15_a3_report": _input_record(
                ML_ROOT / "reports" / "W15" / "A3-report.md"
            ),
        },
        "metadata_files_read": [
            "reports/W18/w18-manifest.json",
            "reports/W20/w20-manifest.json",
            "reports/W15/A3-report.md",
        ],
        "capability_audit": capability,
        "capabilities": {
            "activate_controller_b": False,
            "change_policy_or_threshold": False,
            "command_tec": False,
            "open_w16_locked_test": False,
            "open_w20_outcome_payload": False,
            "physical_actuation": False,
            "physical_fault_injection": False,
            "publish_actuator_message": False,
            "run_energy_experiment": False,
        },
        "adversarial_controls": {
            "probe_count": len(probes),
            "probes_passed": probes_passed,
            "probes": probes,
        },
        "reports": report_hashes,
        "limitations": [
            "The two recorded test IDs share one boot and one raw log; the "
            "independent on-device session count is 1.",
            "The A acceptance evaluator lineage is not on main; independent "
            "evaluator replay is pending.",
            "The actuator output stage was compiled out in every recorded frame.",
            "C W21/W16 evidence is unmerged host software simulation with no "
            "committed evidence artifact.",
            "D's final policy version is not frozen.",
            "Gate F is not opened; no energy analysis was performed.",
            "Manifest coherence and recorded-check cross-checks are marked "
            "VERIFIED only when --verify-sources is supplied; the committed "
            "run reports them NOT_VERIFIED and binds the pinned hashes.",
        ],
    }

    manifest_text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    _write(out_dir / "w21-manifest.json", manifest_text)
    return {
        "out_dir": str(out_dir),
        "reports": sorted(reports),
        "probe_count": len(probes),
        "probes_passed": probes_passed,
        "source_count": len(records),
        "independent_session_count": table.independent_session_count,
        "gate_f": gate_f.status,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only W21 diagnosis/resilience evidence audit"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPORTS_DIR,
        help="output directory (default: ml/reports/W21)",
    )
    parser.add_argument(
        "--source-revision",
        default=W21_BASE_REVISION,
        help="declared analysis base revision",
    )
    parser.add_argument(
        "--verify-sources",
        type=Path,
        default=None,
        help=(
            "read-only checkout at the pinned A evidence commit; verifies actual "
            "bytes instead of relying on the pinned register"
        ),
    )
    for forbidden in ("--evaluate", "--force", "--energy", "--pwm"):
        parser.add_argument(forbidden, action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    for forbidden in ("evaluate", "force", "energy", "pwm"):
        if getattr(args, forbidden):
            parser.error(f"--{forbidden} is not a W21 capability")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        generate(
            args.out_dir,
            source_revision=args.source_revision,
            verify_sources_root=args.verify_sources,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"W21 audit refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
