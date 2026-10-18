/*
 * ColdGuard firmware - MC-38 door contact (Member A, W02).
 */
#include "cg_door.h"

#include <string.h>

#include "driver/gpio.h"

#include "coldguard_config.h"

static const uint64_t DEBOUNCE_US = (uint64_t)CG_DOOR_DEBOUNCE_MS * 1000ULL;

const char *cg_door_state_name(cg_door_state_t state)
{
    switch (state) {
        case CG_DOOR_OPEN:
            return "OPEN";
        case CG_DOOR_CLOSED:
            return "CLOSED";
        case CG_DOOR_UNVERIFIED:
        default:
            return "UNVERIFIED";
    }
}

void cg_door_init(cg_door_t *door)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << (uint32_t)CG_PIN_MC38,
        .mode = GPIO_MODE_INPUT,
        /* The reed contact is wired to ground with an external/internal
         * pull-up; the electrical polarity question is which raw level
         * corresponds to OPEN, not how the pin is biased. */
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&cfg));

    memset(door, 0, sizeof(*door));
    door->raw_last = gpio_get_level(CG_PIN_MC38);
    door->raw_committed = door->raw_last;
    door->stable_since_us = 0;
    door->initialised = true;
}

static inline void door_recompute_derived(cg_door_t *door)
{
    door->cycles = door->transitions / 2u;
    door->discarded_edges = (door->raw_edges > door->transitions)
                                ? (door->raw_edges - door->transitions)
                                : 0u;
}

void cg_door_poll(cg_door_t *door, uint64_t now_us, bool *edge_out,
                  int *raw_edge_level_out, bool *commit_out)
{
    int raw = gpio_get_level(CG_PIN_MC38);

    *edge_out = false;
    *commit_out = false;
    *raw_edge_level_out = raw;

    if (!door->initialised) {
        return;
    }

    if (raw != door->raw_last) {
        door->raw_last = raw;
        door->stable_since_us = now_us;
        door->raw_edges++;
        door_recompute_derived(door);
        *edge_out = true;
        return; /* a new level restarts the stability window */
    }

    if (raw != door->raw_committed) {
        if ((now_us - door->stable_since_us) >= DEBOUNCE_US) {
            door->raw_committed = raw;
            door->transitions++;
            door_recompute_derived(door);
            *commit_out = true;
        }
    }
}

cg_door_state_t cg_door_state(const cg_door_t *door)
{
#if CG_DOOR_POLARITY_CONFIRMED
    return (door->raw_committed == CG_DOOR_RAW_OPEN_LEVEL) ? CG_DOOR_OPEN : CG_DOOR_CLOSED;
#else
    (void)door;
    return CG_DOOR_UNVERIFIED;
#endif
}
