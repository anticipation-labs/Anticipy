# Anticipy — One-Click Manufacturing Order Guide

## How This Works
Everything below is pre-configured. You upload files, confirm the quote, pay, and a sample ships to West Vancouver in ~7 days. You never assemble anything.

---

## Step 1: Order PCBs + Assembly from JLCPCB

**URL:** https://cart.jlcpcb.com/quote

**Upload these files:**
- `firmware/pcb/anticipy.kicad_sch` → export as Gerber (use KiCad "Plot" → Gerber format)
- BOM file (generated from schematic)
- Component Placement List (CPL)

**Settings to select:**
- Layers: 2
- PCB Qty: 5 (for samples)
- Board dimensions: 30 × 20 mm
- Surface finish: HASL (lead-free)
- Assembly: Yes, turnkey
- Assembly side: Top
- Qty to assemble: 5

**Estimated cost:** ~$30–50 USD for 5 assembled boards

---

## Step 2: Order 3D Printed Cases from JLCPCB

**URL:** https://jlcpcb.com/3d-printing

**Upload:** `firmware/case/anticipy_pendant.scad` → export as STL from OpenSCAD first

**Settings:**
- Material: PETG (or SLA resin for smoother finish)
- Color: Black
- Qty: 10 (5 tops + 5 bottoms)
- Finish: Standard

**Estimated cost:** ~$15–30 USD for 10 pieces

**For titanium-look premium samples:** Order from Shapeways or Xometry in titanium or anodized aluminum:
- https://www.shapeways.com/ — titanium milling
- https://www.xometry.com/ — CNC aluminum, anodized titanium finish

---

## Step 3: Order Components (not on JLCPCB)

These ship separately — order from Amazon.ca for fastest delivery to West Vancouver:

| Component | Link | Price CAD | Qty |
|-----------|------|-----------|-----|
| XIAO ESP32-S3 | seeedstudio.com/XIAO-ESP32S3-p-5627.html | $10.33 | 5 |
| INMP441 mic (5-pack) | amazon.ca search "INMP441" | ~$8 | 1 pack |
| TP4056 USB-C charger (10-pack) | amazon.ca search "TP4056 USB-C" | ~$10 | 1 pack |
| 400mAh LiPo battery (5-pack) | amazon.ca search "3.7V 400mAh LiPo JST" | ~$15 | 1 pack |
| SK6812 LED (10-pack) | adafruit.com/product/4960 | ~$5 | 1 pack |

**Total components:** ~$48 CAD for 5 prototype kits

---

## Step 4: Final Assembly Service

**Option A — JLCPCB assembly includes SMT.** Through-hole components (battery connector, mic breakout) need hand soldering. Request "hand soldering" add-on at checkout ($3.50 + $0.0173/joint).

**Option B — Use PCBWay's box build service** (they assemble PCB into case with battery):
- https://www.pcbway.com/pcb-assembly.html
- Request "box build" and provide assembly instructions (firmware/pcb/ASSEMBLY.md)

**Option C — Bittele Electronics (Toronto, Canada):**
- https://www.7pcb.com/
- Ship all components to their Toronto facility
- They assemble, test, flash firmware, ship finished units to you
- 5–10 day turnaround

---

## Step 5: Firmware Flashing

**Before shipping assembled boards, the manufacturer flashes firmware:**

Provide the manufacturer:
1. `firmware/` directory as a zip
2. Instructions: "Install PlatformIO, run `pio run`, flash via USB-C with `pio run --target upload`"

**Or flash yourself on receipt:**
```bash
cd firmware
pio run --target upload  # plugs into USB-C, takes 30 seconds
```

---

## Step 6: Packaging

**Order custom boxes from:**
- https://www.packlane.com/ — custom printed boxes, qty 10+, ~$5-8/box
- https://www.noissue.co/ — eco-friendly startup packaging
- https://www.arka.com/ — custom mailer boxes from 10 units

**Box specs (from PACKAGING.md):**
- Outer: 80 × 60 × 35 mm matte black rigid box
- Gold foil "ANTICIPY" logo on lid
- Inner: foam insert with device cutout
- Includes: USB-C cable, quick start card

---

## Step 7: Ship to Fulfillment Center

**ShipBob Surrey, BC** (30 min from West Vancouver):
- https://www.shipbob.com/
- They receive packages from manufacturer
- Store inventory
- Ship to customers on demand

**Setup:** Create ShipBob account → add SKU → provide manufacturer shipping details → they handle the rest

---

## Total Cost Per Sample Unit

| Item | Cost USD |
|------|----------|
| PCB + assembly (JLCPCB) | ~$8 |
| 3D printed case | ~$3 |
| Components (ESP32, mic, battery, etc.) | ~$15 |
| Packaging box | ~$6 |
| Shipping to you | ~$5 |
| **Total per unit** | **~$37 USD (~$51 CAD)** |

**For titanium/aluminum CNC case:** Add ~$30-80/unit depending on finish

---

## Quick Start: Get a Sample in 7 Days

1. Go to jlcpcb.com → upload Gerber + BOM → order 5 assembled boards (~$40)
2. Go to jlcpcb.com/3d-printing → upload STL → order 10 case halves (~$20)
3. Go to seeedstudio.com → order 5× XIAO ESP32-S3 ($37)
4. Go to amazon.ca → order INMP441 + TP4056 + battery + LED packs (~$38 CAD)
5. Everything arrives in 5-7 days
6. Flash firmware via USB-C (30 seconds per unit)
7. Snap into case, done

**Or for zero-touch:** Send all files to Bittele (7pcb.com) and they do everything including assembly, flashing, and shipping to you.
