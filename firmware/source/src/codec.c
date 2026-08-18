#include <errno.h>
#include <stdbool.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>

#include "codec.h"
#include "config.h"
#include "utils.h"

#if CODEC_OPUS
#include "lib/opus-1.2.1/config.h"
#include "lib/opus-1.2.1/opus.h"
#endif

LOG_MODULE_REGISTER(codec, CONFIG_LOG_DEFAULT_LEVEL);

static codec_callback output_callback;
static codec_error_callback error_callback;
static uint8_t codec_ring_buffer_data[AUDIO_BUFFER_SAMPLES * 2u];
static struct ring_buf codec_ring_buf;
static struct k_spinlock codec_ring_lock;
static atomic_t codec_epoch;
K_SEM_DEFINE(codec_data_ready, 0, 1);

static int16_t codec_input_samples[CODEC_PACKAGE_SAMPLES];
static uint8_t codec_output_bytes[CODEC_OUTPUT_MAX_BYTES];
K_THREAD_STACK_DEFINE(codec_stack, 32000);
static struct k_thread codec_thread;
static int execute_codec(void);

#if CODEC_OPUS
#if CONFIG_OPUS_MODE != CONFIG_OPUS_MODE_CELT
#error "Anticipy firmware supports only the reviewed CELT-only Opus mode"
#endif
#define OPUS_ENCODER_CAPACITY_BYTES 7180u
__ALIGN(4)
static uint8_t opus_encoder_memory[OPUS_ENCODER_CAPACITY_BYTES];
static OpusEncoder *const opus_state =
    (OpusEncoder *)opus_encoder_memory;
#endif

void set_codec_callback(codec_callback callback)
{
    output_callback = callback;
}

void set_codec_error_callback(codec_error_callback callback)
{
    error_callback = callback;
}

int codec_receive_pcm(int16_t *data, size_t len)
{
    if (data == NULL || len == 0u ||
        len > SIZE_MAX / sizeof(*data)) {
        return -EINVAL;
    }

    size_t bytes = len * sizeof(*data);
    if (bytes > UINT32_MAX) {
        return -EOVERFLOW;
    }
    k_spinlock_key_t key = k_spin_lock(&codec_ring_lock);
    if (ring_buf_space_get(&codec_ring_buf) < bytes) {
        k_spin_unlock(&codec_ring_lock, key);
        LOG_ERR("Codec PCM queue is full");
        return -ENOSPC;
    }
    uint32_t written =
        ring_buf_put(&codec_ring_buf, (uint8_t *)data, bytes);
    k_spin_unlock(&codec_ring_lock, key);
    if (written != bytes) {
        LOG_ERR("Codec PCM queue write was unexpectedly partial");
        codec_reset();
        return -ENOSPC;
    }

    k_sem_give(&codec_data_ready);
    return 0;
}

void codec_reset(void)
{
    k_spinlock_key_t key = k_spin_lock(&codec_ring_lock);
    ring_buf_reset(&codec_ring_buf);
    memset(codec_ring_buffer_data, 0, sizeof(codec_ring_buffer_data));
    atomic_inc(&codec_epoch);
    k_spin_unlock(&codec_ring_lock, key);
    k_sem_give(&codec_data_ready);
}

static bool read_codec_frame(atomic_val_t *frame_epoch)
{
    const uint32_t required = sizeof(codec_input_samples);
    k_spinlock_key_t key = k_spin_lock(&codec_ring_lock);
    if (ring_buf_size_get(&codec_ring_buf) < required) {
        k_spin_unlock(&codec_ring_lock, key);
        return false;
    }
    *frame_epoch = atomic_get(&codec_epoch);
    uint32_t bytes_read =
        ring_buf_get(&codec_ring_buf, (uint8_t *)codec_input_samples,
                     required);
    k_spin_unlock(&codec_ring_lock, key);
    if (bytes_read != required) {
        LOG_ERR("Codec PCM queue returned a short frame: %u",
                (unsigned int)bytes_read);
        return false;
    }
    return true;
}

#if CODEC_OPUS
static int reset_encoder_state(void)
{
    int result = opus_encoder_ctl(opus_state, OPUS_RESET_STATE);
    if (result != OPUS_OK) {
        LOG_ERR("Opus encoder reset failed: %d", result);
        return -EIO;
    }
    return 0;
}
#else
static int reset_encoder_state(void)
{
    return 0;
}
#endif

static void codec_entry(void *unused1, void *unused2, void *unused3)
{
    ARG_UNUSED(unused1);
    ARG_UNUSED(unused2);
    ARG_UNUSED(unused3);

    atomic_val_t applied_epoch = atomic_get(&codec_epoch);
    while (true) {
        (void)k_sem_take(&codec_data_ready, K_FOREVER);
        while (true) {
            atomic_val_t current_epoch = atomic_get(&codec_epoch);
            if (current_epoch != applied_epoch) {
                /*
                 * Only this thread touches the Opus encoder. Consent/session
                 * resets therefore cannot race opus_encode(), and every new
                 * epoch resets CELT overlap/predictor state before its first
                 * PCM frame is encoded.
                 */
                int reset_error = reset_encoder_state();
                applied_epoch = current_epoch;
                memset(codec_input_samples, 0,
                       sizeof(codec_input_samples));
                memset(codec_output_bytes, 0,
                       sizeof(codec_output_bytes));
                if (reset_error != 0) {
                    if (error_callback != NULL) {
                        error_callback(reset_error);
                    }
                    break;
                }
            }

            atomic_val_t frame_epoch;
            if (!read_codec_frame(&frame_epoch)) {
                break;
            }
            int output_size = execute_codec();
            if (output_size < 0) {
                LOG_ERR("Opus encoding failed: %d", output_size);
                if (error_callback != NULL) {
                    error_callback(-EIO);
                }
                codec_reset();
            } else if (output_size > 0 && output_callback != NULL &&
                       atomic_get(&codec_epoch) == frame_epoch) {
                output_callback(
                    codec_output_bytes, (size_t)output_size);
            }
            memset(codec_input_samples, 0, sizeof(codec_input_samples));
            memset(codec_output_bytes, 0, sizeof(codec_output_bytes));
            if (output_size < 0) {
                break;
            }
        }
    }
}

int codec_start(void)
{
#if CODEC_OPUS
    int required_size = opus_encoder_get_size(1);
    if (required_size <= 0 ||
        (size_t)required_size > sizeof(opus_encoder_memory)) {
        LOG_ERR("Opus encoder needs %d bytes; capacity is %u",
                required_size,
                (unsigned int)sizeof(opus_encoder_memory));
        return -ENOMEM;
    }
    ASSERT_TRUE(opus_encoder_init(opus_state, 16000, 1,
                                  CODEC_OPUS_APPLICATION) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state,
                    OPUS_SET_BITRATE(CODEC_OPUS_BITRATE)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state, OPUS_SET_VBR(CODEC_OPUS_VBR)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state, OPUS_SET_VBR_CONSTRAINT(0)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state,
                    OPUS_SET_COMPLEXITY(CODEC_OPUS_COMPLEXITY)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state, OPUS_SET_SIGNAL(OPUS_SIGNAL_VOICE)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state, OPUS_SET_LSB_DEPTH(16)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(opus_state, OPUS_SET_DTX(0)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state, OPUS_SET_INBAND_FEC(0)) == OPUS_OK);
    ASSERT_TRUE(opus_encoder_ctl(
                    opus_state, OPUS_SET_PACKET_LOSS_PERC(0)) == OPUS_OK);
#endif

    ring_buf_init(&codec_ring_buf, sizeof(codec_ring_buffer_data),
                  codec_ring_buffer_data);
    k_thread_create(&codec_thread, codec_stack,
                    K_THREAD_STACK_SIZEOF(codec_stack), codec_entry,
                    NULL, NULL, NULL, K_PRIO_PREEMPT(4), 0, K_NO_WAIT);
    return 0;
}

#if CODEC_OPUS
static int execute_codec(void)
{
    opus_int32 size =
        opus_encode(opus_state, codec_input_samples,
                    CODEC_PACKAGE_SAMPLES, codec_output_bytes,
                    sizeof(codec_output_bytes));
    if (size < 0) {
        return (int)size;
    }
    return (int)size;
}
#endif
