# Anticipy Pendant PCB — Assembly Instructions for Contract Manufacturer

**Document version:** 1.0  
**PCB revision:** 1.0  
**Last updated:** 2026-04-15  
**Contact:** omar@anticipy.ai

---

## 1. Overview

This document covers hand-solder prototype assembly (single unit to 5 units). For SMT assembly at JLCPCB (10+ units), a separate Gerber + CPL + BOM package is provided on request.

**PCB:** 40 × 25 mm, 2-layer, 1.0 mm FR4, black solder mask, HASL finish, ENIG optional.  
**Assembly type:** Mixed (SMD passives + through-hole modules + castellated pads).  
**Estimated assembly time:** 45–60 minutes per board (experienced technician).

---

## 2. Bill of Materials

| Ref | Description | Value / Part # | Qty | Package | Supplier |
|-----|-------------|----------------|-----|---------|----------|
| U1 | XIAO ESP32-S3 MCU module | 113991114 | 1 | Castellated 21×17.5mm | Seeed / DigiKey |
| MIC1 | INMP441 I2S microphone breakout | INMP441-MOD | 1 | 6-pin 2.54mm header | AliExpress |
| LED1 | SK6812 Mini-E addressable RGB LED | C2890364 | 1 | 3.5×3.5mm SMD | LCSC |
| U2 | TP4056 + DW01A charger module (USB-C) | TP4056-USBC-MOD | 1 | Module ~18×10mm | AliExpress |
| BT1 | LiPo 3.7V 400mAh | LP402035 | 1 | 4×20×35mm bare cell | AliExpress |
| SW1, SW2 | Tactile button 4×4×1.5mm SMD | SKRPACE010 | 2 | 4×4mm SMD | DigiKey |
| SW_PWR | Slide switch SPDT | SS-12D10 | 1 | Through-hole | LCSC |
| R1, R2 | Resistor 100kΩ | RC0402FR-07100KL | 2 | 0402 | LCSC |
| R3, R4 | Resistor 10kΩ | RC0402FR-0710KL | 2 | 0402 | LCSC |
| R5 | Resistor 33Ω | RC0402FR-0733RL | 1 | 0402 | LCSC |
| C1, C3, C4, C5 | Capacitor 100nF | CL05B104KO5NNNC | 4 | 0402 | LCSC |
| C2, C6 | Capacitor 10µF | CL21A106KAYNNNE | 2 | 0805 | LCSC |
| J1 | Lanyard hole reinforcement ring (optional) | — | 1 | 4mm ID brass grommet | Hardware store |

---

## 3. Required Tools and Materials

- Soldering iron with fine chisel tip (T12-BC2 or T12-D08 recommended), 300–350°C
- Solder wire: SAC305 no-clean, 0.3mm diameter
- Flux pen: no-clean rosin flux (e.g., MG Chemicals 8341)
- Solder paste: SAC305 no-clean paste (for SMD reflow optional, or use iron)
- Hot air rework station (optional, useful for LED1 and TP4056 module)
- Tweezers: fine-point ESD-safe (SA tweezers #5)
- Magnification: stereo microscope or 10× loupe
- Multimeter: continuity and DC voltage
- USB-C cable (for power-on test)
- Isopropyl alcohol 99% + cotton swabs (flux cleanup)
- Kapton tape (to hold modules during soldering)

---

## 4. Pre-Assembly Inspection

Before picking up the iron:

1. **Verify PCB:** inspect for correct silkscreen labels (U1, MIC1, LED1, R1–R5, C1–C6, SW1, SW2, SW_PWR, BT1).
2. **Check polarity markers:** LED1 has a cathode dot on silkscreen. U1 has pin-1 indicator. TP4056 module has IN+/IN–/BAT+/BAT–/OUT+/OUT– labels — verify they match PCB pads.
3. **Inspect pads:** no bridging, no lifted pads, pads are clean and tinned.
4. **Count components:** check off BOM above.

---

## 5. Assembly Order

**Rule:** solder smallest/flattest components first, tallest last. Never place BT1 until all soldering is complete.

### Step 1 — SMD Passives: Resistors and Capacitors

1. Apply small amount of flux to all 0402 and 0805 pads.
2. **Solder in this order:** C1, C2, C3, C4, C5, C6 (capacitors), then R1, R2, R3, R4, R5 (resistors).
3. For 0402: apply solder to one pad, tack component with tweezers, solder second pad, reflow first pad. Use minimal solder — the joint should be a small fillet, not a blob.
4. **Verify values before placement:** R1/R2 = 100kΩ (brown-black-yellow-gold), R3/R4 = 10kΩ (brown-black-orange-gold), R5 = 33Ω (orange-orange-black-gold). Use a DMM ohmmeter to confirm.
5. Post-step check: visual inspection under magnification for solder bridges and tombstoning.

### Step 2 — SK6812 Mini-E LED (LED1)

> **Critical:** The SK6812 is a tiny 3.5×3.5mm IC with 4 pads on the underside. This is the hardest component on the board.

1. Apply flux to all 4 LED pads on PCB.
2. Pre-tin one pad (the GND pad — largest, nearest the cathode dot).
3. Place LED1 with correct orientation: pin 1 / DIN corner matches silkscreen dot.  
   Pin order (looking from above, pads underneath): 1=DIN, 2=VDD, 3=DOUT, 4=GND.
4. Reflow the pre-tinned pad to tack the component.
5. Solder remaining 3 pads with fine tip and minimal solder.
6. Inspect: all 4 pads visible, no bridges between adjacent pads.
7. **Polarity note:** GND pad (pin 4) is the largest pad and has a thermal relief on the PCB — it needs slightly more heat.

### Step 3 — Tactile Buttons (SW1, SW2)

1. SW1 and SW2 are 4×4mm SMD tactile switches.
2. All 4 legs are ground (symmetric) — orientation matters only for fit, not electrically.
3. Solder one leg, check component is seated flat, solder remaining 3 legs.
4. Apply light pressure while soldering to prevent the switch from lifting.

### Step 4 — Slide Switch (SW_PWR)

1. SW_PWR is a through-hole SPDT SS-12D10.
2. Insert through PCB from top, bend leads slightly on bottom to hold in place.
3. Solder 3 leads on PCB bottom side.
4. Trim excess lead length to 0.5mm above solder joint.
5. Verify: switch toggles cleanly with audible click, mechanism not obstructed by solder.

### Step 5 — TP4056 Charging Module (U2)

1. The TP4056 module has solder pads around its perimeter (IN+, IN–, BAT+, BAT–, OUT+, OUT–) plus 2 LED indicator pads.
2. Apply flux to module's pads and corresponding PCB pads.
3. Place module — use Kapton tape to hold in position.
4. Tack one corner pad, verify alignment, solder remaining pads.
5. Optional: use hot air at 300°C to reflow all pads simultaneously for better joint quality.
6. **Post-solder check:** confirm IN+/BAT+/OUT+ are not bridged to their respective minus rails. Use DMM continuity — IN+ to IN– should be open, BAT+ to BAT– should be open (before cell is connected).

### Step 6 — INMP441 Microphone Module (MIC1)

1. MIC1 is a breakout board with a 6-pin 2.54mm header (VDD, GND, SCK, WS, SD, L/R).
2. Two options:
   - **Option A (prototype):** solder 6-pin female socket on PCB, plug module in. Allows replacement without rework.
   - **Option B (production):** solder module directly — trim header pins to 3mm, insert through PCB holes or solder flat pads.
3. **L/R pin must connect to GND** — verify this connection with continuity check.
4. Ensure mic port on INMP441 module faces toward the PCB mic hole (bottom of pendant case).

### Step 7 — XIAO ESP32-S3 (U1)

> **Critical:** Solder this last. The XIAO has 14 castellated pads on each long side. Bridging any pair will kill the module.

1. Apply flux generously to all XIAO footprint pads on the PCB.
2. Place XIAO module — pin 1 (GPIO1) at the marked corner on silkscreen.
3. Tack 2 corner pads first (diagonal corners) to set alignment.
4. Solder each pad individually: touch iron to pad, apply minimal solder (0.3mm wire), remove iron.
5. Work from one end to the other — do not skip around.
6. **Common mistakes:** bridging adjacent pads, cold joints on castellated edges. Inspect every joint.
7. Post-solder: wipe flux residue with IPA + swab. Inspect all 14+14 pads under magnification.
8. Continuity check: adjacent pins should NOT be shorted. Check: 3V3 to GND = open. 5V to GND = open.

---

## 6. Pre-Battery Continuity Checks

Before connecting any power:

| Check | Expected | Method |
|-------|----------|--------|
| 3V3 to GND | Open (no short) | DMM resistance — should be >10kΩ |
| 5V to GND | Open (no short) | DMM resistance |
| I2S_BCLK (GPIO6) | Connected to MIC1 SCK | DMM continuity beep |
| I2S_LRCK (GPIO7) | Connected to MIC1 WS | DMM continuity beep |
| I2S_DATA (GPIO8) | Connected to MIC1 SD | DMM continuity beep |
| LED_DATA (GPIO4) | Connected to R5 → LED1 DIN | DMM continuity beep |
| BATT_ADC midpoint | 100kΩ to BATT_P, 100kΩ to GND | DMM resistance ~100kΩ each way |
| MIC1 L/R | Shorted to GND | DMM continuity beep |
| U2 IN+ | Connected to USB-C VBUS pad | DMM continuity |
| U2 OUT+ | SW_PWR common pin | DMM continuity |

---

## 7. First Power-On Test

**Do not connect the LiPo battery before completing Step 6.**

### 7a. USB-C Power Test (TP4056 only)

1. Slide SW_PWR to OFF position.
2. Connect USB-C cable to a 5V/1A charger (no computer — charger only for this test).
3. **Expected:** TP4056 red CHRG LED illuminates. No smoke. No excessive heat on U2.
4. Measure: BATT_P rail voltage should rise slowly as C5/C6 charge (should read ~5V briefly, then TP4056 settles to 4.2V charge voltage).
5. Disconnect USB-C.

### 7b. LiPo Connection

1. Confirm cell voltage with DMM before connecting: should read 3.5–4.2V.
2. Match polarity: red wire to BT1 + pad, black wire to BT1 – pad.
3. Apply small amount of solder to hold wires. Use Kapton tape as strain relief near connector.
4. **Do not use JST connectors unless footprint is present** — for prototype, direct solder.

### 7c. MCU Power-On

1. With USB-C connected OR battery connected:
2. Slide SW_PWR to ON.
3. **Expected:** XIAO onboard LED blinks once on boot.
4. Connect to USB-C from computer. Open serial monitor at 115200 baud (PlatformIO or Arduino IDE).
5. **Expected serial output:**
   ```
   Anticipy v1.0.0
   NVS: no WiFi credentials stored
   LED: init OK
   I2S: init OK (GPIO6=BCLK, GPIO7=LRCK, GPIO8=DIN)
   VAD: threshold=300 RMS
   BLE: advertising as "Anticipy-Pendant"
   ```
6. If no serial output: check XIAO solder joints with magnification.

### 7d. Functional Tests

| Test | Procedure | Pass Criteria |
|------|-----------|---------------|
| LED | Run `led_test` firmware | All 8 colors cycle, no stuck pixel |
| Microphone | Serial monitor + speak near mic | "VAD: speech detected" prints within 0.5s |
| Button A | Single tap SW1 | Serial: "BTN_A: tap" |
| Button A hold | Hold SW1 3+ seconds | LED goes rainbow cycle |
| Battery ADC | Serial monitor | Battery voltage printed every 30s, ±0.1V of DMM reading |
| WiFi | BLE provision via app | Device connects, gets IP, serial shows IP |
| Upload | Double-tap SW1 | Serial: "HTTP 200" after upload |
| BLE | Hold SW1 3s | "Anticipy-Pendant" visible in phone Bluetooth scan |
| Charging | Plug USB-C while powered | TP4056 CHRG LED on; serial: "charging" |
| Deep sleep | Idle 10 min | LED off, current < 1 mA on bench supply |

---

## 8. Flux Cleanup

After all tests pass:

1. Apply IPA 99% to all soldered areas with a flux brush or swab.
2. Scrub gently to remove flux residue.
3. Allow to dry completely (5 minutes) before final assembly into case.
4. **Do not use water-based cleaners** — they can wick under XIAO module and cause corrosion.

---

## 9. Quality Gate

Unit passes QA if all items below are checked:

- [ ] All 10 functional tests in §7d pass
- [ ] No flux residue visible under magnification
- [ ] XIAO castellated pads all soldered, no bridges
- [ ] SK6812 LED cycles all colors correctly
- [ ] TP4056 charges cell to 4.2V and terminates
- [ ] Slide switch toggles power cleanly
- [ ] Both tactile buttons register in firmware
- [ ] Voltage divider reads correct battery voltage (±0.1V)
- [ ] Serial log shows clean boot, no error messages
- [ ] BLE advertising visible from 5+ meters

Failed units: rework and retest. If rework > 2 attempts, scrap the XIAO module and replace.

---

## 10. Case Assembly

After QA pass:

1. Thread lanyard through 4mm hole in top of front shell before inserting PCB.
2. Insert PCB into front shell: XIAO USB-C port aligns with bottom cutout, SW_PWR faces the side cutout, MIC1 faces the bottom mic port hole, LED1 diffuser window aligns with LED channel.
3. Route battery flat under PCB on the foam pad in the back plate.
4. Snap back plate onto front shell. Finger-tight pressure is sufficient for prototype.
5. Optional: 4× M1.4 screws into screw bosses for production-grade closure.
6. Final visual: USB-C port accessible, slider switch operable, button dimples aligned, LED glow visible through diffuser window.

---

## 11. Packaging for Shipment

See `firmware/PACKAGING.md` for box dimensions, branding, and included accessories.

Each unit ships in:
- Custom kraft box (see PACKAGING.md)
- Unit wrapped in foam sheet
- USB-C charging cable (0.5m, braided)
- Quick-start card (double-sided, 90×55mm)
- Lanyard (pre-threaded)
- Anti-static poly bag (inner wrap)
