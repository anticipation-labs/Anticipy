#include <Arduino.h>
#include "config.h"
#include "audio.h"
#include "vad.h"
#include "network.h"
#include "power.h"
#include "led.h"

#include "esp_log.h"
#include <Preferences.h>

// ═══════════════════════════════════════════════════════════════════════════
//  main.cpp — Anticipy Pendant firmware
//
//  State machine:
//    BOOT → WIFI_CONNECT  (if credentials in NVS)
//         → BLE_PAIR      (if no credentials, or button held 3s)
//    WIFI_CONNECT → IDLE  (on WiFi connected)
//    IDLE → RECORDING     (on VAD speech start)
//    RECORDING → UPLOADING (on VAD utterance end)
//    UPLOADING → IDLE     (on upload complete or error)
//    Any → DEEP_SLEEP     (10 min idle, or critical battery)
// ═══════════════════════════════════════════════════════════════════════════

static const char* TAG = "main";

// ── Device state machine ────────────────────────────────────────────────────

enum class AppState {
    BOOT,
    WIFI_CONNECT,
    BLE_PAIR,
    IDLE,
    RECORDING,
    UPLOADING,
    DEEP_SLEEP,
};

static AppState s_state = AppState::BOOT;

// ── Upload session state ─────────────────────────────────────────────────────
static char   s_session_id[37] = {0};  // UUID v4 for current utterance
static size_t s_upload_cursor  = 0;    // Ring buffer read cursor for upload task
static size_t s_utterance_start_frame = 0;  // Frame index where speech began

// ── Button state ─────────────────────────────────────────────────────────────

struct ButtonState {
    bool     pressed;
    uint32_t press_ms;
    uint32_t last_tap_ms;
    uint8_t  tap_count;
    bool     long_fired;    // True if long-press action already triggered
    bool     vlong_fired;   // True if very-long-press (factory reset) triggered
};

static ButtonState s_btn_a = {};

// ── UUID generator (simple, not RFC-compliant but unique enough for sessions) ─
static void make_session_id(char* out) {
    uint32_t a = esp_random();
    uint32_t b = esp_random();
    uint32_t c = esp_random();
    uint32_t d = esp_random();
    snprintf(out, 37, "%08x-%04x-4%03x-%04x-%08x%04x",
             a, b & 0xFFFF, (c >> 20) & 0x0FFF,
             ((c >> 4) & 0x0FFF) | 0x8000,
             d, b >> 16);
}

// ── State transitions ────────────────────────────────────────────────────────

static void enter_state(AppState next) {
    ESP_LOGI(TAG, "State: %d → %d", (int)s_state, (int)next);
    s_state = next;

    switch (next) {
        case AppState::BOOT:
            break;

        case AppState::WIFI_CONNECT:
            led_wifi_connecting();
            break;

        case AppState::BLE_PAIR:
            led_ble_pairing();
            break;

        case AppState::IDLE:
            power_activity();
            led_connected_idle();
            // Ensure audio capture is running so VAD can fire
            if (!audio_is_running()) audio_start();
            vad_reset();
            break;

        case AppState::RECORDING:
            power_activity();
            led_recording();
            make_session_id(s_session_id);
            // Record the pre-roll start cursor: go back VAD_PREROLL_FRAMES from now
            {
                size_t head = audio_ring_write_head();
                s_utterance_start_frame = (head > VAD_PREROLL_FRAMES)
                                        ? (head - VAD_PREROLL_FRAMES) : 0;
                s_upload_cursor = s_utterance_start_frame;
            }
            ESP_LOGI(TAG, "Recording: session=%s preroll_frame=%u",
                     s_session_id, s_utterance_start_frame);
            break;

        case AppState::UPLOADING:
            power_activity();
            led_uploading();
            break;

        case AppState::DEEP_SLEEP:
            power_deep_sleep();  // Does not return
            break;
    }
}

// ── Button handling ──────────────────────────────────────────────────────────

static void button_tick(ButtonState& btn, int pin) {
    bool now_pressed = (digitalRead(pin) == LOW);
    uint32_t ms = millis();

    if (now_pressed && !btn.pressed) {
        // Press start
        btn.pressed    = true;
        btn.press_ms   = ms;
        btn.long_fired  = false;
        btn.vlong_fired = false;
    }

    if (!now_pressed && btn.pressed) {
        // Release
        btn.pressed = false;
        uint32_t held = ms - btn.press_ms;

        if (!btn.long_fired && !btn.vlong_fired && held >= BTN_DEBOUNCE_MS) {
            // Count as a tap
            uint32_t gap = ms - btn.last_tap_ms;
            if (gap < BTN_DOUBLE_TAP_MS && btn.tap_count > 0) {
                btn.tap_count++;
            } else {
                btn.tap_count = 1;
            }
            btn.last_tap_ms = ms;
        }
    }

    if (btn.pressed) {
        uint32_t held = ms - btn.press_ms;

        // Very-long press: factory reset
        if (!btn.vlong_fired && held >= BTN_FACTORY_RESET_MS) {
            btn.vlong_fired = true;
            btn.tap_count = 0;
            ESP_LOGW(TAG, "Factory reset triggered");
            Preferences prefs;
            prefs.begin(NVS_NAMESPACE, false);
            prefs.clear();
            prefs.end();
            led_set(LedPattern::BLINK_TRIPLE, 0xFF0000);
            delay(2000);
            ESP.restart();
        }

        // Long press: enter BLE pairing
        if (!btn.long_fired && !btn.vlong_fired && held >= BTN_LONG_PRESS_MS) {
            btn.long_fired = true;
            btn.tap_count = 0;
            ESP_LOGI(TAG, "Long press: entering BLE pair mode");
            enter_state(AppState::BLE_PAIR);
        }
    }
}

// Returns number of completed taps and resets the counter
// (wait a little after last tap to distinguish single vs double)
static int button_consume_taps(ButtonState& btn) {
    if (btn.pressed) return 0;  // Still held
    if (btn.tap_count == 0) return 0;
    // Require double-tap gap to pass before returning single tap
    if (btn.tap_count == 1 && (millis() - btn.last_tap_ms) < BTN_DOUBLE_TAP_MS) return 0;
    int n = btn.tap_count;
    btn.tap_count = 0;
    return n;
}

// ── Audio upload helper ──────────────────────────────────────────────────────

// Collect all buffered audio from s_upload_cursor to ring write-head and POST.
// Returns true on success (HTTP 200).
static bool do_upload() {
    size_t write_head = audio_ring_write_head();
    if (s_upload_cursor >= write_head) {
        ESP_LOGI(TAG, "Upload: no new frames");
        return true;
    }

    size_t frames_available = write_head - s_upload_cursor;
    if (frames_available > RING_BUF_FRAMES) {
        // We've fallen too far behind — skip oldest to avoid stale audio
        ESP_LOGW(TAG, "Upload cursor lagged — skipping %u frames",
                 frames_available - RING_BUF_FRAMES);
        s_upload_cursor = write_head - RING_BUF_FRAMES;
        frames_available = RING_BUF_FRAMES;
    }

    // Drain frames into a temporary heap buffer
    // Maximum: UPLOAD_CHUNK_FRAMES per call to cap heap usage
    size_t frames_this_upload = (frames_available > UPLOAD_CHUNK_FRAMES)
                               ? UPLOAD_CHUNK_FRAMES : frames_available;

    size_t buf_samples = frames_this_upload * FRAME_SAMPLES;
    int16_t* buf = (int16_t*)malloc(buf_samples * sizeof(int16_t));
    if (!buf) {
        ESP_LOGE(TAG, "Upload: malloc failed for %u samples", buf_samples);
        return false;
    }

    size_t drained = audio_ring_drain(buf, frames_this_upload, &s_upload_cursor);
    if (drained == 0) {
        free(buf);
        return true;
    }

    int code = -1;
    for (int attempt = 0; attempt < API_RETRY_COUNT; attempt++) {
        code = net_upload_audio(s_session_id, buf, drained * FRAME_SAMPLES);
        if (code == 200) break;
        if (code == 400 || code == 401) break;  // Don't retry auth/bad-request
        ESP_LOGW(TAG, "Upload attempt %d failed (HTTP %d)", attempt + 1, code);
        delay(500 * (attempt + 1));  // Exponential backoff
    }

    free(buf);

    if (code == 200) {
        led_upload_ok();
        return true;
    } else {
        led_upload_err();
        return false;
    }
}

// ── setup ────────────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);

    // Give the serial monitor a moment to connect
    uint32_t boot_ms = millis();
    while (!Serial && (millis() - boot_ms) < 2000) delay(10);

    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, "╔══════════════════════════════╗");
    ESP_LOGI(TAG, "║  Anticipy Pendant v%s     ║", FIRMWARE_VERSION);
    ESP_LOGI(TAG, "╚══════════════════════════════╝");

    // Log wake-up reason (for sleep debugging)
    esp_sleep_wakeup_cause_t wakeup = esp_sleep_get_wakeup_cause();
    if (wakeup != ESP_SLEEP_WAKEUP_UNDEFINED) {
        ESP_LOGI(TAG, "Wake-up cause: %d", (int)wakeup);
    }

    // ── Hardware init ──────────────────────────────────────────────────────
    led_init();
    led_set(LedPattern::BLINK_ONCE, LED_CLR_CONNECTED);

    // Configure button pins with pull-up
    pinMode(PIN_BUTTON_A, INPUT_PULLUP);
    pinMode(PIN_BUTTON_B, INPUT_PULLUP);

    power_init();
    audio_init();
    vad_init();

    // Abort early if battery is critical
    if (power_batt_level() == BattLevel::CRITICAL) {
        ESP_LOGW(TAG, "Critical battery on boot — sleeping immediately");
        enter_state(AppState::DEEP_SLEEP);
    }

    // ── Determine boot path ────────────────────────────────────────────────
    enter_state(AppState::WIFI_CONNECT);
}

// ── loop ────────────────────────────────────────────────────────────────────
// Single-core main loop.  Audio capture, VAD, and upload all run here.
// We avoid FreeRTOS tasks to keep the code easy to follow; the loop runs fast
// enough (< 5ms per iteration in most states) that responsiveness is fine.

static int16_t s_frame_buf[FRAME_SAMPLES];
static uint32_t s_ota_last_check = 0;

void loop() {
    uint32_t loop_ms = millis();

    // ── LED animation ──────────────────────────────────────────────────────
    led_tick();

    // ── Button polling ─────────────────────────────────────────────────────
    button_tick(s_btn_a, PIN_BUTTON_A);
    int taps = button_consume_taps(s_btn_a);

    // ── Power management ──────────────────────────────────────────────────
    power_tick();

    if (power_batt_level() == BattLevel::CRITICAL) {
        led_critical_battery();
        delay(2000);
        enter_state(AppState::DEEP_SLEEP);
        return;
    }

    if (power_batt_level() == BattLevel::LOW && s_state == AppState::IDLE) {
        led_low_battery();
    }

    // ── OTA check (every 6 hours) ──────────────────────────────────────────
    if (s_state == AppState::IDLE
        && net_wifi_connected()
        && (loop_ms - s_ota_last_check) > OTA_CHECK_INTERVAL_MS) {
        s_ota_last_check = loop_ms;
        net_ota_check();  // Returns false if no update; true means device reboots
    }

    // ═════════════════════════════════════════════════════════════════════
    //  State machine
    // ═════════════════════════════════════════════════════════════════════

    switch (s_state) {

        // ── BOOT (should be transitioned away in setup) ──────────────────
        case AppState::BOOT:
            enter_state(AppState::WIFI_CONNECT);
            break;

        // ── WIFI_CONNECT ─────────────────────────────────────────────────
        case AppState::WIFI_CONNECT: {
            if (net_wifi_connect()) {
                ESP_LOGI(TAG, "WiFi connected — starting audio capture");
                audio_start();
                enter_state(AppState::IDLE);
            } else {
                ESP_LOGW(TAG, "WiFi failed — entering BLE provisioning");
                enter_state(AppState::BLE_PAIR);
            }
            break;
        }

        // ── BLE_PAIR ─────────────────────────────────────────────────────
        case AppState::BLE_PAIR: {
            bool got_creds = net_ble_provision(BLE_PAIR_TIMEOUT_MS);
            if (got_creds) {
                // Try to connect with the new credentials
                enter_state(AppState::WIFI_CONNECT);
            } else {
                // Timed out — go to idle anyway and show error
                ESP_LOGW(TAG, "BLE pair timeout — idle without cloud");
                led_upload_err();
                delay(1000);
                audio_start();
                enter_state(AppState::IDLE);
            }
            break;
        }

        // ── IDLE ─────────────────────────────────────────────────────────
        case AppState::IDLE: {
            // Handle button taps
            if (taps == 1) {
                ESP_LOGI(TAG, "Manual record start via button");
                enter_state(AppState::RECORDING);
                break;
            }
            if (taps == 2) {
                ESP_LOGI(TAG, "Double tap: force upload pending audio");
                enter_state(AppState::UPLOADING);
                break;
            }

            // Reconnect WiFi if dropped
            if (!net_wifi_connected()) {
                net_wifi_ensure_connected();
            }

            // Capture one audio frame
            if (audio_capture_frame(s_frame_buf, FRAME_SAMPLES)) {
                VadResult vad = vad_process_frame(s_frame_buf, FRAME_SAMPLES);

                if (vad.utterance_started) {
                    ESP_LOGI(TAG, "VAD: speech detected (RMS=%.0f, thr=%.0f)",
                             vad.rms, vad.threshold);
                    enter_state(AppState::RECORDING);
                }
            }

            // Sleep management
            if (power_should_deep_sleep()) {
                ESP_LOGI(TAG, "10 min idle — entering deep sleep");
                led_off();
                enter_state(AppState::DEEP_SLEEP);
            } else if (power_should_light_sleep()) {
                // Brief light sleep to save power; I2S keeps running
                power_light_sleep(5000);  // sleep up to 5s
                power_activity();  // Reset after wake so we don't immediately re-sleep
            }
            break;
        }

        // ── RECORDING ────────────────────────────────────────────────────
        case AppState::RECORDING: {
            // Handle manual stop tap
            if (taps == 1) {
                ESP_LOGI(TAG, "Manual record stop via button");
                enter_state(AppState::UPLOADING);
                break;
            }

            // Capture frame and run VAD
            if (audio_capture_frame(s_frame_buf, FRAME_SAMPLES)) {
                VadResult vad = vad_process_frame(s_frame_buf, FRAME_SAMPLES);
                power_activity();

                if (vad.utterance_ended) {
                    ESP_LOGI(TAG, "VAD: utterance ended — uploading");
                    enter_state(AppState::UPLOADING);
                }
            }
            break;
        }

        // ── UPLOADING ────────────────────────────────────────────────────
        case AppState::UPLOADING: {
            // Keep capturing audio in background so ring buffer stays fresh
            audio_capture_frame(s_frame_buf, FRAME_SAMPLES);

            bool ok = do_upload();
            ESP_LOGI(TAG, "Upload %s", ok ? "succeeded" : "failed");

            delay(500);  // Brief pause so success/error LED pattern is visible

            enter_state(AppState::IDLE);
            break;
        }

        // ── DEEP_SLEEP ───────────────────────────────────────────────────
        case AppState::DEEP_SLEEP:
            power_deep_sleep();  // Does not return
            break;
    }
}
