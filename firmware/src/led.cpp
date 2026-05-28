#include "led.h"
#include "config.h"
#include <Adafruit_NeoPixel.h>

// ═══════════════════════════════════════════════════════════════════════════
//  led.cpp — Single addressable LED driver (WS2812B / SK6812)
// ═══════════════════════════════════════════════════════════════════════════

static Adafruit_NeoPixel strip(LED_NUM_PIXELS, PIN_LED_DATA, NEO_GRB + NEO_KHZ800);

static LedPattern  s_pattern   = LedPattern::OFF;
static uint32_t    s_color     = 0;
static uint32_t    s_phase_ms  = 0;   // Time since last pattern start
static uint32_t    s_last_ms   = 0;   // millis() at last led_tick()
static uint8_t     s_blink_cnt = 0;   // Blinks remaining for BLINK_ONCE etc.
static bool        s_blink_on  = false;

// ── helpers ────────────────────────────────────────────────────────────────

// Extract R/G/B bytes from packed 0xRRGGBB
static inline uint8_t R(uint32_t c) { return (c >> 16) & 0xFF; }
static inline uint8_t G(uint32_t c) { return (c >>  8) & 0xFF; }
static inline uint8_t B(uint32_t c) { return (c      ) & 0xFF; }

// Scale all channels by factor (0–255)
static uint32_t scale(uint32_t c, uint8_t factor) {
    return strip.Color(
        (R(c) * factor) >> 8,
        (G(c) * factor) >> 8,
        (B(c) * factor) >> 8
    );
}

// HSV to packed RGB (h: 0–255, s: 0–255, v: 0–255)
static uint32_t hsv_to_rgb(uint8_t h, uint8_t s, uint8_t v) {
    return strip.gamma32(strip.ColorHSV((uint16_t)h << 8, s, v));
}

// Write a single color to the strip and show
static void show(uint32_t neopixel_color) {
    strip.setPixelColor(0, neopixel_color);
    strip.show();
}

// ── public API ─────────────────────────────────────────────────────────────

void led_init() {
    strip.begin();
    strip.setBrightness(LED_BRIGHTNESS);
    strip.clear();
    strip.show();
}

void led_set(LedPattern pattern, uint32_t color_rgb) {
    s_pattern  = pattern;
    s_color    = color_rgb;
    s_phase_ms = 0;
    s_blink_cnt = 0;
    s_blink_on  = false;
    s_last_ms   = millis();
}

void led_off() {
    s_pattern = LedPattern::OFF;
    strip.clear();
    strip.show();
}

void led_tick() {
    uint32_t now   = millis();
    uint32_t delta = now - s_last_ms;
    s_last_ms  = now;
    s_phase_ms += delta;

    switch (s_pattern) {

        case LedPattern::OFF:
            strip.clear();
            strip.show();
            break;

        case LedPattern::SOLID:
            show(strip.Color(R(s_color), G(s_color), B(s_color)));
            break;

        // Breathing: sine-wave brightness, period = 1000ms (slow) or 250ms (fast)
        case LedPattern::PULSE_SLOW:
        case LedPattern::PULSE_FAST: {
            uint32_t period = (s_pattern == LedPattern::PULSE_SLOW) ? 1000 : 250;
            float t      = (float)(s_phase_ms % period) / period;  // 0.0 – 1.0
            float bright = 0.5f * (1.0f - cosf(t * 2.0f * M_PI));  // 0 – 1 sine
            uint8_t factor = (uint8_t)(bright * 255.0f);
            show(scale(s_color, factor));
            break;
        }

        // Single 200ms flash, then off, pattern stays at OFF afterward
        case LedPattern::BLINK_ONCE: {
            if (s_phase_ms < 200) {
                show(strip.Color(R(s_color), G(s_color), B(s_color)));
            } else {
                led_off();
            }
            break;
        }

        // Two 100ms flashes with 100ms gaps: on-off-on-off
        case LedPattern::BLINK_DOUBLE: {
            // Timeline: 0–100 ON | 100–200 OFF | 200–300 ON | 300–400 OFF | done
            uint32_t t = s_phase_ms;
            bool on = (t < 100) || (t >= 200 && t < 300);
            if (t < 400) {
                show(on ? strip.Color(R(s_color), G(s_color), B(s_color)) : 0);
            } else {
                led_off();
            }
            break;
        }

        // Three 80ms flashes: on-off-on-off-on-off
        case LedPattern::BLINK_TRIPLE: {
            uint32_t t = s_phase_ms;
            bool on = (t < 80) || (t >= 160 && t < 240) || (t >= 320 && t < 400);
            if (t < 480) {
                show(on ? strip.Color(R(s_color), G(s_color), B(s_color)) : 0);
            } else {
                led_off();
            }
            break;
        }

        // Slow blink: 1Hz, 50% duty — used for connected/idle
        case LedPattern::BLINK_SLOW: {
            bool on = (s_phase_ms % 2000) < 100;  // 100ms ON every 2 seconds
            show(on ? strip.Color(R(s_color), G(s_color), B(s_color)) : 0);
            break;
        }

        // Full hue cycle over 3 seconds — BLE pairing mode
        case LedPattern::RAINBOW: {
            uint8_t hue = (uint8_t)((s_phase_ms % 3000) * 255 / 3000);
            show(hsv_to_rgb(hue, 255, 200));
            break;
        }
    }
}
