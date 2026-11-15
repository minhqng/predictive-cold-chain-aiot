/*
 * ColdGuard firmware - test-only reversible fault injection. See cg_fault_inject.h
 * for the safety contract; the whole implementation compiles to inert stubs when
 * CG_FAULT_INJECTION is 0.
 */
#include "cg_fault_inject.h"

#include "coldguard_config.h"

#include <string.h>

#if CG_FAULT_INJECTION

/* cg_role_t indices (cg_rom_map.h): T1=0, T2=1, T3=2, SPARE=3. */

static int s_ds_role = -1;      /* -1 = none injected */
static bool s_pzem_down = false;

/* Portable whitespace tokenizer (no strtok_r: ESP-IDF newlib has it but the
 * host harness toolchain may not). Returns the position after the token, or
 * NULL at end of input. Sets *truncated when a token exceeded the buffer, in
 * which case the caller rejects the command as malformed. */
static const char *next_token(const char *p, char *out, size_t cap, bool *truncated)
{
    size_t i = 0u;
    *truncated = false;
    while (*p == ' ' || *p == '\t') {
        p++;
    }
    if (*p == '\0') {
        return NULL;
    }
    while (*p != '\0' && *p != ' ' && *p != '\t') {
        if (i + 1u < cap) {
            out[i++] = *p;
        } else {
            *truncated = true;
        }
        p++;
    }
    out[i] = '\0';
    return p;
}

static int parse_role(const char *tok)
{
    if (strcmp(tok, "T1") == 0) {
        return 0;
    }
    if (strcmp(tok, "T2") == 0) {
        return 1;
    }
    if (strcmp(tok, "T3") == 0) {
        return 2;
    }
    if (strcmp(tok, "SPARE") == 0) {
        return 3;
    }
    return -1;
}

static bool parse_onoff(const char *tok, bool *out)
{
    if (strcmp(tok, "ON") == 0) {
        *out = true;
        return true;
    }
    if (strcmp(tok, "OFF") == 0) {
        *out = false;
        return true;
    }
    return false;
}

bool cg_fault_inject_enabled(void)
{
    return true;
}

bool cg_fault_inject_ds_active(int role)
{
    return s_ds_role >= 0 && role == s_ds_role;
}

bool cg_fault_inject_pzem_down(void)
{
    return s_pzem_down;
}

/* The currently injected DS role index, or -1. Exposed so the local console can
 * echo state for operator confirmation; never used to decide actuation. */
int cg_fault_inject_ds_role(void)
{
    return s_ds_role;
}

void cg_fault_inject_reset(void)
{
    s_ds_role = -1;
    s_pzem_down = false;
}

/* Grammar (local console only):
 *   FAULT DS <T1|T2|T3|SPARE> <ON|OFF>
 *   FAULT PZEM <ON|OFF>
 *   FAULT CLEAR
 *   FAULT STATUS
 * Anything whose first token is exactly FAULT is consumed (a malformed or
 * unknown FAULT command is rejected with no state change) so it can never fall
 * through to the TEC command path. A line whose first token is not FAULT
 * returns false and is left for the normal parser. */
bool cg_fault_inject_console_line(const char *line)
{
    char tok[16];
    char val[16];
    const char *p;
    bool trunc = false;
    bool on;
    int role;

    if (line == NULL) {
        return false;
    }
    p = next_token(line, tok, sizeof(tok), &trunc);
    if (p == NULL || trunc || strcmp(tok, "FAULT") != 0) {
        return false;   /* not our verb: leave it to the normal console parser */
    }
    p = next_token(p, tok, sizeof(tok), &trunc);
    if (p == NULL) {
        return true;                     /* bare "FAULT": consume, no change */
    }
    if (trunc) {
        return true;                     /* malformed verb: consume, reject */
    }
    if (strcmp(tok, "CLEAR") == 0) {
        cg_fault_inject_reset();
        return true;
    }
    if (strcmp(tok, "STATUS") == 0) {
        return true;                     /* state is observable via telemetry */
    }
    if (strcmp(tok, "DS") == 0) {
        const char *q = next_token(p, tok, sizeof(tok), &trunc);
        if (q == NULL || trunc) {
            return true;                 /* missing role: reject */
        }
        const char *r = next_token(q, val, sizeof(val), &trunc);
        if (r == NULL || trunc) {
            return true;                 /* missing value: reject */
        }
        if (next_token(r, val, sizeof(val), &trunc) != NULL) {
            return true;                 /* trailing token: reject, no change */
        }
        role = parse_role(tok);
        if (role < 0 || !parse_onoff(val, &on)) {
            return true;                 /* unknown role / bad value: reject */
        }
        if (on) {
            s_ds_role = role;            /* exactly one selected ROM at a time */
        } else if (s_ds_role == role) {
            s_ds_role = -1;              /* OFF clears only the matching role */
        }
        return true;
    }
    if (strcmp(tok, "PZEM") == 0) {
        const char *q = next_token(p, val, sizeof(val), &trunc);
        if (q == NULL || trunc || !parse_onoff(val, &on)) {
            return true;                 /* malformed: reject, no change */
        }
        if (next_token(q, val, sizeof(val), &trunc) != NULL) {
            return true;                 /* trailing token: reject, no change */
        }
        s_pzem_down = on;
        return true;
    }
    return true;                         /* unknown FAULT subcommand: consume */
}

#else  /* CG_FAULT_INJECTION == 0: production build, injection entirely inert. */

bool cg_fault_inject_enabled(void)
{
    return false;
}

bool cg_fault_inject_ds_active(int role)
{
    (void)role;
    return false;
}

bool cg_fault_inject_pzem_down(void)
{
    return false;
}

int cg_fault_inject_ds_role(void)
{
    return -1;
}

void cg_fault_inject_reset(void)
{
}

bool cg_fault_inject_console_line(const char *line)
{
    (void)line;
    return false;   /* never consumes; a FAULT line is an unknown command */
}

#endif
