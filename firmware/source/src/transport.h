#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

int transport_start(void);
int broadcast_audio_packets(uint8_t *buffer, size_t size);
bool transport_audio_is_active(void);
void transport_audio_fault(int error);

#endif
