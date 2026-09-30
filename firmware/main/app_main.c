#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "coldguard";

void app_main(void)
{
    ESP_LOGI(TAG, "ColdGuard firmware bootstrap");
}
