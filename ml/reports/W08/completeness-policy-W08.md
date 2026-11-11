# W08 completeness threshold draft (B-W08-02)

Policy version: `coldguard-w08-completeness-policy-draft-v2`

The policy is derived from physical and event requirements. It does not assert a universal 99.9% threshold. `PROPOSED` values are planning candidates and remain provisional until the owner and reviewer freeze them. `FROZEN` additionally requires recorded freeze evidence; a status string alone is not an approval. `UNRESOLVED` means the validator cannot evaluate the dimension; it is never replaced by zero.

| Dimension | Threshold | Status | Freeze evidence | Applicability | Denominator | Equality | Blocking | Owner |
|---|---|---|---|---|---|---|---|---|
| `WHOLE_CAPTURE_COMPLETENESS` | 0.950000 | PROPOSED | NOT_RECORDED | S1 and S2 | declared planned capture duration divided by the observed modal cadence, plus one; the W05 observed-window fraction is diagnostic only | fraction >= threshold passes | BLOCKING | Member B — AI & Experimental Data |
| `CRITICAL_CHANNEL_COMPLETENESS` | 0.990000 | PROPOSED | NOT_RECORDED | S1 and S2 | declared planned capture duration divided by the observed modal cadence, plus one | fraction >= threshold passes | BLOCKING | Member B — AI & Experimental Data |
| `PRIMARY_EVENT_WINDOW_COMPLETENESS` | 0.990000 | PROPOSED | NOT_RECORDED | S2 (event-required scenarios) | round(event_window_s / nominal_dt_s) | fraction >= threshold passes | BLOCKING | Member B — AI & Experimental Data |
| `PRE_EVENT_BASELINE_COMPLETENESS` | 0.950000 | PROPOSED | NOT_RECORDED | S2 (event-required scenarios) | round(baseline_window_s / nominal_dt_s) | fraction >= threshold passes | BLOCKING | Member B — AI & Experimental Data |
| `POST_EVENT_OR_RECOVERY_COMPLETENESS` | 0.900000 | PROPOSED | NOT_RECORDED | S2 (event-required scenarios) | round((horizon_s - event_window_s) / nominal_dt_s) | fraction >= threshold passes | BLOCKING | Member B — AI & Experimental Data |
| `TIMING_ALIGNMENT_COMPLETENESS` | NOT_ESTIMABLE | UNRESOLVED | NOT_RECORDED | S1 and S2 | expected sample count minus one | not evaluable until a tolerance is frozen | INFO | Member B — AI & Experimental Data |

## Threshold definitions

### `whole_capture_frames` — WHOLE_CAPTURE_COMPLETENESS

- Definition: received frames divided by expected samples derived from the observed modal cadence and the measured capture duration
- Channel family: all received frames
- Required event window: whole capture
- Missing/quality semantics: missing frames reduce the numerator; an undeclared planned duration makes the value NOT_ESTIMABLE, never 1.0
- Source/justification: Doc 03 §119 requires completeness against actual cadence; W05 supplies the observed cadence and a provisional denominator
- Review authority: Project lead + Member A (physical evidence)
- Freeze evidence: NOT_RECORDED

### `critical_channel_samples` — CRITICAL_CHANNEL_COMPLETENESS

- Definition: frames where every declared critical channel is present and source-quality VALID divided by expected samples
- Channel family: required thermal channels; door for S2; PZEM only when claimed
- Required event window: whole capture for S1; event windows for S2
- Missing/quality semantics: missing, INVALID and DEGRADED critical samples are counted separately; none is converted to a numeric zero
- Source/justification: Doc 01 §§19,33 and Doc 03 §122: a critical channel gap overlapping the primary outcome invalidates the run; the numeric fraction is provisional pending A's physical review
- Review authority: Project lead + Member A (physical evidence)
- Freeze evidence: NOT_RECORDED

### `primary_event_window_samples` — PRIMARY_EVENT_WINDOW_COMPLETENESS

- Definition: critical-valid frames inside the primary event window divided by expected samples for that window at the observed cadence
- Channel family: required thermal + door channels
- Required event window: [event anchor, anchor + event window]
- Missing/quality semantics: a window gap is counted separately from whole-capture loss; a missing event anchor makes the dimension NOT_ESTIMABLE
- Source/justification: Doc 03 §119 requires stronger completeness around the event that defines the primary outcome than over the whole run; the event window length is a planning candidate only
- Review authority: Project lead + Member A (physical evidence)
- Freeze evidence: NOT_RECORDED

### `pre_event_baseline_samples` — PRE_EVENT_BASELINE_COMPLETENESS

- Definition: critical-valid frames in the pre-event baseline divided by expected samples for that window at the observed cadence
- Channel family: required thermal + door channels
- Required event window: [anchor - baseline window, anchor)
- Missing/quality semantics: a baseline shorter than the required window is incomplete; missing samples are never back-filled
- Source/justification: Doc 03 §§5–8 require a pre-event baseline for response and prediction claims; W10's 120 s recipe is a planning candidate
- Review authority: Project lead + Member A (physical evidence)
- Freeze evidence: NOT_RECORDED

### `recovery_followup_samples` — POST_EVENT_OR_RECOVERY_COMPLETENESS

- Definition: critical-valid frames in the follow-up window divided by expected samples for that window at the observed cadence; a capture ending before the horizon is censored
- Channel family: required thermal channels
- Required event window: [anchor + event window, anchor + horizon)
- Missing/quality semantics: a censored capture is reported as CENSORED and does not pass; the recovery criterion itself is not invented here
- Source/justification: Doc 01 §20.6 and Doc 03 §7 require a defined recovery reference; W07 reports reset criteria as unresolved, so the numeric value stays provisional
- Review authority: Project lead + Member A (physical evidence)
- Freeze evidence: NOT_RECORDED

### `timing_alignment_intervals` — TIMING_ALIGNMENT_COMPLETENESS

- Definition: observed intervals inside a frozen cadence tolerance divided by expected intervals
- Channel family: sequence/time
- Required event window: whole capture and primary event window
- Missing/quality semantics: negative/zero intervals, sequence reversals and long gaps are reported individually; no tolerance is fabricated here
- Source/justification: Doc 03 §120 forbids assuming exact 1.000 s cadence; the project has not frozen a tolerance, so the fraction remains UNRESOLVED while timing-integrity booleans are still checked
- Review authority: Project lead + Member A (physical evidence)
- Freeze evidence: NOT_RECORDED

## Policy notes

- No universal 99.9% threshold is asserted.
- PROPOSED values are planning candidates and must be reviewed before any frozen dataset claim.
- UNRESOLVED is not zero: the validator reports what is not evaluable.
