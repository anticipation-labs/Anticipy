// SPDX-License-Identifier: MIT

#include "recovery_touch.h"

#include <stddef.h>

void recovery_touch_reset(struct recovery_touch_state *state)
{
    if (state == NULL) {
        return;
    }
    state->high_samples = 0u;
    state->armed_samples_remaining = 0u;
    state->armed = false;
}

bool recovery_touch_update(
    struct recovery_touch_state *state,
    bool configured,
    uint32_t baud_rate,
    bool dtr_high)
{
    if (state == NULL) {
        return false;
    }
    if (!configured || baud_rate != RECOVERY_TOUCH_BAUD_RATE) {
        recovery_touch_reset(state);
        return false;
    }

    if (!state->armed) {
        if (!dtr_high) {
            state->high_samples = 0u;
            return false;
        }
        if (state->high_samples < RECOVERY_TOUCH_HIGH_SAMPLES) {
            state->high_samples++;
        }
        if (state->high_samples == RECOVERY_TOUCH_HIGH_SAMPLES) {
            state->armed = true;
            state->armed_samples_remaining =
                RECOVERY_TOUCH_ARMED_SAMPLES;
        }
        return false;
    }

    if (!dtr_high) {
        recovery_touch_reset(state);
        return true;
    }
    if (state->armed_samples_remaining > 0u) {
        state->armed_samples_remaining--;
    }
    if (state->armed_samples_remaining == 0u) {
        recovery_touch_reset(state);
    }
    return false;
}
