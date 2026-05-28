#include "power.h"
#include "config.h"
#include "led.h"

#include "esp_sleep.h"
#include "esp_log.h"
#include "driver/adc.h"
#include "esp_adc/adc_oneshot.h"

// ═══════════════════════════════════════════════════════════════════════════
//  power.cpp — Battery ADC + sleep modes
// ═══════════════════════════════════════════════════════════════════════════

static const char* TAG = "power";

// ADC handle (ESP-IDF v5 oneshot API)
static adc_oneshot_unit_handle_t s_adc_handle = nullptr;
static adc_channel_t             s_adc_ch     = ADC_CHANNEL_1;  // GPIO2 = ADC1_CH1

// Cache
static float    s_voltage     = 3.70f;  // Last measured voltage
static uint8_t  s_percent     = 80;
static uint32_t s_last_check  = 0;
static uint32_t s_last_active = 0;  // millis() of last activity

// ── voltage → percent (piecewise linear approximation of LiPo discharge curve)
static uint8_t voltage_to_percent(float v) {
    // LiPo typical curve for 1S:
    // 4.20V = 100%, 4.10V = 90%, 3.95V = 75%, 3.80V = 60%,
    // 3.70V = 45%,  3.60V = 30%, 3.50V = 15%, 3.30V = 0%
    static const float v_points[] = {3.30f, 3.50f, 3.60f, 3.70f, 3.80f, 3.95f, 4.10f, 4.20f};
    static const float p_points[] = {    0,    15,    30,    45,    60,    75,    90,   100};
    static const int   N          = 8;

    if (v <= v_points[0])     return 0;
    if (v >= v_points[N - 1]) return 100;

    for (int i = 0; i < N - 1; i++) {
        if (v < v_points[i + 1]) {
            float t = (v - v_points[i]) / (v_points[i + 1] - v_points[i]);
            return (uint8_t)(p_points[i] + t * (p_points[i + 1] - p_points[i]));
        }
    }
    return 100;
}

// ── ADC read (oversampled for accuracy) ────────────────────────────────────
static float read_batt_voltage() {
    if (!s_adc_handle) return 3.70f;

    int64_t sum = 0;
    for (int i = 0; i < BATT_SAMPLES; i++) {
        int raw = 0;
        adc_oneshot_read(s_adc_handle, s_adc_ch, &raw);
        sum += raw;
        delayMicroseconds(100);
    }
    int avg_raw = (int)(sum / BATT_SAMPLES);

    // Convert ADC count to voltage
    // ADC is 12-bit (0–4095), Vref = 3.3V, with 11dB attenuation for 0–3.9V range
    float v_adc = (float)avg_raw / BATT_ADC_MAX_COUNT * BATT_ADC_REF_V;

    // Undo voltage divider to get actual battery voltage
    float v_batt = v_adc * BATT_DIVIDER_RATIO;

    return v_batt;
}

// ── public API ─────────────────────────────────────────────────────────────

void power_init() {
    s_last_active = millis();

    // Configure ADC oneshot unit (ADC1)
    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id  = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    esp_err_t err = adc_oneshot_new_unit(&init_cfg, &s_adc_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ADC init failed: %s", esp_err_to_name(err));
        return;
    }

    // Channel config: GPIO2 = ADC1_CH1, 11dB attenuation (input range 0–3.9V)
    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten    = ADC_ATTEN_DB_11,
        .bitwidth = ADC_BITWIDTH_12,
    };
    adc_oneshot_config_channel(s_adc_handle, s_adc_ch, &chan_cfg);

    // Initial reading
    s_voltage = read_batt_voltage();
    s_percent = voltage_to_percent(s_voltage);

    ESP_LOGI(TAG, "Battery: %.2f V (%d%%)", s_voltage, s_percent);
}

void power_tick() {
    uint32_t now = millis();
    if ((now - s_last_check) < BATT_CHECK_INTERVAL_MS) return;
    s_last_check = now;

    s_voltage = read_batt_voltage();
    s_percent  = voltage_to_percent(s_voltage);

    ESP_LOGI(TAG, "Battery: %.2f V (%d%%)", s_voltage, s_percent);

    if (s_voltage < BATT_CRITICAL_V) {
        ESP_LOGW(TAG, "Critical battery — entering deep sleep");
        led_set(LedPattern::BLINK_TRIPLE, LED_CLR_LOW_BATTERY);
        delay(2000);
        power_deep_sleep();
    }
}

float power_batt_voltage() {
    return s_voltage;
}

uint8_t power_batt_percent() {
    return s_percent;
}

BattLevel power_batt_level() {
    if (s_percent > 80)  return BattLevel::FULL;
    if (s_percent > 40)  return BattLevel::GOOD;
    if (s_percent > 10)  return BattLevel::LOW;
    return BattLevel::CRITICAL;
}

void power_activity() {
    s_last_active = millis();
}

bool power_should_light_sleep() {
    return (millis() - s_last_active) > IDLE_TO_LIGHT_SLEEP_MS;
}

bool power_should_deep_sleep() {
    return (millis() - s_last_active) > IDLE_TO_DEEP_SLEEP_MS;
}

void power_light_sleep(uint32_t timeout_ms) {
    ESP_LOGI(TAG, "Entering light sleep for %u ms (or button wake)", timeout_ms);

    // Configure GPIO wake-up (active-low button on PIN_BUTTON_A)
    gpio_wakeup_enable((gpio_num_t)PIN_BUTTON_A, GPIO_INTR_LOW_LEVEL);
    esp_sleep_enable_gpio_wakeup();
    esp_sleep_enable_timer_wakeup((uint64_t)timeout_ms * 1000ULL);  // µs

    // In light sleep, WiFi is off but I2S DMA keeps running.
    // CPU halts until wake event; execution resumes here.
    esp_light_sleep_start();

    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    if (cause == ESP_SLEEP_WAKEUP_GPIO) {
        ESP_LOGI(TAG, "Wake from light sleep: button pressed");
        power_activity();
    }

    // Disable gpio wakeup source to avoid spurious re-triggers
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_GPIO);
}

void power_deep_sleep() {
    ESP_LOGI(TAG, "Entering deep sleep — press button to wake");
    led_off();
    delay(100);  // Let LED driver settle

    // Wake on falling edge of button (GPIO EXT0)
    esp_sleep_enable_ext0_wakeup((gpio_num_t)PIN_BUTTON_A, 0);  // 0 = low level
    esp_deep_sleep_start();
    // Does not return — device reboots when button pressed
}
