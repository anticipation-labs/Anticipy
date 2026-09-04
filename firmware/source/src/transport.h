#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

int transport_start(void);
int broadcast_audio_packets(uint8_t *buffer, size_t size);
bool transport_audio_is_active(void);
void transport_audio_fault(int error);
/*
 * How many whole audio frames the link refused and this firmware threw away.
 * Monotonic for the life of the boot. The phone measures the same loss
 * independently from the packet-index jump; two instruments that can be
 * compared is the point, because one of them agreeing with itself proves
 * nothing.
 */
uint32_t transport_audio_frames_dropped(void);

#endif
