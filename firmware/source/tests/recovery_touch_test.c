// SPDX-License-Identifier: MIT

#include "../src/recovery_touch.h"

#include <assert.h>

static void arm(struct recovery_touch_state *state)
{
    for (unsigned int index = 0u;
         index < RECOVERY_TOUCH_HIGH_SAMPLES;
         index++) {
        assert(!recovery_touch_update(
            state, true, RECOVERY_TOUCH_BAUD_RATE, true));
    }
    assert(state->armed);
}

int main(void)
{
    struct recovery_touch_state state = {0};

    assert(!recovery_touch_update(
        &state, true, RECOVERY_TOUCH_BAUD_RATE, false));
    assert(!recovery_touch_update(&state, true, 115200u, true));
    assert(!recovery_touch_update(&state, true, 115200u, false));

    arm(&state);
    assert(!recovery_touch_update(&state, false, 0u, false));
    assert(!state.armed);

    arm(&state);
    assert(!recovery_touch_update(&state, true, 9600u, false));
    assert(!state.armed);

    arm(&state);
    assert(recovery_touch_update(
        &state, true, RECOVERY_TOUCH_BAUD_RATE, false));
    assert(!state.armed);
    assert(!recovery_touch_update(
        &state, true, RECOVERY_TOUCH_BAUD_RATE, false));

    arm(&state);
    for (unsigned int index = 0u;
         index < RECOVERY_TOUCH_ARMED_SAMPLES;
         index++) {
        assert(!recovery_touch_update(
            &state, true, RECOVERY_TOUCH_BAUD_RATE, true));
    }
    assert(!state.armed);
    assert(!recovery_touch_update(
        &state, true, RECOVERY_TOUCH_BAUD_RATE, false));

    return 0;
}
