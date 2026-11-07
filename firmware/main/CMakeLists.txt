idf_component_register(
    SRCS
        "app_main.c"
        "cg_rom_map.c"
        "cg_onewire.c"
        "cg_ds18b20.c"
        "cg_fault_inject.c"
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
    # be direct requirements of this component.
    PRIV_REQUIRES esp_driver_gpio esp_driver_uart
)

# CG_FAULT_INJECTION is a test-only, auditable build switch (A-W21-02/03). The
# default build leaves the header default (0), so the injection path is inert.
# Only an explicit test build passes -DCG_FAULT_INJECTION=1, which is forwarded
# to the compiler here so it actually reaches cg_ds18b20.c / cg_power.c /
# cg_console.c (a bare idf.py -D is only a CMake cache variable).
set(CG_FAULT_INJECTION "" CACHE STRING
    "1 to enable the reversible local-console fault injection path for a supervised W21 test build ('' keeps it disabled)")
if(CG_FAULT_INJECTION STREQUAL "0" OR CG_FAULT_INJECTION STREQUAL "1")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        CG_FAULT_INJECTION=${CG_FAULT_INJECTION})
elseif(NOT CG_FAULT_INJECTION STREQUAL "")
    message(FATAL_ERROR
            "CG_FAULT_INJECTION must be '', 0 or 1 (got '${CG_FAULT_INJECTION}')")
endif()
