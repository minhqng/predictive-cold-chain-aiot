# Pairing candidate variables for future Controller A/B comparisons

> W07 / B-W07-04. These are candidate variables for a future physical
> A/B campaign. They are provisional: no numeric matching tolerance is
> set here and no pairing is performed by the W07 EDA.

## Candidate table

| Candidate | Class | Measurement definition | Physical meaning | Source field(s) | Time domain | Quality gate | Availability | Owner | Matching rationale | Confounding mechanism | Status | Missing-evidence reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Initial chamber-air temperature | MATCHING_VARIABLE | tmean_airroles_v0 = mean(T1 centre, T3 bottom, T4 near door) at the first full-term, thermally VALID row of the run, before any cooling action. | Starting sensible-heat state of the chamber air. | t1_c, t3_c, t4_c through the W04 normalized capture; roles from physical_position | DEVICE_BOOT_UPTIME (boot-relative); pre-intervention | thermal VALID; sequence/provenance VALID; W04 physically-qualified run | DIAGNOSTIC_ONLY in the current evidence (one session, admission blocked) | A measures/attests; B defines and consumes | A colder or warmer start shifts the whole cooling curve and time-to-threshold. | Initial-state difference masquerades as a Controller A/B effect if arms start in different bands. | PROVISIONAL | No qualified independent runs, no frozen initial-state band, no calibration identity. |
| Initial spatial temperature spread | MATCHING_VARIABLE | max(T1,T3,T4) - min(T1,T3,T4) at the same pre-intervention row. | Spatial non-uniformity / mixing state proxy, not heat flux. | t1_c, t3_c, t4_c | DEVICE_BOOT_UPTIME; pre-intervention | all three air probes present and thermally VALID at the same row | DIAGNOSTIC_ONLY | A measures; B defines | A stratified chamber can produce a different response with the same mean. | Non-uniform starting field and probe placement differences. | PROVISIONAL | No repeatability estimate for the spread and no frozen gradient tolerance. |
| Ambient temperature and relative humidity | MEASURED_COVARIATE | BME280 air temperature, RH and pressure during the run. | Heat-rejection environment and condensation context. | air_c, rh_pct, pressure_hpa | DEVICE_BOOT_UPTIME | environment section VALID and sensor qualification proved | UNQUALIFIED in the current capture (environment quality UNKNOWN) | A/C | Ambient conditions change heat rejection and passive warming. | Ambient drift across sequential arms becomes a treatment-correlated nuisance. | UNAVAILABLE_VARIABLE | Environment quality is UNKNOWN; BME implementation/qualification is unresolved. |
| Initial door state and recent event history | PROTOCOL_CONSTRAINT | Door CLOSED at run start and no unrecorded opening during the paired block. | Boundary condition for chamber-air exchange. | door_open, door_polarity | DEVICE_BOOT_UPTIME | door quality VALID, polarity commissioned, disturbance protocol executed | UNQUALIFIED/UNKNOWN (door quality UNKNOWN; 17 UNKNOWN rows) | A executes; B consumes | An open or recently opened door changes the load and recovery. | Unrecorded door disturbance or door-state label drift. | UNAVAILABLE_VARIABLE | Door polarity/state qualification and disturbance history are not certified. |
| Initial applied cooling state and duty | MATCHING_VARIABLE_AND_PROTOCOL_CONSTRAINT | Applied state OFF and applied duty 0 permille immediately before the step. | Actuator state at the start of the intervention. | pwm_applied_permille, pwm_req_permille, state | DEVICE_BOOT_UPTIME; pre-intervention | applied duty carried; contradiction checks pass | OBSERVED diagnostic (OFF/0 in the current session) | A | A residual prior action changes the starting thermal trajectory. | Applied-state leakage from the previous arm into the next arm. | PROVISIONAL | Applied-state observations are not command proof; no verified controller-arm identity. |
| Hardware configuration identity | PROTOCOL_CONSTRAINT | Same verified hardware_config_id and physical assembly for both arms. | Comparable plant and sensor installation. | hardware_config_id, hardware_config_status | Run-level metadata | hardware configuration VERIFIED, not merely declared | UNQUALIFIED (declared label CG-HW-001, not verified) | A | Any reassembly changes the plant and invalidates pairing (docs/01 §32). | Configuration drift masquerades as treatment effect. | UNAVAILABLE_VARIABLE | No verification evidence for the declared hardware label. |
| Calibration and sensor-role provenance | PROTOCOL_CONSTRAINT | Same calibration_id and role mapping, with ROM readback and position record. | Comparable measurement scale and physical meaning. | calibration_id, calibration_status, sensor role records | Run-level metadata | calibration VERIFIED; ROM readback verified; role mapping frozen | NOT_CARRIED (calibration identity absent; operator-frozen positions, ROM readback unverified) | A | A changed calibration or role mapping changes the measured outcome. | Measurement-definition drift masquerades as a plant/controller effect. | UNAVAILABLE_VARIABLE | No calibration exists on the current rig and no independent ROM readback is committed. |
| Thermal recovery / reset condition | MATCHING_VARIABLE | Observed chamber-air state and slope at the predeclared reset point before the next arm. | Whether the plant returned to a comparable starting condition. | tmean_airroles_v0 trajectory, applied state | DEVICE_BOOT_UPTIME; post-intervention but pre-next-arm state | reset criterion frozen; recovery not censored; thermal VALID | UNQUALIFIED (reset criterion UNRESOLVED; recovery censored) | A/D | Incomplete recovery carries heat history into the next arm. | Residual heat load and order effects. | UNAVAILABLE_VARIABLE | No frozen reset criterion or observed reset in the current single session. |
| Chamber load and geometry | PROTOCOL_CONSTRAINT | Same internal load, V1 position, door alignment and probe mounting. | Plant thermal mass and boundary geometry. | not carried in the capture | Run-level metadata | geometry frozen and recorded | UNKNOWN | A | Load or geometry changes alter thermal mass and response time. | Physical configuration differences confound the comparison. | UNAVAILABLE_VARIABLE | A-W07-01 remains PARTIAL; no configuration photo/drawing or load record. |
| Prior session heat accumulation | MATCHING_VARIABLE | Thermal history and elapsed recovery time before the run, with the previous arm's applied state. | Carry-over heat from earlier runs. | not carried in the capture | Session history | previous-session state and reset evidence available | UNKNOWN | A/B | Previous heating/cooling shifts the initial state and recovery. | Order and session-day effects correlated with the treatment arm. | UNAVAILABLE_VARIABLE | No prior-session history is carried; only one session exists in the dossier. |
| Cooling-branch electrical quality | MEASURED_COVARIATE | Qualified branch voltage/current/power/energy coverage for energy outcomes. | Actual electrical work delivered to the cooling branch. | voltage_v, current_a, power_w, energy_wh | DEVICE_BOOT_UPTIME | electrical quality VALID and PZEM range/calibration verified | UNQUALIFIED (no recorded electrical validity in the current capture) | A/C | Different electrical work changes the thermal response. | Electrical differences and unqualified meters masquerade as controller efficiency. | UNAVAILABLE_VARIABLE | Electrical status is unqualified; no qualified energy envelope or COP claim is allowed. |

Units: temperatures °C, slopes °C/min, power W, energy Wh,
current A, durations min; source fields retain their W04 normalized
names and time domains.

## Variable classes

- **Matching variable** — measured before the intervention and used to
  define comparable pairs.
- **Measured covariate** — recorded and modelled/adjusted, not silently
  assumed constant.
- **Protocol constraint** — must be identical by design, not merely
  observed afterwards.
- **Unavailable variable** — no qualified source field exists yet.

## Forbidden pairing inputs

Post-intervention outcomes must never define a pair retrospectively:
end temperature, ΔT, whole-phase slope, trailing slope,
time-to-threshold, recovery delta, peak power, energy and any response
derived from the future part of the run. Pairing uses only
pre-intervention state and recorded protocol identity.

## Tolerances

No numeric matching tolerance is claimed. Docs `03` §35 lists
`|Δ initial Tmean| <= ~0.5 °C` and `|Δ initial gradient| <= ~0.3 °C`
as **candidate pilot-era values only**. `statistical-analysis-plan-v0.md`
F6 records initial-condition tolerances as not set until pilot
repeatability exists. This report does not use or freeze either value.

## Consistency with W03/W04 methodology

Future pairs must satisfy the pair-admission checklist: same `pair_id`
on exactly two arms, same scenario/protocol/disturbance duration, same
hardware and calibration lineage, initial conditions within frozen
tolerances, randomized/balanced order, observed reset/recovery, and
comparable outcome definitions. One inadmissible arm makes the pair
invalid; it contributes zero pairs and is never repaired post hoc.

## Current availability

The present evidence has one boot session, no qualified independent
runs, no verified calibration, no verified hardware configuration and
no certified scenario. Every candidate above is therefore provisional
or unavailable; none has an empirically supported tolerance.
