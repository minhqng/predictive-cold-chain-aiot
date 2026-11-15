/*
 * ColdGuard H6 - self-test implementation.
 *
 * Covers: legal transitions only, one run per boot, first-stop-reason latch,
 * the 60 s boundary at 59 999 999 / 60 000 000 us, elapsed semantics, and the
 * PZEM framing classifier against synthetic RX streams (echo prefix, partial
 * reply, wrong register count, CRC failure, exception, ambiguity).
 */
#include "h6_selftest.h"

#include <stddef.h>

#include "h6_config.h"
#include "h6_pzem.h"
#include "h6_state.h"

static unsigned s_checks;
static unsigned s_failures;
static int s_first_failure_line;

#define CHECK(cond)                                                          \
    do {                                                                     \
        s_checks++;                                                          \
        if (!(cond)) {                                                       \
            s_failures++;                                                    \
            if (s_first_failure_line == 0) {                                 \
                s_first_failure_line = __LINE__;                             \
            }                                                                \
        }                                                                    \
    } while (0)

static void force_state(h6_sm_t *sm, h6_state_t state)
{
    h6_sm_init(sm);
    switch (state) {
    case H6_STATE_BOOT:
        break;
    case H6_STATE_SAFE_OFF:
        (void)h6_sm_safe_off(sm);
        break;
    case H6_STATE_WAIT_FOR_MANUAL_ARM:
        (void)h6_sm_safe_off(sm);
        (void)h6_sm_ready(sm);
        break;
    case H6_STATE_ARMED:
        (void)h6_sm_safe_off(sm);
        (void)h6_sm_ready(sm);
        (void)h6_sm_arm(sm);
        break;
    case H6_STATE_RUNNING_10_PERCENT:
        (void)h6_sm_safe_off(sm);
        (void)h6_sm_ready(sm);
        (void)h6_sm_arm(sm);
        (void)h6_sm_start(sm, 1000000);
        break;
    case H6_STATE_SAFE_OFF_FINAL:
        (void)h6_sm_safe_off(sm);
        (void)h6_sm_ready(sm);
        (void)h6_sm_arm(sm);
        (void)h6_sm_start(sm, 1000000);
        (void)h6_sm_stop(sm, H6_STOP_TIMEOUT, 2000000);
        break;
    case H6_STATE_COMPLETE:
        (void)h6_sm_safe_off(sm);
        (void)h6_sm_ready(sm);
        (void)h6_sm_arm(sm);
        (void)h6_sm_start(sm, 1000000);
        (void)h6_sm_stop(sm, H6_STOP_TIMEOUT, 2000000);
        (void)h6_sm_complete(sm);
        break;
    }
    CHECK(sm->state == state);
}

static void test_happy_path(void)
{
    h6_sm_t sm;
    h6_sm_init(&sm);
    CHECK(sm.state == H6_STATE_BOOT);
    CHECK(sm.stop_reason == H6_STOP_NONE);
    CHECK(!sm.run_consumed);

    CHECK(h6_sm_safe_off(&sm));
    CHECK(sm.state == H6_STATE_SAFE_OFF);
    CHECK(h6_sm_ready(&sm));
    CHECK(sm.state == H6_STATE_WAIT_FOR_MANUAL_ARM);

    CHECK(h6_sm_arm(&sm));
    CHECK(sm.state == H6_STATE_ARMED);

    CHECK(h6_sm_start(&sm, 5000000));
    CHECK(sm.state == H6_STATE_RUNNING_10_PERCENT);
    CHECK(sm.run_consumed);
    CHECK(sm.run_start_us == 5000000);

    CHECK(h6_sm_stop(&sm, H6_STOP_OPERATOR, 12500000));
    CHECK(sm.state == H6_STATE_SAFE_OFF_FINAL);
    CHECK(sm.stop_reason == H6_STOP_OPERATOR);
    CHECK(h6_sm_elapsed_us(&sm, 90000000) == 7500000);

    CHECK(h6_sm_complete(&sm));
    CHECK(sm.state == H6_STATE_COMPLETE);
}

static void test_matrix(void)
{
    static const h6_state_t states[] = {
        H6_STATE_BOOT,
        H6_STATE_SAFE_OFF,
        H6_STATE_WAIT_FOR_MANUAL_ARM,
        H6_STATE_ARMED,
        H6_STATE_RUNNING_10_PERCENT,
        H6_STATE_SAFE_OFF_FINAL,
        H6_STATE_COMPLETE,
    };

    for (size_t i = 0; i < sizeof(states) / sizeof(states[0]); i++) {
        const h6_state_t state = states[i];
        const bool can_safe_off = (state == H6_STATE_BOOT);
        const bool can_ready = (state == H6_STATE_SAFE_OFF);
        const bool can_arm = (state == H6_STATE_WAIT_FOR_MANUAL_ARM);
        const bool can_start = (state == H6_STATE_ARMED);
        const bool can_stop = (state == H6_STATE_RUNNING_10_PERCENT);
        const bool can_complete = (state == H6_STATE_SAFE_OFF_FINAL);

        h6_sm_t sm;
        force_state(&sm, state);
        CHECK(h6_sm_safe_off(&sm) == can_safe_off);
        force_state(&sm, state);
        CHECK(h6_sm_ready(&sm) == can_ready);
        force_state(&sm, state);
        CHECK(h6_sm_arm(&sm) == can_arm);
        force_state(&sm, state);
        CHECK(h6_sm_start(&sm, 7000000) == can_start);
        force_state(&sm, state);
        CHECK(h6_sm_stop(&sm, H6_STOP_FAULT, 8000000) == can_stop);
        force_state(&sm, state);
        CHECK(h6_sm_complete(&sm) == can_complete);
    }
}

static void test_one_run_per_boot(void)
{
    h6_sm_t sm;
    force_state(&sm, H6_STATE_SAFE_OFF_FINAL);
    CHECK(!h6_sm_start(&sm, 9000000));
    CHECK(!h6_sm_start(&sm, 9000001));
    CHECK(h6_sm_complete(&sm));
    CHECK(!h6_sm_start(&sm, 9000002));
    CHECK(sm.run_consumed);

    force_state(&sm, H6_STATE_ARMED);
    sm.run_consumed = true;
    CHECK(!h6_sm_start(&sm, 9000003));
    CHECK(sm.state == H6_STATE_ARMED);
}

static void test_stop_reason_latch(void)
{
    h6_sm_t sm;
    force_state(&sm, H6_STATE_RUNNING_10_PERCENT);
    CHECK(h6_sm_stop(&sm, H6_STOP_TELEMETRY_INVALID, 6000000));
    CHECK(!h6_sm_stop(&sm, H6_STOP_OPERATOR, 6000001));
    CHECK(sm.stop_reason == H6_STOP_TELEMETRY_INVALID);
    CHECK(sm.run_stop_us == 6000000);
}

static void test_deadline_boundary(void)
{
    h6_sm_t sm;
    force_state(&sm, H6_STATE_RUNNING_10_PERCENT);

    const int64_t start = sm.run_start_us;
    CHECK(!h6_sm_deadline_reached(&sm, start + H6_MAX_ON_US - 1));
    CHECK(h6_sm_deadline_reached(&sm, start + H6_MAX_ON_US));
    CHECK(h6_sm_deadline_reached(&sm, start + H6_MAX_ON_US + 1));
    CHECK(!h6_sm_deadline_reached(&sm, start + H6_MAX_ON_US - 1000));

    CHECK(h6_sm_stop(&sm, H6_STOP_TIMEOUT, start + H6_MAX_ON_US));
    CHECK(!h6_sm_deadline_reached(&sm, start + H6_MAX_ON_US * 10));
}

static void test_elapsed_semantics(void)
{
    h6_sm_t sm;
    force_state(&sm, H6_STATE_WAIT_FOR_MANUAL_ARM);
    CHECK(h6_sm_elapsed_us(&sm, 123456789) == 0);

    force_state(&sm, H6_STATE_RUNNING_10_PERCENT);
    CHECK(h6_sm_elapsed_us(&sm, sm.run_start_us) == 0);
    CHECK(h6_sm_elapsed_us(&sm, sm.run_start_us + 2500000) == 2500000);

    (void)h6_sm_stop(&sm, H6_STOP_OPERATOR, sm.run_start_us + 3000000);
    CHECK(h6_sm_elapsed_us(&sm, sm.run_start_us + 90000000) == 3000000);

    (void)h6_sm_complete(&sm);
    CHECK(h6_sm_elapsed_us(&sm, sm.run_start_us + 90000000) == 3000000);
}

static void test_names(void)
{
    CHECK(h6_state_name(H6_STATE_BOOT) != NULL);
    CHECK(h6_state_name(H6_STATE_RUNNING_10_PERCENT) != NULL);
    CHECK(h6_state_name(H6_STATE_COMPLETE) != NULL);
    CHECK(h6_stop_reason_name(H6_STOP_TIMEOUT) != NULL);
    CHECK(h6_stop_reason_name(H6_STOP_OPERATOR) != NULL);
    CHECK(h6_state_name((h6_state_t)99) != NULL);
    CHECK(h6_stop_reason_name((h6_stop_reason_t)99) != NULL);
    CHECK(h6_pzem_class_name(H6_PZEM_CLASS_OK) != NULL);
    CHECK(h6_pzem_class_name((h6_pzem_class_t)99) != NULL);
}

/* Frames below are the real Modbus bytes (CRC16/MODBUS computed offline). */
static const uint8_t k_tx6[8] = {0x01, 0x04, 0x00, 0x00, 0x00, 0x06, 0x70, 0x08};
static const uint8_t k_resp6[17] = {0x01, 0x04, 0x0C, 0x04, 0xAC, 0x00, 0x00, 0x00, 0x00,
                                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x59, 0x2A};
static const uint8_t k_resp8[21] = {0x01, 0x04, 0x10, 0x04, 0xAC, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFB, 0x92};
static const uint8_t k_bad6[17] = {0x01, 0x04, 0x0C, 0x04, 0xAC, 0x00, 0x00, 0x00, 0x00,
                                   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x59, 0xD5};
static const uint8_t k_slave2[17] = {0x02, 0x04, 0x0C, 0x04, 0xAC, 0x00, 0x00, 0x00, 0x00,
                                     0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1A, 0x2B};
static const uint8_t k_small8[13] = {0x01, 0x04, 0x08, 0x04, 0xAC, 0x00, 0x00,
                                     0x00, 0x00, 0x00, 0x00, 0x49, 0xF4};
static const uint8_t k_exc[5] = {0x01, 0x84, 0x02, 0xC2, 0xC1};

static void test_pzem_framing(void)
{
    uint8_t buf[64];
    h6_pzem_frame_t f;
    uint16_t regs[6];

    /* Clean 17-byte reply. */
    CHECK(h6_pzem_classify(k_resp6, sizeof(k_resp6), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_OK);
    CHECK(f.usable && f.crc_valid && f.offset == 0U && f.len == 17U);
    CHECK(f.slave == 1U && f.function == 0x04U && f.byte_count == 12U && f.echo_bytes == 0U);

    /* Echo + reply: the pattern measured on the bench (prefix 8). */
    for (size_t i = 0; i < sizeof(k_tx6); i++) {
        buf[i] = k_tx6[i];
    }
    for (size_t i = 0; i < sizeof(k_resp6); i++) {
        buf[sizeof(k_tx6) + i] = k_resp6[i];
    }
    CHECK(h6_pzem_classify(buf, sizeof(k_tx6) + sizeof(k_resp6), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_OK);
    CHECK(f.usable && f.offset == 8U && f.len == 17U && f.echo_bytes == 8U);

    /* Echo with the first byte lost (prefix 7, also seen on the bench). */
    for (size_t i = 0; i < sizeof(k_tx6) - 1U; i++) {
        buf[i] = k_tx6[i + 1U];
    }
    for (size_t i = 0; i < sizeof(k_resp6); i++) {
        buf[sizeof(k_tx6) - 1U + i] = k_resp6[i];
    }
    CHECK(h6_pzem_classify(buf, sizeof(k_tx6) - 1U + sizeof(k_resp6), k_tx6, sizeof(k_tx6),
                           &f) == H6_PZEM_CLASS_OK);
    CHECK(f.usable && f.offset == 7U && f.echo_bytes == 7U);

    /* Trailing byte after the reply must not hide it. */
    for (size_t i = 0; i < sizeof(k_resp6); i++) {
        buf[i] = k_resp6[i];
    }
    buf[sizeof(k_resp6)] = 0x00U;
    CHECK(h6_pzem_classify(buf, sizeof(k_resp6) + 1U, k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_OK);
    CHECK(f.usable && f.offset == 0U);

    /* The exact failure H6 produced: echo, nothing else. */
    CHECK(h6_pzem_classify(k_tx6, sizeof(k_tx6), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_ECHO_ONLY);
    CHECK(!f.usable && f.echo_bytes == 8U);

    /* Echo followed by a truncated reply. */
    for (size_t i = 0; i < sizeof(k_tx6); i++) {
        buf[i] = k_tx6[i];
    }
    for (size_t i = 0; i < 10U; i++) {
        buf[sizeof(k_tx6) + i] = k_resp6[i];
    }
    CHECK(h6_pzem_classify(buf, sizeof(k_tx6) + 10U, k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_PARTIAL);
    CHECK(!f.usable);

    /* Eight-register reply is usable telemetry with a different count. */
    CHECK(h6_pzem_classify(k_resp8, sizeof(k_resp8), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_OK);
    CHECK(f.usable && f.len == 21U && f.byte_count == 16U);

    /* Full-shape reply with a broken CRC. */
    CHECK(h6_pzem_classify(k_bad6, sizeof(k_bad6), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_CRC_INVALID);
    CHECK(!f.usable && !f.crc_valid);

    /* CRC-valid reply from another slave. */
    CHECK(h6_pzem_classify(k_slave2, sizeof(k_slave2), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_BAD_SLAVE);
    CHECK(!f.usable && f.has_header && f.slave == 2U);

    /* CRC-valid reply that cannot hold six registers. */
    CHECK(h6_pzem_classify(k_small8, sizeof(k_small8), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_FULL_WRONG_COUNT);
    CHECK(!f.usable && f.byte_count == 8U);

    /* CRC-valid exception. */
    CHECK(h6_pzem_classify(k_exc, sizeof(k_exc), k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_EXCEPTION);
    CHECK(!f.usable);

    /* Nothing received. */
    CHECK(h6_pzem_classify(NULL, 0U, k_tx6, sizeof(k_tx6), &f) == H6_PZEM_CLASS_NO_RESPONSE);

    /* Two different usable replies cannot be resolved. */
    for (size_t i = 0; i < sizeof(k_resp6); i++) {
        buf[i] = k_resp6[i];
        buf[sizeof(k_resp6) + i] = k_resp6[i];
    }
    CHECK(h6_pzem_classify(buf, sizeof(k_resp6) * 2U, k_tx6, sizeof(k_tx6), &f) ==
          H6_PZEM_CLASS_AMBIGUOUS);
    CHECK(!f.usable);

    /* Register decoding. */
    CHECK(h6_pzem_parse_registers(k_resp6, sizeof(k_resp6), regs));
    CHECK(regs[0] == 0x04ACU && regs[1] == 0U && regs[2] == 0U && regs[5] == 0U);
    CHECK(h6_pzem_parse_registers(k_resp8, sizeof(k_resp8), regs));
    CHECK(regs[0] == 0x04ACU);
    CHECK(!h6_pzem_parse_registers(k_bad6, sizeof(k_bad6), regs));
    CHECK(!h6_pzem_parse_registers(k_small8, sizeof(k_small8), regs));
}

bool h6_selftest_run(unsigned *checks, unsigned *failures, int *first_failure_line)
{
    s_checks = 0U;
    s_failures = 0U;
    s_first_failure_line = 0;

    test_happy_path();
    test_matrix();
    test_one_run_per_boot();
    test_stop_reason_latch();
    test_deadline_boundary();
    test_elapsed_semantics();
    test_names();
    test_pzem_framing();

    if (checks != NULL) {
        *checks = s_checks;
    }
    if (failures != NULL) {
        *failures = s_failures;
    }
    if (first_failure_line != NULL) {
        *first_failure_line = s_first_failure_line;
    }
    return (s_failures == 0U) && (s_checks > 0U);
}
