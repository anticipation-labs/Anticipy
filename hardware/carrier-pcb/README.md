# Anticipy V1 carrier PCB

53.0 × 19.5 mm, 2-layer board that turns each unit from ~45 min of hand-wiring
into ~10 min of soldering: drop the XIAO nRF52840 Sense onto the 14 header
pads, everything else is already on the board.

## What's on it
| Ref | Part | Job |
|---|---|---|
| U1 | XIAO nRF52840 Sense (module, 2×7 pins 2.54 mm) | brain / BLE / mic / charger |
| U2 | W25Q128JVSIQ (SOIC-8) | 16 MB offline backlog flash |
| Q1 | S8050 (SOT-23) | haptic motor low-side driver |
| R1 | 1 kΩ 0805 | base resistor |
| D1 | 1N4148W (SOD-123) | motor flyback diode |
| C1 | 100 nF 0805 | flash decoupling |
| J1 | 4 wire pads | BTN1/BTN2 (side button), MOT+/MOT− (coin motor) |

Battery: solder the 502030 cell leads directly to the XIAO underside BAT+/BAT−
pads (charging stays on the XIAO's built-in charger). The cell tapes over the
bare right half of this board.

## Nets
GND zone on F.Cu, 3V3 zone on B.Cu. Signals: D1=BTN, D2=CS, D3=HAP_CTRL,
D8=SCK, D9=MISO, D10=MOSI — matches `../case_v7/BUILD_GUIDE.md`.

## Files
- `generate_carrier.py` — regenerates everything (KiCad 6 pcbnew scripting)
- `anticipy_carrier.kicad_pcb` — the board (open in KiCad)
- `drc_report.txt` — **0 violations, 0 unconnected pads** (KiCad 6 DRC)
- `gerbers/` — fab-ready Gerbers + Excellon drill files (zip this folder and
  upload to jlcpcb.com; 2-layer, 1.6 mm, HASL, any color)
- `render/` — copper renders (front / back)

## Status — honest
- DRC-clean and fully routed: YES (electrically verified in software).
- Physically fabbed and tested: NO — order 5 from JLCPCB (~$4 + ship,
  24–48 h fab) and bring one up before committing the batch to it.
- Week-1 unit does NOT need this board (6 hand-soldered wires per the build
  guide); it's for the 12-unit customer batch.
- W25Q128 = 16 MB ≈ 6–8 h of VAD-gated speech. If a guaranteed 20 h
  continuous backlog is required, swap U2 for a microSD socket rev (same SPI
  nets, footprint change only).
