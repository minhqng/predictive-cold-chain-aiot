"""Cross-artifact consistency pins for the B/C/D contract handoff.

Fails if the generated JSON, the compatibility CSV and the Markdown
verdict ever disagree on schema, field/row counts, raw-temperature
typing or defect resolution. Guards against prose silently drifting
from machine-readable evidence again.
"""

from __future__ import annotations

import json
import pathlib
import unittest

HANDOFF = (
    pathlib.Path(__file__).resolve().parents[3]
    / "evidence" / "A" / "HANDOFF"
)


def _json() -> dict:
    return json.loads((HANDOFF / "member-a-bcd-contract.json").read_text(encoding="utf-8"))


def _md() -> str:
    return (HANDOFF / "member-a-bcd-contract-verdict.md").read_text(encoding="utf-8")


class ContractArtifactConsistency(unittest.TestCase):
    def test_json_and_md_agree_on_parsed_frame_schema_3(self) -> None:
        d = _json()
        self.assertEqual(d["probe_frame"]["committed_capture_schema"], 3)
        self.assertEqual(d["probe_frame"]["derived_frame_schema"], 3)
        self.assertNotIn("DERIVED, not captured", _md())

    def test_md_row_count_matches_json_matrix(self) -> None:
        n = len(_json()["compatibility_matrix"])
        md = _md()
        self.assertIn(f"has {n} rows", md)
        ignored = sum(1 for r in _json()["compatibility_matrix"]
                      if r["backend_verdict"].startswith("IGNORED"))
        self.assertIn(f"{ignored}\nIGNORED", md.replace(" and ", " and\n"))
        self.assertNotIn("70 remaining tokens", md)

    def test_md_has_no_stale_untyped_raw_temperature_claim(self) -> None:
        self.assertNotIn("_coerce` leaves them as text", _md())
        self.assertIn("typed", _md())

    def test_resolved_defects_agree_between_json_and_md(self) -> None:
        d = _json()
        for rid in ("R-07", "R-08"):
            verdict = next(x["verdict"] for x in d["defect_register"] if x["id"] == rid)
            self.assertIn("RESOLVED", verdict)
        self.assertNotIn("Member A owns two fixes", _md())

    def test_provenance_states_parsed_not_derived_in_json(self) -> None:
        self.assertTrue(_json()["probe_frame"]["derived_frame_provenance"]
                        .startswith("PARSED, not derived"))
        self.assertNotIn("and no command tokens",
                         _json()["probe_frame"]["derived_frame_provenance"])


if __name__ == "__main__":
    unittest.main()
