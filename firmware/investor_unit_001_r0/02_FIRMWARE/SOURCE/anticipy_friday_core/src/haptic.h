#ifndef ANTICIPY_HAPTIC_H
#define ANTICIPY_HAPTIC_H

#include <stdint.h>

int haptic_init(void);
void haptic_play_ms(uint32_t duration_ms);
void haptic_off(void);
void register_haptic_service(void);

#endif
