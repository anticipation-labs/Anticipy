// SPDX-License-Identifier: MIT

#ifndef ANTICIPY_BATTERY_MATH_H
#define ANTICIPY_BATTERY_MATH_H

#include <stdint.h>

int battery_scale_divider_millivolts(
    uint32_t adc_millivolt,
    uint32_t divider_high_kohm,
    uint32_t divider_low_kohm,
    uint16_t *battery_millivolt);

#endif
