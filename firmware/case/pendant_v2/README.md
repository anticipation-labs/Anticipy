# Pendant v2 — capsule design (matches the anticipy.ai renders)

v1 was a box with a bolted-on lug. v2 is the actual product shape: a flattened pebble
capsule with fully rounded edges, an **integrated chain through-hole** in the solid top
end (no lug, no loop part, nothing to snap off), one LED dot + one discreet mic hole on
the front, and the seam hidden on the back face. Closure is a press-fit lip **plus two
M1.4 self-tapping screws** through the side walls — it cannot pop open.

## Why v1 failed (honest answers)

1. **Too clunky/bulky** — it was sized for the board *with 9 mm headers still soldered
   on*. v2 assumes you clip/desolder the headers (2-minute job with flush cutters +
   solder wick), which removes 8+ mm of thickness, and stacks board-on-battery instead
   of leaving dead air.
2. **Snap lid wouldn't stay shut** — a friction lip alone in PETG relaxes over time.
   v2 keeps the lip for alignment but adds two hidden side screws for real retention.
3. **It was a square box** — flat faces, straight walls, right-angle silhouette. v2 is a
   minkowski-rounded capsule: every edge has a 4.5 mm radius, like the renders.
4. **Loop system didn't work** — a thin printed lug with a cross-hole is the weakest
   possible chain mount. v2 drills the chain hole straight through the solid rounded end
   of the body (5 mm dia, chamfered both sides) — the strongest printable attachment,
   and exactly what the website product does.

## Variants (32 STLs = 16 configs × shell+back)

Filename grammar: `shell|back` + `_200mah|_500mah` + `[_storage]` + `[_haptic]` + `[_usb]`

| Axis | Options | Notes |
|---|---|---|
| Battery | `200mah` (502025) / `500mah` (752042) | 200 = 40×25×16 mm body; 500 = 58×25×19 mm |
| Storage | with/without | pocket in the back for a W25Q128 16 MB SPI flash breakout — this is the 4–8 h offline buffer |
| Haptic | with/without | pocket for a 10×2.7 mm 1027 coin vibration motor (3V7 → motor via a 2N7002/S8050 on D2) |
| USB | with/without | bottom USB-C slot; without = perfectly clean body, open the back to charge |

**Recommended first print:** `shell_200mah.stl` + `back_200mah.stl` — the smallest,
cleanest unit ("plug one thing in" = USB-C after opening the back; nothing else to wire
except the battery).

**Recommended demo-day unit:** `shell_500mah_storage_usb.stl` + matching back — 3-day
battery, 4–8 h offline audio, charge without opening.

## Storage, made stupidly simple

One part: a W25Q128 breakout (~$10, Amazon.ca search `W25Q128 spi flash module`). Four
wires to the XIAO: VCC→3V3, GND→GND, CLK→D8, DO→D9, DI→D10, CS→D7. It drops into the
pocket printed in the `_storage` back covers. Firmware ring-buffers compressed audio to
it while offline, drains over BLE on reconnect. Without it you still get ~4 minutes of
offline buffer from the XIAO's onboard 2 MB flash.

## Hardware to order (all Amazon.ca searches)

- 502025 200 mAh 3.7 V LiPo with protection — `502025 lipo battery 200mah`
- M1.4×5 self-tapping screws — `M1.4 self tapping screws laptop`
- 1027 coin vibration motor — `10mm coin vibration motor 3v`
- Everything else: see `../proto_nrf52840/BUILD_GUIDE.md` (wire, foam, Kapton, chain).

## Print

PETG silver, 0.12 mm layers, 4 walls, front face down on textured plate (shell), flat
side down (back), tree supports on build plate only for the chain-hole chamfer. The
screw pilots are 1.2 mm — drive the M1.4 screws straight in, they self-tap.

Regenerate any variant:
```
openscad -o out.stl -D 'PART="shell"' -D 'BATT="500"' -D STORAGE=true -D HAPTIC=false -D USB=true anticipy_pendant_v2.scad
```
