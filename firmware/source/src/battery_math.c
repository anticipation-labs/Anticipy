// SPDX-License-Identifier: MIT

#include "battery_math.h"

#include <errno.h>
#include <limits.h>
#include <stddef.h>
#include <stdint.h>

int battery_scale_divider_millivolts(
    uint32_t adc_millivolt,
    uint32_t divider_high_kohm,
    uint32_t divider_low_kohm,
    uint16_t *battery_millivolt)
{
    if (battery_millivolt == NULL || divider_low_kohm == 0u) {
        return -EINVAL;
    }

    uint64_t divider_sum =
        (uint64_t)divider_high_kohm + divider_low_kohm;
    uint64_t rounding = divider_low_kohm / 2u;
    if (divider_sum == 0u ||
        adc_millivolt >
            (UINT64_MAX - rounding) / divider_sum) {
        return -EOVERFLOW;
    }

    uint64_t scaled =
        ((uint64_t)adc_millivolt * divider_sum + rounding) /
        divider_low_kohm;
    if (scaled > UINT16_MAX) {
        return -EOVERFLOW;
    }

    *battery_millivolt = (uint16_t)scaled;
    return 0;
}
