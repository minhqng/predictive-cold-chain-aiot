# ColdGuard Member A — W21 Physical Reliability Soak Protocol

**Requirement Authority:** `docs/05A §30: A-W21-01`  
**Status:** **SOFTWARE_READY / PENDING_OPERATOR_RUN**

---

## 1. Protocol Specifications

1. **Duration:** 2 to 4 hours of continuous telemetry recording at ~1 Hz.
2. **Monitored Invariants:**
   - Monotonic increase of `uptime_ms` (0 unexpected ESP32-S3 reboots or watchdog resets).
   - Sensor read error counts across DS18B20 1-Wire bus (T1, T2, T3, T4) and BME280 I2C bus.
   - Modbus RTU communication timeout count on PZEM-017.
   - Temperature stability: heatsink hot-side steady equilibrium check.
