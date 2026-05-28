import Link from "next/link";

export default function HardwarePage() {
  return (
    <div className="min-h-screen" style={{ background: "#0C0C0C", color: "#F5F0EB" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">

        <Link href="/internal" className="inline-flex items-center gap-2 text-sm mb-8 hover:opacity-80 transition-opacity" style={{ color: "#8A8A8A" }}>
          ← Internal Dashboard
        </Link>

        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span style={{ color: "#C8A97E" }}>⬡</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Hardware</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight mb-2">Firmware Design Document</h1>
          <p style={{ color: "#8A8A8A" }}>Anticipy Ambient AI Pendant — Version 1.0.0 · ESP32-S3 · PlatformIO + Arduino · Updated 2026-04-14</p>
        </div>

        {/* Executive Summary */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Executive Summary</h2>
          <div className="p-5 rounded-xl mb-4" style={{ background: "#161616", border: "1px solid #252525" }}>
            <p className="text-sm leading-relaxed mb-4" style={{ color: "#A0A0A0" }}>
              The Anticipy Pendant is a wearable ambient audio capture device. It continuously monitors ambient conversation
              via a MEMS microphone, runs on-device Voice Activity Detection (VAD) to detect meaningful speech, and ships
              audio clips to the Anticipy cloud engine for transcription and autonomous task execution.
            </p>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Privacy-first", value: "Audio never stored on device — uploaded in near-real-time and discarded" },
                { label: "Jewelry aesthetic", value: "38 × 25 × 11 mm, 18g, matte black PETG, single RGB LED status dot" },
                { label: "Battery life", value: "15–20 hours of normal conversational use from 400 mAh LiPo" },
                { label: "Zero-config", value: "Press button to pair via BLE — device handles WiFi and API authentication" },
              ].map((p) => (
                <div key={p.label} className="p-3 rounded-lg" style={{ background: "#0C0C0C" }}>
                  <div className="text-xs font-semibold mb-1" style={{ color: "#C8A97E" }}>{p.label}</div>
                  <div className="text-xs" style={{ color: "#8A8A8A" }}>{p.value}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Block diagram */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>System Block Diagram</h2>
          <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
            <pre className="text-xs p-6 overflow-x-auto leading-relaxed" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`                     ┌─────────────────────────────────────────────────────┐
                     │              Anticipy Pendant PCB                    │
                     │                                                      │
USB-C ──────────────►│  TP4056 + DW01A    LiPo 400mAh                      │
(5V, charging only)  │  Charger Module ──► 3.7V cell ──► XIAO ESP32-S3     │
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
                             └─────────────────────────────────────────┘`}</pre>
          </div>
        </section>

        {/* Pin assignments */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Pin Assignments</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["GPIO", "Signal", "Direction", "Notes"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { gpio: "GPIO1", signal: "BUTTON_A", dir: "Input (pull-up)", notes: "Tap = toggle record; Hold 3s = pair mode; Hold 8s = factory reset" },
                  { gpio: "GPIO2", signal: "BATT_ADC", dir: "Input (ADC)", notes: "100k/100k divider — reads 0–1.85V for 0–3.7V cell" },
                  { gpio: "GPIO3", signal: "BUTTON_B", dir: "Input (pull-up)", notes: "Reserved — double-tap gesture" },
                  { gpio: "GPIO4", signal: "LED_DATA", dir: "Output", notes: "WS2812B/SK6812 single addressable LED via 33Ω R5" },
                  { gpio: "GPIO5", signal: "—", dir: "—", notes: "Spare / future use" },
                  { gpio: "GPIO6", signal: "I2S_BCLK", dir: "Output", notes: "INMP441 SCK (bit clock)" },
                  { gpio: "GPIO7", signal: "I2S_LRCK", dir: "Output", notes: "INMP441 WS (word select / L/R clock)" },
                  { gpio: "GPIO8", signal: "I2S_DATA", dir: "Input", notes: "INMP441 SD (serial data, 24-bit I2S)" },
                ].map((row) => (
                  <tr key={row.gpio} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 font-mono text-xs font-semibold" style={{ color: "#C8A97E" }}>{row.gpio}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "#F5F0EB" }}>{row.signal}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#8A8A8A" }}>{row.dir}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Memory map */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Memory Map</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Region", "Size", "Purpose"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { region: "Flash — app0", size: "3 MB", purpose: "Firmware image (active)" },
                  { region: "Flash — app1", size: "3 MB", purpose: "OTA update slot" },
                  { region: "Flash — nvs", size: "20 KB", purpose: "WiFi credentials, device config" },
                  { region: "Flash — spiffs", size: "1.5 MB", purpose: "Reserved" },
                  { region: "PSRAM", size: "8 MB", purpose: "Audio ring buffer (~960 KB) + WiFi TX buffers" },
                  { region: "SRAM", size: "512 KB", purpose: "Stack, heap, I2S DMA descriptors" },
                ].map((row) => (
                  <tr key={row.region} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "#C8A97E" }}>{row.region}</td>
                    <td className="px-4 py-3 text-sm font-medium" style={{ color: "#F5F0EB" }}>{row.size}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* State machine */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Firmware State Machine</h2>
          <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
            <pre className="text-xs p-6 overflow-x-auto leading-relaxed" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`     ┌──────────┐
     │   BOOT   │  (setup, NVS read, hardware init)
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
     │ RECORDING │  (buffer audio, keep VAD running)
     └────┬──────┘
          │ silence > 2s (hang timeout)
     ┌────▼──────┐
     │ UPLOADING │  (POST PCM to API, await 200)
     └────┬──────┘
          │ done (or timeout)
     └────► IDLE

Any state ──► LOW_BATTERY   (Vbatt < 3.5V)
Any state ──► BLE_PAIR      (button held > 5s)
IDLE × 5min ──► DEEP_SLEEP  (button to wake)`}</pre>
          </div>
        </section>

        {/* Audio pipeline */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Audio Capture Pipeline</h2>
          <div className="rounded-xl overflow-hidden mb-4" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
            <pre className="text-xs p-6 overflow-x-auto leading-relaxed" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`INMP441 (analog → 24-bit I2S) ──► ESP32-S3 I2S peripheral (DMA)
    ──► DMA ring buffer (SRAM, 4×1024 samples)
    ──► Audio task (reads 20ms frames = 320 samples)
    ──► Right-shift 16: 32-bit I2S → 16-bit PCM
    ──► VAD analysis (RMS energy per frame)
    ──► Ring buffer in PSRAM (30s = 960 KB)
    ──► Upload task (reads 10s chunks from ring buffer)
    ──► HTTPS POST to /api/engine/transcribe`}</pre>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Sample rate", value: "16,000 Hz" },
              { label: "Bit depth", value: "16-bit (from 24-bit I2S)" },
              { label: "Channels", value: "Mono (L/R tied to GND)" },
              { label: "Frame size", value: "20ms = 320 samples = 640 bytes" },
              { label: "Ring buffer", value: "1,500 frames = 30s = ~960 KB (PSRAM)" },
              { label: "Upload chunk", value: "500 frames = 10s per POST" },
            ].map((p) => (
              <div key={p.label} className="p-3 rounded-lg" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="text-xs mb-1" style={{ color: "#5A5A5A" }}>{p.label}</div>
                <div className="text-sm font-medium font-mono" style={{ color: "#C8A97E" }}>{p.value}</div>
              </div>
            ))}
          </div>
        </section>

        {/* LED patterns */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>LED Status Patterns</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Situation", "Pattern", "Color"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { situation: "Connecting to WiFi", pattern: "Slow pulse (1Hz)", color: "Blue", dot: "#3b82f6" },
                  { situation: "BLE pairing mode", pattern: "Rainbow cycle", color: "Cycling", dot: "#C8A97E" },
                  { situation: "Connected, listening", pattern: "Single 100ms blink every 3s", color: "Dim green", dot: "#22c55e" },
                  { situation: "VAD triggered (speech)", pattern: "Solid on", color: "Red", dot: "#ef4444" },
                  { situation: "Uploading audio", pattern: "Fast pulse (4Hz)", color: "Cyan", dot: "#06b6d4" },
                  { situation: "Upload success", pattern: "2 quick blinks", color: "Green", dot: "#22c55e" },
                  { situation: "Upload error", pattern: "3 quick blinks", color: "Orange", dot: "#f97316" },
                  { situation: "Low battery (<20%)", pattern: "Slow pulse", color: "Yellow", dot: "#eab308" },
                  { situation: "Critical battery (<5%)", pattern: "Fast blink", color: "Yellow", dot: "#eab308" },
                  { situation: "Deep sleep", pattern: "Off", color: "—", dot: "#252525" },
                ].map((row) => (
                  <tr key={row.situation} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs" style={{ color: "#F5F0EB" }}>{row.situation}</td>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#A0A0A0" }}>{row.pattern}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: row.dot }} />
                        <span className="text-xs" style={{ color: "#8A8A8A" }}>{row.color}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Button controls */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Button Controls</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Gesture", "Action"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { gesture: "Single tap", action: "Toggle manual record on/off" },
                  { gesture: "Double tap (<400ms)", action: "Force upload current buffer" },
                  { gesture: "Hold 3 seconds", action: "Enter BLE pairing mode" },
                  { gesture: "Hold 8 seconds", action: "Factory reset (clear NVS — WiFi creds + device config)" },
                ].map((row) => (
                  <tr key={row.gesture} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-semibold" style={{ color: "#C8A97E" }}>{row.gesture}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* API Contract */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>API Contract — /api/engine/transcribe</h2>
          <div className="space-y-4">
            <div>
              <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Request</div>
              <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
                <pre className="text-xs p-4 overflow-x-auto" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`POST https://www.anticipy.ai/api/engine/transcribe
Content-Type: application/octet-stream
Authorization: Bearer <device_api_token>
X-Device-ID: <MAC address hex, e.g. "AABBCCDDEEFF">
X-Session-ID: <UUID v4, new per utterance>
X-Sample-Rate: 16000
X-Channels: 1
X-Bit-Depth: 16
X-Duration-MS: <integer ms of audio in body>
X-Firmware-Version: 1.0.0

<body: raw little-endian 16-bit PCM audio samples>`}</pre>
              </div>
            </div>
            <div>
              <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Response</div>
              <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
                <pre className="text-xs p-4 overflow-x-auto" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`{
  "ok": true,
  "session_id": "...",
  "transcript": "Remind me to call the dentist tomorrow at 9am.",
  "intent_detected": true,
  "task_queued": true
}`}</pre>
              </div>
            </div>
            <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                    {["HTTP", "Meaning", "Firmware action"].map((h) => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    { code: "200", meaning: "Accepted", action: "Blink green ×2, discard audio" },
                    { code: "400", meaning: "Bad request (audio < 500ms)", action: "Log, discard silently" },
                    { code: "401", meaning: "Invalid token", action: "LED orange, retry with re-auth" },
                    { code: "413", meaning: "Payload too large (>5MB)", action: "Should never happen — chunk is 10s = 320KB" },
                    { code: "429", meaning: "Rate limited", action: "Exponential backoff, LED yellow" },
                    { code: "500", meaning: "Server error", action: "Retry 3×, then discard" },
                    { code: "Timeout", meaning: "No response in 15s", action: "Retry once, then discard" },
                  ].map((row) => (
                    <tr key={row.code} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                      <td className="px-4 py-3 font-mono text-xs font-semibold" style={{ color: "#C8A97E" }}>{row.code}</td>
                      <td className="px-4 py-3 text-xs" style={{ color: "#F5F0EB" }}>{row.meaning}</td>
                      <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Source code reference */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Source Code Reference</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["File", "Purpose"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { file: "firmware/platformio.ini", purpose: "PlatformIO project config (ESP32-S3, Arduino)" },
                  { file: "firmware/src/config.h", purpose: "All pin defs, constants, API endpoints" },
                  { file: "firmware/src/main.cpp", purpose: "setup(), loop(), state machine, button handler" },
                  { file: "firmware/src/audio.h/.cpp", purpose: "I2S init, DMA capture, ring buffer (PSRAM)" },
                  { file: "firmware/src/vad.h/.cpp", purpose: "Energy-based VAD with adaptive noise floor" },
                  { file: "firmware/src/network.h/.cpp", purpose: "WiFi connect, BLE provisioning, HTTPS upload, OTA" },
                  { file: "firmware/src/power.h/.cpp", purpose: "Battery ADC, sleep modes, wake-up handlers" },
                  { file: "firmware/src/led.h/.cpp", purpose: "WS2812B control via RMT, pattern library" },
                  { file: "firmware/case/anticipy_pendant.scad", purpose: "OpenSCAD parametric 3D case design" },
                ].map((row) => (
                  <tr key={row.file} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "#C8A97E" }}>{row.file}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 3D case */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>3D Printed Case Design</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="text-xs font-medium mb-3" style={{ color: "#8A8A8A" }}>Dimensions</div>
              <div className="space-y-2">
                {[
                  { k: "Body", v: "38mm (W) × 25mm (H) × 11mm (D)" },
                  { k: "Wall thickness", v: "1.5mm" },
                  { k: "Lanyard hole", v: "4mm diameter, top edge, centered" },
                  { k: "Electronics weight", v: "~18g" },
                  { k: "PETG case weight", v: "~6g" },
                  { k: "Total weight", v: "~24g" },
                ].map((p) => (
                  <div key={p.k} className="flex justify-between text-xs">
                    <span style={{ color: "#5A5A5A" }}>{p.k}</span>
                    <span style={{ color: "#C8A97E" }}>{p.v}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="text-xs font-medium mb-3" style={{ color: "#8A8A8A" }}>Material options</div>
              <div className="space-y-2">
                {[
                  { stage: "DIY prototype", mat: "PLA", note: "0.2mm, easy to print" },
                  { stage: "Wearable proto", mat: "PETG matte black", note: "Durable, slight flex" },
                  { stage: "Pilot production", mat: "Resin SLA", note: "Smooth, jewelry quality" },
                  { stage: "Mass production", mat: "Injection ABS", note: "~$3K tooling, $0.50/unit" },
                ].map((p) => (
                  <div key={p.stage} className="flex justify-between text-xs gap-2">
                    <span style={{ color: "#5A5A5A" }}>{p.stage}</span>
                    <span className="text-right" style={{ color: "#A0A0A0" }}>{p.mat} — {p.note}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
            <div className="px-4 py-2 border-b text-xs font-medium" style={{ borderColor: "#252525", color: "#5A5A5A" }}>
              firmware/case/anticipy_pendant.scad — Key parameters
            </div>
            <pre className="text-xs p-4 overflow-x-auto" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`body_w   = 38;   // Width in mm
body_h   = 25;   // Height in mm
body_d   = 11;   // Depth in mm (front to back)
wall_t   = 1.5;  // Wall thickness
corner_r = 4.0;  // Corner radius (rounded edges)

// Print settings (PETG):
// Layer height: 0.15mm (smooth finish)
// Infill: 20% gyroid
// Perimeters: 3 (for strength)
// Supports: yes for mic port overhang
// Orientation: front-face-down on PEI plate`}</pre>
          </div>
        </section>

        {/* Flashing */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Flashing Procedure</h2>
          <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
            <div className="px-4 py-2 border-b text-xs font-medium" style={{ borderColor: "#252525", color: "#5A5A5A" }}>First-time flash via USB-C</div>
            <pre className="text-xs p-4 overflow-x-auto" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`# Install PlatformIO
pip install platformio

# Enter firmware directory
cd firmware

# Copy credentials config
cp src/config_example.h src/config_secrets.h
# Edit config_secrets.h: WiFi SSID/password + API token

# Build and flash (30 seconds)
pio run --target upload

# Monitor serial output
pio device monitor --baud 115200`}</pre>
          </div>
          <div className="mt-3 p-4 rounded-xl text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
            <span className="font-medium" style={{ color: "#F5F0EB" }}>Force bootloader mode</span> (if device unresponsive): Hold BOOT button on XIAO → Press+release RESET → Release BOOT → device enters USB DFU mode.
          </div>
        </section>

      </div>
    </div>
  );
}
