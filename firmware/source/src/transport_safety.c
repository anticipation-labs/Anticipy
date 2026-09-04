// SPDX-License-Identifier: MIT

#include "transport_safety.h"

#include <errno.h>
#include <limits.h>

bool transport_error_is_backpressure(int error)
{
    /*
     * -ENOSPC is a ring that filled because the radio is behind; both rings
     * drain on their own. -EAGAIN and -ENOMEM are the controller refusing a
     * buffer, which is what backpressure looks like on this stack. None of
     * the three says the stream has stopped being valid.
     *
     * Everything else stays fatal on purpose: -EACCES is consent revoked,
     * -ECANCELED is capture already stopped, -EMSGSIZE is an MTU too small to
     * carry a frame at all, and an encoder or PDM failure really has
     * invalidated the stream. Success is not backpressure either — a caller
     * that asks about 0 has already lost track of what it is doing.
     */
    return error == -ENOSPC || error == -EAGAIN || error == -ENOMEM;
}

int transport_fragment_plan(
    uint16_t att_mtu,
    uint32_t frame_size,
    const struct transport_fragment_state *current,
    size_t *payload_bytes)
{
    if (current == NULL || payload_bytes == NULL) {
        return -EINVAL;
    }
    if (current->offset >= frame_size) {
        return -ERANGE;
    }
    if (att_mtu < TRANSPORT_MINIMUM_ATT_MTU) {
        return -EMSGSIZE;
    }

    size_t value_capacity =
        (size_t)att_mtu - TRANSPORT_ATT_NOTIFY_OVERHEAD_BYTES;
    if (value_capacity <= TRANSPORT_AUDIO_HEADER_BYTES) {
        return -EMSGSIZE;
    }
    size_t audio_capacity =
        value_capacity - TRANSPORT_AUDIO_HEADER_BYTES;
    size_t remaining = (size_t)(frame_size - current->offset);
    *payload_bytes =
        remaining < audio_capacity ? remaining : audio_capacity;
    return 0;
}

int transport_fragment_commit(
    const struct transport_fragment_state *current,
    size_t payload_bytes,
    int notify_result,
    struct transport_fragment_state *next)
{
    if (current == NULL || next == NULL) {
        return -EINVAL;
    }
    if (notify_result != 0) {
        return notify_result;
    }
    if (payload_bytes == 0u) {
        return -ERANGE;
    }
    if (payload_bytes > UINT32_MAX ||
        current->offset > UINT32_MAX - (uint32_t)payload_bytes) {
        return -EOVERFLOW;
    }
    if (current->fragment_index == UINT8_MAX) {
        return -EOVERFLOW;
    }

    *next = *current;
    next->offset += (uint32_t)payload_bytes;
    next->sequence++;
    next->fragment_index++;
    return 0;
}
