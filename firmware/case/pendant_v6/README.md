# Anticipy Pendant v6 — multi-mechanism comparison set

Same print-proven v5.1 pill body (the geometry that finally printed with solid
walls), with the closure system redesigned and THREE mechanisms to compare
physically. The separate glued seating ring is gone.

## What changed vs v5.1
- **Integral lip (tongue-and-groove)**: the back half carries a 1.2 mm lip that
  seats into a matching groove in the front half. No separate ring part, no glue,
  self-aligning in both axes. Clearance `LID_CLR` comes from the printed coupon.
- **Three closures (MECH)**:
  - `friction` — plain lip with a 0.10 mm tighter (coupon-tuned) clearance.
    Clean press-together fit, no tiny snap features to fuzz or wear; open with
    a coin/thumbnail in the pry notch at the USB end.
  - `magnet` — lip for alignment + 2 pairs of 5×2 mm disc-magnet pockets in the
    solid chain end (glue in with CA, alternate polarity so it self-aligns).
    Silent, infinite reopen, zero wear.
  - `screw` — lip + 2 hidden M1.4×4 screws from the back into the solid chain
    end (counterbored, invisible when worn). Most secure.
- **USB-C opening enlarged to 14.0 × 8.0 mm** (research: real cable overmolds
  measure up to 13.0 × 7.4 mm and are often off-center — the old 12.6 × 7.0 slot
  could reject some cables), with a 1.2 mm chamfered lead-in at the outer face
  so the opening edge prints crisp instead of fuzzing.
- **Pry notch** at the seam on the USB end of every variant.
- Chain: NOT printed. A 4.5 mm through-hole in the solid top end takes any
  2.5–3 mm necklace chain.

## Sizes
| Variant | Battery | Outer (L × W × T mm) |
|---|---|---|
| 200 | 31×20.5×6.0 (250 mAh class) | 54.9 × 27.7 × 20.2 |
| 500 | 44×20.5×8.5 (500 mAh class) | 67.9 × 27.7 × 22.7 |

Front bay: board (21.0 × 17.8, headers CLIPPED FLUSH, 6.6 mm stack) pressed
against the USB end wall. Back bay: battery. Wire/tab room: the cavity is
2.5 mm longer and 1.2 mm wider than the largest component, plus the full lip
gap at the seam for wire pass-over.

## Files (stl/)
`front_<batt>_<mech>.stl`, `back_<batt>_<mech>.stl` for batt ∈ {200,500},
mech ∈ {friction,magnet,screw}, plus `lip_coupon.stl` (0.15/0.25/0.35 clearance
slots — press a lip edge in, pick the snug one, set `LID_CLR`).

`front_<batt>_<mech>_pins.stl` — headers-ON variants: the front bay is 9 mm
deeper so unclipped header pins (pointing up into the dome) clear; the board
still sits at the parting plane so the USB opening lines up. Back halves are
identical between pins/no-pins, so any back mates with either front.

## Verification done on the exported STLs (not renders)
- All 19 meshes watertight (13 base + 6 headers-on fronts).
- Layer-by-layer cross-section audit at 0.12 mm steps: nominal walls ≥ 1.0 mm.
  Local sub-mm readings exist at the chain-hole exit rims through the domed
  faces — the tangent crescent any through-hole makes exiting a curved surface;
  identical geometry printed solid in the v5.1 gated print. This audit is a
  mesh check, not physical proof — final confirmation is the printed parts.
- Magnet pockets verified to clear the groove (0.8 mm wall), the chain hole
  (>0.8 mm), and the exterior (>1.1 mm).

## Plate file
`plate_v6_all13.3mf` (name is historical) now contains all **19** parts:
12 base shells + coupon + 6 headers-on fronts, sliced 0.12 mm / 3 walls with
5 mm outer brims, 65 °C textured-PEI bed, 20 mm/s first layer (silk-PLA
adhesion fixes after two failed plate attempts).

## Print settings (Bambu P2S)
- 0.12 mm layers, 3 walls, 4 top/5 bottom shells, 15 % gyroid infill
  (shells are mostly walls; infill matters only in the solid chain end —
  gyroid there gives the chain hole its strength).
- NO supports (supports scar the visible faces). Both halves print rim-down /
  visible dome UP.
- The USB slot prints as a short bridge — fine without support.
- Silk PLA works; PETG better for daily wear.

## Still only provable with plastic + real parts
Exact battery body/tab size, real cable overmold, printer clearance, friction
grip force, magnet grip. That is what this comparison plate is for:
print, try all three closures with the real board/battery/cable, pick the
winner.
