# Anticipy Pendant — Schematic Pin Mapping

**PCB revision:** 1.0  
**Board size:** 40 × 25 mm, 2-layer, 1.0 mm FR4, black HASL  
**Last updated:** 2026-04-15

---

## Pin Mapping Table

### U1 — Seeed XIAO ESP32-S3

| XIAO Pin | GPIO | Net Name | Connected To | Notes |
|----------|------|----------|--------------|-------|
| 1 | GPIO1 | BTN_A | SW1 pin 1; pull-up to 3V3 via R3 10kΩ | Tap = toggle record, hold 3s = BLE pair |
| 2 | GPIO2 | BATT_ADC | R1/R2 voltage divider midpoint | 100k/100k divider, reads 0–1.85V for 0–3.7V cell |
| 3 | GPIO3 | BTN_B | SW2 pin 1; pull-up to 3V3 via R4 10kΩ | Reserved (double-tap) |
| 4 | GPIO4 | LED_DATA | LED1 DIN pin | WS2812/SK6812 data; series 33Ω R5 |
| 5 | GPIO5 | GPIO5 | — | Spare / future use |
| 6 | GPIO6 | I2S_BCLK | MIC1 SCK pin | I2S bit clock output to INMP441 |
| 7 | GPIO7 | I2S_LRCK | MIC1 WS pin | I2S word select (L/R) output to INMP441 |
| 8 | GPIO8 | I2S_DATA | MIC1 SD pin | I2S data input from INMP441 |
| 9 | GPIO9 | GPIO9 | — | Spare |
| 10 | GPIO10 | GPIO10 | — | Spare |
| 11 | 3V3 | PWR_3V3 | C1 100nF, C2 10µF (bypass to GND); MIC1 VDD; LED1 VDD; R3/R4 pull-ups | 3.3V LDO output from XIAO onboard ME6211 |
| 12 | GND | GND | System ground | TP4056 GND, battery –, MIC1 GND, LED1 GND, SW1/SW2 pin 2 |
| 13 | 5V | PWR_5V | TP4056 OUT+ via SW_PWR SPDT slide switch | Battery-side 3.7V → XIAO 5V pad (XIAO accepts 3.7–5.5V on this pad) |
| 14 | BAT | PWR_BAT | — | Not connected (XIAO internal LiPo connector, unused — TP4056 charges via 5V pad) |
| — | USB D+ | USB_DP | USB-C connector via XIAO castellated pad | Programming / debug |
| — | USB D– | USB_DM | USB-C connector via XIAO castellated pad | Programming / debug |

---

### MIC1 — INMP441 I2S MEMS Microphone Breakout

| Module Pin | Net Name | Connected To | Notes |
|------------|----------|--------------|-------|
| VDD | PWR_3V3 | U1 3V3 pin 11 | 3.3V supply; module has onboard 100nF bypass cap |
| GND | GND | System GND | |
| SCK | I2S_BCLK | U1 GPIO6 (pin 6) | Bit clock |
| WS | I2S_LRCK | U1 GPIO7 (pin 7) | Word select / LR clock |
| SD | I2S_DATA | U1 GPIO8 (pin 8) | Serial data output (MISO from mic POV) |
| L/R | GND | System GND | Selects left channel (0 = left); ties to GND |

---

### LED1 — SK6812 Mini-E Addressable RGB LED

| LED Pin | Net Name | Connected To | Notes |
|---------|----------|--------------|-------|
| VDD | PWR_3V3 | U1 3V3 pin 11 via C3 100nF bypass | 3.3V supply |
| GND | GND | System GND | |
| DIN | LED_DATA | U1 GPIO4 (pin 4) via R5 33Ω | Series resistor protects ESP32 GPIO |
| DOUT | — | NC | No daisy-chain — single LED |

---

### U2 — TP4056 + DW01A Charging Module (USB-C input)

| Module Pin | Net Name | Connected To | Notes |
|------------|----------|--------------|-------|
| IN+ | USB_5V | USB-C connector VBUS pin | 5V from USB charger |
| IN– | GND | System GND | |
| BAT+ | BATT_P | Battery + terminal; SW_PWR SPDT common pin | Charge output to LiPo cell |
| BAT– | GND | Battery – terminal; System GND | |
| OUT+ | PWR_5V | SW_PWR SPDT switched pin → U1 5V pad | Switched power to MCU |
| OUT– | GND | System GND | DW01A protection; load must go through OUT+ |
| CHRG LED | — | NC (LED on TP4056 module) | Red = charging |
| STDBY LED | — | NC (LED on TP4056 module) | Blue = standby |

---

### BT1 — LiPo 3.7V 400mAh (LP402035)

| Terminal | Net Name | Connected To |
|----------|----------|--------------|
| + (red wire) | BATT_P | U2 BAT+; R1 top (voltage divider input) |
| – (black wire) | GND | U2 BAT–; System GND |

---

### R1, R2 — Voltage Divider (Battery ADC)

| Component | Value | Net | Notes |
|-----------|-------|-----|-------|
| R1 | 100kΩ 0402 | Top: BATT_P; Bottom: BATT_ADC | Upper leg |
| R2 | 100kΩ 0402 | Top: BATT_ADC; Bottom: GND | Lower leg |
| BATT_ADC midpoint | — | U1 GPIO2 (pin 2) | Divider output → ADC; reads ½ × Vbatt |

Divider ratio = 0.5; at Vbatt = 3.7V → ADC sees 1.85V (within ESP32-S3 ADC range of 0–3.3V).

---

### SW1, SW2 — Tactile Buttons (4×4×1.5mm SMD, SKRPACE010)

| Pin | Net | Notes |
|-----|-----|-------|
| SW1 pin 1 | BTN_A | To U1 GPIO1; internal pull-up enabled in firmware, external R3 10kΩ optional |
| SW1 pin 2 | GND | Ground |
| SW2 pin 1 | BTN_B | To U1 GPIO3; internal pull-up enabled in firmware, external R4 10kΩ optional |
| SW2 pin 2 | GND | Ground |

---

### SW_PWR — Slide Switch (SS-12D10 SPDT)

| Pin | Net | Notes |
|-----|-----|-------|
| Common | BATT_P | Battery positive from TP4056 OUT+ |
| ON position | PWR_5V | To U1 5V pad — powers the MCU |
| OFF position | NC | Disconnects load; TP4056 still charges |

---

### C1–C6 — Bypass Capacitors

| Ref | Value | Footprint | Placed Near | Net |
|-----|-------|-----------|-------------|-----|
| C1 | 100nF 0402 | 0402 | U1 3V3 pin | 3V3 to GND |
| C2 | 10µF 0805 | 0805 | U1 3V3 pin | 3V3 to GND (bulk) |
| C3 | 100nF 0402 | 0402 | LED1 VDD | 3V3 to GND |
| C4 | 100nF 0402 | 0402 | MIC1 VDD | 3V3 to GND |
| C5 | 100nF 0402 | 0402 | U2 IN+ | 5V USB to GND |
| C6 | 10µF 0805 | 0805 | U2 IN+ | 5V USB to GND (bulk) |

---

### R3–R5 — Resistors

| Ref | Value | Purpose | Net |
|-----|-------|---------|-----|
| R3 | 10kΩ 0402 | BTN_A pull-up | 3V3 to BTN_A |
| R4 | 10kΩ 0402 | BTN_B pull-up | 3V3 to BTN_B |
| R5 | 33Ω 0402 | LED signal series | LED_DATA line between GPIO4 and LED1 DIN |

---

## Net Summary

| Net Name | Nodes |
|----------|-------|
| PWR_5V | U2 OUT+, SW_PWR switched, U1 5V pad |
| PWR_3V3 | U1 3V3 output, C1, C2, C3, C4, R3, R4, MIC1 VDD, LED1 VDD |
| GND | U1 GND, U2 GND, BT1 –, MIC1 GND, LED1 GND, SW1-2, SW2-2, R2 bottom, C1–C6 bottom |
| BATT_P | BT1 +, U2 BAT+, SW_PWR common, R1 top |
| BATT_ADC | R1 bottom, R2 top, U1 GPIO2 |
| I2S_BCLK | U1 GPIO6, MIC1 SCK |
| I2S_LRCK | U1 GPIO7, MIC1 WS |
| I2S_DATA | U1 GPIO8, MIC1 SD |
| LED_DATA | U1 GPIO4, R5 left; R5 right, LED1 DIN |
| BTN_A | SW1 pin 1, R3 bottom, U1 GPIO1 |
| BTN_B | SW2 pin 1, R4 bottom, U1 GPIO3 |

---

## Design Notes

1. **L/R pin on INMP441** must be tied to GND for left-channel selection. If left floating, output is undefined.
2. **SK6812 VDD at 3.3V** — the SK6812 Mini-E is rated 3.3–5V. Running at 3.3V is fine; brightness is slightly reduced vs 5V but within spec.
3. **TP4056 OUT+ vs BAT+** — always connect the MCU load to OUT+ (protected side), never directly to BAT+. The DW01A cuts OFF on over-discharge.
4. **Series resistor R5** on LED data line prevents GPIO latch-up during power transitions and dampens ringing on the line.
5. **No USB-C PD negotiation** — TP4056 charges at 5V/1A from any USB-A to USB-C or USB-C to USB-C charger. The XIAO 5V pad is only powered from battery via TP4056, never directly from USB during charge (slide switch ensures mutual exclusion isn't required — both can be active simultaneously: charge + run).
