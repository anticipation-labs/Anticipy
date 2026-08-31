# Anticipy R1 — First-Article Bring-Up Checklist

Tools: bench PSU or USB-C cable, multimeter, J-Link (or nRF52-DK as debugger),
Tag-Connect TC2030-IDC-NL cable, nRF Connect on a phone.

## 1. Visual / pre-power

- [ ] Inspect U1, U2, U6, MK1/MK2 solder joints under magnification.
- [ ] Check mic port holes (under MK1/MK2) are open, no flux/paste.
- [ ] Meter in continuity mode: **no short** GND↔VBUS_5V, GND↔VSYS, GND↔+3V3, GND↔VBAT.

## 2. Power (no battery yet)

- [ ] Plug USB-C. Measure VBUS_5V ≈ 5.0 V, VSYS ≈ 4.4–5.0 V, +3V3 = 3.3 V ± 3%.
- [ ] Current draw < 30 mA idle (unprogrammed).
- [ ] nPGOOD (U2 pin 7) reads low with USB present.

## 3. Battery path

- [ ] Unplug USB. Connect battery to J2 (verify pinout VBAT/NTC/GND matches pigtail!).
- [ ] +3V3 still 3.3 V from battery.
- [ ] Replug USB: charge current flows (≈150 mA into battery, set by R3 11k on ISET);
      red charge behavior visible via nCHG_STAT low.

## 4. Programming (SWD via J4 Tag-Connect)

- [ ] `nrfjprog --recover` succeeds (or `probe-rs erase`).
- [ ] Flash a blinky targeting LED_RED P0.17 / LED_BLUE P0.19 — both LEDs work.
- [ ] Flash test firmware; verify over RTT/serial.

## 5. Peripheral tests (test firmware)

- [ ] SPI flash: read JEDEC ID = `C2 20 19` (MX25L25645G, 256 Mbit / 32 MB). Addressing is 4-byte above 128 Mbit: use EN4B (0xB7) or the 4-byte opcodes (0x13 read, 0x12 page program, 0xDC block erase).
- [ ] Accelerometer: I2C addr 0x18 WHO_AM_I = `0x33` (LIS2DH12); INT1 fires on tap.
- [ ] Both PDM mics: record 2 s, check both channels show audio, no rail noise.
- [ ] Button: BTN P1.06 reads low when pressed.
- [ ] Haptic: HAPTIC_EN P0.20 high spins motor on J3; no VSYS droop reset.
- [ ] VBAT_SENSE (P0.29/AIN5) ADC reading = VBAT/2 ± 5%.
- [ ] USB: enumerate as device (CDC test app).

## 6. BLE / RF

- [ ] Advertise; phone sees it at ≥ 3 m through a wall (crude antenna sanity check).
- [ ] Connection stable for 10 min streaming test data.

## 7. Final integration

- [ ] Battery into bay, motor into pocket, PCB onto shelf (USB aligned with cutout).
- [ ] Close faces; button actuates through front hole; mics not occluded.
- [ ] Full charge-discharge cycle inside the closed enclosure (thermal sanity).

Any failure at step 2–3 → stop, do not connect battery until root-caused.
