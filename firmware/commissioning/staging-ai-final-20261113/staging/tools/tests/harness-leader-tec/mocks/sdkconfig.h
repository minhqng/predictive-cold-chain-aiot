/*
 * Host-harness sdkconfig.h, Leader-owned.
 *
 * Every CONFIG_ the code under test may read defaults to the shipped
 * configuration (adapter off, no interlock installed, defaults preserved).
 * The test driver overrides with -D per variant, exactly like a real
 * sdkconfig selection does on target.
 */
#pragma once

#ifndef CONFIG_CG_LEADER_TEC_HW
#define CONFIG_CG_LEADER_TEC_HW 0
#endif

#ifndef CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN
#define CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN (-1)
#endif

#ifndef CONFIG_CG_LEADER_TEC_HW_ACTIVE_LOW
#define CONFIG_CG_LEADER_TEC_HW_ACTIVE_LOW 1
#endif

#ifndef CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS
#define CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS 0
#endif
