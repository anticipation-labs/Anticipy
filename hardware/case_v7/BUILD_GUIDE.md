# Case v7 — print + wiring + assembly

Hardware per unit: XIAO nRF52840 Sense (headers clipped flush), 502030
250 mAh LiPo, W25Q128 SPI-flash breakout (or microSD SPI module), 10 mm coin
vibration motor, 6×6 side-stem tactile switch, S8050/2N2222 NPN, 1N4148,
1 kΩ resistor, 28 AWG silicone wire, SS-12D10 slide switch (optional).

## 1. Print (files in `stl/`)

| File | Part | Orientation |
|---|---|---|
| `front_v7.stl` | Domed front (mic grille, button hole, LED window, USB slot half) | exported cavity-up — print as-is |
| `back_v7.stl` | Flat back lid with integral tongue | cavity-up as exported |

Settings (P2S, from v5/v6 print-proven runs): PETG Pro for battery-carrying
units (never PLA against skin/heat), 0.12 mm layers, 4 walls, 40 % infill, no
supports, seam rear, slow outer wall. Lip clearance is the coupon-tuned 0.30
(friction bias −0.05). Too tight → scale lid 99.5 % XY; loose → 100.5 %.

Titanium wave: upload the same two STLs to JLC3DP, material SLM Ti (TC4),
sandblasted finish, note ±0.3 mm — order one test set before the batch and
re-check the lip fit; Ti may need `LID_CLR = 0.40` re-export.

## 2. Wiring (nets, XIAO pin names)

| Net | XIAO pin | Notes |
|---|---|---|
| BAT+ | BAT+ pad (underside) | via slide switch if fitted |
| BAT− | BAT− pad | |
| Button | D1 → switch → GND | internal pull-up in firmware |
| Haptic | D3 → 1 kΩ → NPN base; motor 3V3→collector; emitter→GND; 1N4148 flyback across motor |
| SPI flash / SD | CS→D2, SCK→D8, MOSI→D10, MISO→D9, VCC→3V3, GND→GND |
| Mic / LED / IMU / charger | onboard | |

## 3. Soldering order (zero-failure, from proto v1 guide)

1. Clip header pins flush; clean pads.
2. Wire SPI flash/SD module flat (14 mm leads), then button, then motor driver.
3. Tape battery leads apart — never let them touch.
4. Tin BAT pads, solder wires board-first, Kapton over joints.
5. Multimeter polarity check, then connect the cell.
6. Flash firmware over USB-C **before** closing the case.

## 4. Assembly

Board into the USB-end bay (USB-C aligned to the 15.0 × 8.6 slot, mic under
the 7-hole grille, button stem through the 4.2 mm hole). Cell into the long
bay with 1 mm foam both faces; flash breakout then coin motor flat on top of
the cell (VHB tape), wires over the lip gap. Press the lid: tongue into
groove, pry notch at the USB end to reopen. Chain: 2.5–3 mm stainless chain +
5 mm jump ring through the 4.6 mm end hole.
