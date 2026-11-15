/*
 * ColdGuard firmware - local operator console (W04).
 *
 * The console shares UART0 with the log stream. Bytes typed by the operator
 * are not echoed by the firmware (the terminal normally echoes locally);
 * every line that is not a valid command produces one #CG ERR line with a
 * stable reason token. A half-typed line at boot is discarded, never
 * executed.
 */
#include "cg_console.h"

#include <string.h>

#include "sdkconfig.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#include "driver/usb_serial_jtag.h"
#endif

#include "cg_log.h"
#include "coldguard_config.h"
#include "cg_fault_inject.h"

#define CG_CONSOLE_RX_BUFFER 512
#define CG_CONSOLE_STACK_WORDS 3072
#define CG_CONSOLE_TASK_PRIORITY 3

static QueueHandle_t s_queue;
static bool s_available;

static void handle_line(const char *line)
{
    cg_tec_command_t command;
    const char *error = "OK";

#if CG_FAULT_INJECTION
    /* Test-only local control path. A FAULT line is consumed here and never
     * reaches the TEC command parser/queue, so it cannot be driven by a network
     * command. Compiled out entirely when CG_FAULT_INJECTION is 0. */
    if (cg_fault_inject_console_line(line)) {
        cg_log_line("%s %s event=FAULT_INJECT_HANDLED line=%s ds_role=%d pzem_down=%d",
                    CG_LOG_PREFIX, CG_LOG_TEC, line, cg_fault_inject_ds_role(),
                    cg_fault_inject_pzem_down() ? 1 : 0);
        return;
    }
#endif

    if (!cg_tec_command_parse(line, &command, &error)) {
        cg_log_error("console=PARSE_FAIL error=%s", error);
        return;
    }
    if (xQueueSend(s_queue, &command, 0) != pdTRUE) {
        cg_log_error("console=QUEUE_FULL command=%s", cg_tec_command_name(command.kind));
    }
}

static void console_task(void *arg)
{
    uint8_t chunk[32];
    char line[CG_CONSOLE_LINE_MAX];
    size_t len = 0U;
    bool overflow = false;

    (void)arg;

    for (;;) {
#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
        /* The primary console is the native USB-Serial/JTAG port (COM4). UART0
         * is not connected to USB (CONFIG_ESP_CONSOLE_UART_NUM=-1), so reading
         * UART0 would never see operator input. Read the USB peripheral. */
        const int received = usb_serial_jtag_read_bytes(chunk, sizeof(chunk),
                                                        pdMS_TO_TICKS(50));
#else
        const int received = uart_read_bytes(UART_NUM_0, chunk, sizeof(chunk), pdMS_TO_TICKS(50));
#endif
        if (received <= 0) {
            continue;
        }
        for (int i = 0; i < received; i++) {
            const char c = (char)chunk[i];
            if (c == '\r') {
                continue;
            }
            if (c == '\n') {
                if (overflow) {
                    cg_log_error("console=LINE_TOO_LONG discarded=1");
                } else if (len > 0U) {
                    line[len] = '\0';
                    handle_line(line);
                }
                len = 0U;
                overflow = false;
                continue;
            }
            if (c == '\b' || c == 0x7F) {
                if (len > 0U) {
                    len--;
                }
                continue;
            }
            if (c < 0x20 || c > 0x7E) {
                continue;
            }
            if (len + 1U >= sizeof(line)) {
                overflow = true;
                len = 0U;
                continue;
            }
            line[len++] = c;
        }
    }
}

bool cg_console_start(QueueHandle_t command_queue)
{
#if CG_CONSOLE_ENABLED == 1
    if (command_queue == NULL) {
        return false;
    }
    s_queue = command_queue;
#ifdef CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    /* Install the USB-Serial/JTAG driver so RX bytes from COM4 are buffered and
     * readable. stdout (the log stream) shares the same peripheral. If the VFS
     * console already installed it, accept that state rather than failing. */
    usb_serial_jtag_driver_config_t usj_config = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    esp_err_t usj_err = usb_serial_jtag_driver_install(&usj_config);
    if (usj_err != ESP_OK && usj_err != ESP_ERR_INVALID_STATE) {
        cg_log_error("console=USJ_INSTALL_FAIL commands=disabled err=%s",
                     esp_err_to_name(usj_err));
        return false;
    }
#else
    uart_config_t config = {
        .baud_rate = CG_CONSOLE_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    if (uart_driver_install(UART_NUM_0, CG_CONSOLE_RX_BUFFER, 0, 0, NULL, 0) != ESP_OK) {
        cg_log_error("console=UART_INSTALL_FAIL commands=disabled");
        return false;
    }
    if (uart_param_config(UART_NUM_0, &config) != ESP_OK) {
        cg_log_error("console=UART_CONFIG_FAIL commands=disabled");
        return false;
    }
#endif
    s_available = true;
    (void)xTaskCreate(console_task, "cg_console", CG_CONSOLE_STACK_WORDS, NULL,
                      CG_CONSOLE_TASK_PRIORITY, NULL);
    return true;
#else
    (void)command_queue;
    s_available = false;
    return false;
#endif
}

bool cg_console_available(void)
{
    return s_available;
}
