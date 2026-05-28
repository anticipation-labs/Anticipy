#pragma once
#include <Arduino.h>

// ═══════════════════════════════════════════════════════════════════════════
//  vad.h — Voice Activity Detection
//
//  Energy-based VAD with adaptive noise floor.  Works well for wearable use
//  where the mic is worn by the speaker and ambient office/home noise is
//  relatively steady.
//
//  Call vad_process_frame() for every 20ms audio frame.
//  It returns true when a new utterance boundary is detected (speech start).
// ═══════════════════════════════════════════════════════════════════════════

enum class VadState {
    SILENCE,   // Background — noise floor updating
    SPEECH,    // Active speech — silence hang counter ticking down
};

struct VadResult {
    VadState state;
    bool     utterance_ended;   // True for exactly one frame at end of utterance
    bool     utterance_started; // True for exactly one frame at start of utterance
    float    rms;               // RMS of this frame (for debug / tuning)
    float    noise_floor;       // Current adaptive noise estimate
    float    threshold;         // Effective threshold = max(abs, floor×mult)
};

void      vad_init();
void      vad_reset();
VadResult vad_process_frame(const int16_t* samples, int num_samples);

// Returns current VAD state (useful for polling without processing a frame)
VadState  vad_state();
