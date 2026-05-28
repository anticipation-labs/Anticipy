#pragma once
#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

// ═══════════════════════════════════════════════════════════════════════════
//  audio.h — I2S microphone capture + ring buffer
//
//  The INMP441 is a 24-bit I2S MEMS microphone.  The ESP32-S3 I2S peripheral
//  reads 32-bit slots (24-bit data + 8-bit padding, left-justified).  We
//  right-shift by 16 to get a usable 16-bit PCM sample and store it in the
//  PSRAM ring buffer.
//
//  The ring buffer is a circular array of 20ms frames.  It records
//  continuously — VAD and the upload task read from it asynchronously.
// ═══════════════════════════════════════════════════════════════════════════

// Called once at startup
void audio_init();

// Called to start/stop the I2S peripheral (saves ~1.4 mA when stopped)
void audio_start();
void audio_stop();

// Returns true if I2S is currently running
bool audio_is_running();

// Blocking call: waits for one 20ms frame of PCM from the I2S DMA buffer,
// then appends it to the ring buffer and returns the PCM in out_frame.
// Returns false if I2S is not running or on DMA timeout.
bool audio_capture_frame(int16_t* out_frame, size_t frame_samples);

// Ring buffer access ─────────────────────────────────────────────────────────

// Total frames currently in the ring buffer (wrap-safe)
size_t audio_ring_available();

// Read `num_frames` frames starting `offset_frames` frames before the write
// head (i.e. offset 0 = most recent frame, offset N = N frames ago).
// Returns actual frames read. Reads are non-destructive.
size_t audio_ring_read(int16_t* out, size_t num_frames, size_t offset_from_head);

// Absolute write-head index (monotonically increasing, wraps at RING_BUF_FRAMES)
size_t audio_ring_write_head();

// Drain all frames between read_cursor and write_head into out_buf.
// Advances *read_cursor. Returns number of frames written to out_buf.
// out_buf must have capacity of at least `max_frames` frames × FRAME_SAMPLES samples.
size_t audio_ring_drain(int16_t* out_buf, size_t max_frames, size_t* read_cursor);
