# Anticipy R1 — Manufacturing Package & Order Instructions

Digital package for a rush (48h-class) build at any capable local PCB/PCBA vendor
(e.g. CCI Canadian Circuits, Enigma, or JLCPCB/PCBWay for lowest cost).

## What's in this package

| Path | What it is | Who it goes to |
|------|-----------|----------------|
| `pcb/anticipy_r1.kicad_sch` / `.kicad_pcb` | Editable KiCad 9 sources | Reviewing engineer |
| `fab/anticipy_r1_gerbers.zip` | Gerbers (4 copper layers) + Excellon drills | PCB fab |
| `fab/assembly/anticipy_r1_bom.csv` | BOM with manufacturer part numbers | Assembly house |
| `fab/assembly/anticipy_r1_cpl.csv` | Pick-and-place (Top/Bottom, mm) | Assembly house |
| `fab/assembly/assembly_front.pdf` / `assembly_back.pdf` | Assembly drawings | Assembly house |
| `fab/anticipy_r1_pcba.step` | 3D model of assembled board | Mechanical review |
| `enclosure/out/pc_center.3mf` / `.stl` / `.step` | Polycarbonate center frame | Bambu printer (yours) |
| `enclosure/out/alu_face_front.dxf` / `alu_face_rear.dxf` | 0.8 mm 5052 aluminum face profiles | Metal/laser shop |
| `enclosure/out/enclosure_assembly.step` / `enclosure_exploded.step` | Full enclosure model | Mechanical review |

## PCB fabrication spec (tell the fab this)

- 4-layer FR-4, finished thickness **0.8 mm**
- Stackup: F.Cu (signal) / In1.Cu (GND) / In2.Cu (+3V3) / B.Cu (signal+GND), standard 0.8 mm 4L stackup
- Finish: **ENIG** (fine-pitch QFN + LGA parts)
- Min trace/space used: 0.127 mm / 0.127 mm; min via 0.5 mm pad / 0.25 mm drill
- Solder mask both sides, silkscreen both sides
- Board outline 47 x 18 mm, rounded corners (in Edge.Cuts)

## Assembly notes

- Double-sided SMT. Reflow both sides (BOM parts are all reflow-safe).
- U2 (BQ24075, VQFN-16) and U6 (LIS2DH12, LGA-14) need good paste/stencil control.
- MK1/MK2 (Knowles SPH0641LU4H-1) are **bottom-port mics**: the port holes in the
  PCB must stay free of paste/flux — flag to the assembler.
- J4 (Tag-Connect TC2030-IDC-NL) is **bare pads, no part to place** — remove from
  any auto-quoted BOM line; it is programming pads only.
- DNP: none. Everything in the BOM is placed.

## Parts you order separately (not on the PCBA)

- Battery: **EEMB LP451235** — 150 mAh LiPo, 4.5 x 12 x 35 mm, MUST be ordered
  with protection circuit + 10k NTC + JST SH 3-pin pigtail (VBAT / NTC / GND).
  Alternate: EEMB LP401230 (105 mAh).
- Haptic motor: 8 mm x 3.4 mm ERM coin, 3 V (e.g. Seeed/Jinlong Z4TL2B0640001),
  terminated in JST SH 2-pin.
- Tag-Connect TC2030-IDC-NL cable (one-time purchase, for programming).

## Enclosure

- PC center: print `pc_center.3mf` on the Bambu in polycarbonate (or PETG for a
  first fit-check). 0.1 mm layers, 100% perimeter walls preferred.
- Aluminum faces: send both DXFs to a laser/waterjet shop, 0.8 mm 5052, brushed
  finish. Front face has mic ports (2x 1.2 mm), button hole (4.2 mm) and LED
  window (1.6 mm); rear is plain.
- Faces glue into the recessed lips of the PC center (VHB tape or epoxy).
- The antenna end of the PCB sits under the PC-only end (no metal above the
  MDBT50Q antenna); do not extend the aluminum faces.

## Order sequence (48h-class rush)

1. Send `anticipy_r1_gerbers.zip` + BOM + CPL + assembly PDFs to the fab/assembler,
   request 24h fab + 24h assembly rush quote, quantity 2–5.
2. Order battery + motor + TC2030 cable same day (digikey/mouser stock parts).
3. While boards are being made: print the PC center, order/cut aluminum faces.
4. On arrival: bring-up per `BRINGUP.md`, then final integration.

## MUST-review engineering gates before paying for fab

A human EE should spend ~1 hour on these; they are the known risk areas:

1. **Charger architecture**: design uses TI BQ24075 (power-path charger) + AP2112K
   LDO instead of the originally discussed Nordic nPM1300 (no usable KiCad symbol
   was available). Confirm this substitution is acceptable.
2. **BQ24075 layout** vs TI datasheet reference layout (ISET/ILIM resistor Kelvin
   routing, thermal pad stitching).
3. **Antenna keepout**: MDBT50Q antenna end has a copper keepout on all 4 layers;
   verify against Raytac's layout guide, and keep metal enclosure parts away.
4. **Battery**: confirm exact LP451235 dimensions/connector orientation against
   the enclosure battery bay (35.5 x 12.5 x 4.7 mm pocket) before ordering.
5. **USB-C/ESD routing** and mic port acoustics (bottom-port hole stack).
6. Vendor DFM report — accept their feedback before release to fab.

First 1–2 boards are **first articles**: they must pass the bring-up checklist
before building more.
