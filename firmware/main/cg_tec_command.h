/*
 * ColdGuard firmware - local operator console grammar (W04).
 *
 * Pure C and strict: a line is either a complete, valid command or it is
 * rejected with a reason token. There is no partial acceptance, no numeric
 * coercion and no way to express a reverse or an unbounded run.
 *
 *   ARM <8 hex token>   authorize one bounded run (token printed at boot)
 *   START <seconds>     request a run with the configured duty and duration
 *   STOP                operator stop (cool-down follows)
 *   ESTOP               immediate output off, latching fault
 *   CLEAR <8 hex token> clear a latched fault (healthy inputs required)
 *   RUN <label>         set the experiment label carried in TEMETRY lines
 *   PHASE <name>        UNSET | G0..G5 | TEC_OFF
 *   STATUS              print the controller status
 *
 * The console is local UART only. No network command path exists in this
 * firmware, so nothing remote can override a local protection.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define CG_TEC_CMD_ARG_MAX 33

typedef enum {
    CG_TEC_CMD_NONE = 0,
    CG_TEC_CMD_ARM,
    CG_TEC_CMD_START,
    CG_TEC_CMD_STOP,
    CG_TEC_CMD_ESTOP,
    CG_TEC_CMD_CLEAR,
    CG_TEC_CMD_RUN,
    CG_TEC_CMD_PHASE,
    CG_TEC_CMD_STATUS,
    /* W06 local test bridge. It feeds the SAME canonical validator as a backend
     * command would, and its record is stamped source=LOCAL_CONSOLE and
     * command_id_form=TEST_TOKEN, so it can never be mistaken for a docs/02
     * network command in the evidence. It has no clock to stamp absolute
     * expiry with, so through the validator it is blocked fail-closed. */
    CG_TEC_CMD_CMDTEST,
} cg_tec_command_kind_t;

typedef struct {
    cg_tec_command_kind_t kind;
    char arg[CG_TEC_CMD_ARG_MAX];
    uint32_t value; /* START: requested duration in seconds; CMDTEST: duty permille */
    uint8_t flag;   /* CMDTEST: 1 = cooling ON, 0 = cooling OFF */
} cg_tec_command_t;

/* Parses one line (without the trailing newline is fine). On failure returns
 * false and points `error` at a stable reason token. */
bool cg_tec_command_parse(const char *line, cg_tec_command_t *out, const char **error);

const char *cg_tec_command_name(cg_tec_command_kind_t kind);
