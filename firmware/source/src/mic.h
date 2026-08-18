#ifndef MIC_H
#define MIC_H

#include <stdbool.h>
#include <stdint.h>

typedef void (*mic_handler)(int16_t *buffer);
typedef void (*mic_error_handler)(int error);

/*
 * mic_init() configures the PDM peripheral without sampling. mic_start() and
 * mic_stop() are bound to the audio CCC state by transport.c.
 */
int mic_init(void);
int mic_start(void);
int mic_stop(void);
bool mic_is_running(void);
void mic_emergency_power_off(void);
void set_mic_callback(mic_handler callback);
void set_mic_error_callback(mic_error_handler callback);

#endif
