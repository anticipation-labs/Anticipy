// SPDX-License-Identifier: MIT

#include "lib/opus-1.2.1/opus.h"

/*
 * The encoder's repacketizer needs this small TOC parser, but pulling the
 * complete decoder object into an encoder-only image also retains dormant
 * SILK decoder references. Keep the encoder link closed over the reviewed
 * CELT/encoder source set.
 */
int opus_packet_get_nb_frames(const unsigned char packet[], opus_int32 len)
{
    if (len < 1) {
        return OPUS_BAD_ARG;
    }

    int code = packet[0] & 0x3;
    if (code == 0) {
        return 1;
    }
    if (code != 3) {
        return 2;
    }
    if (len < 2) {
        return OPUS_INVALID_PACKET;
    }
    return packet[1] & 0x3f;
}
