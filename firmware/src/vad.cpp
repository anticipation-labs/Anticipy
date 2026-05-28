#include "vad.h"
#include "config.h"
#include <math.h>

// ═══════════════════════════════════════════════════════════════════════════
//  vad.cpp — Energy-based Voice Activity Detection
//
//  Algorithm:
//    1. Compute RMS energy of a 20ms PCM frame.
//    2. Maintain an exponential moving average (EMA) of RMS in silence —
//       this is the adaptive noise floor.
//    3. Speech threshold = max(VAD_ABSOLUTE_THRESHOLD, noise_floor × mult).
//    4. State machine:
//         SILENCE → SPEECH when RMS > threshold
//         SPEECH  → SILENCE after VAD_HANG_FRAMES consecutive frames below threshold
//    5. Emit utterance_started / utterance_ended events on transitions.
// ═══════════════════════════════════════════════════════════════════════════

static VadState  s_state       = VadState::SILENCE;
static float     s_noise_floor = (float)VAD_ABSOLUTE_THRESHOLD;
static int       s_hang_frames = 0;   // Countdown in SPEECH state

void vad_init() {
    vad_reset();
}

void vad_reset() {
    s_state       = VadState::SILENCE;
    s_noise_floor = (float)VAD_ABSOLUTE_THRESHOLD;
    s_hang_frames = 0;
}

VadState vad_state() {
    return s_state;
}

VadResult vad_process_frame(const int16_t* samples, int num_samples) {
    // ── 1. Compute RMS ──────────────────────────────────────────────────────
    int64_t sum_sq = 0;
    for (int i = 0; i < num_samples; i++) {
        int32_t s = samples[i];
        sum_sq += s * s;
    }
    float rms = sqrtf((float)sum_sq / num_samples);

    // ── 2. Compute threshold ─────────────────────────────────────────────────
    float threshold = fmaxf(
        (float)VAD_ABSOLUTE_THRESHOLD,
        s_noise_floor * VAD_NOISE_MULTIPLIER
    );

    // ── 3. State machine ─────────────────────────────────────────────────────
    VadResult result;
    result.state             = s_state;
    result.utterance_started = false;
    result.utterance_ended   = false;
    result.rms               = rms;
    result.noise_floor       = s_noise_floor;
    result.threshold         = threshold;

    switch (s_state) {

        case VadState::SILENCE:
            // Update noise floor slowly during silence
            s_noise_floor = s_noise_floor * (1.0f - VAD_NOISE_EMA_ALPHA)
                          + rms            * VAD_NOISE_EMA_ALPHA;

            if (rms > threshold) {
                // Transition to SPEECH
                s_state       = VadState::SPEECH;
                s_hang_frames = VAD_HANG_FRAMES;
                result.state             = VadState::SPEECH;
                result.utterance_started = true;
            }
            break;

        case VadState::SPEECH:
            if (rms > threshold) {
                // Still speech — reset hang counter
                s_hang_frames = VAD_HANG_FRAMES;
            } else {
                // Below threshold — count down hang
                s_hang_frames--;
                if (s_hang_frames <= 0) {
                    // Transition to SILENCE
                    s_state = VadState::SILENCE;
                    // Re-seed noise floor with current RMS to adapt quickly
                    s_noise_floor = rms;
                    result.state           = VadState::SILENCE;
                    result.utterance_ended = true;
                }
            }
            break;
    }

    return result;
}
