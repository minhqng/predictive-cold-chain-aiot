# Leader integration overlay inside the Leader-owned component directory.
# ESP-IDF includes each component dir's project_include.cmake during
# __build_process_project_includes, BEFORE component targets are created, so
# a definition added here reaches every later translation unit.
#
# Inert unless the supervised-build environment sets the knob to exactly "1"
# (the trigger Member A's own documented seam expects: coldguard_config.h
# guards CG_BME280_TRIM_LAYOUT_CONFIRMED with #ifndef and sanctions a
# supervised -D=1 build only after the fitted-module decode is verified on
# hardware - evidence: fitted trim decode PASS with T- and H-match on the
# device's own diagnostic bytes, demo-out evidence bundle 2026-11-12).
# Per-build, never persisted, never actuator-enabling.
if(DEFINED ENV{COLDGUARD_BME280_TRIM_CONFIRM})
  if("$ENV{COLDGUARD_BME280_TRIM_CONFIRM}" STREQUAL "1")
    add_compile_definitions(CG_BME280_TRIM_LAYOUT_CONFIRMED=1)
  endif()
endif()
