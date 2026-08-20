# Anticipy pendant v4 — true pebble clamshell

v4 exists because v3 fixed mechanics but lost the product's shape. v4 goes
back to the real Anticipy form: a continuous-curvature pebble, board stacked
over battery, seam hidden in the side profile.

## REQUIRED PREP (non-negotiable)
Clip the header pins flush off the XIAO with flush cutters (~2 min, no
soldering). No pendant-shaped object can contain 9 mm pins.

## Sizes (OpenSCAD echo)
- 200 mAh: 49.1 × 27.3 × 18.6 mm
- 500 mAh: 62.1 × 27.3 × 21.1 mm

## Parts per pendant
- `front_XXXmah.stl` — dome with mic hole (1.2 mm), LED dot (2 mm), USB-C
  slot in the end wall, board bay + corner posts.
- `back_XXXmah.stl` — dome with battery bay.
- `ring_XXXmah.stl` — seating ring: glue into the BACK half's rim groove,
  it presses into the FRONT half's groove. Two M1.4 screws through the back
  into the solid chain end keep it locked and reopenable.
- `ring_coupon.stl` — fit test: bar + three slots (0.15 / 0.25 / 0.35 mm).

## Print order — do NOT skip
1. `ring_coupon.stl` (~10 min). Push the bar into each slot. The snuggest
   slot that still fully seats = set `LID_CLR` in the .scad to that number,
   re-export the front.
2. ONE `front_200mah.stl` + `back_200mah.stl`. Drop the real board
   (pins clipped) and battery in. Check: board sits on posts, USB-C cable
   reaches through the slot, battery + wires close freely.
3. Only after step 2 passes: ring, screws, second unit, 500 version.

## Print settings (P2S, silk PLA)
- Both halves print rim-down / dome-UP as exported: zero supports, no plate
  texture on any visible surface.
- 0.12 mm layers for the visible domes; ring/coupon at 0.20 mm.

## Honest status
Renders verify geometry only. Battery dimensions are estimated from photos
(no calipers available) — the fit-check print in step 2 is the real test.
Mic/LED positions assume the XIAO's PDM mic and user LED under the front
dome; verify against the actual board during step 2.
