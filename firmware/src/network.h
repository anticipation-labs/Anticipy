#pragma once
#include <Arduino.h>

// ═══════════════════════════════════════════════════════════════════════════
//  network.h — WiFi connection, BLE provisioning, HTTPS audio upload, OTA
// ═══════════════════════════════════════════════════════════════════════════

// ── WiFi ────────────────────────────────────────────────────────────────────

// Load WiFi credentials from NVS and connect.
// Returns true on successful connection within WIFI_CONNECT_TIMEOUT_MS.
bool net_wifi_connect();

// Check if WiFi is currently connected
bool net_wifi_connected();

// Attempt reconnect if disconnected; returns true if now connected.
bool net_wifi_ensure_connected();

// Disconnect WiFi (call before light sleep to save power)
void net_wifi_disconnect();

// MAC address as 12-char hex string "AABBCCDDEEFF"
const char* net_device_id();

// ── BLE provisioning ────────────────────────────────────────────────────────

// Start BLE advertisement and wait for phone to send credentials.
// Blocks until credentials are received OR timeout_ms elapses.
// Returns true if credentials were received and saved to NVS.
bool net_ble_provision(uint32_t timeout_ms);

// True while BLE provisioning is active
bool net_ble_is_provisioning();

// ── Audio upload ─────────────────────────────────────────────────────────────

// Upload a buffer of raw 16-bit PCM audio to the transcription API.
// session_id: UUID string identifying this utterance
// samples: pointer to PCM data, little-endian 16-bit
// num_samples: total number of samples (= duration_ms * SAMPLE_RATE / 1000)
// Returns HTTP status code, or -1 on connection error.
int net_upload_audio(const char* session_id,
                     const int16_t* samples,
                     size_t num_samples);

// ── OTA ──────────────────────────────────────────────────────────────────────

// Check for and apply an OTA firmware update.
// Returns true if an update was applied (device will reboot shortly after).
// Returns false if no update available or update failed.
bool net_ota_check();
