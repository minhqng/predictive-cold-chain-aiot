idf_component_register(
    SRCS
        "app_main.c"
        "cg_rom_map.c"
        "cg_onewire.c"
        "cg_ds18b20.c"
        "cg_bme280.c"
        "cg_bme280_idf.c"
        "cg_door.c"
        "cg_safety.c"
        "cg_log.c"
        "cg_crc16.c"
        "cg_pzem.c"
        "cg_rs485.c"
        "cg_power.c"
        "cg_actuator.c"
        "cg_tec_limits.c"
        "cg_tec_control.c"
        "cg_tec_hw.c"
        "cg_tec_command.c"
        "cg_snapshot.c"
        "cg_quality.c"
        "cg_health.c"
        "cg_telemetry.c"
        "cg_command.c"
        "cg_console.c"
        "cg_commission.c"
    INCLUDE_DIRS "."
    REQUIRES esp_timer nvs_flash
    # GPIO APIs (driver/gpio.h) live in esp_driver_gpio and UART APIs
    # (driver/uart.h) live in esp_driver_uart on ESP-IDF v6.x: the legacy
    # "driver" meta-component no longer re-exports those headers. Both must
    # be direct requirements of this component. I2C (driver/i2c_master.h) is
    # used by the BME280 transport only.
    PRIV_REQUIRES esp_driver_gpio esp_driver_uart esp_driver_i2c
)

# CG_BME280_TRIM_LAYOUT_CONFIRMED is the fitted-trim verification gate. The
# default build leaves the header default (0, fail closed). A supervised build
# passes -DCG_BME280_TRIM_LAYOUT_CONFIRMED=1 only after the corrected decode of
# the fitted module's calibration registers has been verified on hardware.
set(CG_BME280_TRIM_LAYOUT_CONFIRMED "" CACHE STRING
    "1 to publish BME280 ambient after fitted-trim verification ('' keeps the fail-closed default)")
if(CG_BME280_TRIM_LAYOUT_CONFIRMED STREQUAL "0" OR CG_BME280_TRIM_LAYOUT_CONFIRMED STREQUAL "1")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        CG_BME280_TRIM_LAYOUT_CONFIRMED=${CG_BME280_TRIM_LAYOUT_CONFIRMED})
elseif(NOT CG_BME280_TRIM_LAYOUT_CONFIRMED STREQUAL "")
    message(FATAL_ERROR
            "CG_BME280_TRIM_LAYOUT_CONFIRMED must be '', 0 or 1 (got '${CG_BME280_TRIM_LAYOUT_CONFIRMED}')")
endif()
