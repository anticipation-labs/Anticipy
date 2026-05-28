#include "audio.h"
#include "config.h"

#include "driver/i2s_std.h"
#include "esp_log.h"
#include <string.h>
#include <stdlib.h>

// ═══════════════════════════════════════════════════════════════════════════
//  audio.cpp — INMP441 I2S capture + PSRAM ring buffer
// ═══════════════════════════════════════════════════════════════════════════

static const char* TAG = "audio";

// ── I2S state ───────────────────────────────────────────────────────────────
static i2s_chan_handle_t s_rx_chan  = nullptr;
static bool              s_running = false;

// ── Ring buffer in PSRAM ────────────────────────────────────────────────────
// Layout: flat array of int16_t samples, RING_BUF_FRAMES × FRAME_SAMPLES long.
// Write head is an absolute frame index (never wraps); the real index into the
// array is (write_head % RING_BUF_FRAMES).
static int16_t* s_ring          = nullptr;   // Allocated in PSRAM
static volatile size_t s_write_head = 0;     // Monotonic frame counter

// ── init ────────────────────────────────────────────────────────────────────

void audio_init() {
    // Allocate ring buffer in PSRAM
    s_ring = (int16_t*)ps_malloc(RING_BUF_BYTES);
    if (!s_ring) {
        ESP_LOGE(TAG, "PSRAM alloc failed for ring buffer (%u bytes)", RING_BUF_BYTES);
        // Fallback to SRAM — will be smaller; adjust RING_BUF_FRAMES in config.h
        s_ring = (int16_t*)malloc(RING_BUF_BYTES);
        if (!s_ring) {
            ESP_LOGE(TAG, "SRAM alloc also failed — halting");
            while (true) { vTaskDelay(1000); }
        }
    }
    memset(s_ring, 0, RING_BUF_BYTES);
    s_write_head = 0;

    ESP_LOGI(TAG, "Ring buffer: %u KB (%u frames) at %p",
             RING_BUF_BYTES / 1024, RING_BUF_FRAMES, s_ring);
}

// ── I2S channel creation ────────────────────────────────────────────────────

void audio_start() {
    if (s_running) return;

    // Channel config: master RX, I2S_NUM_AUTO selects a free peripheral
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);
    chan_cfg.dma_bufs      = I2S_DMA_BUF_COUNT;
    chan_cfg.dma_frame_num = I2S_DMA_BUF_SAMPLES;

    esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &s_rx_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_new_channel failed: %s", esp_err_to_name(err));
        return;
    }

    // Standard I2S mode, Philips format
    // INMP441 outputs 24-bit audio in 32-bit slots (data left-justified).
    // We configure the slot as 32-bit wide and shift down in software.
    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
                        I2S_DATA_BIT_WIDTH_32BIT,
                        I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk       = I2S_GPIO_UNUSED,
            .bclk       = (gpio_num_t)PIN_I2S_BCLK,
            .ws         = (gpio_num_t)PIN_I2S_LRCK,
            .dout       = I2S_GPIO_UNUSED,
            .din        = (gpio_num_t)PIN_I2S_DATA,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    // INMP441 L/R pin tied to GND → left channel; only read left slot
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;

    err = i2s_channel_init_std_mode(s_rx_chan, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_init_std_mode failed: %s", esp_err_to_name(err));
        i2s_del_channel(s_rx_chan);
        s_rx_chan = nullptr;
        return;
    }

    err = i2s_channel_enable(s_rx_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_enable failed: %s", esp_err_to_name(err));
        i2s_del_channel(s_rx_chan);
        s_rx_chan = nullptr;
        return;
    }

    s_running = true;
    ESP_LOGI(TAG, "I2S started: %d Hz, 32-bit slots, mono left", AUDIO_SAMPLE_RATE);
}

void audio_stop() {
    if (!s_running || !s_rx_chan) return;
    i2s_channel_disable(s_rx_chan);
    i2s_del_channel(s_rx_chan);
    s_rx_chan  = nullptr;
    s_running  = false;
    ESP_LOGI(TAG, "I2S stopped");
}

bool audio_is_running() {
    return s_running;
}

// ── frame capture ───────────────────────────────────────────────────────────

bool audio_capture_frame(int16_t* out_frame, size_t frame_samples) {
    if (!s_running) return false;

    // Read one frame worth of 32-bit I2S samples from DMA
    static int32_t raw_buf[FRAME_SAMPLES];
    size_t bytes_read = 0;
    esp_err_t err = i2s_channel_read(
        s_rx_chan,
        raw_buf,
        frame_samples * sizeof(int32_t),
        &bytes_read,
        pdMS_TO_TICKS(100)  // 100ms timeout (5× frame duration — generous)
    );

    if (err != ESP_OK || bytes_read == 0) {
        ESP_LOGW(TAG, "I2S read timeout/error: %s", esp_err_to_name(err));
        return false;
    }

    int actual_samples = (int)(bytes_read / sizeof(int32_t));

    // Convert 32-bit I2S words → 16-bit PCM.
    // INMP441 is 24-bit, left-justified in 32-bit word.
    // Word layout: [bit31..bit8 = audio data][bit7..bit0 = zero padding]
    // Shift right by 16 to get the top 16 bits (most significant audio bits).
    for (int i = 0; i < actual_samples; i++) {
        out_frame[i] = (int16_t)(raw_buf[i] >> 16);
    }

    // Append frame to ring buffer
    size_t slot = s_write_head % RING_BUF_FRAMES;
    memcpy(&s_ring[slot * FRAME_SAMPLES], out_frame, frame_samples * sizeof(int16_t));
    s_write_head++;   // Atomic on single-core access; safe here since only audio task writes

    return true;
}

// ── ring buffer access ──────────────────────────────────────────────────────

size_t audio_ring_available() {
    return (s_write_head < RING_BUF_FRAMES) ? s_write_head : RING_BUF_FRAMES;
}

size_t audio_ring_write_head() {
    return s_write_head;
}

// Read frames relative to current write head.
// offset_from_head=0 → most-recent completed frame
// offset_from_head=N → N frames ago
size_t audio_ring_read(int16_t* out, size_t num_frames, size_t offset_from_head) {
    if (s_write_head == 0) return 0;

    // Clamp request to available data
    size_t available = audio_ring_available();
    if (offset_from_head >= available) return 0;

    size_t max_read = available - offset_from_head;
    if (num_frames > max_read) num_frames = max_read;

    // Start reading from (write_head - offset_from_head - num_frames) frames
    // Use signed arithmetic then take mod to handle wrapping
    size_t start_abs = s_write_head - offset_from_head - num_frames;
    for (size_t i = 0; i < num_frames; i++) {
        size_t slot = (start_abs + i) % RING_BUF_FRAMES;
        memcpy(
            &out[i * FRAME_SAMPLES],
            &s_ring[slot * FRAME_SAMPLES],
            FRAME_BYTES
        );
    }
    return num_frames;
}

size_t audio_ring_drain(int16_t* out_buf, size_t max_frames, size_t* read_cursor) {
    size_t write_head = s_write_head;
    if (*read_cursor >= write_head) return 0;  // Nothing new

    size_t available = write_head - *read_cursor;
    if (available > max_frames) available = max_frames;

    for (size_t i = 0; i < available; i++) {
        size_t slot = (*read_cursor + i) % RING_BUF_FRAMES;
        memcpy(
            &out_buf[i * FRAME_SAMPLES],
            &s_ring[slot * FRAME_SAMPLES],
            FRAME_BYTES
        );
    }

    *read_cursor += available;
    return available;
}
