#pragma once

// ═══════════════════════════════════════════════════════════════════════════
//  config.h — Anticipy Pendant firmware constants
//  All tunable parameters live here. Do not scatter magic numbers in .cpp files.
// ═══════════════════════════════════════════════════════════════════════════

// ─── Firmware version ───────────────────────────────────────────────────────
#define FIRMWARE_VERSION        "1.0.0"
#define FIRMWARE_VERSION_INT    10000   // major*10000 + minor*100 + patch

// ─── Pin definitions ────────────────────────────────────────────────────────
// XIAO ESP32-S3 exposes these GPIOs via its castellated pads.
// See DESIGN.md §3 for the full schematic and block diagram.

#define PIN_BUTTON_A        1   // Tap / long-press button (active-low, internal pull-up)
#define PIN_BUTTON_B        3   // Reserved (double-tap gesture), same convention
#define PIN_BATT_ADC        2   // Battery voltage through 100kΩ/100kΩ divider
#define PIN_LED_DATA        4   // WS2812B / SK6812 data line (single LED via RMT)
#define PIN_I2S_BCLK        6   // INMP441 SCK  (I2S bit clock, output)
#define PIN_I2S_LRCK        7   // INMP441 WS   (I2S word select / LR clock, output)
#define PIN_I2S_DATA        8   // INMP441 SD   (I2S data, input)

// ─── I2S / audio parameters ─────────────────────────────────────────────────
#define AUDIO_SAMPLE_RATE   16000   // Hz — good speech quality, Whisper-native
#define AUDIO_SAMPLE_BITS   16      // Bits per sample (stored in ring buffer)
#define AUDIO_CHANNELS      1       // Mono

// 20ms frame: standard for speech processing (WebRTC, Opus, Speex all use this)
#define FRAME_MS            20
#define FRAME_SAMPLES       (AUDIO_SAMPLE_RATE * FRAME_MS / 1000)  // 320
#define FRAME_BYTES         (FRAME_SAMPLES * (AUDIO_SAMPLE_BITS / 8))  // 640

// I2S DMA: 4 buffers × 1024 samples gives ~256ms of buffering before a read
// must occur — plenty of headroom for task scheduling jitter.
#define I2S_DMA_BUF_COUNT   4
#define I2S_DMA_BUF_SAMPLES 1024
#define I2S_DMA_BUF_BYTES   (I2S_DMA_BUF_SAMPLES * sizeof(int32_t))  // 4096

// Ring buffer in PSRAM: 30 seconds of audio
// 1500 frames × 640 bytes = 960,000 bytes ≈ 960 KB (fits in 8 MB PSRAM)
#define RING_BUF_FRAMES     1500
#define RING_BUF_BYTES      ((size_t)RING_BUF_FRAMES * FRAME_BYTES)  // ~960 KB

// ─── VAD parameters ─────────────────────────────────────────────────────────
// Tune VAD_THRESHOLD if the mic placement changes or the environment is loud.
// Start at 300 and increase by 50 until false triggers stop.
#define VAD_ABSOLUTE_THRESHOLD  300     // Minimum RMS to count as speech
#define VAD_NOISE_MULTIPLIER    4.0f    // threshold = max(abs, noise_floor × mult)
#define VAD_HANG_FRAMES         100     // Silence frames before utterance ends (2s)
#define VAD_PREROLL_FRAMES      25      // Frames of pre-roll audio to include (500ms)
#define VAD_NOISE_EMA_ALPHA     0.05f   // Noise floor update speed (smaller = slower)

// ─── Upload parameters ──────────────────────────────────────────────────────
// Upload chunks of 10 seconds to avoid very large HTTP bodies while still
// giving the cloud engine enough context per request.
#define UPLOAD_CHUNK_FRAMES     500                             // 10 s of audio
#define UPLOAD_CHUNK_BYTES      (UPLOAD_CHUNK_FRAMES * FRAME_BYTES)  // 320 KB max

// API endpoint — change to staging URL during development
#define API_BASE_URL            "https://anticipy.ai"
#define API_TRANSCRIBE_PATH     "/api/engine/transcribe"
#define API_OTA_CHECK_PATH      "/api/firmware/latest"
#define API_TRANSCRIBE_URL      API_BASE_URL API_TRANSCRIBE_PATH
#define API_OTA_CHECK_URL       API_BASE_URL API_OTA_CHECK_PATH

#define API_TIMEOUT_MS          15000   // HTTP request timeout
#define API_RETRY_COUNT         3       // Retries on transient failures

// ─── WiFi parameters ────────────────────────────────────────────────────────
#define WIFI_CONNECT_TIMEOUT_MS 20000   // Give up connecting after 20s
#define WIFI_RETRY_INTERVAL_MS  30000   // Retry every 30s if disconnected

// ─── BLE provisioning ───────────────────────────────────────────────────────
#define BLE_DEVICE_NAME         "Anticipy-Pendant"
#define BLE_PAIR_TIMEOUT_MS     120000  // Stop advertising after 2 min

// GATT service/characteristic UUIDs (custom, generated via uuidgenerator.net)
#define BLE_SERVICE_UUID        "12345678-1234-1234-1234-1234567890AB"
#define BLE_CHAR_SSID_UUID      "12345678-1234-1234-1234-1234567890AC"
#define BLE_CHAR_PASS_UUID      "12345678-1234-1234-1234-1234567890AD"
#define BLE_CHAR_TOKEN_UUID     "12345678-1234-1234-1234-1234567890AE"
#define BLE_CHAR_STATUS_UUID    "12345678-1234-1234-1234-1234567890AF"

// ─── NVS keys (Non-Volatile Storage) ────────────────────────────────────────
#define NVS_NAMESPACE           "anticipy"
#define NVS_KEY_SSID            "wifi_ssid"
#define NVS_KEY_PASS            "wifi_pass"
#define NVS_KEY_TOKEN           "api_token"
#define NVS_KEY_DEVICE_ID       "device_id"

// ─── Power / battery parameters ─────────────────────────────────────────────
// The voltage divider (100kΩ top + 100kΩ bottom) divides battery voltage by 2.
// At 4.2V full, ADC sees 2.1V. ADC reference is 3.3V, 12-bit → 4095 counts.
#define BATT_DIVIDER_RATIO      2.0f    // Vin = Vadc × ratio
#define BATT_ADC_REF_V          3.3f    // ADC reference voltage
#define BATT_ADC_MAX_COUNT      4095    // 12-bit ADC
#define BATT_FULL_V             4.20f   // LiPo fully charged
#define BATT_NOMINAL_V          3.70f   // Nominal LiPo voltage
#define BATT_LOW_V              3.50f   // Low battery warning (~20%)
#define BATT_CRITICAL_V         3.30f   // Critical — force deep sleep (~5%)
#define BATT_CHECK_INTERVAL_MS  60000   // Check battery every 60 seconds
#define BATT_SAMPLES            16      // ADC oversample count for accuracy

// ─── Sleep / idle timeouts ──────────────────────────────────────────────────
#define IDLE_TO_LIGHT_SLEEP_MS  30000   // Light sleep after 30s of silence
#define IDLE_TO_DEEP_SLEEP_MS   600000  // Deep sleep after 10 min of silence

// ─── OTA parameters ─────────────────────────────────────────────────────────
#define OTA_CHECK_INTERVAL_MS   21600000UL  // Check for updates every 6 hours
#define OTA_TIMEOUT_MS          60000       // OTA download timeout

// ─── Button timing ──────────────────────────────────────────────────────────
#define BTN_DEBOUNCE_MS         20      // Debounce period
#define BTN_DOUBLE_TAP_MS       400     // Max gap between taps for double-tap
#define BTN_LONG_PRESS_MS       3000    // Long press threshold (BLE pair mode)
#define BTN_FACTORY_RESET_MS    8000    // Hold for factory reset

// ─── LED ────────────────────────────────────────────────────────────────────
#define LED_NUM_PIXELS          1       // Single SK6812/WS2812B
#define LED_BRIGHTNESS          40      // 0–255 (40 ≈ 16% — saves battery, still visible)

// Packed RGB colors (0xRRGGBB) used by led.cpp
#define LED_CLR_OFF             0x000000
#define LED_CLR_WIFI_CONNECTING 0x0000FF   // Blue
#define LED_CLR_CONNECTED       0x003300   // Dim green
#define LED_CLR_RECORDING       0xFF0000   // Red
#define LED_CLR_UPLOADING       0x00CCCC   // Cyan
#define LED_CLR_SUCCESS         0x00FF00   // Bright green (brief flash)
#define LED_CLR_ERROR           0xFF4400   // Orange
#define LED_CLR_LOW_BATTERY     0xFFCC00   // Yellow
#define LED_CLR_BLE_PAIR        0x000000   // Cycling rainbow (handled in code)
