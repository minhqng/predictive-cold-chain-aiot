/*
 * ColdGuard firmware - local operator console grammar (W04).
 */
#include "cg_tec_command.h"

#include <stdlib.h>
#include <string.h>

#define CG_TEC_CMD_LINE_MAX 96U
#define CG_TEC_CMD_MAX_SECONDS 86400UL

static bool is_space(char c)
{
    return c == ' ' || c == '\t';
}

static bool is_digit(char c)
{
    return c >= '0' && c <= '9';
}

static bool is_hex(char c)
{
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f');
}

static bool is_label_char(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || is_digit(c) || c == '_' || c == '-';
}

static bool equals_ci(const char *a, const char *b)
{
    while (*a != '\0' && *b != '\0') {
        char ca = *a;
        char cb = *b;
        if (ca >= 'a' && ca <= 'z') {
            ca = (char)(ca - 'a' + 'A');
        }
        if (cb >= 'a' && cb <= 'z') {
            cb = (char)(cb - 'a' + 'A');
        }
        if (ca != cb) {
            return false;
        }
        a++;
        b++;
    }
    return *a == '\0' && *b == '\0';
}

static bool token_is_hex8(const char *text)
{
    size_t len = strlen(text);
    if (len != 8U) {
        return false;
    }
    for (size_t i = 0; i < len; i++) {
        if (!is_hex(text[i])) {
            return false;
        }
    }
    return true;
}

static bool label_is_valid(const char *text)
{
    size_t len = strlen(text);
    if (len == 0U || len > 32U) {
        return false;
    }
    for (size_t i = 0; i < len; i++) {
        if (!is_label_char(text[i])) {
            return false;
        }
    }
    return true;
}

static bool phase_is_valid(const char *text)
{
    static const char *const phases[] = {"UNSET", "G0", "G1", "G2", "G3", "G4", "G5", "TEC_OFF"};
    for (size_t i = 0; i < sizeof(phases) / sizeof(phases[0]); i++) {
        if (equals_ci(text, phases[i])) {
            return true;
        }
    }
    return false;
}

/* Splits the trimmed line into a verb and at most one argument. */
static bool split_line(char *line, char **verb, char **arg)
{
    char *start = line;
    char *space;

    while (is_space(*start)) {
        start++;
    }
    if (*start == '\0') {
        return false;
    }
    space = strchr(start, ' ');
    if (space == NULL) {
        space = strchr(start, '\t');
    }
    if (space == NULL) {
        *verb = start;
        *arg = NULL;
        return true;
    }
    *space = '\0';
    *arg = space + 1;
    while (is_space(**arg)) {
        (*arg)++;
    }
    if (**arg == '\0') {
        *arg = NULL;
        return true;
    }
    if (strchr(*arg, ' ') != NULL || strchr(*arg, '\t') != NULL) {
        return false; /* more than one argument */
    }
    return true;
}

bool cg_tec_command_parse(const char *line, cg_tec_command_t *out, const char **error)
{
    char buffer[CG_TEC_CMD_LINE_MAX];
    size_t len;
    char *verb;
    char *arg;
    char *end;

    if (error != NULL) {
        *error = "OK";
    }
    if (line == NULL || out == NULL) {
        if (error != NULL) {
            *error = "NULL_LINE";
        }
        return false;
    }
    len = strlen(line);
    while (len > 0U && (line[len - 1U] == '\r' || line[len - 1U] == '\n' ||
                        is_space(line[len - 1U]))) {
        len--;
    }
    if (len == 0U) {
        if (error != NULL) {
            *error = "EMPTY_LINE";
        }
        return false;
    }
    if (len >= sizeof(buffer)) {
        if (error != NULL) {
            *error = "LINE_TOO_LONG";
        }
        return false;
    }
    memcpy(buffer, line, len);
    buffer[len] = '\0';

    if (!split_line(buffer, &verb, &arg)) {
        if (error != NULL) {
            *error = "BAD_ARITY";
        }
        return false;
    }

    memset(out, 0, sizeof(*out));

    if (equals_ci(verb, "ARM") || equals_ci(verb, "CLEAR")) {
        const cg_tec_command_kind_t kind =
            equals_ci(verb, "ARM") ? CG_TEC_CMD_ARM : CG_TEC_CMD_CLEAR;
        if (arg == NULL) {
            if (error != NULL) {
                *error = "BAD_ARITY";
            }
            return false;
        }
        if (!token_is_hex8(arg)) {
            if (error != NULL) {
                *error = "BAD_TOKEN";
            }
            return false;
        }
        out->kind = kind;
        memcpy(out->arg, arg, 8U);
        out->arg[8] = '\0';
        return true;
    }

    if (equals_ci(verb, "RUN")) {
        if (arg == NULL) {
            if (error != NULL) {
                *error = "BAD_ARITY";
            }
            return false;
        }
        if (!label_is_valid(arg)) {
            if (error != NULL) {
                *error = "BAD_LABEL";
            }
            return false;
        }
        out->kind = CG_TEC_CMD_RUN;
        memcpy(out->arg, arg, strlen(arg));
        return true;
    }

    if (equals_ci(verb, "PHASE")) {
        if (arg == NULL) {
            if (error != NULL) {
                *error = "BAD_ARITY";
            }
            return false;
        }
        if (!phase_is_valid(arg)) {
            if (error != NULL) {
                *error = "BAD_PHASE";
            }
            return false;
        }
        out->kind = CG_TEC_CMD_PHASE;
        memcpy(out->arg, arg, strlen(arg));
        for (char *p = out->arg; *p != '\0'; p++) {
            if (*p >= 'a' && *p <= 'z') {
                *p = (char)(*p - 'a' + 'A');
            }
        }
        return true;
    }

    if (equals_ci(verb, "START")) {
        unsigned long seconds;
        if (arg == NULL) {
            if (error != NULL) {
                *error = "BAD_ARITY";
            }
            return false;
        }
        for (char *p = arg; *p != '\0'; p++) {
            if (!is_digit(*p)) {
                if (error != NULL) {
                    *error = "BAD_SECONDS";
                }
                return false;
            }
        }
        seconds = (unsigned long)strtoul(arg, &end, 10);
        if (end == arg || *end != '\0' || seconds == 0UL || seconds > CG_TEC_CMD_MAX_SECONDS) {
            if (error != NULL) {
                *error = "BAD_SECONDS";
            }
            return false;
        }
        out->kind = CG_TEC_CMD_START;
        out->value = (uint32_t)seconds;
        return true;
    }

    if (equals_ci(verb, "STOP") || equals_ci(verb, "ESTOP") || equals_ci(verb, "STATUS")) {
        if (arg != NULL) {
            if (error != NULL) {
                *error = "BAD_ARITY";
            }
            return false;
        }
        out->kind = equals_ci(verb, "STOP")
                        ? CG_TEC_CMD_STOP
                        : (equals_ci(verb, "ESTOP") ? CG_TEC_CMD_ESTOP : CG_TEC_CMD_STATUS);
        return true;
    }

    if (error != NULL) {
        *error = "UNKNOWN_COMMAND";
    }
    return false;
}

const char *cg_tec_command_name(cg_tec_command_kind_t kind)
{
    switch (kind) {
        case CG_TEC_CMD_ARM:
            return "ARM";
        case CG_TEC_CMD_START:
            return "START";
        case CG_TEC_CMD_STOP:
            return "STOP";
        case CG_TEC_CMD_ESTOP:
            return "ESTOP";
        case CG_TEC_CMD_CLEAR:
            return "CLEAR";
        case CG_TEC_CMD_RUN:
            return "RUN";
        case CG_TEC_CMD_PHASE:
            return "PHASE";
        case CG_TEC_CMD_STATUS:
            return "STATUS";
        case CG_TEC_CMD_NONE:
        default:
            return "NONE";
    }
}
