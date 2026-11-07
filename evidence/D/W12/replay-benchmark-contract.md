# D-W12-02 — Controller A replay benchmark contract

**Runner available, benchmark result OPEN.** `replay_controller_a()` accepts
ordered `ControllerASample` values and a versioned `ControllerAConfig`. This
document states what input is required before its output is a W12 benchmark,
without manufacturing thresholds or using the single W07 session as repeated
evidence.

For each admitted A/B run, pin `run_id`, raw capture SHA-256, hardware/firmware
configuration, sensor representation and quality, Controller A config version,
timestamps, applied cooling, initial condition and predeclared validity
decision. Reconstruct the same policy inputs at each observation time; replay
must use the captured applied state, not assume the intent was applied.

Report per run: ON/OFF intent timestamps, observed applied transitions,
threshold crossings, chatter or dwell blocks, invalid/stale samples, and any
command/ACK/electrical/thermal gaps. Compare the replay decision against the
actual run using the same timebase and explain every mismatch. Aggregate only
independent, comparable valid runs; never count multiple segments of one boot
as independent repeats.

The current A W07 evidence has one cooling session and A W12 marks electrical
quality and configuration signoff unresolved. Therefore no qualified run set
can yet be admitted and no benchmark metric or G3 pass is published here.

Sources: Doc 03 §§5–8, Doc 04 Gate G3, Doc 05D D-W12-02.
