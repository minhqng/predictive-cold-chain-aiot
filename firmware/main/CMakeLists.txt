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
    REQUIRES driver esp_timer nvs_flash
)
