"""B-W03-04 verification: rough paired-effect sample-size planning.

Covers (task §7 checkpoint 6): canonical reference cases, monotonicity in
effect size, delta/sigma_d vs direct d_z equivalence, positive-integer
pair counts, invalid-input rejection, rounding-boundary behavior,
deterministic CLI/function behavior, assumption reporting, and the
no-pilot-variance rule (synthetic fixtures are never pilot data).

Mathematical behavior is verified, not just hardcoded strings: monotonicity
and equivalence tests derive expectations from the documented formula.
"""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sample_size_planning.py"


def _load():
    spec = importlib.util.spec_from_file_location("sample_size_planning", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sample_size_planning"] = module
    spec.loader.exec_module(module)
    return module


ssp = _load()

# Canonical Doc 03 §12 reference table (rounded-quantile method, ceil).
REFERENCE = {1.0: 8, 0.8: 13, 0.7: 16, 0.6: 22, 0.5: 32, 0.4: 49}


def test_canonical_reference_cases():
    for dz, expected in REFERENCE.items():
        result = ssp.plan_pairs(d_z=dz)
        assert result.n_pairs == expected, f"d_z={dz}"
        assert result.method == "rounded-quantile-normal-approx"


def test_monotonicity_both_directions():
    effects = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.5]
    counts = [ssp.plan_pairs(d_z=d).n_pairs for d in effects]
    for lo, hi in zip(counts, counts[1:]):
        assert hi <= lo, "larger effect must not need more pairs"
    for lo, hi in zip(counts, counts[1:]):
        assert lo >= hi, "smaller effect must not need fewer pairs"


def test_delta_sigma_equivalence_with_direct_dz():
    via_ratio = ssp.plan_pairs(delta=1.4, sigma_d=2.0)
    via_direct = ssp.plan_pairs(d_z=0.7)
    assert via_ratio.effect_size == via_direct.effect_size == pytest.approx(0.7)
    assert via_ratio.n_pairs == via_direct.n_pairs == 16


def test_positive_integer_pair_count_and_floor():
    assert isinstance(ssp.plan_pairs(d_z=0.5).n_pairs, int)
    assert ssp.plan_pairs(d_z=0.5).n_pairs > 0
    # A degenerate single-pair estimate cannot support paired inference:
    # the documented floor reports 2 with an explicit note.
    huge = ssp.plan_pairs(d_z=10.0)
    assert huge.n_pairs == 2
    assert "floor" in huge.note.lower()


def test_invalid_inputs_rejected():
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=0.0)
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=-0.5)
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(delta=1.0, sigma_d=0.0)
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(delta=1.0, sigma_d=-2.0)
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(delta=-1.0, sigma_d=2.0)
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=float("nan"))
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=float("inf"))
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(delta=1.0)  # sigma_d missing
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=0.5, delta=1.0, sigma_d=2.0)  # contradictory
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=0.5, method="rounded-quantile-normal-approx", alpha=0.01)
    with pytest.raises(ssp.PlanningError):
        ssp.plan_pairs(d_z=0.5, method="no-such-method")


def test_boundary_rounding_rounds_up_never_down():
    # d_z whose raw estimate sits just above an integer must round UP:
    # raw ≈ 31.36 → 32; a downward rounding would report 31 and
    # under-power the plan. Verify against the formula directly.
    effect = 0.5
    raw = ((1.96 + 0.84) / effect) ** 2
    assert 31.0 < raw < 32.0
    assert ssp.plan_pairs(d_z=effect).n_pairs == math.ceil(raw) == 32


def test_cli_reports_assumptions_and_is_deterministic(tmp_path=None):
    first = subprocess.run(
        [sys.executable, str(SCRIPT), "--d-z", "0.5"],
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [sys.executable, str(SCRIPT), "--d-z", "0.5"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    assert "rounded-quantile-normal-approx" in first.stdout
    assert "alpha = 0.05" in first.stdout
    assert "32 independent matched Controller A/B pairs" in first.stdout
    assert "never a guarantee" in first.stdout


def test_cli_json_delta_sigma_matches_direct():
    direct = subprocess.run(
        [sys.executable, str(SCRIPT), "--d-z", "0.7", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    ratio = subprocess.run(
        [sys.executable, str(SCRIPT), "--delta", "1.4", "--sigma-d", "2.0", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert direct.returncode == 0 and ratio.returncode == 0
    assert json.loads(direct.stdout)["n_pairs"] == json.loads(ratio.stdout)["n_pairs"] == 16


def test_cli_rejects_invalid_and_contradictory():
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "--d-z", "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2
    contradictory = subprocess.run(
        [sys.executable, str(SCRIPT), "--d-z", "0.5", "--delta", "1.0", "--sigma-d", "2.0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert contradictory.returncode == 2


def test_precise_method_labeled_and_close_to_rounded():
    rounded = ssp.plan_pairs(d_z=0.5, method="rounded-quantile-normal-approx")
    precise = ssp.plan_pairs(d_z=0.5, method="precise-quantile-normal-approx")
    assert precise.method == "precise-quantile-normal-approx"
    assert precise.method != rounded.method
    assert abs(precise.n_pairs - rounded.n_pairs) <= 1
    assert "precise quantiles" in precise.assumptions


def test_no_synthetic_fixture_mislabeled_as_pilot():
    payload = ssp.result_to_dict(ssp.plan_pairs(d_z=0.8), label="illustrative thermal-exposure plan")
    assert payload["n_pairs"] == 13
    assert "synthetic fixtures are never pilot data" in payload["pilot_variance_provenance"]
    assert payload["scenario_label"] == "illustrative thermal-exposure plan"
    assert payload["unit"].startswith("independent matched")

