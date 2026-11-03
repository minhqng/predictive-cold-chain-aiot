"""Verify the W12 evidence dossier.

    py evidence/A/W12/validate_w12.py

Checks, in order:

1. every file listed in ``SHA256SUMS.txt`` exists and hashes to the pinned value,
   **and** every dossier file is pinned (an unpinned file, an unpinned ``__pycache__``
   or committed bytecode fails here even if the pin of the remaining files is
   re-generated to match a mutation);
2. no flash image (``*.bin``) was committed into the dossier;
3. ``acceptance.md`` keeps its honest, non-GREEN verdict;
4. honesty re-asserts (the point of this validator):
   * nothing in the dossier is labelled PHYSICALLY_VERIFIED and the report's
     ``physical_verified`` flag is False;
   * the gate G3 input does NOT declare a whole-team G3 GREEN;
   * the PZEM audit fails a *claim* of electrical qualification that has no
     evidence behind it - it never fails qualification itself, because the
     OPERATOR_ACTION_QUEUE asks a future capture to supply exactly that;
   * duty-0-with-current frames are listed individually (never a folded-in mean);
   * no door->critical number appears anywhere - in prose or in the real nested
     JSON shape (``"door_to_critical": {"value_s": 123.4}``) - because W13 owns
     that ask and it is NOT COMPUTABLE;
   * no forbidden physical-acceptance phrase ("clean runs", "physical acceptance",
     "compliance certified", ...) appears in any text artifact;
   * the hardware-configuration identity is checked in three layers (F-2): an independent
     invariant pass that re-reads the committed capture bytes with this validator's own parser
     (so a mutation that edits the producer AND regenerates artifacts and pins still fails),
     the published review/authorization provenance (a matching hash proves content binding,
     never a human act), the three-state signoff machine, and a final recomputation through the
     shipped producer.

Exit code 0 only when every check passes. Nothing here touches hardware.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

DOSSIER = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DOSSIER.parents[2]
# Layer 2 of the identity checks re-runs the shipped producer, and importing it must not be
# able to drop a bytecode cache next to a pinned dossier file.
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO_ROOT / "firmware" / "tools"))

HONEST_VERDICT = "W12 is **not** a GREEN week"
# A gate-GREEN *claim* fails the dossier; a disclaimer that the slice does NOT
# declare GREEN must be allowed to say so in plain words. The scan finds each
# "G3/G4 ... GREEN" occurrence and fails only when no negation governs it.
_GATE = re.compile(r"\bG[34]\b[^\n]{0,25}?\bGREEN\b", re.IGNORECASE)
_NEG = re.compile(r"\b(not|never|cannot|no|without|declines?|does not|refuses|out of scope|blocked)\b",
                  re.IGNORECASE)
# Physical-acceptance claims that this host slice must never make, in any form,
# anywhere in the dossier text. Honest disclaimers do not use these strings.
FORBIDDEN_PHRASES = (
    "clean runs", "physical acceptance", "physically accepted",
    "compliance certified", "repeatability established", "physical freeze declared",
)
# A numeric door->critical claim in prose: "door->critical = 90 s" etc.
_DOOR_PROSE = re.compile(r"door[\s>_\-–—→]*critical[^\n]{0,40}?[:=]\s*-?\d", re.IGNORECASE)
_QUALIFICATION_CLAIMS = ("QUALIFIED", "PARTIALLY_QUALIFIED")
# A configuration-identity claim in prose: the rig's label, the geometry or the hardware
# described as verified / certified / confirmed / signed off. Honest disclaimers put a
# negation in front of the phrase, which _NEG already detects. "approved" is deliberately
# absent - `limits=APPROVED` is a published limits posture, not a configuration signoff.
_CONFIG_IDENTITY_CLAIM = re.compile(
    r"(?:hardware configuration|configuration identity|physical configuration|"
    r"installed configuration|CG-HW-001)[^\n]{0,80}?"
    r"\b(?:verified|certified|confirmed|signed[- ]off)\b", re.IGNORECASE)


def declares_gate_green(text: str) -> bool:
    for m in _GATE.finditer(text):
        window = text[max(0, m.start() - 40):m.start()]
        if not _NEG.search(window):
            return True
    return False


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _all_dossier_files(root: pathlib.Path) -> set[str]:
    """Every file under the dossier except the pin file itself (caches included)."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and p.name != "SHA256SUMS.txt"}


def check_pin_completeness(pinned: set[str], root: pathlib.Path) -> list[str]:
    """An unpinned file or a committed bytecode cache fails, even with re-pinned hashes."""
    failures: list[str] = []
    expected = _all_dossier_files(root)
    for unpinned in sorted(expected - pinned):
        failures.append(f"{unpinned} is in the dossier but not pinned")
    for stale in sorted(pinned - expected):
        failures.append(f"{stale} is pinned but no longer present (deleted or cache)")
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix == ".pyc" or "__pycache__" in path.parts):
            failures.append(f"{path.relative_to(root).as_posix()}: committed bytecode cache")
    return failures


def _door_leaf_is_numeric(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        for key in ("value_s", "value"):
            if key in value and not isinstance(value[key], bool) \
                    and isinstance(value[key], (int, float)):
                return True
    return False


def _walk_for_door_claims(obj: object, where: str, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            label = f"{where}.{k}"
            if re.search(r"door.*critical", str(k), re.IGNORECASE) and _door_leaf_is_numeric(v):
                out.append(label)
            _walk_for_door_claims(v, label, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_for_door_claims(v, f"{where}[{i}]", out)


def claims_verified_configuration(text: str) -> list[str]:
    """Hand-written lines that certify the hardware configuration, negation aside.

    Two shapes are caught. A requirement row whose **status cell** carries a verification
    token (`HOST_VERIFIED`, `PHYSICALLY_VERIFIED`) for the configuration identity - the
    shape the W12 acceptance table actually used - and flowing prose that says the
    configuration/identity/CG-HW-001 is "verified|certified|confirmed|signed off".
    Status cells are judged positionally, because an unrelated "not" elsewhere in the same
    table row must not launder a certification. A cell reading UNVERIFIED is the honest
    form and never matches; prose with a negation in front of the phrase is a disclaimer.
    """
    hits: list[str] = []
    for line in text.splitlines():
        if not re.search(r"CG-HW-001|hardware config|configuration identity|"
                         r"configuration signoff|A-W12-04", line, re.IGNORECASE):
            continue
        if line.lstrip().startswith("|"):
            for cell in line.split("|"):
                status = re.fullmatch(r"\s*\**([A-Z][A-Z_]{3,})\**\s*", cell)
                if status:
                    token = status.group(1)
                    if token.endswith("VERIFIED") and not token.endswith("UNVERIFIED"):
                        hits.append(f"status cell {token} on {line.strip()[:80]}")
                        break
        for m in _CONFIG_IDENTITY_CLAIM.finditer(line):
            # A disclaimer puts its negation either before the phrase or inside it
            # ("CG-HW-001 is the intended label; it is not a verified identity"), so both
            # positions are inspected. The positional status-cell rule above is the guard
            # for a certification that carries no negation at all.
            window = line[max(0, m.start() - 80):m.end()]
            if not _NEG.search(window):
                hits.append(m.group(0)[:90])
    return hits


# --- Layer 1: independent identity invariants ------------------------------------------
# These checks deliberately do NOT call cg_w12_drift_audit. They re-read the committed
# capture bytes with their own parser and re-state the operator-frozen role map from docs/01,
# so a mutation that edits the producer AND regenerates its artifacts and pins still fails:
# the underlying capture contradicts the claim regardless of what the tool now reports.
FROZEN_ROLE_MAP = {"t1": "CHAMBER_CENTER", "t2": "TEC_HOT_SIDE", "t3": "CHAMBER_BOTTOM",
                   "t4": "CHAMBER_NEAR_DOOR"}
UNASSIGNED_ROLE_TOKENS = {"", "UNASSIGNED", "NOT_ASSIGNED", "UNKNOWN", "UNVERIFIED"}
ISO_DATE = re.compile(r"20\d{2}-\d{2}-\d{2}")
REQUIRED_INSPECTION_ASPECTS = ("sensor_fixtures", "v1_mounting", "terminals",
                               "fuse_body_marking", "conductor_marking")
SELF_AUTHORED_NAMESPACE = "evidence/A/W12"
NON_HUMAN_PARTIES = ("host", "tool", "audit", "agent", "validator", "script", "python",
                     "cg_w12_drift_audit", "validate_w12", "coordinator", "ci", "bot",
                     "member a", "operator a", "system", "automation")
HEX40 = re.compile(r"[0-9a-f]{40}")


def _capture_file(name: str) -> pathlib.Path | None:
    """Locate a published capture by name anywhere under evidence/A, independently."""
    if not name:
        return None
    matches = sorted((REPO_ROOT / "evidence" / "A").rglob(name))
    return matches[0] if matches else None


def _raw_capture_facts(path: pathlib.Path) -> dict[str, object]:
    """Read the capture bytes directly: frames, boot ids, per-slot role tokens, image basis."""
    import csv as _csv
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [r for r in _csv.DictReader(handle) if (r.get("seq") or "").strip()]
    tokens = {slot: sorted({(r.get(f"{slot}_role") or "").strip().upper()
                             for r in rows} - {""}) for slot in FROZEN_ROLE_MAP}
    boots = sorted({(r.get("boot_id") or "").strip() for r in rows} - {""})
    image_basis = ""
    for key in ("image", "firmware_version"):
        seen = sorted({(r.get(key) or "").strip() for r in rows} - {""})
        if seen:
            image_basis = f"column:{key}"
            break
    if not image_basis:
        text_blob = " ".join((r.get("session") or "") + " " + (r.get("run_id") or "")
                             for r in rows[:50])
        if HEX40.search(text_blob) or "01cedce3" in text_blob:
            image_basis = "heuristic:session-text"
    return {"frames": len(rows), "boot_ids": boots, "role_tokens": tokens,
            "image_basis": image_basis,
            "labelled_slots": [slot for slot in FROZEN_ROLE_MAP
                               if any(t not in UNASSIGNED_ROLE_TOKENS
                                      for t in tokens.get(slot, []))],
            "contradicting_slots": [
                slot for slot, frozen in FROZEN_ROLE_MAP.items()
                for t in tokens.get(slot, [])
                if t not in UNASSIGNED_ROLE_TOKENS
                and t != frozen and t not in frozen and frozen not in t]}


def _human(value: object) -> str:
    text_value = str(value or "").strip()
    if not text_value or any(token in text_value.lower() for token in NON_HUMAN_PARTIES):
        return ""
    return text_value


def _identity_invariants_from_captures(audit: dict) -> list[str]:
    """Compare published evidence against the capture bytes, not against the producer."""
    failures: list[str] = []
    signoff = audit.get("hardware_config_signoff") or {}
    published = {row.get("capture"): row
                 for row in (signoff.get("dataset_validity_table") or [])}
    caps = {cap.get("capture"): cap for cap in audit.get("captures", [])}
    for name, row in published.items():
        path = _capture_file(str(name))
        if path is None:
            failures.append(f"{name}: no committed capture file to verify the configuration "
                            "evidence against, so verification cannot fail closed")
            continue
        raw = _raw_capture_facts(path)
        evidence = row.get("configuration_evidence") or {}
        frozen_slots = sorted(FROZEN_ROLE_MAP)
        if evidence.get("probe_role_labels") and sorted(raw["labelled_slots"]) != frozen_slots:
            failures.append(f"{name}: published probe_role_labels=true but the capture leaves "
                            f"{sorted(set(frozen_slots) - set(raw['labelled_slots']))} unlabelled")
        if evidence.get("role_map_consistent_with_freeze") and raw["contradicting_slots"]:
            failures.append(f"{name}: published role_map_consistent_with_freeze=true but the "
                            f"capture contradicts the frozen map on {raw['contradicting_slots']}")
        if evidence.get("installed_image_identity") and not raw["image_basis"]:
            failures.append(f"{name}: published installed_image_identity=true but no image "
                            "evidence exists in the capture bytes")
        published_boots = sorted(row.get("physical_session_identity") or [])
        if published_boots != sorted(raw["boot_ids"]):
            failures.append(f"{name}: physical_session_identity {published_boots} is not the "
                            f"boot set the capture carries {sorted(raw['boot_ids'])}")
        cap = caps.get(name) or {}
        if cap.get("frames") is not None and cap.get("frames") != raw["frames"]:
            failures.append(f"{name}: published frames {cap.get('frames')} != {raw['frames']} "
                            "rows re-read from the capture")
        contradictions = (cap.get("role_geometry_audit") or {}).get("contradictions") or []
        verdict = str(row.get("role_verdict") or "").upper()
        if raw["contradicting_slots"] and verdict == "CONSISTENT_WITH_FREEZE":
            failures.append(f"{name}: role_verdict {verdict} while the capture contradicts the "
                            "freeze on "
                            f"{raw['contradicting_slots']}")
        if not raw["contradicting_slots"] and contradictions:
            failures.append(f"{name}: the audit lists role contradictions that the capture "
                            "bytes do not support")
    return failures


def _identity_provenance_invariants(signoff: dict) -> list[str]:
    """A hash proves content binding, never that a person reviewed or approved anything."""
    failures: list[str] = []
    rows = signoff.get("dataset_validity_table") or []
    for row in rows:
        name = row.get("capture")
        review = row.get("review_binding") or {}
        if review.get("reviewed"):
            ref = str(review.get("bound_reference") or "")
            if not ref:
                failures.append(f"{name}: review claims EVIDENCE_REVIEWED with no bound reference")
                continue
            path = REPO_ROOT / ref.replace("\\", "/")
            if not path.is_file():
                failures.append(f"{name}: review binds {ref!r}, which does not resolve in the "
                                "repository")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != review.get("bound_sha256"):
                failures.append(f"{name}: the hash bound by the review does not match {ref}: "
                                "content binding is broken, so the review attests nothing")
            if not _human(review.get("reviewer")):
                failures.append(f"{name}: reviewer {review.get('reviewer')!r} is host tooling or "
                                "a role, not a named person")
            if not ISO_DATE.fullmatch(str(review.get("reviewed_on") or "")):
                failures.append(f"{name}: review date {review.get('reviewed_on')!r} is not an "
                                "ISO YYYY-MM-DD")
        provenance = row.get("approval_provenance") or {}
        if provenance.get("valid"):
            source = str(provenance.get("provenance_source") or "")
            if not source:
                failures.append(f"{name}: approval claims AUTHORIZED_PROVENANCE with no source")
                continue
            if source.replace("\\", "/").lower().startswith(SELF_AUTHORED_NAMESPACE.lower()):
                failures.append(f"{name}: approval provenance {source!r} sits inside the "
                                "namespace this tool generates, so it is self-authored")
                continue
            path = REPO_ROOT / source.replace("\\", "/")
            if not path.is_file():
                failures.append(f"{name}: approval provenance {source!r} does not resolve")
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
            if hashlib.sha256(path.read_bytes()).hexdigest() != provenance.get("provenance_sha256"):
                failures.append(f"{name}: approval provenance hash does not match {source}")
            if "CG-HW-001" not in body:
                failures.append(f"{name}: approval provenance never names the configuration it "
                                "approves")
            if not ISO_DATE.search(body):
                failures.append(f"{name}: approval provenance carries no date of its own")
            if not _human(provenance.get("approved_by")):
                failures.append(f"{name}: approving party {provenance.get('approved_by')!r} is "
                                "not a named person outside the host tooling")
            if not ISO_DATE.fullmatch(str(provenance.get("approved_on") or "")):
                failures.append(f"{name}: approval date is not an ISO YYYY-MM-DD")
    if signoff.get("host_cannot_verify_human_authenticity") is not True:
        failures.append("the signoff block no longer states that host code cannot verify human "
                        "authenticity")
    if str(signoff.get("configuration_signoff_status")) == "SIGNED_OFF" \
            and signoff.get("physical_acceptance_pending") is not False:
        failures.append("configuration_signoff_status=SIGNED_OFF while physical_acceptance_pending "
                        "is still true")
    return failures


def _identity_state_machine_invariants(signoff: dict) -> list[str]:
    """The three states must be semantically distinct and reachable in the right order."""
    failures: list[str] = []
    status = str(signoff.get("configuration_signoff_status") or "").upper()
    rows = signoff.get("dataset_validity_table") or []
    if status not in ("UNRESOLVED", "READY_FOR_SIGNOFF", "SIGNED_OFF"):
        failures.append(f"unknown configuration_signoff_status {status!r}")
        return failures
    verified = [row for row in rows if str(row.get("config_verification")).upper() == "VERIFIED"]
    unverified = [row for row in rows if row not in verified]
    prerequisites = bool(rows) and all(row.get("reference_valid") and row.get("evidence_reviewed")
                                      for row in rows)
    for row in rows:
        state = str(row.get("config_verification")).upper()
        if state not in ("VERIFIED", "UNVERIFIED"):
            failures.append(f"{row.get('capture')}: config_verification must be VERIFIED or "
                            f"UNVERIFIED, got {row.get('config_verification')!r}")
        if state == "VERIFIED" and not (row.get("reference_valid")
                                       and row.get("evidence_reviewed")
                                       and row.get("authorized_provenance_valid")):
            failures.append(f"{row.get('capture')}: VERIFIED without all three layers "
                            "(reference, hash-bound review, authorized provenance)")
        if "hardware_config_id" in row:
            failures.append(f"{row.get('capture')}: row publishes a bare hardware_config_id "
                            "column; the intended label and the verified identity are separate "
                            "fields")
        if str(row.get("intended_hardware_config") or "") == state:
            failures.append(f"{row.get('capture')}: the intended label is being used as a "
                            "verification value")
        if row.get("reference_valid") and not row.get("configuration_evidence"):
            failures.append(f"{row.get('capture')}: reference_valid with an empty evidence "
                            "census cannot fail closed")
    if status == "SIGNED_OFF" and (unverified or not prerequisites):
        failures.append("configuration_signoff_status=SIGNED_OFF while a capture is UNVERIFIED "
                        "or a prerequisite is unmet")
    if status == "READY_FOR_SIGNOFF" and (not prerequisites or verified):
        failures.append("configuration_signoff_status=READY_FOR_SIGNOFF requires every technical "
                        "requirement and every hash-bound review to be complete, and no row "
                        "VERIFIED")
    if status == "UNRESOLVED" and prerequisites and not verified:
        pass  # legitimate: evidence complete but reviews outstanding
    if status == "UNRESOLVED" and prerequisites and verified:
        failures.append("every prerequisite is met and rows are VERIFIED while the status is "
                        "still UNRESOLVED")
    return failures


def _identity_producer_recomputation(audit: dict) -> list[str]:
    """Layer 2: recompute with the shipped producer and compare. Kept as an extra layer only."""
    failures: list[str] = []
    try:
        import cg_w12_drift_audit as w12  # noqa: PLC0415
    except ImportError as exc:
        return [f"producer recomputation unavailable: {exc}"]
    paths = w12.default_captures()
    if not paths:
        return ["producer reports no committed captures to recompute against"]
    derived = w12.hardware_config_signoff([w12.audit_capture(p) for p in paths])
    published = audit.get("hardware_config_signoff") or {}
    pub_rows = {row.get("capture"): row for row in (published.get("dataset_validity_table") or [])}
    for row in derived.get("dataset_validity_table") or []:
        name = row.get("capture")
        got = pub_rows.get(name)
        if got is None:
            failures.append(f"{name}: the producer derives a capture the dossier does not publish")
            continue
        if set(row.keys()) != set(got.keys()):
            failures.append(f"{name}: dataset-validity key set differs from the producer's "
                            f"({sorted(set(row) ^ set(got))})")
        for field in ("configuration_evidence", "reference_valid", "evidence_reviewed",
                      "authorized_provenance_valid", "role_verdict",
                      "evidence_derived_config_identity", "physical_session_identity"):
            if row.get(field) != got.get(field):
                failures.append(f"{name}: published {field}={got.get(field)!r} but recomputation "
                                f"from the committed capture gives {row.get(field)!r}")
    if not published.get("approval_record", {}).get("valid"):
        if published.get("configuration_signoff_status") != derived["configuration_signoff_status"]:
            failures.append("published configuration_signoff_status differs from the producer's "
                            "recomputation with no approval record supplied")
        if published.get("physical_acceptance_pending") is not True:
            failures.append("no approval provenance exists, so physical_acceptance_pending must "
                            "be true")
    return failures


def check_config_identity_claims(audit: dict) -> list[str]:
    """A verified hardware configuration needs all three layers, verified independently.

    Four ways this used to be readable as a certification: the artifact stamped a bare
    ``hardware_config_id: CG-HW-001`` because the rig's *name* was known; prose could claim a
    verified configuration while the derived artifact said UNVERIFIED; the published evidence
    census was trusted rather than re-derived, so a hand-edited artifact plus regenerated pins
    passed; and a fully labelled but contradictory role map still satisfied the census. The
    independent layer here re-reads the capture bytes with its own parser, so a mutation that
    changes both the producer's claim and its generated artifact still fails.
    """
    failures: list[str] = []
    signoff = audit.get("hardware_config_signoff") or {}
    if not signoff:
        return ["drift-audit.json carries no hardware_config_signoff section"]
    rows = signoff.get("dataset_validity_table") or []
    if not rows:
        return ["hardware_config_signoff published an empty dataset_validity_table"]
    failures.extend(_identity_invariants_from_captures(audit))
    failures.extend(_identity_provenance_invariants(signoff))
    failures.extend(_identity_state_machine_invariants(signoff))
    failures.extend(_identity_producer_recomputation(audit))

    # Layer 3: internal consistency, so a hand-edited artifact fails even where its capture
    # file cannot be located.
    for row in rows:
        name = row.get("capture")
        evidence = row.get("configuration_evidence") or {}
        satisfied = [key for key, ok in sorted(evidence.items()) if ok]
        unmet = [key for key, ok in sorted(evidence.items()) if not ok]
        state = str(row.get("config_verification") or "").upper()
        if state == "VERIFIED":
            if unmet:
                failures.append(f"{name}: config_verification=VERIFIED while evidence "
                                f"requirements are unmet: {unmet}")
            if row.get("verification_open_items"):
                failures.append(f"{name}: config_verification=VERIFIED while "
                                "verification_open_items is non-empty")
            if any(key.startswith("authorized") or key.endswith("reviewed")
                   for key in satisfied):
                failures.append(f"{name}: review and authorization are human acts and must never "
                                "appear inside the capture evidence census")
        if not evidence:
            failures.append(f"{name}: no configuration_evidence requirements were evaluated, so "
                            "verification cannot fail closed")
    layers = signoff.get("verification_layers") or {}
    for layer in ("REFERENCE_VALID", "EVIDENCE_REVIEWED", "AUTHORIZED_PROVENANCE"):
        if not str(layers.get(layer) or "").strip():
            failures.append(f"verification_layers no longer defines {layer}")
    return failures


def check_pzem_qualification_claim(audit: dict) -> list[str]:
    """Fail a QUALIFIED *claim* that carries no evidence, never qualification itself.

    The old check failed whenever ``electrical_qualification`` left UNQUALIFIED -
    which asserted today's missing-qualification defect as an invariant and turned
    the chain red on the exact qualified capture this slice's action queue requests.

    Two gaps close here. ``PARTIALLY_QUALIFIED`` did not start with ``QUALIFIED`` so it
    escaped the prefix test entirely, and the evidence demanded was a *non-empty* cell,
    which INVALID, STALE or TIMEOUT tokens satisfy. A claim must now be backed by frames
    carrying the producer's own validating status (cg_pzem_status_name: OK), and any
    qualification string outside the published vocabulary fails rather than passing quietly.
    """
    failures: list[str] = []
    for cap in audit.get("captures", []):
        pz = cap.get("pzem_audit", {})
        if pz.get("duty0_with_current_frames", {}).get("listed_individually_never_averaged") is False:
            failures.append(f"{cap.get('capture')}: duty-0 current frames were averaged")
        qual = str(pz.get("electrical_qualification") or "")
        if qual in _QUALIFICATION_CLAIMS:
            evidence = pz.get("qualified_frame_evidence") or {}
            if not evidence.get("frames_with_valid_status"):
                failures.append(f"{cap.get('capture')}: claims {qual!r} electrical "
                                "qualification with no frame carrying a validating status "
                                "token - non-empty is not enough, INVALID and TIMEOUT are "
                                "both non-empty")
        elif qual not in ("UNQUALIFIED", ""):
            failures.append(f"{cap.get('capture')}: electrical_qualification {qual!r} is "
                            "outside the published qualification vocabulary")
    return failures


def main() -> int:
    failures: list[str] = []

    sums_path = DOSSIER / "SHA256SUMS.txt"
    if not sums_path.is_file():
        print("FAIL: SHA256SUMS.txt is missing")
        return 1
    pinned: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([0-9a-f]{64})  (.+)$", line.strip())
        if not m:
            if line.strip():
                failures.append(f"unparsable SHA256SUMS line: {line[:80]!r}")
            continue
        digest, rel = m.groups()
        pinned[rel] = digest
        target = DOSSIER / rel
        if not target.is_file():
            failures.append(f"missing evidence file: {rel}")
            continue
        if b"\r" in target.read_bytes():
            failures.append(f"{rel} is not LF-only")
        if sha256(target) != digest:
            failures.append(f"hash mismatch: {rel}")

    failures.extend(check_pin_completeness(set(pinned), DOSSIER))

    stray_bin = sorted(p.name for p in DOSSIER.rglob("*.bin"))
    if stray_bin:
        failures.append("flash images committed: " + ", ".join(stray_bin))

    acceptance = (DOSSIER / "acceptance.md").read_text(encoding="utf-8")
    if HONEST_VERDICT not in acceptance:
        failures.append("acceptance.md no longer states W12 is not a GREEN week")
    if declares_gate_green(acceptance):
        failures.append("acceptance.md declares a whole-team G3/G4 GREEN")

    audit_path = DOSSIER / "drift-audit.json"
    signoff_signed = False
    if not audit_path.is_file():
        failures.append("drift-audit.json is missing")
    else:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("physical_verified") is not False:
            failures.append("drift-audit.json no longer declares physical_verified=false")
        if audit.get("touches_hardware") is not False:
            failures.append("drift-audit.json claims it touched hardware")
        for cap in audit.get("captures", []):
            if cap.get("is_probe_identification") and cap.get("sensor_consistency", {}).get(
                    "slot_offsets"):
                failures.append(f"{cap['capture']}: probe-id capture produced drift stats")
        failures.extend(check_pzem_qualification_claim(audit))
        failures.extend(check_config_identity_claims(audit))
        signoff_signed = str(
            (audit.get("hardware_config_signoff") or {}).get(
                "configuration_signoff_status") or "").upper() == "SIGNED_OFF"

    g3_path = DOSSIER / "gate-g3-input.json"
    if g3_path.is_file():
        g3 = json.loads(g3_path.read_text(encoding="utf-8"))
        if str(g3.get("a_side_status", "")).upper() in ("GREEN", "PHYSICALLY_VERIFIED",
                                                         "TEAM_GATE_G3_GREEN"):
            failures.append("gate-g3-input.json claimed a whole-team/physical status")
        if not str(g3.get("does_not_declare", "")).startswith("G3"):
            failures.append("gate-g3-input.json no longer states it does not declare G3")
    else:
        failures.append("gate-g3-input.json is missing")

    # Cross-tree door-number guard: W13 owns door->critical, but a stray numeric
    # door value anywhere under W12 - in prose or the real nested JSON shape - is a
    # hard failure. The old single-line regex missed {"door_to_critical":
    # {"value_s": 123.4}}; this walker matches the actual structure.
    for path in sorted(DOSSIER.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(DOSSIER).as_posix()
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            hits: list[str] = []
            _walk_for_door_claims(data, rel, hits)
            for h in hits:
                failures.append(f"{rel}: a door-critical numeric value appeared "
                                f"without data ({h})")
        elif path.suffix in (".md", ".csv", ".txt"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for phrase in FORBIDDEN_PHRASES:
                if phrase in text.lower():
                    failures.append(f"{rel}: forbidden physical-acceptance phrase {phrase!r}")
            if _DOOR_PROSE.search(text):
                failures.append(f"{rel}: a numeric door->critical claim appeared in prose")
            # Hand-written prose must not certify what the derived artifact leaves open.
            # Generated CSV/JSON is exempt: it publishes the vocabulary the invariant above
            # already checks (CG-HW-001 as a label, UNVERIFIED as a status).
            if path.suffix == ".md" and not signoff_signed:
                for hit in claims_verified_configuration(text):
                    failures.append(
                        f"{rel}: prose asserts a verified hardware configuration ({hit!r}) "
                        "while drift-audit.json does not record a signed-off configuration")

    if not failures:
        print(f"W12 DOSSIER: OK ({len(pinned)} pinned files, honest verdict intact)")
        return 0
    print("W12 DOSSIER: FAIL")
    for f in failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
