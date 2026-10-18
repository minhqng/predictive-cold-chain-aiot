idf_component_register(
    SRCS
        "app_main.c"
        "cg_rom_map.c"
        "cg_onewire.c"
        "cg_ds18b20.c"
        "cg_door.c"
        "cg_safety.c"
        "cg_log.c"
    INCLUDE_DIRS "."
    REQUIRES esp_timer nvs_flash
    # GPIO APIs (driver/gpio.h) live in esp_driver_gpio on ESP-IDF v6.x. The
    # legacy "driver" meta-component no longer re-exports that header, so the
    # esp32s3 build fails with "driver/gpio.h: No such file or directory"
    # unless esp_driver_gpio is a direct requirement of this component.
    PRIV_REQUIRES esp_driver_gpio
)
