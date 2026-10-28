# W02 evidence — policy states, transitions, SAFE_LOCAL and validator contract

## Goal

Define the deterministic policy-state vocabulary and transition order, specify SAFE_LOCAL entry/exit requirements, and draft the W03 command-validator contract. This branch contains design artifacts only; W03 supplies the pure implementation and unit tests.

## Deliverables

| Deliverable | File | W02 status |
|---|---|---|
| Seven policy states | `policy-states.md` | Defined as v0 design |
| Transition table | `transitions.md` | TR-01..TR-25; gate order and open decisions documented |
| SAFE_LOCAL entry/exit | `transitions.md` §4 and `policy-states.md` | Requirements specified; not implemented in this branch |
| Command-validator contract | `command-validator-contract.md` | Draft v0 for W03 implementation |
| Handoffs A/B/C | `handoffs.md` | Draft; receiving owners have not signed off |

## Design checks

| Check | Evidence | Verdict |
|---|---|---|
| Seven policy states and device-mode distinction | `policy-states.md` §1, §4 | PASS (design) |
| Ordered policy gates and transition outcomes | `transitions.md` §1–3 | PASS (design) |
| SAFE_LOCAL entry and fail-closed exit requirements | `transitions.md` §4 | PASS (design) |
| Command validation order and ACK semantics | `command-validator-contract.md` §2–4 | PASS (contract draft) |
| Ownership and unresolved integration inputs | `handoffs.md` | Open items assigned; no acceptance claimed |

No tests or control code are included or claimed in this W02 branch. W03 is expected to implement the pure policy and validator and add automated tests against these contracts. All numeric thresholds, timing values, hardware behavior, persistence, transport, identity and authorization evidence remain open pending their owning members.
