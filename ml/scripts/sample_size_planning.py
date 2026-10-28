#!/usr/bin/env python3
"""Rough paired-effect sample-size planning (B-W03-04, Doc ``03`` §12).

Canonical model (CANONICAL inputs, DERIVED computation)::

    d_z = delta / sigma_d
    n   ≈ ((1.96 + 0.84) / d_z)^2        (two-sided alpha = 0.05, power ≈ 0.80)

``delta`` is the target mean paired improvement
(``I_i = Y_A,i - Y_B,i``; positive favors predictive Controller B for
lower-is-better outcomes — analysis plan §4.1); ``sigma_d`` is the SD of
paired differences, normally from *pilot* data whose provenance is recorded
separately (never synthetic fixtures, never the final A/B outcomes).

Two labeled methods (IMPLEMENTATION_CHOICE, stdlib only):

* ``rounded`` (default) — the Doc ``03`` §12 rough formula with the
  documented rounded quantiles 1.96 + 0.84, evaluated in decimal arithmetic
  so hand-computed reference values reproduce exactly. This is the only
  mandatory W03 method.
* ``precise`` — the same normal approximation with precise quantiles from
  ``statistics.NormalDist`` for the requested alpha/power. Reported
  separately; never silently substituted for ``rounded``.

Both round UP (``ceil``) to a positive integer number of independent
matched Controller A/B pairs, with a documented floor of 2: a single pair
cannot support the paired uncertainty machinery (plan §4.4). The estimate
is a planning aid, never a guarantee of the final test's actual power.

No third-party dependency (stdlib: argparse, dataclasses, decimal, json,
math, statistics, sys). No data access, no model, no randomness:
identical inputs give identical outputs.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

METHOD_ROUNDED = "rounded-quantile-normal-approx"
METHOD_PRECISE = "precise-quantile-normal-approx"
Z_ALPHA_ROUNDED = Decimal("1.96")
Z_POWER_ROUNDED = Decimal("0.84")
DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80
MIN_PAIRS_FLOOR = 2


class PlanningError(ValueError):
    """A sample-size planning request is invalid or ambiguous."""


@dataclass(frozen=True)
class PlanResult:
    """Deterministic planning output (units: independent matched pairs)."""

    method: str
    alpha: float
    power: float
    effect_size: float
    n_pairs: int
    unit: str = "independent matched Controller A/B pairs"
    assumptions: str = "rough normal approx, paired effect"
    caveat: str = "planning estimate only, never a power guarantee"
    note: str = ""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanningError(f"{name} must be a real number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise PlanningError(f"{name} must be finite, got {value!r}")
    return value


def _check_alpha_power(alpha: float, power: float) -> tuple[float, float]:
    alpha = _finite(alpha, "alpha")
    power = _finite(power, "power")
    if not 0.0 < alpha < 1.0:
        raise PlanningError(f"alpha must lie in (0, 1), got {alpha!r}")
    if not 0.0 < power < 1.0:
        raise PlanningError(f"power must lie in (0, 1), got {power!r}")
    return alpha, power


def resolve_effect_size(
    d_z: float | None = None,
    delta: float | None = None,
    sigma_d: float | None = None,
) -> Decimal:
    """Resolve the standardized paired effect (CANONICAL d_z)."""
    if d_z is not None and (delta is not None or sigma_d is not None):
        raise PlanningError("provide either d_z or (delta and sigma_d), not both")
    if d_z is not None:
        d = _finite(d_z, "d_z")
        if d <= 0:
            raise PlanningError(f"d_z must be > 0, got {d_z!r}")
        return Decimal(str(d))
    if delta is None or sigma_d is None:
        raise PlanningError("provide d_z, or both delta and sigma_d")
    delta_f = _finite(delta, "delta")
    sigma_f = _finite(sigma_d, "sigma_d")
    if delta_f <= 0:
        raise PlanningError(f"delta must be > 0, got {delta!r}")
    if sigma_f <= 0:
        raise PlanningError(f"sigma_d must be > 0, got {sigma_d!r}")
    return Decimal(str(delta_f)) / Decimal(str(sigma_f))


def _ceil_pairs(raw: Decimal | float) -> tuple[int, str]:
    # Canonical rounded-quantile inputs are two-decimal (1.96, 0.84), so the
    # rounded method evaluates in Decimal and ceils exactly: Decimal('7.84')
    # -> 8, Decimal('12.25') -> 13, Decimal('16') stays 16, never 17.
    # Float binary drift (7.84 -> 7.839999999999999) is why the canonical
    # path must NOT go through float: naive float ceil under-reports pairs
    # sitting exactly on reference integers. The float branch below serves
    # only the precise-quantile method, where inputs are irrational anyway.
    if isinstance(raw, float):
        n = int(math.ceil(raw))
    else:
        whole = int(raw.to_integral_value(rounding="ROUND_FLOOR"))
        n = whole if raw == whole else whole + 1
    note = ""
    if n < MIN_PAIRS_FLOOR:
        note = (
            f"raw estimate rounds to {n}; reported floor is "
            f"{MIN_PAIRS_FLOOR} pairs (one pair cannot support "
            "paired uncertainty machinery)"
        )
        n = MIN_PAIRS_FLOOR
    return n, note


def plan_pairs(
    d_z: float | None = None,
    delta: float | None = None,
    sigma_d: float | None = None,
    *,
    method: str = METHOD_ROUNDED,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    label: str | None = None,
) -> PlanResult:
    """Estimate required independent matched pairs (deterministic)."""
    effect = resolve_effect_size(d_z=d_z, delta=delta, sigma_d=sigma_d)
    _check_alpha_power(alpha, power)
    if method == METHOD_ROUNDED:
        if alpha != DEFAULT_ALPHA or power != DEFAULT_POWER:
            raise PlanningError("rounded method is alpha=0.05/power~=0.80 only")
        raw = (Z_ALPHA_ROUNDED + Z_POWER_ROUNDED) / effect
        n, note = _ceil_pairs(raw * raw)
        assumptions = (
            "rough normal approximation for a paired effect; "
            "two-sided alpha = 0.05, target power ~= 0.80; "
            "pairs are independent; pilot variance recorded separately"
        )
        caveat = (
            "planning estimate only, never a guarantee of actual power; "
            "rounded quantiles differ near boundaries from precise solvers"
        )
    elif method == METHOD_PRECISE:
        dist = statistics.NormalDist()
        za = dist.inv_cdf(1.0 - alpha / 2.0)
        zb = dist.inv_cdf(power)
        raw = (za + zb) / float(effect)
        n, note = _ceil_pairs(raw * raw)
        assumptions = (
            f"normal approximation with precise quantiles "
            f"(z_alpha={za:.4f}, z_power={zb:.4f}); "
            f"two-sided alpha = {alpha}, target power = {power}; "
            "pairs are independent; pilot variance recorded separately"
        )
        caveat = (
            "planning estimate only, never a guarantee of actual power; "
            "precise values may differ by 1 pair from rounded references"
        )
    else:
        raise PlanningError(f"unknown method {method!r}")
    if label is not None and not str(label).strip():
        raise PlanningError("scenario label must be non-empty when provided")
    return PlanResult(method, alpha, power, float(effect), n, assumptions=assumptions,
                      caveat=caveat, note=note)


def result_to_dict(result: PlanResult, label: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "method": result.method,
        "assumptions": result.assumptions,
        "effect_size_dz": result.effect_size,
        "n_pairs": result.n_pairs,
        "unit": result.unit,
        "alpha": result.alpha,
        "power": result.power,
        "approximation_caveat": result.caveat,
        "pilot_variance_provenance": (
            "no pilot variance used here; when pilot variance informs "
            "planning, record its run set, manifest ids, and commit; "
            "synthetic fixtures are never pilot data"
        ),
    }
    if result.note:
        payload["note"] = result.note
    if label:
        payload["scenario_label"] = label
    return payload


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Paired-effect sample-size planning.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--d-z", type=float, default=None)
    g.add_argument("--delta", type=float, default=None)
    p.add_argument("--sigma-d", type=float, default=None)
    p.add_argument("--method", choices=[METHOD_ROUNDED, METHOD_PRECISE],
                   default=METHOD_ROUNDED)
    p.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    p.add_argument("--power", type=float, default=DEFAULT_POWER)
    p.add_argument("--label", type=str, default=None)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.delta is not None and args.sigma_d is None:
        print("error: --delta requires --sigma-d", file=sys.stderr)
        return 2
    if args.sigma_d is not None and args.delta is None:
        print("error: --sigma-d requires --delta", file=sys.stderr)
        return 2
    try:
        result = plan_pairs(
            d_z=args.d_z, delta=args.delta, sigma_d=args.sigma_d,
            method=args.method, alpha=args.alpha, power=args.power,
            label=args.label,
        )
    except PlanningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    payload = result_to_dict(result, label=args.label)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"method:      {payload['method']}")
        print(f"assumptions: {payload['assumptions']}")
        print(f"effect d_z:  {payload['effect_size_dz']:.4g}")
        print(f"pairs needed: {payload['n_pairs']} {payload['unit']}")
        print(f"caveat:      {payload['approximation_caveat']}")
        print(f"pilot data:  {payload['pilot_variance_provenance']}")
        if payload.get("note"):
            print(f"note:        {payload['note']}")
        if payload.get("scenario_label"):
            print(f"scenario:    {payload['scenario_label']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())






