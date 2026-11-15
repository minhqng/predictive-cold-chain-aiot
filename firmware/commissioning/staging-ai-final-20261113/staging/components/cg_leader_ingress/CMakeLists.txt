# Leader-owned integration component (external to all delivered member
# files, which are imported and interposed, never edited).
idf_component_register(
    SRCS
        "cg_leader_ingress.c"
        "cg_leader_ingress_core.c"
    INCLUDE_DIRS "."
    REQUIRES esp_timer
    PRIV_REQUIRES esp_driver_uart esp_driver_usb_serial_jtag
                  esp_app_format esp_partition app_update cg_leader_tec_hw
)

# The component reads the delivered Member A/D contract headers directly
# (cg_command.h, cg_tec_*.h, cg_log.h, coldguard_config.h) and resolves the
# delivered symbols at final link, so the delivered component graph stays
# exactly as shipped - no component dependency in either direction.
target_include_directories(${COMPONENT_LIB} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/../../main")

# Linker-level interposition on the delivered module boundaries:
# - cg_console_start hosts the Leader reader (member console.c stays intact
#   in the tree and remains the active reader for test builds and opt-outs);
# - cg_log_raw_line observes the device's own published world (TELEM).
# The wrap makes the member console object unreachable through any static
# reference, and with it the archive member that defines cg_tec_command_parse
# (the delivered console grammar is the only delivered caller); -u keeps that
# member linked without whole-archive side effects.
target_link_libraries(${COMPONENT_LIB} INTERFACE
    "-Wl,--wrap=cg_console_start"
    "-Wl,--wrap=cg_log_raw_line"
    "-Wl,--wrap=cg_door_state"
    "-Wl,--wrap=cg_door_attest_polarity"
    "-Wl,-u,cg_tec_command_parse"
)
