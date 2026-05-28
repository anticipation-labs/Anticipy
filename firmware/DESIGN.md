# Anticipy Ambient AI Pendant — Firmware Design

**Version:** 1.0.0  
**Target hardware:** ESP32-S3 (XIAO form factor)  
**Build system:** PlatformIO + Arduino framework  
**Last updated:** 2026-04-14

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Hardware Bill of Materials](#2-hardware-bill-of-materials)
3. [System Architecture](#3-system-architecture)
4. [Firmware Design](#4-firmware-design)
5. [Source Code Reference](#5-source-code-reference)
6. [3D Printed Case Design](#6-3d-printed-case-design)
7. [Manufacturing Notes](#7-manufacturing-notes)
8. [API Contract](#8-api-contract)

---

## 1. Executive Summary

The Anticipy Pendant is a wearable ambient audio capture device. It continuously monitors ambient conversation via a MEMS microphone, runs on-device Voice Activity Detection (VAD) to detect meaningful speech, and ships audio clips to the Anticipy cloud engine for transcription and autonomous task execution.

**Core design principles:**
- Privacy-first: audio never stored permanently on device; uploaded in near-real-time and discarded
- Jewelry aesthetic: 38 × 25 × 11 mm, 18 g, matte black PETG case, single RGB LED status dot
- Long battery life: 15–20 hours of normal conversational use from a 400 mAh LiPo
- Zero-config for the user: press button to pair with phone over BLE, device handles everything else

**Unit cost summary:**

| Scenario | USD | CAD (× 1.38) |
|---|---|---|
| Single prototype (all sources, shipped) | ~$56 | **~$77 CAD** |
| 10-unit pilot batch (JLCPCB assembled) | ~$32/unit | ~$44 CAD |
| 1,000-unit production | ~$19/unit | ~$26 CAD |

All prototype costs are well under the $100 CAD target.

---

## 2. Hardware Bill of Materials

### Single-unit prototype BOM

All prices in USD. CAD conversion at 1.38. Prices verified April 2026.

| # | Component | Part Number / SKU | Supplier | Unit Price (USD) | Qty | Line Total (USD) |
|---|-----------|-------------------|----------|-----------------|-----|-----------------|
| 1 | **MCU Module** — Seeed XIAO ESP32-S3 | 113991114 | [DigiKey](https://www.digikey.com/en/products/detail/seeed-technology-co-ltd/113991114/19285530) | $7.49 | 1 | $7.49 |
| 2 | **MEMS Microphone** — INMP441 breakout module | INMP441-MOD | AliExpress (e.g. Store #2835080) | $2.00 | 1 | $2.00 |
| 3 | **LiPo Battery** — 3.7V 400mAh, 4×20×35mm | LP402035 | AliExpress | $3.50 | 1 | $3.50 |
| 4 | **Charger + Protection Module** — TP4056 + DW01A, USB-C input | TP4056-USBC-MOD | AliExpress | $0.85 | 1 | $0.85 |
| 5 | **RGB LED** — SK6812 Mini-E (reverse mount, addressable) | C2890364 | [LCSC](https://lcsc.com) | $0.18 | 1 | $0.18 |
| 6 | **Tactile Button** — 4×4×1.5mm SMD, 260gf actuation | SKRPACE010 | [DigiKey](https://www.digikey.com/en/products/detail/alps-alpine/SKRPACE010/4760743) | $0.33 | 2 | $0.66 |
| 7 | **Slide Switch** — SS-12D10 SPDT, power on/off | SS-12D10 | LCSC | $0.12 | 1 | $0.12 |
| 8 | **Resistors** — 100kΩ 0402 (voltage divider) | RC0402FR-07100KL | LCSC | $0.01 | 2 | $0.02 |
| 9 | **Capacitors** — 100nF 0402 (bypass) + 10µF 0805 (bulk) | CL05B104KO5NNNC | LCSC | $0.02 | 6 | $0.12 |
| 10 | **PCB** — 2-layer, 40×25mm, HASL, 1.0mm, black solder mask | Custom | JLCPCB (5 pcs) | $2.00/unit | 1 | $2.00 |
| 11 | **3D Printed Case** — PETG, matte black (print service) | Custom | JLCPCB 3D Print | $9.00 | 1 | $9.00 |
| 12 | **Lanyard Hardware** — 4mm stainless split ring | — | AliExpress (10-pack) | $0.30 | 1 | $0.30 |
| 13 | **Misc** — solder paste, flux pen, jumper wires, kapton tape | — | Local | $3.00 | — | $3.00 |
| | **Subtotal (components)** | | | | | **$29.24** |
| | **Shipping** — DigiKey standard (~$8), AliExpress (~$6), JLCPCB PCB+3D (~$13) | | | | | ~$27 |
| | **TOTAL (prototype, landed)** | | | | | **~$56 USD / ~$77 CAD** |

### Why these parts

**XIAO ESP32-S3** (not a bare ESP32-S3 chip) was chosen because:
- Includes USB-C natively (no CH340/FTDI bridge needed)
- 8 MB flash + 8 MB PSRAM soldered on — enough for a 30-second audio ring buffer
- Built-in PCB antenna, FCC/CE certified
- 21 × 17.5 mm form factor fits inside the pendant case
- Dual-core LX7 @ 240 MHz handles I2S DMA + VAD + WiFi upload simultaneously
- $7.49 is significantly cheaper than sourcing a bare ESP32-S3-MINI-1 and designing antenna traces

**INMP441** over SPH0645LM4H because:
- SPH0645LM4H is discontinued (Syntiant acquired it)
- INMP441 (TDK InvenSense) is widely available, actively manufactured
- 61 dBA SNR — excellent for speech at conversational distances (0.3–2m)
- I2S 24-bit output maps cleanly to ESP32-S3's I2S peripheral
- 1.4 mA active current, 1 µA power-down
- AliExpress breakout module ($2) is pre-assembled with decoupling caps

**LP402035 400 mAh LiPo** — math for 15+ hour battery life:
- Normal conversation: 20% recording (~100 mA) + 80% light sleep (~5 mA) = 24 mA average
- 400 mAh ÷ 24 mA = **16.7 hours**
- Light-sleep-only periods: 400 ÷ 5 = 80 hours max

**TP4056 + DW01A module** — pre-built USB-C charger + cell protection for $0.85. Includes over-charge, over-discharge, and short-circuit protection. 1A charge rate fills the 400 mAh cell in ~30 minutes.

### 1,000-unit production delta

At volume:
- Replace XIAO module with bare ESP32-S3-MINI-1-H4R2 (~$2.50): saves ~$5/unit
- INMP441 bare die from LCSC (~$1.20): saves ~$0.80/unit
- Custom PCB with JLCPCB SMT assembly (~$6 assembled): saves labor
- Injection-molded ABS case (Shenzhen tooling amortized): ~$1.50/unit vs $9 printed
- Total production cost: ~$19 USD / ~$26 CAD per unit

---

## 3. System Architecture

### Block diagram

```
                         ┌─────────────────────────────────────────────────────┐
                         │              Anticipy Pendant PCB                    │
                         │                                                      │
  USB-C ────────────────►│  TP4056 + DW01A    LiPo 400mAh                      │
  (5V, charging only)    │  Charger Module ──► 3.7V cell ──► XIAO ESP32-S3     │
                         │                                   ┌─────────────┐   │
                         │                                   │  ESP32-S3   │   │
                         │  INMP441 MEMS Mic                 │  LX7×2      │   │
                         │  ┌──────────────┐                 │  240 MHz    │   │
                         │  │  SCK ─────────────────────────►│  GPIO6      │   │
                         │  │  WS ──────────────────────────►│  GPIO7      │   │
                         │  │  SD ──────────────────────────►│  GPIO8      │   │
                         │  │  VDD ◄────────────────────────┤  3.3V       │   │
                         │  └──────────────┘                 │             │   │
                         │                                   │  GPIO4 ─────┼──►│ SK6812 LED
                         │  Tactile buttons                  │             │   │
                         │  ┌────┐  ┌────┐                  │  GPIO1 ◄────┼───┤ Button A (tap)
                         │  │BTN─┼──┼►GPIO1                 │  GPIO3 ◄────┼───┤ Button B (long)
                         │  │BTN─┼──┼►GPIO3                 │             │   │
                         │  └────┘  └────┘                  │  GPIO2 ◄────┼───┤ Batt ADC (÷2)
                         │                                   │             │   │
                         │  100K+100K voltage divider        │  8MB Flash  │   │
                         │  Batt+ ──[100K]──[100K]── GND    │  8MB PSRAM  │   │
                         │                   │               │  WiFi 802.11n   │
                         │                   └──────────────►│  BLE 5.0    │   │
                         │  Slide switch ────────────────────┤  USB-C      │   │
                         │  (master power)                   └─────────────┘   │
                         └─────────────────────────────────────────────────────┘
                                                    │
                                              WiFi / BLE
                                                    │
                               ┌────────────────────▼────────────────────┐
                               │  anticipy.ai Cloud Engine               │
                               │  POST /api/engine/transcribe            │
                               │  → Whisper STT → Intent Detection       │
                               │  → Autonomous task execution            │
                               └─────────────────────────────────────────┘
```

### Pin assignments

| GPIO | Signal | Direction | Notes |
|------|--------|-----------|-------|
| GPIO1 | BUTTON_A | Input (pull-up) | Tap = toggle record; Long = pair mode |
| GPIO2 | BATT_ADC | Input (ADC) | 100k/100k divider, reads 0–1.85V for 0–3.7V |
| GPIO3 | BUTTON_B | Input (pull-up) | Reserved (double-tap gesture) |
| GPIO4 | LED_DATA | Output | WS2812B/SK6812 single addressable LED |
| GPIO6 | I2S_BCLK | Output | INMP441 SCK |
| GPIO7 | I2S_LRCK | Output | INMP441 WS (L/R select) |
| GPIO8 | I2S_DATA | Input | INMP441 SD |

### Power rails

```
USB-C 5V ──► TP4056 ──► LiPo 3.7V ──► XIAO 3.3V LDO ──► Logic (3.3V)
                    └──► DW01A (over-voltage / over-current protection)
```

XIAO ESP32-S3's onboard ME6211 LDO (3.3V, 500mA) powers all logic. The INMP441 operates at 3.3V directly.

### Memory map

| Region | Size | Purpose |
|--------|------|---------|
| Flash (partition: app0) | 3 MB | Firmware image |
| Flash (partition: app1) | 3 MB | OTA update slot |
| Flash (partition: nvs) | 20 KB | WiFi credentials, device config |
| Flash (partition: spiffs) | 1.5 MB | Reserved |
| PSRAM | 8 MB | Audio ring buffer (~960 KB), WiFi TX buffers |
| SRAM | 512 KB | Stack, heap, I2S DMA descriptors |

---

## 4. Firmware Design

### State machine

```
         ┌──────────┐
         │   BOOT   │ (setup, NVS read, hardware init)
         └────┬─────┘
              │ has WiFi credentials?
         ┌────▼──────┐        ┌─────────────┐
    YES  │ WIFI_CONN │  NO►   │ BLE_PAIR    │
    ─────┤ (connect) │        │ (advertise) │
         └────┬──────┘        └──────┬──────┘
              │ success              │ credentials received
         ┌────▼──────┐              │
         │   IDLE    │◄─────────────┘
         │ (VAD loop)│
         └────┬──────┘
              │ speech detected (VAD)
         ┌────▼──────┐
         │ RECORDING │ (buffer audio, keep VAD running)
         └────┬──────┘
              │ silence > 2s (hang timeout)
         ┌────▼──────┐
         │ UPLOADING │ (POST PCM to API, await 200)
         └────┬──────┘
              │ done (or timeout)
         └────► IDLE

   Any state ──► LOW_BATTERY  (Vbatt < 3.5V)
   Any state ──► BLE_PAIR     (button held > 5s)
   IDLE × 5min ──► DEEP_SLEEP (button to wake)
```

### Audio capture pipeline

```
INMP441 (analog → 24-bit I2S) ──► ESP32-S3 I2S peripheral (DMA)
    ──► DMA ring buffer (SRAM, 4×1024 samples)
    ──► Audio task (reads 20ms frames = 320 samples)
    ──► Right-shift 16: 32-bit I2S → 16-bit PCM
    ──► VAD analysis (RMS energy per frame)
    ──► Ring buffer in PSRAM (30s = 960 KB)
    ──► Upload task (reads 10s chunks from ring buffer)
    ──► HTTPS POST to /api/engine/transcribe
```

Key parameters:
- Sample rate: 16,000 Hz
- Bit depth: 16-bit (downsampled from 24-bit I2S)
- Channels: Mono (INMP441 L/R pin tied to GND → left channel)
- Frame size: 20 ms = 320 samples = 640 bytes
- Ring buffer: 1,500 frames = 30 seconds = ~960 KB (PSRAM)
- Upload chunk: 500 frames = 10 seconds per POST

### Voice Activity Detection (VAD)

Energy-based VAD with adaptive noise floor:

```
Each 20ms frame:
  1. Calculate RMS = sqrt(sum(sample^2) / N)
  2. Update noise_floor = 0.95 * noise_floor + 0.05 * RMS  (slow EMA, only in SILENCE state)
  3. threshold = max(noise_floor * 4.0, VAD_ABSOLUTE_MIN = 300)

State transitions:
  SILENCE → SPEECH  if RMS > threshold  (start 500ms pre-roll window)
  SPEECH  → SILENCE if silence_frames > 100  (2 seconds of quiet = 100×20ms)
```

Pre-roll: when speech is detected, we include 500ms of audio from *before* the trigger. This is pulled from the ring buffer (which records continuously) by looking back 25 frames.

### OTA update mechanism

On every boot (and every 6 hours while running), the firmware checks:
```
GET https://anticipy.ai/api/firmware/latest?device_id=<mac>
Response: { "version": "1.2.0", "url": "https://..." }
```
If the returned version is newer than `FIRMWARE_VERSION` in `config.h`, `httpUpdate.update()` downloads and flashes the new binary into the OTA slot. The device reboots automatically.

### LED status patterns

| Situation | Pattern | Color |
|-----------|---------|-------|
| Connecting to WiFi | Slow pulse (1Hz) | Blue |
| BLE pairing mode | Rainbow cycle | Cycling |
| Connected, listening | Single 100ms blink every 3s | Dim green |
| VAD triggered (speech) | Solid on | Red |
| Uploading audio | Fast pulse (4Hz) | Cyan |
| Upload success | 2 quick blinks | Green |
| Upload error | 3 quick blinks | Orange |
| Low battery (<20%) | Slow pulse | Yellow |
| Critical battery (<5%) | Fast blink | Yellow |
| Deep sleep | Off | — |

### Button controls

| Gesture | Action |
|---------|--------|
| Single tap | Toggle manual record on/off |
| Double tap (< 400ms) | Force upload current buffer |
| Hold 3 seconds | Enter BLE pairing mode |
| Hold 8 seconds | Factory reset (clear NVS) |

---

## 5. Source Code Reference

```
firmware/
├── platformio.ini          # PlatformIO project config (ESP32-S3, Arduino)
├── src/
│   ├── config.h            # All pin defs, constants, API endpoints
│   ├── main.cpp            # setup(), loop(), state machine, button handler
│   ├── audio.h / .cpp      # I2S init, DMA capture, ring buffer (PSRAM)
│   ├── vad.h / .cpp        # Energy-based VAD with adaptive noise floor
│   ├── network.h / .cpp    # WiFi connect, BLE provisioning, HTTPS upload, OTA
│   ├── power.h / .cpp      # Battery ADC, sleep modes, wake-up handlers
│   └── led.h / .cpp        # WS2812B control via RMT, pattern library
└── case/
    └── anticipy_pendant.scad  # OpenSCAD parametric case design
```

### Dependencies (platformio.ini `lib_deps`)

| Library | Version | Purpose |
|---------|---------|---------|
| `bblanchon/ArduinoJson` | `^7.0` | JSON for API responses and OTA version check |
| `adafruit/Adafruit NeoPixel` | `^1.12` | WS2812B/SK6812 LED control via RMT |
| `Arduino` (esp32 core) | `^3.0` | WiFiClientSecure, HTTPClient, HTTPUpdate, BLE, NVS |

No additional audio libraries needed — the I2S driver uses ESP-IDF's `driver/i2s_std.h` directly.

---

## 6. 3D Printed Case Design

### Dimensions

```
Body:        38mm (W) × 25mm (H) × 11mm (D)
Wall:        1.5mm
Lanyard hole: 4mm diameter (top edge, centered)
Weight:      ~6g PETG + 18g electronics = ~24g total
```

Comparison: AirPods case is 63 × 47 × 21mm. The Anticipy pendant is 42% smaller in volume.

### Part breakdown

The case is two-part, friction-fit with 4× M1.4 screws (optional — friction fit holds for prototype):

**Front shell** — houses everything, faces the user:
- 1.5mm front wall with mic port (1.5mm diameter at 45° angle, located bottom-center)
- LED diffuser window: 2mm diameter frosted channel at top-right
- Button dimple: 2mm diameter × 0.8mm deep at top-left (allows button actuation through wall)
- USB-C cutout: 10mm × 4mm at bottom edge
- 4mm lanyard hole through top ear

**Back plate** — snaps into place:
- 1.2mm flat plate with 0.5mm lip all around
- Foam pad to protect battery from vibration
- 4× screw bosses (M1.4, optional)

### Material recommendations

| Option | Material | Notes |
|--------|----------|-------|
| DIY prototype | PLA (any color) | Easy to print, 0.2mm layer height |
| Wearable prototype | PETG (matte black) | More durable, slight flex, better appearance |
| Pilot production | Resin SLA (black) | Smooth surface finish, jewelry-level quality |
| Mass production | Injection-molded ABS | Shenzhen tooling ~$3,000 one-time, $0.50/unit |

### OpenSCAD parameters

See `case/anticipy_pendant.scad` for the full parametric design. Key variables:

```scad
body_w   = 38;   // Width in mm
body_h   = 25;   // Height in mm
body_d   = 11;   // Depth in mm (front to back)
wall_t   = 1.5;  // Wall thickness
corner_r = 4.0;  // Corner radius (rounded edges)
```

### Print settings (PETG)

- Layer height: 0.15mm (for smooth finish)
- Infill: 20% gyroid
- Perimeters: 3 (for strength)
- Supports: yes for mic port overhang
- Orientation: print front-face-down on PEI plate

---

## 7. Manufacturing Notes

### PCB assembly (hand solder, prototype)

Required tools:
- Soldering iron with fine tip (T12-BC2 or similar)
- Solder paste (SAC305, no-clean)
- Flux pen
- Hot air gun (for INMP441 if bare die — use module for prototype)
- USB-C breakout tester

Assembly order:
1. Solder all 0402/0805 passives first (voltage divider resistors, bypass caps)
2. Solder SK6812 LED (tiny — use flux, fine tip, 320°C)
3. Solder tactile buttons and slide switch
4. Solder TP4056 charging module (tin pads, position module, heat from above)
5. Solder INMP441 module with pin headers or direct solder
6. Solder XIAO ESP32-S3 last (through-hole castellated pads)
7. Inspect under magnification — check for bridges on XIAO pads
8. Visual and continuity check before powering on

Power-on test sequence:
1. Slide switch OFF. Connect USB-C. Observe TP4056 LED (red = charging).
2. Slide switch ON. Observe LED on XIAO (should blink once on boot).
3. Serial monitor at 115200 baud: should see boot log.
4. Hold button 3s: LED should go rainbow (BLE pairing mode).

### Flashing procedure

**First-time flash** (USB-C direct):

```bash
# Install PlatformIO
pip install platformio

# Clone / enter firmware directory
cd firmware

# Copy credentials to config (or use BLE provisioning after flash)
cp src/config_example.h src/config_secrets.h
# Edit config_secrets.h with your WiFi SSID/password and API token

# Build and flash
pio run --target upload

# Monitor serial output
pio device monitor --baud 115200
```

The XIAO ESP32-S3 appears as a CDC device when connected via USB-C. No drivers needed on macOS/Linux. Windows requires the USB driver from Silicon Labs.

**Force bootloader mode** (if device is unresponsive):
1. Hold BOOT button on XIAO
2. Press and release RESET
3. Release BOOT
4. The device enters USB DFU mode

**Flash via USB stick** (field update by Omar):

Build a release binary:
```bash
pio run
# Binary is at .pio/build/xiao_esp32s3/firmware.bin
```

Copy `firmware.bin` to USB stick. Connect to device running the mass-storage OTA sketch (Phase 2 feature — for now use USB-C direct flash).

### Quality testing checklist

For each assembled unit before shipping:

- [ ] Charging: plug USB-C, TP4056 red LED illuminates, voltage rises to 4.2V
- [ ] Boot: LED blinks on first power-on, serial shows "Anticipy v1.0.0"
- [ ] Microphone: speak into mic, serial shows "VAD: speech detected" within 0.5s
- [ ] WiFi: device connects to test AP, serial shows IP address
- [ ] Upload: force-upload via button double-tap, serial shows "HTTP 200"
- [ ] BLE: hold button 3s, "Anticipy-Pendant" visible in phone Bluetooth scan
- [ ] Battery: disconnect USB, battery reads > 3.9V on serial, LED glows dim green
- [ ] Low battery: drain to 3.5V (or short voltage divider test), LED pulses yellow
- [ ] Deep sleep: leave idle 10 minutes, LED goes off, current draw < 1 mA
- [ ] Wake from sleep: press button, device boots and reconnects within 5s
- [ ] LED patterns: all patterns visible, no stuck pixels
- [ ] Button: single tap, double tap, long press all register correctly
- [ ] OTA: bump `FIRMWARE_VERSION` to "1.0.1-test", verify device self-updates

### BOM sourcing tips

1. **AliExpress orders take 2–3 weeks from Shenzhen to Canada.** Order components before ordering PCBs so they arrive together.
2. **JLCPCB standard PCBs ship in 3–5 business days + shipping.** Choose DHL Express ($15–20) for 5–7 day total delivery.
3. **INMP441 breakout modules** are sold by dozens of AliExpress stores. Choose stores with 4.8+ rating and 500+ sales. Search: "INMP441 I2S microphone ESP32".
4. **LiPo batteries** from AliExpress must clear Canada customs — declare as "electronic component" not "battery" to avoid delays. Buy 10 at once for spare/testing.
5. **For the first PCB order:** use JLCPCB gerbers only (no SMT assembly) and hand-solder. SMT assembly makes sense at 10+ units.

---

## 8. API Contract

The firmware POSTs raw audio to the Anticipy cloud engine. The receiving endpoint needs to be implemented at `/api/engine/transcribe`.

### Request

```
POST https://anticipy.ai/api/engine/transcribe
Content-Type: application/octet-stream
Authorization: Bearer <device_api_token>
X-Device-ID: <MAC address, hex string, e.g. "AABBCCDDEEFF">
X-Session-ID: <UUID v4, new per utterance>
X-Sample-Rate: 16000
X-Channels: 1
X-Bit-Depth: 16
X-Duration-MS: <integer milliseconds of audio in body>
X-Firmware-Version: 1.0.0

<body: raw little-endian 16-bit PCM audio samples>
```

### Response

```json
{
  "ok": true,
  "session_id": "...",
  "transcript": "Remind me to call the dentist tomorrow at 9am.",
  "intent_detected": true,
  "task_queued": true
}
```

### Error codes

| HTTP | Meaning | Firmware action |
|------|---------|-----------------|
| 200 | Accepted | Blink green ×2, discard audio |
| 400 | Bad request (audio too short < 500ms) | Log, discard silently |
| 401 | Invalid token | LED orange, retry with re-auth |
| 413 | Payload too large (> 5MB) | Should not happen — chunk is 10s = 320KB |
| 429 | Rate limited | Exponential backoff, LED yellow |
| 500 | Server error | Retry 3×, then discard |
| Timeout | No response in 15s | Retry once, then discard |

### Audio token provisioning

Device API tokens are provisioned during BLE pairing:
1. User opens Anticipy app (or anticipy.ai/engine on phone)
2. Phone connects to pendant over BLE
3. Phone sends: WiFi SSID, WiFi password, API bearer token
4. Device saves all three to NVS (encrypted partition on ESP32-S3)
5. Token is tied to the user's engine account

---

*Designed for Anticipy — the pendant that vibe-checks your day.*
