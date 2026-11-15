# Week 20 — Final paired A/B campaign wave 2 control audit

**Current status: HOST AUDIT MODULE TESTED; PHYSICAL CAMPAIGN WAVE 2 PENDING; G5 PENDING.**

`campaign_audit.py` implements Doc 05D section 52 (D-W20-01..D-W20-04) as a
pure decision layer. For the final campaign it:

- audits every **valid Controller B run** for prediction presence, policy
  decision trace, command, ACK and physical verification (D-W20-02);
- audits every **valid Controller A run** for a correct reactive trigger
  (D-W20-02);
- lists, without editing evidence: rejected commands, verification failures,
  SAFE_LOCAL events and control anomalies (D-W20-03);
- computes **G5 control readiness** (D-W20-04) only when the final campaign
  has at least one valid A run and one valid B run, every valid run passes
  the audit, every valid run has provenance-backed live authority, each
  controller uses one policy/config/action identity, and a campaign-level G5
  signoff is supplied (D-W20-01 — no policy drift, no change "for better
  results").

The module never edits, mutates or silently corrects input evidence, makes no
physical or transport claims, and never emits a physical command. The
single-frozen-policy-version check applies to every campaign record (valid or
not): any run under a different policy version is drift.

**Wave 2 / G5 are pending.** No physical wave-2 A/B campaign has been run and
no G5 signoff has been issued; this wave provides only the audited host
tooling. Host booleans and per-run flags cannot sign G5. Readiness remains
`False` until valid Controller A and B campaign runs have evidence references,
operator identity, the full trace, and an explicit G5 signoff record.
