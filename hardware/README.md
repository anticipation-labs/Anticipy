# Anticipy Hardware V1 — end-to-end build package

Goal: Anticipy-branded always-on pendant. Streams audio to iPhone over BLE,
records offline to flash when the phone is away (20 h backlog), back-syncs on
reconnect, 16 h+ speaking-time battery, VAD, side button, haptic feedback.
First units hand-assembled (week 1), customer wave (week 2).

## Contents

| Path | What |
|---|---|
| `case_v7/` | Pendant case v7 "Plaud envelope" — parametric SCAD, print-ready STLs, render |
| `case_v7/BUILD_GUIDE.md` | Print settings, wiring, soldering order, assembly |
| `firmware/README.md` | Omi-fork firmware plan: build target, haptic patch, flash procedure |
| `ORDERING.md` | Exact carts (RobotShop, Amazon.ca, JLC3DP, Apple) with prices |
| `EXECUTION_PLAN.md` | Day-by-day 2-week schedule, costs, risks, compliance |
| `qa/QA_CHECKLIST.md` | Per-unit acceptance test before a unit ships |

## Size target vs. reality (stated straight)

Reference: Plaud NotePin 51 × 21 × 11 mm; +15% margin = **58.7 × 24.2 × 12.65 mm**.

v7 measures **67.9 × 26.3 × 12.8 mm** (STL-verified). Thickness hits the
envelope; width is 2 mm over; length is 9 mm over because an off-the-shelf
XIAO nRF52840 Sense (21 mm) must sit beside a 30.5 mm 250 mAh cell — physics,
not laziness. The true Plaud envelope requires the custom-PCB phase
(nRF52840-QIAA directly on the board, cell over the board), which is the
week-3+ V2 board. v7 is still Plaud-NotePin *class*: pill-shaped, domed,
chain-hung, under 13 mm thin.

## Architecture (decided)

- **MCU/radio/mic**: Seeed XIAO nRF52840 Sense (FCC modular approval
  Z4T-XIAONRF52840 — the only legal fast path to customer radios in 2 weeks).
  Onboard PDM mic, BLE 5, BQ25101 LiPo charger, USB-C.
- **Battery**: 502030 250 mAh LiPo → ~11–16 h streaming (est., must be
  measured on unit #1), ~30 h offline. Not validated yet — QA step 8.
- **Offline backlog**: W25Q128 16 MB SPI flash breakout (ADPCM 4 KB/s ≈ 70 min
  continuous; with VAD gating ≈ 6–8 h of real speech). For a guaranteed
  20 h continuous: substitute the microSD SPI module (same 4 SPI pins) —
  case has room; both wirings in the build guide.
- **Firmware**: fork of Omi (MIT) Zephyr firmware — BLE audio service,
  offline storage + back-sync, button events already implemented. We add
  haptics + Anticipy device name. See `firmware/README.md`.
- **App**: Omi's open-source Flutter app rebranded Anticipy on TestFlight
  (week 1: stock protocol-compatible app for bring-up).
- **Haptics**: 10 mm coin motor, NPN low-side driver on a GPIO.
- **Shells**: FDM (Bambu P2S, silver PETG Pro) for week-1 units; JLC3DP
  SLM titanium prints of the same STLs for the customer wave.
