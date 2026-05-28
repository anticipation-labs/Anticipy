#include "network.h"
#include "config.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <Preferences.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <ArduinoJson.h>
#include "esp_log.h"

// ═══════════════════════════════════════════════════════════════════════════
//  network.cpp — WiFi + BLE provisioning + HTTPS upload + OTA
// ═══════════════════════════════════════════════════════════════════════════

static const char* TAG = "network";

// ── Credentials (loaded from NVS at startup) ────────────────────────────────
static char s_ssid[64]      = {0};
static char s_password[64]  = {0};
static char s_api_token[128] = {0};
static char s_device_id[13]  = {0};  // 12 hex chars + null

// ── BLE state ───────────────────────────────────────────────────────────────
static BLEServer*          s_ble_server    = nullptr;
static BLECharacteristic*  s_char_status   = nullptr;
static volatile bool       s_ble_got_creds = false;
static volatile bool       s_ble_active    = false;

// ── GATT callbacks ──────────────────────────────────────────────────────────

class ProvisionCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* ch) override {
        std::string val = ch->getValue();
        if (val.empty()) return;

        // Route incoming write to the correct field based on characteristic UUID
        std::string uuid = ch->getUUID().toString();

        if (uuid == BLE_CHAR_SSID_UUID) {
            strlcpy(s_ssid, val.c_str(), sizeof(s_ssid));
            ESP_LOGI(TAG, "BLE: received SSID");
        } else if (uuid == BLE_CHAR_PASS_UUID) {
            strlcpy(s_password, val.c_str(), sizeof(s_password));
            ESP_LOGI(TAG, "BLE: received password");
        } else if (uuid == BLE_CHAR_TOKEN_UUID) {
            strlcpy(s_api_token, val.c_str(), sizeof(s_api_token));
            ESP_LOGI(TAG, "BLE: received API token");

            // Token is last — save everything and signal completion
            Preferences prefs;
            prefs.begin(NVS_NAMESPACE, false);
            prefs.putString(NVS_KEY_SSID,  s_ssid);
            prefs.putString(NVS_KEY_PASS,  s_password);
            prefs.putString(NVS_KEY_TOKEN, s_api_token);
            prefs.end();

            // Notify phone of success
            if (s_char_status) {
                const char* ok = "ok";
                s_char_status->setValue((uint8_t*)ok, 2);
                s_char_status->notify();
            }

            s_ble_got_creds = true;
            ESP_LOGI(TAG, "BLE: credentials saved to NVS");
        }
    }
};

static ProvisionCallbacks s_prov_callbacks;

// ── helpers ─────────────────────────────────────────────────────────────────

static void load_credentials_from_nvs() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, true);
    prefs.getString(NVS_KEY_SSID,  s_ssid,      sizeof(s_ssid));
    prefs.getString(NVS_KEY_PASS,  s_password,   sizeof(s_password));
    prefs.getString(NVS_KEY_TOKEN, s_api_token,  sizeof(s_api_token));
    prefs.end();
}

static void build_device_id() {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    snprintf(s_device_id, sizeof(s_device_id),
             "%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

// ── WiFi ────────────────────────────────────────────────────────────────────

bool net_wifi_connect() {
    load_credentials_from_nvs();
    build_device_id();

    if (strlen(s_ssid) == 0) {
        ESP_LOGW(TAG, "No WiFi credentials in NVS");
        return false;
    }

    ESP_LOGI(TAG, "Connecting to WiFi: %s", s_ssid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(s_ssid, s_password);

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if ((millis() - start) > WIFI_CONNECT_TIMEOUT_MS) {
            ESP_LOGW(TAG, "WiFi connect timeout");
            return false;
        }
        delay(250);
    }

    ESP_LOGI(TAG, "WiFi connected: %s (RSSI: %d dBm)", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return true;
}

bool net_wifi_connected() {
    return WiFi.status() == WL_CONNECTED;
}

bool net_wifi_ensure_connected() {
    if (net_wifi_connected()) return true;
    return net_wifi_connect();
}

void net_wifi_disconnect() {
    WiFi.disconnect(true);
}

const char* net_device_id() {
    if (s_device_id[0] == 0) build_device_id();
    return s_device_id;
}

// ── BLE provisioning ────────────────────────────────────────────────────────

bool net_ble_provision(uint32_t timeout_ms) {
    ESP_LOGI(TAG, "Starting BLE provisioning (timeout: %u ms)", timeout_ms);

    // Build device name with last 4 hex chars of MAC for uniqueness
    build_device_id();
    char ble_name[32];
    snprintf(ble_name, sizeof(ble_name), "%s-%s",
             BLE_DEVICE_NAME, s_device_id + 8);  // last 4 chars

    BLEDevice::init(ble_name);
    s_ble_server = BLEDevice::createServer();

    BLEService* svc = s_ble_server->createService(BLE_SERVICE_UUID);

    // SSID characteristic: write without response
    BLECharacteristic* c_ssid = svc->createCharacteristic(
        BLE_CHAR_SSID_UUID,
        BLECharacteristic::PROPERTY_WRITE_NR | BLECharacteristic::PROPERTY_WRITE
    );
    c_ssid->setCallbacks(&s_prov_callbacks);

    // Password characteristic
    BLECharacteristic* c_pass = svc->createCharacteristic(
        BLE_CHAR_PASS_UUID,
        BLECharacteristic::PROPERTY_WRITE_NR | BLECharacteristic::PROPERTY_WRITE
    );
    c_pass->setCallbacks(&s_prov_callbacks);

    // Token characteristic
    BLECharacteristic* c_token = svc->createCharacteristic(
        BLE_CHAR_TOKEN_UUID,
        BLECharacteristic::PROPERTY_WRITE_NR | BLECharacteristic::PROPERTY_WRITE
    );
    c_token->setCallbacks(&s_prov_callbacks);

    // Status characteristic: notify to confirm receipt
    s_char_status = svc->createCharacteristic(
        BLE_CHAR_STATUS_UUID,
        BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ
    );
    s_char_status->addDescriptor(new BLE2902());

    svc->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(BLE_SERVICE_UUID);
    adv->setScanResponse(true);
    adv->setMinPreferred(0x06);
    BLEDevice::startAdvertising();

    s_ble_active    = true;
    s_ble_got_creds = false;

    uint32_t start = millis();
    while (!s_ble_got_creds && (millis() - start) < timeout_ms) {
        delay(100);
    }

    BLEDevice::stopAdvertising();
    s_ble_active = false;

    if (s_ble_got_creds) {
        ESP_LOGI(TAG, "BLE provisioning complete");
        BLEDevice::deinit(true);
        return true;
    }

    ESP_LOGW(TAG, "BLE provisioning timed out");
    BLEDevice::deinit(true);
    return false;
}

bool net_ble_is_provisioning() {
    return s_ble_active;
}

// ── Audio upload ─────────────────────────────────────────────────────────────

int net_upload_audio(const char* session_id,
                     const int16_t* samples,
                     size_t num_samples) {
    if (!net_wifi_ensure_connected()) {
        ESP_LOGW(TAG, "Upload skipped — no WiFi");
        return -1;
    }

    load_credentials_from_nvs();

    // Duration metadata
    uint32_t duration_ms = (uint32_t)((uint64_t)num_samples * 1000 / AUDIO_SAMPLE_RATE);
    size_t   payload_bytes = num_samples * sizeof(int16_t);

    ESP_LOGI(TAG, "Uploading %u samples (%u ms, %u bytes) session=%s",
             num_samples, duration_ms, payload_bytes, session_id);

    WiFiClientSecure client;
    client.setInsecure();  // TODO: pin certificate in production
    client.setTimeout(API_TIMEOUT_MS / 1000);

    HTTPClient http;
    http.begin(client, API_TRANSCRIBE_URL);
    http.setTimeout(API_TIMEOUT_MS);

    // Headers
    http.addHeader("Content-Type",          "application/octet-stream");
    http.addHeader("Authorization",         String("Bearer ") + s_api_token);
    http.addHeader("X-Device-ID",           s_device_id);
    http.addHeader("X-Session-ID",          session_id);
    http.addHeader("X-Sample-Rate",         String(AUDIO_SAMPLE_RATE));
    http.addHeader("X-Channels",            "1");
    http.addHeader("X-Bit-Depth",           "16");
    http.addHeader("X-Duration-MS",         String(duration_ms));
    http.addHeader("X-Firmware-Version",    FIRMWARE_VERSION);

    int code = http.POST((uint8_t*)samples, payload_bytes);

    if (code > 0) {
        ESP_LOGI(TAG, "Upload response: %d", code);
        if (code == 200) {
            String body = http.getString();
            ESP_LOGI(TAG, "Response: %s", body.c_str());
        }
    } else {
        ESP_LOGW(TAG, "HTTP error: %s", http.errorToString(code).c_str());
    }

    http.end();
    return code;
}

// ── OTA ──────────────────────────────────────────────────────────────────────

bool net_ota_check() {
    if (!net_wifi_ensure_connected()) return false;

    WiFiClientSecure client;
    client.setInsecure();
    client.setTimeout(10);

    HTTPClient http;
    http.begin(client, String(API_OTA_CHECK_URL) + "?device_id=" + s_device_id
                                                 + "&version=" + FIRMWARE_VERSION);
    int code = http.GET();

    if (code != 200) {
        ESP_LOGI(TAG, "OTA check: HTTP %d — no update available", code);
        http.end();
        return false;
    }

    String body = http.getString();
    http.end();

    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) {
        ESP_LOGW(TAG, "OTA check: invalid JSON");
        return false;
    }

    const char* remote_version = doc["version"];
    const char* firmware_url   = doc["url"];

    if (!remote_version || !firmware_url) return false;

    // Simple string comparison: "1.0.1" > "1.0.0" works lexicographically for
    // versions with same-width fields.  Fine for prototype — replace with semver
    // integer comparison if needed.
    if (strcmp(remote_version, FIRMWARE_VERSION) <= 0) {
        ESP_LOGI(TAG, "OTA: already on latest (%s)", FIRMWARE_VERSION);
        return false;
    }

    ESP_LOGI(TAG, "OTA: updating %s → %s from %s",
             FIRMWARE_VERSION, remote_version, firmware_url);

    WiFiClientSecure ota_client;
    ota_client.setInsecure();

    httpUpdate.setLedPin(PIN_LED_DATA, HIGH);
    httpUpdate.rebootOnUpdate(true);

    t_httpUpdate_return ret = httpUpdate.update(ota_client, firmware_url);
    switch (ret) {
        case HTTP_UPDATE_OK:
            ESP_LOGI(TAG, "OTA update successful — rebooting");
            return true;
        case HTTP_UPDATE_FAILED:
            ESP_LOGE(TAG, "OTA failed: %s", httpUpdate.getLastErrorString().c_str());
            return false;
        case HTTP_UPDATE_NO_UPDATES:
            return false;
    }
    return false;
}
