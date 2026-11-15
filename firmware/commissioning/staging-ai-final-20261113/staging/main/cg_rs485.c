/*
 * ColdGuard firmware - RS-485 UART transport (Member A, W03).
 */
#include "cg_rs485.h"

#include "driver/gpio.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "coldguard_config.h"

#if CG_RS485_DATA_BITS != 8
#error "This UART driver only implements the documented 8 data bits"
#endif
#if CG_RS485_PARITY != 0 && CG_RS485_PARITY != 1 && CG_RS485_PARITY != 2
#error "CG_RS485_PARITY must be 0 (none), 1 (even) or 2 (odd)"
#endif
#if CG_RS485_STOP_BITS != 1 && CG_RS485_STOP_BITS != 2
#error "CG_RS485_STOP_BITS must be 1 or 2"
#endif

#define CG_RS485_PORT ((uart_port_t)CG_RS485_UART_PORT)
#define CG_RS485_RX_BUFFER 256
#define CG_RS485_TX_BUFFER 256

static bool s_initialized;

bool cg_rs485_init(void)
{
    uart_config_t config = {
        .baud_rate = CG_RS485_BAUD,
        .data_bits = UART_DATA_8_BITS,
#if CG_RS485_PARITY == 1
        .parity = UART_PARITY_EVEN,
#elif CG_RS485_PARITY == 2
        .parity = UART_PARITY_ODD,
#else
        .parity = UART_PARITY_DISABLE,
#endif
#if CG_RS485_STOP_BITS == 2
        .stop_bits = UART_STOP_BITS_2,
#else
        .stop_bits = UART_STOP_BITS_1,
#endif
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    if (uart_param_config(CG_RS485_PORT, &config) != ESP_OK) {
        return false;
    }
    if (uart_set_pin(CG_RS485_PORT, CG_PIN_RS485_TX, CG_PIN_RS485_RX, UART_PIN_NO_CHANGE,
                     UART_PIN_NO_CHANGE) != ESP_OK) {
        return false;
    }
    if (uart_driver_install(CG_RS485_PORT, CG_RS485_RX_BUFFER, CG_RS485_TX_BUFFER, 0, NULL, 0) !=
        ESP_OK) {
        return false;
    }

#if CG_RS485_DIR_MODE == CG_RS485_DIR_MANUAL
    gpio_config_t dir = {
        .pin_bit_mask = 1ULL << (uint32_t)CG_PIN_RS485_DE_RE,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE, /* receiver unless transmitting */
        .intr_type = GPIO_INTR_DISABLE,
    };
    if (gpio_config(&dir) != ESP_OK) {
        return false;
    }
    (void)gpio_set_level(CG_PIN_RS485_DE_RE, 0);
#endif

    uart_flush_input(CG_RS485_PORT);
    s_initialized = true;
    return true;
}

bool cg_rs485_write(const uint8_t *data, size_t len)
{
    if (!s_initialized || data == NULL || len == 0U) {
        return false;
    }

#if CG_RS485_DIR_MODE == CG_RS485_DIR_MANUAL
    (void)gpio_set_level(CG_PIN_RS485_DE_RE, 1); /* driver enabled */
#endif

    const int written = uart_write_bytes(CG_RS485_PORT, data, len);
    const bool ok =
        written == (int)len &&
        uart_wait_tx_done(CG_RS485_PORT, pdMS_TO_TICKS(CG_RS485_TX_DONE_TIMEOUT_MS)) == ESP_OK;

#if CG_RS485_DIR_MODE == CG_RS485_DIR_MANUAL
    (void)gpio_set_level(CG_PIN_RS485_DE_RE, 0); /* back to receive */
    /* Give the transceiver a few bit times to release the differential pair
     * before the slave starts answering. One tick is the smallest real
     * sleep at the configured FreeRTOS tick. */
    vTaskDelay(1);
#endif

    return ok;
}

int cg_rs485_read(uint8_t *buffer, size_t want, uint32_t timeout_ms)
{
    if (!s_initialized || buffer == NULL || want == 0U) {
        return -1;
    }

    const TickType_t start = xTaskGetTickCount();
    TickType_t timeout_ticks = pdMS_TO_TICKS(timeout_ms);
    if (timeout_ms > 0U && timeout_ticks == 0U) {
        timeout_ticks = 1U;
    }
    TickType_t idle_ticks = pdMS_TO_TICKS(CG_RS485_RX_IDLE_MS);
    if (idle_ticks == 0U) {
        idle_ticks = 1U;
    }

    size_t total = 0U;
    TickType_t last_rx = start;
    bool got_data = false;

    while (total < want) {
        size_t available = 0U;
        if (uart_get_buffered_data_len(CG_RS485_PORT, &available) != ESP_OK) {
            return -1;
        }

        if (available > 0U) {
            size_t take = available;
            if (take > want - total) {
                take = want - total;
            }
            const int received =
                uart_read_bytes(CG_RS485_PORT, buffer + total, (uint32_t)take, 0);
            if (received < 0) {
                return -1;
            }
            if (received > 0) {
                total += (size_t)received;
                last_rx = xTaskGetTickCount();
                got_data = true;
                continue;
            }
        }

        const TickType_t now = xTaskGetTickCount();
        if (got_data && (TickType_t)(now - last_rx) >= idle_ticks) {
            break;
        }
        if ((TickType_t)(now - start) >= timeout_ticks) {
            break;
        }
        vTaskDelay(1);
    }

    return (int)total;
}

void cg_rs485_flush_input(void)
{
    if (s_initialized) {
        (void)uart_flush_input(CG_RS485_PORT);
    }
}

cg_rs485_dir_mode_t cg_rs485_dir_mode(void)
{
#if CG_RS485_DIR_MODE == CG_RS485_DIR_MANUAL
    return CG_RS485_MODE_MANUAL;
#else
    return CG_RS485_MODE_AUTO;
#endif
}
