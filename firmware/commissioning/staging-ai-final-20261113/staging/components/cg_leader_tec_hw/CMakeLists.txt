# Leader-owned integration component (external to all delivered member
# files, which are imported and interposed, never edited).
idf_component_register(
    SRCS
        "cg_leader_tec_hw.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gpio esp_driver_ledc
    PRIV_REQUIRES esp_timer
)

# The component reads the delivered Member A contract headers directly
# (cg_tec_platform.h, cg_actuator.h, coldguard_config.h) and resolves the
# delivered symbols at final link, so the delivered component graph stays
# exactly as shipped - no component dependency in either direction.
target_include_directories(${COMPONENT_LIB} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/../../main")

# Linker-level interposition on the hardware accessor boundary:
# - cg_tec_hw_ops: the member controller binds whatever this accessor
#   returns at init; the wrap lets a commissioning sdkconfig hand it the
#   Leader IBT-2 adapter while every shipped build keeps the delivered
#   refusing stub unchanged.
target_link_libraries(${COMPONENT_LIB} INTERFACE
    "-Wl,--wrap=cg_tec_hw_ops"
    "-Wl,--wrap=cg_tec_control_init"
)
