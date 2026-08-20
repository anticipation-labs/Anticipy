# Pendant v3 — rebuilt from the failed-print photos

Every v2 failure, mapped to its v3 fix:

| What went wrong on the first print | v3 fix |
|---|---|
| Header pins too tall, nothing fit | Designed around the board **with headers on** (`PINS=true`, default). 9.2 mm pin stack measured from your photos. `_slim` variants exist only if you ever clip them. |
| No USB-C cutout | USB-C slot in the bottom edge on **every** variant, aligned to the board, with an outside chamfer so the plug self-finds. Charge without opening. |
| No lock, no tolerance | Two-step closure: lid panel sits flush in an outer rebate, a 2.4 mm lip seats deeper, plus 2 hidden M1.4 screws and a pry notch. Clearance is `LID_CLR` — print `tolerance_coupon.stl` (10 min), push the tab into the 0.15 / 0.25 / 0.35 sockets, snuggest that closes = your number. |
| Supports ruined the parts | Zero supports by design. Shell prints opening-down: vertical walls, top-only fillet, interior features hang off the walls, cavity roof bridges internally where nobody sees. |
| Plate texture on the visible face | Both parts print with the visible face UP. Only the lid's hidden underside and the shell rim touch the plate. |
| No wire room | Wire notch over the bay divider + 9 mm of open depth behind the board for the battery leads. |
| Sealed forever | Unscrew 2 screws, pry at the notch, everything comes out. |

## Parts (in `stl/`)
- `shell_200mah.stl` / `lid_200mah.stl` — 70 × 28 × 19 mm (headers on)
- `shell_500mah.stl` / `lid_500mah.stl` — 83 × 28 × 19 mm (headers on)
- `*_slim` — 12.8 mm thin versions **only if headers are clipped flush**
- `tolerance_coupon.stl` — print FIRST

## Print order (do not skip)
1. `tolerance_coupon.stl` — ~10 min. Find your `LID_CLR`.
2. `shell_200mah.stl` alone — ~35 min. Drop the real board (headers down, USB
   toward the slot) and battery in. Board's header plastic rests on the two
   internal ledges; pins hang free.
3. If both pass: regenerate lids with your `LID_CLR` if it isn't 0.25, then
   print the remaining parts. No supports, 0.20 mm, visible faces up
   (the STLs are already oriented — do not rotate them in the slicer).

## Assembly
Board goes in component-side first (USB toward the bottom slot, pins facing
you). Battery in its own bay, leads over the divider notch, soldered to the
BAT+/BAT− pads on the board's back. 1 mm foam on the lid presses everything
still. Lid on, 2× M1.4 screws through the side walls.

Verification renders: `check_200_long.png`, `check_200_cross.png` (mock
board + headers + battery inside the closed case), regenerate with `check_v3.scad`.
