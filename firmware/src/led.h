#pragma once
#include <Arduino.h>

// ═══════════════════════════════════════════════════════════════════════════
//  led.h — Single SK6812/WS2812B status LED
//
//  The pendant has exactly one addressable RGB LED driven through the ESP32-S3
//  RMT peripheral (via Adafruit NeoPixel).  All LED state changes go through
//  this module — never call NeoPixel directly from other files.
// ═══════════════════════════════════════════════════════════════════════════

enum class LedPattern {
    OFF,             // LED off — used in deep sleep
    SOLID,           // Steady color
    PULSE_SLOW,      // Breathing effect, 1 Hz
    PULSE_FAST,      // Breathing effect, 4 Hz
    BLINK_ONCE,      // Single 200ms flash then off
    BLINK_DOUBLE,    // Two quick 100ms flashes (success)
    BLINK_TRIPLE,    // Three quick 100ms flashes (error)
    BLINK_SLOW,      // 0.5 Hz on/off
    RAINBOW,         // Full hue cycle — used for BLE pairing mode
};

void    led_init();
void    led_tick();                              // Call every loop() iteration
void    led_set(LedPattern pattern, uint32_t color_rgb = 0x000000);
void    led_off();

// Convenience wrappers that match the patterns from DESIGN.md §4
inline void led_wifi_connecting()  { led_set(LedPattern::PULSE_SLOW,  0x0000FF); }
inline void led_ble_pairing()      { led_set(LedPattern::RAINBOW,      0x000000); }
inline void led_connected_idle()   { led_set(LedPattern::BLINK_SLOW,  0x003300); }
inline void led_recording()        { led_set(LedPattern::SOLID,        0xFF0000); }
inline void led_uploading()        { led_set(LedPattern::PULSE_FAST,   0x00CCCC); }
inline void led_upload_ok()        { led_set(LedPattern::BLINK_DOUBLE, 0x00FF00); }
inline void led_upload_err()       { led_set(LedPattern::BLINK_TRIPLE, 0xFF4400); }
inline void led_low_battery()      { led_set(LedPattern::PULSE_SLOW,   0xFFCC00); }
inline void led_critical_battery() { led_set(LedPattern::BLINK_FAST,  0xFFCC00); }

// Overload used in inline above (forward-declare the fast variant)
inline void led_blink_fast()       { led_set(LedPattern::PULSE_FAST,   0xFFCC00); }
