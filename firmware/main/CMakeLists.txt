idf_component_register(
    SRCS
        "app_main.c"
        "cg_rom_map.c"
        "cg_onewire.c"
        "cg_ds18b20.c"
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
