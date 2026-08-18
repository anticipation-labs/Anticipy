// SPDX-License-Identifier: MIT

#ifndef ANTICIPY_RECOVERY_TOUCH_H
#define ANTICIPY_RECOVERY_TOUCH_H

#include <stdbool.h>
#include <stdint.h>

#define RECOVERY_TOUCH_BAUD_RATE 1200u
#define RECOVERY_TOUCH_HIGH_SAMPLES 5u
#define RECOVERY_TOUCH_ARMED_SAMPLES 100u

struct recovery_touch_state {
    uint16_t high_samples;
    uint16_t armed_samples_remaining;
    bool armed;
};

void recovery_touch_reset(struct recovery_touch_state *state);

bool recovery_touch_update(
    struct recovery_touch_state *state,
    bool configured,
    uint32_t baud_rate,
    bool dtr_high);

#endif
