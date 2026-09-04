// SPDX-License-Identifier: MIT
//
// The two decisions that used to be made wrong, checked on a host compiler
// with no Zephyr, no radio and no board — the same shape as
// recovery_touch_test.c beside it.
//
// WHAT THIS EXISTS FOR. Every send failure was fatal, and fatal in this
// firmware means request_audio_state(false): the microphone off for the rest
// of the connection, recoverable only by a fresh CCC write the phone does not
// send while a link is up. A ring that filled for 320ms, or one congested
// connection event, therefore ended capture for the whole session. The
// classifier below is the fix, so it is the thing most worth pinning.

#include "../src/transport_safety.h"
#include "../src/config.h"

#include <assert.h>
#include <errno.h>

int main(void)
{
    // ---- backpressure is survivable, and nothing else is -----------------
    assert(transport_error_is_backpressure(-ENOSPC));
    assert(transport_error_is_backpressure(-EAGAIN));
    assert(transport_error_is_backpressure(-ENOMEM));

    // Consent revoked, capture already stopped, and an MTU too small to carry
    // a frame are all genuinely fatal. Classing any of them as backpressure
    // would keep a stream alive that must stop — the inverse of the original
    // bug and a worse one, because it is a privacy failure rather than an
    // availability failure.
    assert(!transport_error_is_backpressure(-EACCES));
    assert(!transport_error_is_backpressure(-ECANCELED));
    assert(!transport_error_is_backpressure(-EMSGSIZE));
    assert(!transport_error_is_backpressure(-EIO));
    assert(!transport_error_is_backpressure(-EINVAL));
    assert(!transport_error_is_backpressure(-ENOTCONN));

    // Success is not backpressure. A caller asking about 0 has lost track of
    // what it is doing, and answering "yes" would drop a frame that went out.
    assert(!transport_error_is_backpressure(0));

    // ---- the capture geometry, read from the real config.h ---------------
    // 1600 / 160 = 10 exactly. That integer ratio is the only reason a DMA
    // block boundary and an Opus frame boundary re-align on every block
    // instead of drifting, and until the BUILD_ASSERTs landed nothing stated
    // or checked it. Asserted here as well as at compile time because this
    // test runs on a machine with no cross-toolchain, where a BUILD_ASSERT
    // that never compiles proves nothing at all.
    assert(MIC_BUFFER_SAMPLES % CODEC_PACKAGE_SAMPLES == 0);
    assert(AUDIO_BUFFER_SAMPLES % CODEC_PACKAGE_SAMPLES == 0);

    // CODEC_OUTPUT_MAX_BYTES was `CODEC_PACKAGE_SAMPLES * 2` unparenthesised.
    // Multiplication binds tighter than addition, so array bounds happened to
    // be right; a DIVISION does not, and this is the expression that would
    // have silently returned four times the intended answer.
    assert(1u / CODEC_OUTPUT_MAX_BYTES == 0u);
    assert(640u / CODEC_OUTPUT_MAX_BYTES == 2u);
    assert(CODEC_OUTPUT_MAX_BYTES == 320);

    // ---- the fragment commit still refuses to advance on a failure -------
    // The sequence counter is the phone's only loss detector. A commit that
    // stepped it on a failed notify would hide the very gap the drop path
    // exists to make visible.
    struct transport_fragment_state current = {0};
    struct transport_fragment_state next = {0};
    assert(transport_fragment_commit(&current, 100u, -EAGAIN, &next) == -EAGAIN);
    assert(transport_fragment_commit(&current, 100u, 0, &next) == 0);
    assert(next.sequence == 1u);
    assert(next.offset == 100u);

    return 0;
}
