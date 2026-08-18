// SPDX-License-Identifier: MIT

#ifndef ANTICIPY_BATTERY_SMOOTHER_H
#define ANTICIPY_BATTERY_SMOOTHER_H

#include <stdbool.h>
#include <stdint.h>

struct battery_smoother {
    uint16_t percentage_q8;
    bool initialized;
};

void battery_smoother_reset(struct battery_smoother *smoother);
uint8_t battery_smoother_update(struct battery_smoother *smoother,
                                uint8_t sample_percentage);

#endif
