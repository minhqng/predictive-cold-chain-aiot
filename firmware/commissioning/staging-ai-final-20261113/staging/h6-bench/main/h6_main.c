/*
 * ColdGuard H6 - TEC hot/cold polarity bench test (isolated, temporary).
 *
 * This image is NOT production firmware. It exists to run one 60 s, 10% duty
 * TEC pulse so the operator can feel which side gets cold, and nothing else.
 *
 *   BOOT -> SAFE_OFF -> WAIT_FOR_MANUAL_ARM -> ARMED -> RUNNING_10_PERCENT
 *                                                        |
 *                                                        v
 *                                               SAFE_OFF_FINAL -> COMPLETE
 *
 * Safety properties of this file:
 *   - GPIO5/6/10 are configured output-low as the first action of app_main;
 *   - no code path enables the TEC without an operator ARM followed by START;
 *   - one run per boot, no retry, no automatic restart;
 *   - the 60 s bound comes from a monotonic esp_timer one-shot that is
 *     independent of serial input and of the run task;
 *   - every exit path zeroes PWM first, then drops R_EN and L_EN.
 *
 * Software protection only: a reset or CPU lock-up is bounded by the
 * operator's PSU switch, not by this firmware.
 */
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_console.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#include "h6_config.h"
#include "h6_pzem.h"
#include "h6_selftest.h"
#include "h6_state.h"

#if !CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#error "H6 bench image requires CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG (commands over COMx USB-Serial/JTAG)"
#endif

#define H6_RUN_TASK_STACK 4096
#define H6_RUN_TASK_PRIO 6
#define H6_LOG(...) printf(__VA_ARGS__)

static h6_sm_t s_sm;
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_run_task;
static esp_timer_handle_t s_guard_timer;
static bool s_pwm_ready;
static bool s_pzem_ready;
static int s_duty_permille;
static h6_pzem_sample_t s_last_sample;
static bool s_have_last_sample;

/* ---------------------------------------------------------------- outputs */

static void outputs_off(void)
{
    (void)ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0);
    (void)ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
    gpio_set_level(H6_PIN_REN, 0);
    gpio_set_level(H6_PIN_LEN, 0);
    s_duty_permille = 0;
}

static void outputs_early_safe(void)
{
    const gpio_config_t io = {
        .pin_bit_mask =
            (1ULL << H6_PIN_RPWM) | (1ULL << H6_PIN_REN) | (1ULL << H6_PIN_LEN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    (void)gpio_config(&io);
    (void)gpio_set_level(H6_PIN_RPWM, 0);
    (void)gpio_set_level(H6_PIN_REN, 0);
    (void)gpio_set_level(H6_PIN_LEN, 0);
    s_duty_permille = 0;
}

static bool pwm_init(void)
{
    const ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_13_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = H6_PWM_FREQ_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    if (ledc_timer_config(&timer) != ESP_OK) {
        return false;
    }
    const ledc_channel_config_t channel = {
        .gpio_num = H6_PIN_RPWM,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    if (ledc_channel_config(&channel) != ESP_OK) {
        return false;
    }
    outputs_off();
    return true;
}

/* duty 0 -> both enables -> 10% duty. Any failure leaves the branch off. */
static bool outputs_on_10_percent(void)
{
    outputs_off();
    vTaskDelay(pdMS_TO_TICKS(1));

    gpio_set_level(H6_PIN_REN, 1);
    gpio_set_level(H6_PIN_LEN, 1);
    vTaskDelay(pdMS_TO_TICKS(2));

    if (ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, H6_PWM_DUTY_COUNT) != ESP_OK ||
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0) != ESP_OK) {
        outputs_off();
        return false;
    }
    s_duty_permille = H6_PWM_DUTY_PERMILLE;
    return true;
}

/* ------------------------------------------------------------- reporting */

static void print_commands(void)
{
    H6_LOG("H6 COMMANDS (case-sensitive):\n");
    H6_LOG("  STATUS  - state, elapsed, pin levels, live PZEM sample (TEC off)\n");
    H6_LOG("  ARM     - WAIT_FOR_MANUAL_ARM -> ARMED (no output change)\n");
    H6_LOG("  START   - ARMED -> RUNNING_10_PERCENT, one 60 s max run per boot\n");
    H6_LOG("  STOP    - RUNNING -> SAFE_OFF_FINAL immediately\n");
    H6_LOG("  HELP    - this text\n");
    H6_LOG("Every PZEM attempt also prints H6 PZEM_TRACE (raw TX/RX hex, timing, class).\n");
}

static void hex_encode(const uint8_t *data, size_t len, char *out, size_t cap)
{
    static const char digits[] = "0123456789ABCDEF";
    size_t written = 0U;

    for (size_t i = 0; i < len && written + 2U < cap; i++) {
        out[written++] = digits[(data[i] >> 4) & 0x0F];
        out[written++] = digits[data[i] & 0x0F];
    }
    out[written] = '\0';
}

/* Raw diagnostic line for one PZEM attempt: what was sent, what came back,
 * when each chunk arrived, how the stream was classified. */
static void print_pzem_trace(uint8_t attempt, const h6_pzem_trace_t *t, void *ctx)
{
    (void)ctx;
    char tx_hex[sizeof(t->tx) * 2U + 1U];
    char rx_hex[H6_PZEM_TRACE_RX_MAX * 2U + 1U];
    char chunks[H6_PZEM_TRACE_CHUNKS * 9U + 1U];
    size_t pos = 0U;

    hex_encode(t->tx, t->tx_len, tx_hex, sizeof(tx_hex));
    hex_encode(t->rx, t->rx_len, rx_hex, sizeof(rx_hex));
    chunks[0] = '\0';
    const unsigned shown =
        t->chunk_count < H6_PZEM_TRACE_CHUNKS ? t->chunk_count : H6_PZEM_TRACE_CHUNKS;
    for (unsigned i = 0; i < shown && pos + 10U < sizeof(chunks); i++) {
        const int n = snprintf(chunks + pos, sizeof(chunks) - pos, "%s%u@%ums",
                               (i == 0U) ? "" : ",", t->chunk_len[i],
                               (unsigned)t->chunk_at_ms[i]);
        if (n < 0) {
            break;
        }
        pos += (size_t)n;
    }
    if (t->rx_len == 0U) {
        rx_hex[0] = '-';
        rx_hex[1] = '\0';
    }

    H6_LOG("H6 PZEM_TRACE attempt=%u tx=%s rx_len=%u rx=%s chunk_count=%u chunks=%s"
           " first_ms=%lu last_ms=%lu echo=%u frame_off=%d frame_len=%d slave=%d fc=%d"
           " count=%d crc_ok=%d usable=%d early=%d uart_err=%d class=%s\n",
           (unsigned)attempt, tx_hex, (unsigned)t->rx_len, rx_hex, (unsigned)t->chunk_count,
           chunks, (unsigned long)t->first_byte_ms, (unsigned long)t->last_byte_ms,
           (unsigned)t->echo_bytes, t->frame_off, t->frame_len, t->slave, t->function,
           t->byte_count, t->crc_ok ? 1 : 0, t->usable ? 1 : 0, t->early_exit ? 1 : 0,
           t->uart_error ? 1 : 0, h6_pzem_class_name(t->cls));
}

static void print_pzem_line(const char *tag, int64_t elapsed_ms, const h6_pzem_sample_t *s)
{
    if (s->valid) {
        H6_LOG("H6 %s state=RUNNING_10_PERCENT duty_permille=%d elapsed_ms=%" PRId64
               " vbus_mv=%d current_ma=%d power_mw=%d pzem=%s\n",
               tag, s_duty_permille, elapsed_ms, (int)(s->voltage_v * 1000.0f + 0.5f),
               (int)(s->current_a * 1000.0f + 0.5f), (int)(s->power_w * 1000.0f + 0.5f),
               h6_pzem_status_name(s->status));
    } else {
        H6_LOG("H6 %s state=RUNNING_10_PERCENT duty_permille=%d elapsed_ms=%" PRId64
               " vbus_mv=-1 current_ma=-1 power_mw=-1 pzem=%s\n",
               tag, s_duty_permille, elapsed_ms, h6_pzem_status_name(s->status));
    }
}

/* Caller holds s_lock. Always removes drive; latches the stop reason once. */
static bool trip_locked(h6_stop_reason_t reason, int64_t *elapsed_us_out)
{
    const bool was_running = (s_sm.state == H6_STATE_RUNNING_10_PERCENT);
    outputs_off();
    if (was_running) {
        const int64_t now = esp_timer_get_time();
        (void)h6_sm_stop(&s_sm, reason, now);
        if (elapsed_us_out != NULL) {
            *elapsed_us_out = h6_sm_elapsed_us(&s_sm, now);
        }
    } else if (elapsed_us_out != NULL) {
        *elapsed_us_out = 0;
    }
    return was_running;
}

static void print_off(const char *source, h6_stop_reason_t reason, int64_t elapsed_us)
{
    H6_LOG("H6 OFF source=%s reason=%s elapsed_ms=%" PRId64
           " duty_permille=0 ren=%d len=%d rpwm_level=%d\n",
           source, h6_stop_reason_name(reason), elapsed_us / 1000,
           gpio_get_level(H6_PIN_REN), gpio_get_level(H6_PIN_LEN), gpio_get_level(H6_PIN_RPWM));
}

static void complete_run(void)
{
    h6_state_t state;
    int64_t elapsed_us;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const int64_t now = esp_timer_get_time();
    elapsed_us = h6_sm_elapsed_us(&s_sm, now);
    (void)h6_sm_complete(&s_sm);
    state = s_sm.state;
    xSemaphoreGive(s_lock);

    H6_LOG("H6 END state=%s elapsed_ms=%" PRId64
           " duty_permille=0 ren=%d len=%d rpwm_level=%d start_rejected_until_reboot=1\n",
           h6_state_name(state), elapsed_us / 1000, gpio_get_level(H6_PIN_REN),
           gpio_get_level(H6_PIN_LEN), gpio_get_level(H6_PIN_RPWM));
}

/* ------------------------------------------------------------ guard timer */

/* Independent of the run task and of serial input: fires once at START+60 s
 * and removes drive even if the run task is blocked. */
static void guard_cb(void *arg)
{
    (void)arg;
    int64_t elapsed_us = 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const bool was_running = trip_locked(H6_STOP_TIMEOUT, &elapsed_us);
    xSemaphoreGive(s_lock);

    if (was_running) {
        print_off("guard_timer", H6_STOP_TIMEOUT, elapsed_us);
    }
}

/* ---------------------------------------------------------------- run task */

static void run_task(void *arg)
{
    (void)arg;

    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        /* Enable under the lock so a STOP that arrives in this window is
         * serialized: either it wins and no drive is applied, or it waits and
         * removes drive after the enable has completed. */
        bool enabled = false;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (s_sm.state == H6_STATE_RUNNING_10_PERCENT) {
            enabled = outputs_on_10_percent();
        }
        xSemaphoreGive(s_lock);

        if (!enabled) {
            int64_t elapsed_us = 0;
            xSemaphoreTake(s_lock, portMAX_DELAY);
            const bool was_running = trip_locked(H6_STOP_FAULT, &elapsed_us);
            xSemaphoreGive(s_lock);
            if (was_running) {
                print_off("output_enable_failed", H6_STOP_FAULT, elapsed_us);
            }
            (void)esp_timer_stop(s_guard_timer);
            complete_run();
            continue;
        }

        H6_LOG("H6 ON duty_permille=%d duty_count=%d pwm_freq_hz=%d freq_reconstructed=%d\n",
               H6_PWM_DUTY_PERMILLE, H6_PWM_DUTY_COUNT, H6_PWM_FREQ_HZ,
               H6_PWM_FREQ_RECONSTRUCTED);

        int64_t start_us;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        start_us = s_sm.run_start_us;
        xSemaphoreGive(s_lock);

        uint32_t next_poll_ms = 0;
        unsigned consecutive_bad = 0;

        for (;;) {
            const int64_t now = esp_timer_get_time();
            const int64_t elapsed_ms = (now - start_us) / 1000;
            bool running;
            bool timed_out;
            xSemaphoreTake(s_lock, portMAX_DELAY);
            running = (s_sm.state == H6_STATE_RUNNING_10_PERCENT);
            timed_out = h6_sm_deadline_reached(&s_sm, now);
            xSemaphoreGive(s_lock);

            if (!running) {
                break; /* STOP or guard already removed drive and latched a reason */
            }
            if (timed_out) {
                int64_t elapsed_us = 0;
                xSemaphoreTake(s_lock, portMAX_DELAY);
                const bool was_running = trip_locked(H6_STOP_TIMEOUT, &elapsed_us);
                xSemaphoreGive(s_lock);
                if (was_running) {
                    print_off("run_task_deadline", H6_STOP_TIMEOUT, elapsed_us);
                }
                break;
            }

            if (elapsed_ms >= (int64_t)next_poll_ms) {
                const h6_pzem_sample_t sample = h6_pzem_poll();
                xSemaphoreTake(s_lock, portMAX_DELAY);
                s_last_sample = sample;
                s_have_last_sample = true;
                const bool still_running = (s_sm.state == H6_STATE_RUNNING_10_PERCENT);
                xSemaphoreGive(s_lock);
                if (!still_running) {
                    break; /* stopped while the poll was in flight */
                }
                print_pzem_line("T", elapsed_ms, &sample);

                if (!sample.valid) {
                    if (++consecutive_bad >= 2U) {
                        int64_t elapsed_us = 0;
                        xSemaphoreTake(s_lock, portMAX_DELAY);
                        const bool was_running =
                            trip_locked(H6_STOP_TELEMETRY_INVALID, &elapsed_us);
                        xSemaphoreGive(s_lock);
                        if (was_running) {
                            print_off("telemetry_invalid", H6_STOP_TELEMETRY_INVALID,
                                      elapsed_us);
                        }
                        break;
                    }
                } else {
                    consecutive_bad = 0;
                    if (sample.current_a < -0.01f || sample.current_a > H6_MAX_CURRENT_A ||
                        sample.voltage_v < H6_MIN_BUS_V || sample.voltage_v > H6_MAX_BUS_V) {
                        int64_t elapsed_us = 0;
                        xSemaphoreTake(s_lock, portMAX_DELAY);
                        const bool was_running = trip_locked(H6_STOP_FAULT, &elapsed_us);
                        xSemaphoreGive(s_lock);
                        if (was_running) {
                            print_off("telemetry_implausible", H6_STOP_FAULT, elapsed_us);
                        }
                        break;
                    }
                }
                next_poll_ms += H6_PZEM_POLL_MS;
            }

            vTaskDelay(pdMS_TO_TICKS(H6_RUN_LOOP_MS));
        }

        (void)esp_timer_stop(s_guard_timer);
        complete_run();
    }
}

/* ---------------------------------------------------------------- commands */

static int cmd_arm(int argc, char **argv)
{
    (void)argv;
    h6_state_t state;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const bool ok = (argc == 1) && h6_sm_arm(&s_sm);
    state = s_sm.state;
    xSemaphoreGive(s_lock);

    if (argc != 1) {
        H6_LOG("H6 CMD ARM rejected reason=ARGS state=%s\n", h6_state_name(state));
        return 1;
    }
    if (ok) {
        H6_LOG("H6 CMD ARM accepted state=ARMED duty_permille=0 next=START\n");
        return 0;
    }
    H6_LOG("H6 CMD ARM rejected reason=INVALID_TRANSITION state=%s\n", h6_state_name(state));
    return 1;
}

static int cmd_start(int argc, char **argv)
{
    (void)argv;
    h6_state_t state;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    state = s_sm.state;
    xSemaphoreGive(s_lock);

    if (argc != 1) {
        H6_LOG("H6 CMD START rejected reason=ARGS state=%s\n", h6_state_name(state));
        return 1;
    }
    if (state != H6_STATE_ARMED) {
        H6_LOG("H6 CMD START rejected reason=INVALID_TRANSITION state=%s\n",
               h6_state_name(state));
        return 1;
    }
    if (!s_pwm_ready) {
        H6_LOG("H6 CMD START rejected reason=PWM_NOT_READY\n");
        return 1;
    }

    const h6_pzem_sample_t pre = h6_pzem_poll();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_last_sample = pre;
    s_have_last_sample = true;
    xSemaphoreGive(s_lock);

    if (pre.valid) {
        H6_LOG("H6 PRECHECK pzem=OK vbus_mv=%d current_ma=%d power_mw=%d\n",
               (int)(pre.voltage_v * 1000.0f + 0.5f), (int)(pre.current_a * 1000.0f + 0.5f),
               (int)(pre.power_w * 1000.0f + 0.5f));
    } else {
        H6_LOG("H6 PRECHECK pzem=%s\n", h6_pzem_status_name(pre.status));
    }
    if (!pre.valid) {
        H6_LOG("H6 CMD START rejected reason=PZEM_INVALID state=ARMED\n");
        return 1;
    }
    if (pre.current_a > H6_START_MAX_OFF_CURRENT_A) {
        H6_LOG("H6 CMD START rejected reason=BRANCH_CURRENT_AT_OFF current_ma=%d\n",
               (int)(pre.current_a * 1000.0f + 0.5f));
        return 1;
    }

    bool ok;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    ok = h6_sm_start(&s_sm, esp_timer_get_time());
    state = s_sm.state;
    xSemaphoreGive(s_lock);
    if (!ok) {
        H6_LOG("H6 CMD START rejected reason=INVALID_TRANSITION state=%s\n",
               h6_state_name(state));
        return 1;
    }

    if (esp_timer_start_once(s_guard_timer, H6_MAX_ON_US) != ESP_OK) {
        int64_t elapsed_us = 0;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        const bool was_running = trip_locked(H6_STOP_FAULT, &elapsed_us);
        xSemaphoreGive(s_lock);
        if (was_running) {
            print_off("guard_timer_failed", H6_STOP_FAULT, elapsed_us);
        }
        complete_run();
        H6_LOG("H6 CMD START aborted reason=GUARD_TIMER_FAULT\n");
        return 1;
    }

    H6_LOG("H6 CMD START accepted state=RUNNING_10_PERCENT max_on_ms=%" PRId64 "\n",
           H6_MAX_ON_US / 1000);
    xTaskNotifyGive(s_run_task);
    return 0;
}

static int cmd_stop(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) {
        H6_LOG("H6 CMD STOP rejected reason=ARGS\n");
        return 1;
    }
    int64_t elapsed_us = 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const bool was_running = trip_locked(H6_STOP_OPERATOR, &elapsed_us);
    const h6_state_t state = s_sm.state;
    xSemaphoreGive(s_lock);

    if (!was_running) {
        H6_LOG("H6 CMD STOP ignored reason=NOT_RUNNING state=%s\n", h6_state_name(state));
        return 1;
    }
    (void)esp_timer_stop(s_guard_timer);
    print_off("operator_stop", H6_STOP_OPERATOR, elapsed_us);
    return 0;
}

static int cmd_status(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) {
        H6_LOG("H6 CMD STATUS rejected reason=ARGS\n");
        return 1;
    }

    h6_sm_t snap;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    snap = s_sm;
    xSemaphoreGive(s_lock);

    const int64_t now = esp_timer_get_time();
    H6_LOG("H6 STATUS state=%s reason=%s run_consumed=%d elapsed_ms=%" PRId64
           " duty_permille=%d ren=%d len=%d rpwm_level=%d pzem_ready=%d\n",
           h6_state_name(snap.state), h6_stop_reason_name(snap.stop_reason),
           (int)snap.run_consumed, h6_sm_elapsed_us(&snap, now) / 1000, s_duty_permille,
           gpio_get_level(H6_PIN_REN), gpio_get_level(H6_PIN_LEN), gpio_get_level(H6_PIN_RPWM),
           (int)s_pzem_ready);

    if (snap.state != H6_STATE_RUNNING_10_PERCENT) {
        const h6_pzem_sample_t sample = h6_pzem_poll();
        if (sample.valid) {
            H6_LOG("H6 STATUS pzem=OK vbus_mv=%d current_ma=%d power_mw=%d\n",
                   (int)(sample.voltage_v * 1000.0f + 0.5f),
                   (int)(sample.current_a * 1000.0f + 0.5f),
                   (int)(sample.power_w * 1000.0f + 0.5f));
        } else {
            H6_LOG("H6 STATUS pzem=%s\n", h6_pzem_status_name(sample.status));
        }
    } else {
        h6_pzem_sample_t last = {0};
        bool have;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        last = s_last_sample;
        have = s_have_last_sample;
        xSemaphoreGive(s_lock);
        if (have && last.valid) {
            H6_LOG("H6 STATUS last_pzem=OK vbus_mv=%d current_ma=%d power_mw=%d\n",
                   (int)(last.voltage_v * 1000.0f + 0.5f),
                   (int)(last.current_a * 1000.0f + 0.5f),
                   (int)(last.power_w * 1000.0f + 0.5f));
        } else {
            H6_LOG("H6 STATUS last_pzem=%s\n",
                   have ? h6_pzem_status_name(last.status) : "NONE");
        }
    }
    return 0;
}

static int cmd_help(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    print_commands();
    return 0;
}

static void register_commands(void)
{
    static const esp_console_cmd_t commands[] = {
        {.command = "ARM", .help = "ARM the one-shot TEC run (no output change)", .func = &cmd_arm},
        {.command = "START", .help = "Start the 10% TEC run (one per boot)", .func = &cmd_start},
        {.command = "STOP", .help = "Stop the TEC run immediately", .func = &cmd_stop},
        {.command = "STATUS", .help = "Print state, pins and a PZEM sample", .func = &cmd_status},
        {.command = "HELP", .help = "List commands", .func = &cmd_help},
    };
    for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
        ESP_ERROR_CHECK(esp_console_cmd_register(&commands[i]));
    }
}

/* ------------------------------------------------------------------- boot */

void app_main(void)
{
    /* First action: intended OFF state on every control pin. */
    outputs_early_safe();

    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        H6_LOG("H6 FAULT mutex_create_failed outputs_forced_off_until_reset\n");
        while (true) {
            outputs_off();
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }

    h6_sm_init(&s_sm);
    (void)h6_sm_safe_off(&s_sm);

    unsigned checks = 0U;
    unsigned failures = 0U;
    int fail_line = 0;
    const bool selftest_ok = h6_selftest_run(&checks, &failures, &fail_line);
    if (selftest_ok) {
        H6_LOG("H6 SELFTEST result=PASS checks=%u failures=0\n", checks);
    } else {
        H6_LOG("H6 SELFTEST result=FAIL checks=%u failures=%u first_line=%d arm_blocked=1\n",
               checks, failures, fail_line);
    }

    H6_LOG("\nH6 BOOT firmware=coldguard_h6_bench build=%s %s pins_rpwm=%d pins_ren=%d "
           "pins_len=%d pwm_freq_hz=%d freq_reconstructed=%d duty_permille=%d "
           "max_on_ms=%" PRId64 " pzem_uart=%d\n",
           __DATE__, __TIME__, H6_PIN_RPWM, H6_PIN_REN, H6_PIN_LEN, H6_PWM_FREQ_HZ,
           H6_PWM_FREQ_RECONSTRUCTED, H6_PWM_DUTY_PERMILLE, H6_MAX_ON_US / 1000,
           H6_PZEM_UART_PORT);
    H6_LOG("H6 SAFE_OFF duty_permille=0 ren=%d len=%d rpwm_level=%d tec_output=OFF\n",
           gpio_get_level(H6_PIN_REN), gpio_get_level(H6_PIN_LEN), gpio_get_level(H6_PIN_RPWM));

    s_pwm_ready = pwm_init();
    if (!s_pwm_ready) {
        H6_LOG("H6 FAULT pwm_init_failed state=SAFE_OFF arm_blocked=1\n");
    }

    s_pzem_ready = h6_pzem_init();
    if (s_pzem_ready) {
        h6_pzem_set_trace(&print_pzem_trace, NULL);
    }
    H6_LOG("H6 PZEM init=%s uart=%d tx=%d rx=%d baud=%d slave=%d framing=8N1 read_only=1\n",
           s_pzem_ready ? "OK" : "FAILED", H6_PZEM_UART_PORT, H6_PZEM_TX, H6_PZEM_RX,
           H6_PZEM_BAUD, H6_PZEM_SLAVE);

    const esp_timer_create_args_t guard_args = {
        .callback = &guard_cb,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "h6_guard",
        .skip_unhandled_events = true,
    };
    bool runtime_ready = (esp_timer_create(&guard_args, &s_guard_timer) == ESP_OK);
    if (!runtime_ready) {
        H6_LOG("H6 FAULT guard_timer_create_failed arm_blocked=1\n");
    }
    if (runtime_ready &&
        xTaskCreate(run_task, "h6_run", H6_RUN_TASK_STACK, NULL, H6_RUN_TASK_PRIO,
                    &s_run_task) != pdPASS) {
        H6_LOG("H6 FAULT run_task_create_failed arm_blocked=1\n");
        runtime_ready = false;
    }
    if (!runtime_ready) {
        s_pwm_ready = false;
    }
    if (!selftest_ok) {
        s_pwm_ready = false;
    }

    if (s_pwm_ready) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        (void)h6_sm_ready(&s_sm);
        const h6_state_t state = s_sm.state;
        xSemaphoreGive(s_lock);
        H6_LOG("H6 READY state=%s tec_output=OFF waiting_for=ARM\n", h6_state_name(state));
    }

    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t repl_config = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    repl_config.prompt = "h6>";
    repl_config.max_cmdline_length = 64;
    esp_console_dev_usb_serial_jtag_config_t hw_config =
        ESP_CONSOLE_DEV_USB_SERIAL_JTAG_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_console_new_repl_usb_serial_jtag(&hw_config, &repl_config, &repl));
    ESP_ERROR_CHECK(esp_console_register_help_command());
    register_commands();
    ESP_ERROR_CHECK(esp_console_start_repl(repl));

    H6_LOG("H6 CONSOLE ready commands=ARM,START,STOP,STATUS,HELP\n");
    print_commands();
}
