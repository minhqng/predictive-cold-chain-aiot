/*
 * Leader TEC hardware adapter - public surface (Leader-owned).
 *
 * The adapter interposes Member A's accessor via --wrap=cg_tec_hw_ops when
 * CONFIG_CG_LEADER_TEC_HW=1. The member controller keeps every decision;
 * this layer only answers hardware truthfully or refuses and force-offs.
 */
#pragma once

#include <stdbool.h>

#include "cg_tec_limits.h"
#include "cg_tec_platform.h"

/* The Leader ops table (same shape as the delivered stub's). */
const cg_tec_hw_ops_t *cg_leader_tec_hw_ops(void);

/* Passive evidence accessor: the limit table pointer the init interposition
 * actually handed the member controller, or NULL before that call. Never a
 * substitute for the table that was passed. Read-only; callers must not
 * treat a non-NULL result as proof that every entry is resolved. */
const cg_tec_limit_table_t *cg_leader_tec_effective_limits(void);

/* Where that table came from: "SUPERVISED" (the recorded session envelope),
 * "MEMBER_SHIPPED" (the delivered all-UNRESOLVED table), "CALLER_TABLE"
 * (some other pointer the caller supplied), or NULL before init. */
const char *cg_leader_tec_effective_limits_source(void);

/* The cold-side presence policy the member controller actually enforces
 * after init: true for the normal build, false only for the explicitly
 * selected supervised no-cold-probe profile. Read-only evidence; never a
 * way to change the policy. */
bool cg_leader_tec_cold_probe_required(void);

/* The continuous policy the member controller actually received: false for
 * every default build; true only for the fully gated TEC1000 full-duty demo.
 * Read-only evidence used by LEADER_CONFIG and the gateway's GRANT binding. */
bool cg_leader_tec_continuous_allowed(void);
