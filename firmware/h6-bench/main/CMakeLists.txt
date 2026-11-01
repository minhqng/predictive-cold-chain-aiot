idf_component_register(
    SRCS
        "h6_main.c"
        "h6_state.c"
        "h6_selftest.c"
        "h6_pzem.c"
    INCLUDE_DIRS "."
    REQUIRES esp_timer console esp_driver_gpio esp_driver_uart esp_driver_ledc esp_driver_usb_serial_jtag
)
