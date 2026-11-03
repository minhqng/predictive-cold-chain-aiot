/*
 * ColdGuard H6 - isolated TEC polarity bench-test firmware.
 *
 * Fixed constants for one bench test. Nothing here is a production limit and
 * nothing here may be reused as one: the six W04 commissioning limits remain
 * unresolved.
 */
#pragma once

/* IBT-2 control lines, as-built map v2 (see coldguard_config.h in the
 * production firmware). LPWM is tied to module GND and is not driven. */
#define H6_PIN_RPWM 5
#define H6_PIN_REN 6
#define H6_PIN_LEN 10

/* 10% duty is the only attribute of the earlier successful TEC run that was
 * recorded (PZEM ~0.98 A at 10%). The 1 kHz frequency is RECONSTRUCTED (the
 * ESP32 Arduino analogWrite default); it is not recovered from evidence and
 * must be reported as reconstructed. Polarity depends on the average DC
 * direction, not on the chopping frequency. */
#define H6_PWM_FREQ_HZ 1000
#define H6_PWM_FREQ_RECONSTRUCTED 1
#define H6_PWM_DUTY_BITS 13
#define H6_PWM_FULL_SCALE 8192
#define H6_PWM_DUTY_COUNT 819 /* 819/8192 = 9.9988% */
#define H6_PWM_DUTY_PERMILLE 100

/* Hard ON-time bound, enforced by the run task and by an independent
 * esp_timer one-shot. Software only: a CPU lock-up or reset is bounded by
 * the operator's PSU switch, not by this firmware. */
#define H6_MAX_ON_US 60000000LL
#define H6_RUN_LOOP_MS 20

/* PZEM-017 transport, identical to the validated production driver. */
#define H6_PZEM_UART_PORT 1
#define H6_PZEM_TX 36
#define H6_PZEM_RX 37
#define H6_PZEM_BAUD 9600
#define H6_PZEM_SLAVE 1
#define H6_PZEM_TIMEOUT_MS 250
#define H6_PZEM_ATTEMPTS 2
#define H6_PZEM_POLL_MS 1000
#define H6_PZEM_RX_MAX 32
#define H6_PZEM_TX_CMD_MS 50
#define H6_PZEM_INPUT_FRAME_LEN 17
#define H6_PZEM_EXCEPTION_FRAME_LEN 5

/* Test-only plausibility window for the 12 V bench branch. This is not a
 * commissioning or production limit. */
#define H6_MAX_CURRENT_A 5.0f
#define H6_MIN_BUS_V 6.0f
#define H6_MAX_BUS_V 16.0f
#define H6_START_MAX_OFF_CURRENT_A 0.2f
