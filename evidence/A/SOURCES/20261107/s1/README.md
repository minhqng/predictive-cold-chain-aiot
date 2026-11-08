# Retained S1/S2 source evidence — 2026-11-07

This source package makes the existing A-W09-02/A-W10-03 inputs independently
locatable for the W15 electrical-availability derivation. It is **not a new
physical run, acceptance evaluation, A/B campaign, model dataset freeze or
operator authorization**.

- S1 is passive thermal/electrical-idle evidence: fuse OUT, no TEC actuation.
  Three later S1 windows share a single boot; rows/windows are not independent
  hardware configurations. Missing thermal summary values remain missing.
- S2 consists of four real door-disturbance windows, not controller-pair runs.
  The recorded door durations are preserved; no threshold or reset tolerance is
  retrospectively frozen here.
- The source-result snapshots are the exact bytes used by the existing W15
  derivation. They preserve original empty evidence lists/operator fields rather
  than inventing provenance inside the original result.
- Raw logs, command-end markers and original summaries are copied byte-for-byte
  from the existing captures, once. `source-publication-index.json` pins their
  canonical repository locations and source hashes. The source originals remain
  untouched; local text attributes prevent newline normalization on checkout.
- This is the **supporting-input subset**, not an all-attempt census. Interrupted
  acquisitions, other door attempts, full store histories and software scratch
  outputs remain retained at their original local locations. Their exclusion
  from this supporting package is not an assertion that they were valid.

## Contents

- `s1-20261107T063828Z/`: imported S1 window, 600 telemetry frames.
- `s1-multi-20261107T064902Z/`: three additional S1 windows, 600/600/601 frames.
- `../s2/door-20261107T081539Z/`: four 300-frame S2 windows
  within the complete retained door capture; setup and timing records retained.
- `source-result-A-W09-02.json` and the W10 source-result counterpart: original
  accepted-result snapshots, not rewritten physical observations.
- `../../../SOURCE-RESULTS/20261108/`: exact original A-W15-01/A-W15-03 result
  snapshots, allowing source-versus-publication transformation checks. Original
  locator strings inside these archived JSON bytes are metadata, not paths that
  a reader should resolve or execute.

Use the W15 follow-up provenance validator with this repository as
`--sources-repo`. Its boot/sequence selectors reproduce the eight exact windows
without guessing endpoints from mutable report state. No device is opened and no
acceptance store is written.
