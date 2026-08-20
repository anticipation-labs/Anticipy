# Anticipy pendant — v5 (stadium pill, matches website product)

v5 rebuilds the exterior as the actual Anticipy silhouette: a vertical
stadium/pill (parallel sides, semicircular ends), soft-domed faces, chain
hole through the solid top end, one LED dot + one pinhole mic on the front.
See `v5_side_by_side.png` for the render vs the website product.

## Sizes (echoed by the CAD)
- 200 mAh: 49.5 × 27.7 × 18.2 mm
- 500 mAh: 62.5 × 27.7 × 20.7 mm

## Verification status — be honest about what is proven
- CAD/render-verified: silhouette, wall thickness, cavity vs board+battery
  mocks (`check_v5.scad`, long + cross sections), USB slot reach, chain-hole
  wall, ring/screw geometry.
- Physically UNVERIFIED until the fit-check print: real battery size
  (200 mAh assumed 31×20.5×6, 500 mAh 44×20.5×8.5), your cable's overmold
  (slot is 12.6×7.0), printer clearance (coupon decides `LID_CLR`).

## Required prep
- Clip the XIAO header pins flush (2 min, flush cutters). Non-negotiable —
  9 mm pins cannot live inside an 18 mm pendant.

## Interior (flat open planes — no posts, no blocks)
- Front half: one flat bay; the board lies component-side-up, USB-C pressed
  against the end wall so a plug can reach it. A 1 mm foam pad above the
  board holds it.
- Back half: one flat bay for the battery; wire/tab relief along the seam.

## Closure
- Gold seat ring glues into the BACK half, presses into the FRONT half with
  clearance `LID_CLR` (default 0.25) + 2 hidden M1.4×4 screws from the back.
- Print `stl/ring_coupon.stl` first (~10 min); the tightest slot the tab
  seats in = your `LID_CLR`. Re-export fronts with that value.

## Print (Bambu P2S, Silk Silver PLA)
- Both halves print seam-face DOWN → all visible surfaces face up,
  zero supports, no plate texture on anything you see.
- 0.12 mm layer height for the silk finish.

## Print order — do not skip the gate
1. Coupon → pick `LID_CLR`.
2. One 200 mAh front+back+ring → drop in the REAL board (pins clipped) and
   REAL battery, check USB plug, wires, closure, chain.
3. Only after that passes: the 500 mAh / final set.

## Files
- `anticipy_pendant_v5.scad` — source (PART = front|back|ring|coupon|both,
  BATT = 200|500)
- `check_v5.scad` — cutaway verification scene with hardware mocks
- `stl/` — front/back/ring for both batteries + ring_coupon
