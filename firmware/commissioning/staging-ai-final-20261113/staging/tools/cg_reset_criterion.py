"""Reset-criterion v0 for the chamber state machine (A-W07-05).

Standard library only. This is a **candidate**, deliberately not frozen:
docs/05A A-W07-05 asks for a state-based criterion and the W07 pass criteria say
no universal threshold is required, so the numbers must come from measured
repeatability. Where they do not exist yet they stay UNRESOLVED.

The rule that makes it safe to ship before the numbers exist:

* a criterion whose value is UNRESOLVED can never contribute to READY;
* missing evidence - an UNKNOWN door, a nan reading, an absent slope - yields
  UNKNOWN, never a silent pass (docs/01 §19: unknown must not silently become
  normal);
* NOT_READY is reserved for recorded evidence that positively contradicts a
  resolved criterion.

So the three answers stay distinct: NOT_READY means "the chamber is not in a
resettable state", UNKNOWN means "this tool cannot tell you yet". A project that
reads UNKNOWN as READY gets the opposite of what was measured.

`tmean_band_c` is an upper bound on the chamber-air mean at the moment a run may
be declared reset. A two-sided band needs a centre, and any centre this tool
supplied for itself would be a threshold nobody measured, so v0 ships the simpler
test and leaves the band-with-centre question open in the parameter file. The
state must also name the `representation` its numbers were computed on, and a
mismatch is refused: judging one mean against a band written for another is a
silent redefinition, and the open T2 question is exactly where that would happen.

The parameter file is a restricted YAML subset - top-level ``key: value`` lines
plus a list of ``- name/value/status/source`` blocks - and :func:`load_criteria`
rejects unknown keys, duplicate top-level keys, a missing required parameter and
a status outside the vocabulary, so the artifact cannot drift into something this
tool quietly ignores.
"""

from __future__ import annotations

from collections.abc import Callable
import argparse
import json
import math
import pathlib
import sys

import cg_thermal_repeatability as repeatability

includes_hot_side = repeatability.includes_hot_side

CRITERION_SCHEMA = "reset-criterion-v0"
STATUS_VOCABULARY = ("FROZEN", "PROPOSED", "UNRESOLVED")
PARAMETER_KEYS = ("name", "value", "status", "source")
# A block missing `value` or `status` would silently read as unresolved or,
# worse, as satisfied with an empty string.
REQUIRED_BLOCK_KEYS = ("name", "value", "status", "source")
TOP_LEVEL_KEYS = ("schema", "status", "owner", "applies_to", "notes")

# The five conditions docs/05A A-W07-05 names, plus the representation they are
# measured on. `tmean_definition` is a parameter rather than a constant because
# the docs/01 chamber-air freeze and the capture's physical T2=HOT_SIDE label
# disagree; the criterion inherits that open decision instead of resolving it
# silently.
REQUIRED_PARAMETERS = (
    "tmean_definition",
    "tmean_band_c",
    "gradient_bound_c_per_min",
    "door_required",
    "cooling_state_required_known",
    "sensor_quality_required",
)


class CriteriaError(ValueError):
    pass


def _scalar(text: str) -> str:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_criteria(path: pathlib.Path) -> dict[str, object]:
    top: dict[str, str] = {}
    parameters: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_parameters = False

    def close_block() -> None:
        nonlocal current
        if current is not None:
            parameters.append(current)
            current = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if ":" not in stripped:
            raise CriteriaError(f"{path}: unparsable line {raw!r}")
        key, value = (part.strip() for part in stripped.split(":", 1))
        # Indentation is the only thing separating a top-level `status:` from a
        # parameter's `status:`, so the restricted grammar keys on it rather than
        # on the key name.
        at_top_level = not raw[:1].isspace()

        if at_top_level and key == "parameters" and value == "":
            close_block()
            in_parameters = True
            continue
        if stripped.startswith("- "):
            if not in_parameters:
                raise CriteriaError(f"{path}: list item outside `parameters`: {raw!r}")
            close_block()
            current = {}
            key, value = key[2:].strip(), _scalar(value)
        elif at_top_level:
            if key not in TOP_LEVEL_KEYS:
                raise CriteriaError(f"{path}: unknown top-level key {key!r}")
            if key in top:
                raise CriteriaError(f"{path}: duplicate top-level key {key!r}")
            close_block()
            in_parameters = False
            top[key] = _scalar(value)
            continue

        if current is None:
            raise CriteriaError(f"{path}: {key!r} outside any parameter block: {raw!r}")
        if key not in PARAMETER_KEYS:
            raise CriteriaError(f"{path}: unknown parameter key {key!r}")
        if key in current:
            raise CriteriaError(f"{path}: duplicate {key!r} inside one parameter block: "
                                f"{raw!r}")
        current[key] = _scalar(value)
    close_block()

    if top.get("schema") != CRITERION_SCHEMA:
        raise CriteriaError(f"{path}: schema {top.get('schema')!r}, expected "
                            f"{CRITERION_SCHEMA!r}")
    names = [entry.get("name", "") for entry in parameters]
    missing = sorted(set(REQUIRED_PARAMETERS) - set(names))
    if missing:
        raise CriteriaError(f"{path}: missing parameters {missing}")
    # A repeated block is not a duplicate top-level key, so it survives the check
    # above - and `parameter()` answers the first match, which lets a later
    # UNRESOLVED block hide behind an earlier invented value (or the reverse).
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        raise CriteriaError(f"{path}: repeated parameter blocks {duplicated}: the "
                            f"evaluator answers the first match, so a duplicate is a "
                            f"silent redefinition")
    for entry in parameters:
        for key in REQUIRED_BLOCK_KEYS:
            if key not in entry:
                raise CriteriaError(f"{path}: parameter {entry.get('name')!r} has no "
                                    f"{key!r}")
    for entry in parameters:
        if entry.get("status") not in STATUS_VOCABULARY:
            raise CriteriaError(f"{path}: bad status {entry.get('status')!r} "
                                f"for {entry.get('name')!r}")
    return {"schema": top["schema"], "status": top.get("status", ""),
            "owner": top.get("owner", ""), "parameters": parameters}


def parameter(criteria: dict[str, object], name: str) -> tuple[str, str]:
    """The recorded (value, status) pair for one parameter."""
    for entry in criteria["parameters"]:  # type: ignore[index]
        if entry["name"] == name:
            return entry.get("value", ""), entry["status"]
    raise CriteriaError(f"parameter {name!r} is absent")


def _number(value: object) -> float | None:
    """A finite number, or None. `inf` as a bound means no bound, so it is not a number here.

    Accepting it let `tmean_band_c: inf` with status FROZEN answer READY for any chamber
    temperature - a vacuous threshold is the same defect as an invented one.

    The boundary is finiteness, not plausibility: `1e9` still passes, because deciding
    what counts as a sensible chamber bound is exactly the measurement A-W07-05 refuses
    to guess. The shipped file's UNRESOLVED status and validate_w07.py's pin on it are
    what keep an unmeasured number out of delivery, not an invented range here.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if text in ("", "nan", "UNAVAILABLE", "UNRESOLVED", "UNKNOWN", "null"):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def evaluate(criteria: dict[str, object], state: dict[str, object]) -> dict[str, object]:
    """Judge one chamber state against the candidate criterion.

    `state` carries recorded evidence only: `representation` (which mean the
    numbers were computed on), `tmean_c`,
    `slope_c_per_min`, `door_state` (CLOSED/OPEN/UNKNOWN), `cooling_state`
    (ON/OFF/UNKNOWN) and `quality` (VALID/DEGRADED/INVALID/UNKNOWN). An absent
    key is absent evidence, not a default: a missing door reading is UNKNOWN, and
    UNKNOWN is not CLOSED.
    """
    failing: list[str] = []
    unresolved: list[str] = []
    missing: list[str] = []

    def active(entry_status: str) -> bool:
        """Only a status the file format can express activates a gate.

        `load_criteria` already rejects unknown statuses; this keeps a hand-built
        criteria dict - the way the artifact generator injects test values - from
        reaching READY through a string the shipped format would not accept.
        """
        return entry_status in ("FROZEN", "PROPOSED")

    def numeric_gate(name: str, evidence: str, measured: float | None,
                     test: Callable[[float, float], bool]) -> None:
        """One numeric criterion: its parameter, the evidence that answers it, the test.

        The two names are kept apart on purpose. `missing` must say which
        measurement is absent (`tmean_c`), not which parameter the project has not
        frozen (`tmean_band_c`) - those are different follow-up actions for
        different people.
        """
        value, status = parameter(criteria, name)
        number = _number(value)
        if not active(status) or number is None:
            unresolved.append(f"{name} ({status})")
        elif measured is None:
            missing.append(evidence)
        elif not test(measured, number):
            failing.append(f"{name}: evidence {measured} against {name}={number}")

    # The representation is the first thing the criterion can get wrong: a band
    # written against one mean judged against another is a silent redefinition, and
    # the open T2 question is exactly where that would happen.
    definition, definition_status = parameter(criteria, "tmean_definition")
    if not active(definition_status):
        unresolved.append(f"tmean_definition ({definition_status})")
    elif definition not in repeatability.REPRESENTATIONS:
        failing.append(f"criterion names {definition!r}, which is not a representation this "
                       f"toolkit defines, so nothing can have been measured on it")
    else:
        observed = str(state.get("representation") or "").strip()
        if not observed:
            missing.append("representation")
        elif observed not in repeatability.REPRESENTATIONS:
            failing.append(f"state names {observed!r}, which is not a representation this "
                           f"toolkit defines")
        elif observed != definition:
            failing.append(f"state was measured on {observed!r}, but the criterion names "
                           f"{definition!r}")
        elif includes_hot_side(observed):
            failing.append(f"representation {observed!r} averages a TEC hot-side probe into a "
                           f"chamber-air mean, which this criterion cannot judge")

    numeric_gate("tmean_band_c", "tmean_c", _number(state.get("tmean_c")),
                 lambda measured, band: measured <= band)

    numeric_gate("gradient_bound_c_per_min", "slope_c_per_min",
                 _number(state.get("slope_c_per_min")),
                 lambda measured, bound: abs(measured) <= abs(bound))

    def state_gate(name: str, required: str, status: str, observed: str,
                   condition: str, evidence: str) -> None:
        """One frozen state requirement - activated only by a real readiness condition.

        Two ways a file can pretend to gate on state without gating: an unwriteable status
        on the hand-built path the artifact generator uses, and a value that names no
        condition (`door_required: OPEN` cannot be what a reset asks for). Neither may
        reach READY, so both answer UNKNOWN and say which.
        """
        wanted = required.strip().upper()
        if not active(status):
            unresolved.append(f"{name} ({status})")
        elif wanted != condition:
            unresolved.append(f"{name}={wanted!r} states no readiness condition; this "
                              f"criterion requires {condition}")
        elif observed == "UNKNOWN":
            missing.append(evidence)
        elif observed != wanted:
            failing.append(f"{evidence} {observed} is not the required {wanted}")

    state_gate("door_required", *parameter(criteria, "door_required"),
               condition="CLOSED", evidence="door_state",
               observed=str(state.get("door_state") or "UNKNOWN").strip().upper())

    state_gate("sensor_quality_required", *parameter(criteria, "sensor_quality_required"),
               condition="VALID", evidence="quality",
               observed=str(state.get("quality") or "UNKNOWN").strip().upper())

    known, known_status = parameter(criteria, "cooling_state_required_known")
    cooling = str(state.get("cooling_state") or "UNKNOWN").strip().upper()
    if not active(known_status):
        unresolved.append(f"cooling_state_required_known ({known_status})")
    elif known.strip().lower() not in ("true", "1", "yes"):
        unresolved.append(f"cooling_state_required_known={known!r} states no readiness "
                          f"condition; a reset may not be decided on a cooling state that "
                          f"is allowed to be never-observed")
    elif cooling == "UNKNOWN":
        missing.append("cooling_state")
    elif cooling not in ("ON", "OFF"):
        failing.append(f"cooling_state {cooling} is not a known state")

    if failing:
        verdict = "NOT_READY"
    elif unresolved or missing:
        verdict = "UNKNOWN"
    else:
        verdict = "READY"

    return {
        "verdict": verdict,
        "criterion_status": criteria.get("status", ""),
        "failing": failing,
        "unresolved_parameters": unresolved,
        "missing_evidence": missing,
        "why": _explain(verdict, failing, unresolved, missing),
    }


def _explain(verdict: str, failing: list[str], unresolved: list[str],
             missing: list[str]) -> str:
    if verdict == "NOT_READY":
        return "recorded evidence contradicts a resolved criterion: " + "; ".join(failing)
    if verdict == "UNKNOWN":
        parts = []
        if unresolved:
            parts.append("criterion not yet measurable: " + ", ".join(unresolved))
        if missing:
            parts.append("state evidence absent: " + ", ".join(missing))
        return " | ".join(parts) + ". UNKNOWN is not READY."
    return "every resolved criterion is satisfied by recorded evidence"


def state_from_capture_row(row: dict[str, str],
                           representation: str = "tmean_airroles_v0") -> dict[str, object]:
    """Adapt one recorded bench row into the criterion's evidence vocabulary.

    The default is the as-built chamber-air mean; a caller that means a different
    definition must pass it explicitly so the artifact always names what it used.

    Separate from the evaluator on purpose: a different capture layout must not be
    able to change what READY means.
    """
    value, count, terms = repeatability.tmean(row, representation)
    door_raw = (row.get("door_open") or "").strip()
    if door_raw in ("", "UNKNOWN"):
        door = "UNKNOWN"
    elif door_raw in ("0", "1"):
        door = "OPEN" if door_raw == "1" else "CLOSED"
    else:
        door = door_raw.upper()

    duty = repeatability.number(row, "pwm_applied_permille")
    cooling = "UNKNOWN" if duty is None else ("ON" if duty > 0.0 else "OFF")

    # The quality verdict must cover the probes the mean is actually made of. It used
    # to read t1/t2/t3 unconditionally, so on the as-built air mean (t1, t3, t4) a row
    # with t4_status INVALID still answered VALID, and the gate vouched for t2 - a probe
    # the criterion refuses to average at all.
    statuses = [(row.get(f"{probe}_status") or "").strip()
                for probe in (term[:-2] for term in repeatability.terms_of(representation))]
    if not statuses or any(item == "" for item in statuses):
        quality = "UNKNOWN"
    elif all(item == "OK" for item in statuses):
        quality = "VALID"
    elif all(item in ("OK", "STALE") for item in statuses):
        quality = "DEGRADED"
    else:
        quality = "INVALID"

    return {
        "tmean_c": None if value is None or count != terms else round(value, 4),
        "tmean_usable_terms": count,
        "tmean_term_count": terms,
        "representation": representation,
        "door_state": door,
        "cooling_state": cooling,
        "quality": quality,
        "slope_c_per_min": None,
        "source": "capture_row",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("criteria", type=pathlib.Path)
    parser.add_argument("--state", help="a JSON object of state evidence")
    parser.add_argument("--state-file", type=pathlib.Path)
    args = parser.parse_args(argv)

    criteria = load_criteria(args.criteria)
    if args.state_file is not None:
        state = json.loads(args.state_file.read_text(encoding="utf-8"))
    elif args.state is not None:
        state = json.loads(args.state)
    else:
        state = {}
    print(json.dumps(evaluate(criteria, state), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
