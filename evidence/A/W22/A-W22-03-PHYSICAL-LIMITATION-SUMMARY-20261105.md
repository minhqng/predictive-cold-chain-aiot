# A-W22-03 physical limitation summary

Derived strictly from recorded results in session `capture-20261104T092140Z` and the imported
hash-pinned W01-W04 evidence. Every number below is quoted from a stored measurement; none is
estimated. Operator review is pending - this document supplies the measured basis for the six
limitation classes the canonical criterion requires.

## 1. Scale limitation

One bench chamber, one Controller A, one TEC branch, one 12 V PSU, one PZEM-004T. All thermal
results are single-unit bench-scale results:

- A-W04-05 (60 s, 500 permille): chamber drop 0.6188 C, mean 4.424 A, peak 4.99 A, 52.378 W.
- A-W07-03 (three 180 s runs, 500 permille): drops 2.2708 / 2.2688 / 2.2688 C, means
  4.2705 / 4.2922 / 4.3021 A, peaks 4.94 / 5.03 / 4.99 A, hot-side maxima 33.5625 / 33.5625 /
  33.625 C from starts of 29.875 / 29.8125 C.

No multi-unit, multi-chamber, stacked-TEC or production-scale behaviour is evidenced anywhere in
this session. Nothing here may be read as a continuous-duty rating: the bench profile caps duty at
500 permille and on-time at 190 s, and hot-side sustainability (A-W08-03, 600 s actuated) is
unevidenced because 600 s exceeds that firmware on-time limit.

## 2. Single-unit limitation

Identity in every frame: `device_id=coldguard-001`, `hardware_config_id=CG-HW-001`, `pin_map=2`,
`grammar=2`, `firmware_version=cg-w06-0.1.0`, `firmware_kind=CANONICAL`,
**`calibration_id=UNRECORDED`**. Consequences:

- No unit-to-unit spread exists, so no tolerance, pairing or fleet statement is supported by this
  session (A-W10-04/A-W16-03 pairing tolerances remain derived from one chamber only).
- `calibration_id=UNRECORDED` means the telemetry carries no per-unit calibration provenance; a
  later unit or a recalibrated sensor set cannot be distinguished from this one by identity alone.
- Probe identity is by ROM, verified in A-W14-01: T1 `287088CA00000051`, T2 `28AEBF2200000006`,
  T3 `28CBE9CA00000072`, SPARE `283BE5C9000000A9`. Roles are as-built, while
  `role_status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` and the plan-era YAML labels for T1/T3 are
  still wrong; any consumer that trusts the labels instead of the ROM map will mis-assign probes.

## 3. TEC / V1 uncertainty

- Applied output is verified from the firmware's own applied-state field, not from an independent
  measurement of the PWM: each A-W07-03 trial recorded `applied_duty_samples=[500]` and
  `applied_on_frames=180`. The electrical truth is the PZEM current, which agrees (4.27-4.30 A mean).
- The bench profile is **not** the worst electrical case the hardware can produce: the imported
  W01-W04 evidence (A-W04-03) records 9.35 A steady and 9.35 A transient at full duty with a 15 A
  fuse fitted, versus 4.99-5.03 A peak at the 500 permille bench cap. Any future duty increase
  re-opens the fuse and terminal-heating question.
- Command-to-electrical delay is 1.02 s in all three trials (A-W13-01 median 1.02 s, spread 0), so
  the delay is reproducible but is measured at 1 Hz telemetry resolution: the true value is only
  bounded to about +/-1 s.
- Command-to-thermal response 35.00-37.04 s (median 36.02 s) is defined by the criterion
  "first sustained 0.2 C chamber drop over two frames" - it is a detection-latency proxy, not a
  physical transport delay, and it is quantised by the same 1 Hz sampling.
- The exponential time constant (61.69 / 62.59 / 63.13 s, R2 0.907-0.912) assumes a single dominant
  exponential over a 2.27 C drop; the fit quality is recorded with it and is not a plant model.
- Hot side never exceeded 33.625 C against a 45 C bench limit, so **no** thermal collapse,
  protection trigger or abnormal terminal/IBT-2 behaviour has been observed. Absence of evidence
  here is not evidence of sustainability.
- V1 fan state is read from telemetry (`fan_command`, `fan_status=OK`, `fan_on_all=true`) only. No
  independent airflow, RPM or fan-failure measurement exists in this session; a stalled rotor would
  not be detected.

## 4. Sensor limitations

- DS18B20 resolution is 0.0625 C per probe. Chamber-air Tmean (T1/T3/SPARE) therefore moves in
  ~0.0208 C steps and a genuinely quiet 90-100 s window commonly shows a 0.0625 C spread from code
  toggling alone. This is why the stabilization criterion (|slope| <= 0.02 C/min and Tmean spread
  <= 0.05 C) sometimes needs several windows and why the A-W12-01 capture tail was rejected as a
  stabilization witness (spread 0.0625 C) while the dedicated monitor passed at 0.0417 C. It is a
  resolution limit, not instability - but it does mean small thermal effects (<0.06 C) are not
  resolvable at all.
- Placement spread is real and larger than the drift being measured. In the A-W12-01 capture the
  maximum instantaneous four-probe spread was 0.4375 C and the largest pairwise mean difference was
  0.3775 C (T2 vs SPARE), while T2 vs T3 differed by only 0.0063 C. A-W14-02 measured a 0.0823 C
  difference between a single-probe and a three-probe chamber mean. Any claim must state which probe
  set produced it.
- Sensor offset drift is small and stable (A-W12-01: 0.0233 C max absolute offset drift against the
  A-W02-05 baseline, limit 0.3 C, valid rate 99.83 %), so offset drift is not the dominant error -
  placement and ambient level are.
- No BME280 environmental channel exists on the flashed image: every frame carries
  `relative_humidity_status=SENSOR_NOT_PRESENT`, `t_ambient_status=NOT_ASSIGNED`,
  `health_bme=NEVER`, `environment_quality=DEGRADED`. Consequences: no humidity or ambient-pressure
  compensation is possible, latent-load or condensation claims cannot be made, and the composite
  `quality` field can never be VALID (59/60 frames UNKNOWN, 1 INVALID in the A-W05-04 capture),
  which is exactly why A-W05-05 cannot pass on this image.
- Door semantics were unproven until the 2026-11-05 observation: the flashed image asserts
  OPEN = raw 1, and only CLOSED at raw 0 had ever been seen (983 attested frames, 0 transitions).
  The consolidated MC-38 session observed 42 raw edges / 21 physical cycles with the first opening
  moving raw 0 -> 1, confirming OPEN = raw 1 on the installed GPIO35 wiring. Residual limits:
  attestation is per boot (every COM4 open resets the board and the door returns to UNVERIFIED
  until re-attested), debounce is firmware-side, and no forced-open-under-load or tamper scenario
  has been tested.

## 5. Ambient effects

- Between the A-W02-05 baseline (14:01:08Z, chamber-air common mean 29.2297 C) and the A-W12-01
  recheck (16:39-16:49Z) the whole chamber rose 0.8586 C with the room. That common-mode shift is
  ~37x larger than the sensor offset drift it could mask (0.0233 C), which is why the first
  A-W12-01 attempt was correctly classified INVALID_CONDITIONS rather than PASS.
- Within a verified-stable window the ambient is genuinely flat (slope -0.0047 C/min over 600 s;
  stabilization windows at -0.0031 and -0.0014 C/min), so in-window comparisons are sound.
- Consequences for every claim in this session: cooling deltas must be compared against in-window
  baselines, not across hours; each actuated run needs its own verified stabilization; start
  conditions must be reported (A-W07-03 starts 30.0833 / 30.1042 / 30.0208 C, spread 0.083 C);
  and no result is valid as an ambient-independent or room-condition-independent claim. The chamber
  is not insulated against room-level changes and no ambient conditioning is evidenced.

## 6. PZEM limitations

- The OFF floor is 0.000 A / 0.000 W: A-W03-05 over 600 frames and A-W12-02 over 120 frames both
  measured current min/mean/max = 0.000 A and power max 0.000 W. "0 A" therefore means "below
  resolution", not "exactly zero"; leakage or standby current below that floor is undetectable, and
  the OFF envelope in A-W08-01 (`off_current_max_a = 0.0`) inherits that floor.
- First-poll latency after boot produces `nan` electrical fields: A-W12-02 valid rate 0.9833
  (118/120) and the A-W05-04 capture had 2/60 frames with `current_a=nan`, `voltage_v=nan`,
  `power_validity=NO_DATA`. Any window that begins at boot must exclude those frames or its
  statistics are wrong; the bounded-capture and first-poll-wait fixes exist for this reason.
- Absolute accuracy is unverified: no comparison against a reference meter exists in this session
  (A-W15-03 is NOT_RUN), so all current/power figures carry the module's uncalibrated accuracy.
  Voltage read 11.94-11.95 V throughout, i.e. the PSU is stable, but that is a single measurement
  point of one meter.
- `energy_wh` is device-side, monotonic and not host-resettable (129.0000 Wh at the end of the
  A-W05-04 capture), so per-run energy must be integrated from V x I samples, not read from the
  counter.
- Power consistency (`power_consistency_max_rel_error = 0.0` in both OFF captures) is only proven
  at zero load; at 50 W the PZEM's own power figure was consistent with V x I in the actuated runs
  (50.55-52.38 W against 11.95 V x 4.27-4.42 A), which is a coherence check, not an accuracy check.

## 7. What these limitations invalidate

- Any continuous-duty, multi-unit, fleet-tolerance, humidity-compensated, fan-failure,
  thermal-sustainability, door-tamper or absolute-accuracy claim.
- Any verdict that treats a common-mode ambient shift as sensor drift, a 0.0625 C spread as
  instability, or a 0.000 A reading as proven zero current.
- Any door-dependent verdict recorded before the 2026-11-05 polarity observation, and any
  door-dependent verdict recorded in a boot where the door was not re-attested.
