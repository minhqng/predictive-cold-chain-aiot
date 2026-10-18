# ColdGuard W02 — DS18B20 bench report

**Provenance:** standalone Arduino/OneWire/DallasTemperature, NOT official ESP-IDF firmware.
- Captured on host (UTC start): 2026-10-18T12:40:41.375298+00:00
- Serial port: COM4; 115200 baud
- Original serial log SHA-256: `44228795d48f223b1fdde619c184eccd1c34a56f4dd3d19fdfa12f239289b91c`
- Samples captured: 620/620
- Elapsed between first/last sample: 619.000 seconds
- Interval min/max: 1000/1000 ms
- Status: **NOT PASS**

## Statistics (sample SD)

| Role | N | Mean (°C) | SD (°C) | Min (°C) | Max (°C) |
|---|---:|---:|---:|---:|---:|
| T1 | 620 | 29.8785 | 0.0215 | 29.8125 | 29.9375 |
| T2 | 620 | 30.1879 | 0.0163 | 30.1250 | 30.2500 |
| T3 | 620 | 29.5683 | 0.0234 | 29.5000 | 29.6250 |
| SPARE | 620 | 29.9218 | 0.0281 | 29.8125 | 29.9375 |

## Pairwise mean differences (T1/T2/T3)

- T1 − T2: -0.3094 °C
- T1 − T3: +0.3102 °C
- T2 − T3: +0.6196 °C
- Maximum instantaneous disagreement (T1/T2/T3): 0.6875 °C

## Observed ROMs


## Validation issues

- ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG

Test context: probes should share a stable ambient condition; record actual physical arrangement separately. Not traceable calibration.
Full W02 still needs official ESP-IDF runtime/reboot evidence, labeling and H0 decision.
