#pragma once
#include <Arduino.h>

// ═══════════════════════════════════════════════════════════════════════════
//  power.h — Battery monitoring and sleep management
// ═══════════════════════════════════════════════════════════════════════════

enum class BattLevel {
    FULL,       // > 80%
    GOOD,       // 40–80%
    LOW,        // 20–40%  → yellow LED warning
    CRITICAL,   // < 5%   → force deep sleep
};

void       power_init();
void       power_tick();                 // Call periodically from main loop
float      power_batt_voltage();         // Raw battery voltage in volts
uint8_t    power_batt_percent();         // 0–100
BattLevel  power_batt_level();

// Enter light sleep: WiFi off, CPU clocked down, I2S keeps running.
// Returns when button pressed or timeout_ms elapses.
void power_light_sleep(uint32_t timeout_ms);

// Enter deep sleep: everything off, only RTC keeps time.
// Wake only via button press (GPIO wake-up configured automatically).
// This function does NOT return — device reboots on wake.
void power_deep_sleep();

// Notify power module that activity occurred (resets idle timer)
void power_activity();

// Returns true if idle timeout has been reached (caller should initiate sleep)
bool power_should_light_sleep();
bool power_should_deep_sleep();
