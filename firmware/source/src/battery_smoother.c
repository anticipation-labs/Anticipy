// SPDX-License-Identifier: MIT

#include "battery_smoother.h"

#define BATTERY_PERCENT_MAX 100u
#define BATTERY_PERCENT_Q8_SCALE 256u
#define BATTERY_EMA_PREVIOUS_WEIGHT 3u
#define BATTERY_EMA_SAMPLE_WEIGHT 1u
#define BATTERY_EMA_WEIGHT_TOTAL 4u

void battery_smoother_reset(struct battery_smoother *smoother)
{
    smoother->percentage_q8 = 0u;
    smoother->initialized = false;
}

uint8_t battery_smoother_update(struct battery_smoother *smoother,
                                uint8_t sample_percentage)
{
    if (sample_percentage > BATTERY_PERCENT_MAX) {
        sample_percentage = BATTERY_PERCENT_MAX;
    }

    uint16_t sample_q8 = (uint16_t)sample_percentage * BATTERY_PERCENT_Q8_SCALE;

    if (!smoother->initialized) {
        smoother->percentage_q8 = sample_q8;
        smoother->initialized = true;
    } else {
        uint32_t weighted_q8 =
            BATTERY_EMA_PREVIOUS_WEIGHT * (uint32_t)smoother->percentage_q8 +
            BATTERY_EMA_SAMPLE_WEIGHT * (uint32_t)sample_q8;
        smoother->percentage_q8 = (uint16_t)(
            (weighted_q8 + BATTERY_EMA_WEIGHT_TOTAL / 2u) /
            BATTERY_EMA_WEIGHT_TOTAL);
    }

    uint16_t rounded_percentage = (uint16_t)(
        (smoother->percentage_q8 + BATTERY_PERCENT_Q8_SCALE / 2u) /
        BATTERY_PERCENT_Q8_SCALE);
    return (uint8_t)(rounded_percentage > BATTERY_PERCENT_MAX
                         ? BATTERY_PERCENT_MAX
                         : rounded_percentage);
}
