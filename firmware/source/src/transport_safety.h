// SPDX-License-Identifier: MIT

#ifndef ANTICIPY_TRANSPORT_SAFETY_H
#define ANTICIPY_TRANSPORT_SAFETY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TRANSPORT_ATT_NOTIFY_OVERHEAD_BYTES 3u
#define TRANSPORT_AUDIO_HEADER_BYTES 3u
#define TRANSPORT_MINIMUM_ATT_MTU 100u

struct transport_fragment_state {
    uint32_t offset;
    uint16_t sequence;
    uint8_t fragment_index;
};

int transport_fragment_plan(
    uint16_t att_mtu,
    uint32_t frame_size,
    const struct transport_fragment_state *current,
    size_t *payload_bytes);
/*
 * IS THIS THE LINK BEING BUSY, OR THE STREAM BEING OVER?
 *
 * Lives here, in the pure half, because it is the decision that used to be
 * made wrong: every send failure was treated as fatal, and fatal means the
 * microphone off for the rest of the connection. Pure and header-declared so
 * tests/transport_safety_test.c can walk the whole classification on a host
 * compiler, with no Zephyr, no radio and no board.
 */
bool transport_error_is_backpressure(int error);

int transport_fragment_commit(
    const struct transport_fragment_state *current,
    size_t payload_bytes,
    int notify_result,
    struct transport_fragment_state *next);

#endif
