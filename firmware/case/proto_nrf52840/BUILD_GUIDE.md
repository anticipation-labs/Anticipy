# Anticipy Prototype v1 — Build Guide (XIAO nRF52840 Sense + 752042 LiPo)

Everything in this folder is for the exact hardware in your photos: a Seeed XIAO nRF52840
Sense with soldered headers and a 752042 3.7 V 500 mAh LiPo, printed on your Bambu Lab P2S
(AMS combo).

## 1. What to print (files in `stl/`)

| File | What it is | Print it? |
|---|---|---|
| `anticipy_shell_headers.stl` | Main body, sized for the board **with headers still on** (47.7 × 24.7 × 28.5 mm) | Yes — print this first |
| `anticipy_shell_slim.stl` | Main body if you clip/desolder the headers (47.7 × 24.7 × 20.5 mm — 8 mm thinner) | Optional, much nicer to wear |
| `anticipy_lid.stl` | Snap-fit back lid (shared by both shells) | Yes |
| `anticipy_chain_cap.stl` | Magnetic chain cap experiment (needs 2× 6×2 mm magnets) | Optional |

The shell has: USB-C cutout (charge without opening), 3 mic holes, LED light-pipe window,
reset pinhole, chain lug with a 4.6 mm hole (fits a 4–5 mm chain via a split ring or
jump ring), and internal battery cradle rails.

## 2. Print settings (P2S)

- **Material for prototypes: your silver PETG Pro.** PETG is tougher and more
  heat/impact-resistant than silk PLA, and LiPo cells should not live inside PLA if the
  pendant sits in a hot car or against skin all day. Silk PLA silver looks best — use it
  for a look-and-feel shell, but use PETG for the unit that actually carries the battery.
- 0.12 mm layer height, 4 walls, 40 % infill (it's tiny — strength is free).
- Print shell open-face-up (cavity up), lid flat. No supports needed except a small
  support blocker check under the chain lug — enable "tree supports, on build plate only".
- Seam: rear. Slow outer wall (60 mm/s) for the silk-like finish.
- Tolerance check: the lid lip has 0.20 mm clearance. If the lid is too tight, scale the
  lid 99.5 % in XY; too loose, 100.5 %.

## 3. Wiring (see `wiring_diagram.svg` / `.png`)

Battery + (red) → optional SS-12D10 slide switch → **BAT+** pad on the underside of the
XIAO. Battery − (black) → **BAT−** pad directly. That's the whole electrical build — the
XIAO Sense has the LiPo charger (BQ25101), mic, IMU, BLE and antenna onboard. Charging is
just USB-C through the case cutout.

Zero-failure soldering order:
1. Tape the battery leads apart. Never let them touch.
2. Tin the BAT pads and solder the wires to the board first.
3. Heat-shrink or Kapton over the joints.
4. Multimeter polarity check, then connect the cell.
5. Foam pad (1 mm EVA/PORON) on both faces of the cell, drop it into the cradle rails,
   route wires through the side channel, seat the board, snap the lid.

## 4. Battery map & runtime (the honest math)

500 mAh cell. Measured/typical currents for nRF52840 + PDM mic:
- BLE connected idle: ~0.3 mA → weeks of standby.
- Always-listening capture (mic + CPU + flash writes): ~5–8 mA average.
- **Runtime while recording: 500 / 8 ≈ 60 h+ worst case.** Power is not your problem.

**Storage is the real 4–8 h constraint.** The XIAO has 2 MB onboard QSPI flash:
- 16 kHz 16-bit raw = 32 KB/s → only ~1 minute. Unusable raw.
- IMA-ADPCM (4:1, standard on nRF52) at 16 kHz = 8 KB/s → **~4 min**.
- 8 kHz ADPCM = 4 KB/s → ~8 min.

So for true 4–8 h offline capture you need external flash. Two options:
- **v1.1 (recommended): W25Q128 16 MB SPI flash module** wired to D7/D8/D9/D10 (pinout in
  the wiring diagram). 16 MB @ 4 KB/s ≈ **70 min continuous**, and with voice-activity
  gating (people speak ~15–20 % of the time) that's **6–8 h of real-world offline coverage**.
- **v1.2: W25Q01JV 128 MB** → 8 h+ continuous even without gating.

The firmware just ring-buffers ADPCM to flash while offline and drains it over BLE when
the phone reconnects — nothing exotic, this is how commercial pendants (Omi, Limitless)
do it.

## 5. Chain

- 4.6 mm lug hole = fits a standard **2.5–3 mm stainless cable/curb chain** with a 5 mm
  jump ring, or 4–5 mm chain threaded directly.
- Magnetic snap-on cap: glue one 6×2 mm N52 disc magnet into the shell lug pocket and one
  into the cap (CA glue, check polarity before gluing!). It works, but a magnet this size
  holds ~600–800 g shear — fine for a pendant, but test it before trusting it. The plain
  lug hole is the fallback and is always there.

## 6. Amazon.ca shopping list

| Item | Why | Order link (Amazon.ca search — pick the top Prime listing) |
|---|---|---|
| 6×2 mm N52 neodymium disc magnets | Magnetic chain cap | https://www.amazon.ca/s?k=6x2mm+neodymium+disc+magnets+N52 |
| 28 AWG silicone wire (red/black) | Battery leads | https://www.amazon.ca/s?k=28+awg+silicone+wire+kit |
| SS-12D10 / SS-12F15 mini slide switch | Optional power switch | https://www.amazon.ca/s?k=SS-12D10+mini+slide+switch |
| 1 mm adhesive EVA foam sheet | Battery padding | https://www.amazon.ca/s?k=1mm+adhesive+eva+foam+sheet |
| Kapton (polyimide) tape 10 mm | Insulating BAT pads | https://www.amazon.ca/s?k=kapton+tape+10mm |
| 2.5–3 mm stainless chain, 60 cm, clasp | Pendant chain | https://www.amazon.ca/s?k=2.5mm+stainless+steel+necklace+chain+60cm |
| W25Q128 SPI flash breakout | 4–8 h offline buffer (v1.1) | https://www.amazon.ca/s?k=W25Q128+spi+flash+module |
| 5 mm stainless jump rings | Chain-to-lug | https://www.amazon.ca/s?k=5mm+stainless+steel+jump+rings |

(Search links are used deliberately — direct ASIN links go stale on Amazon.ca within
weeks. The top Prime result for each search is the right part.)

## 7. Prototype → production path

1. **Now (P2S):** PETG silver shells, hand-soldered internals. Good for 5–20 units.
2. **~100 units:** same CAD exported as STEP → **MJF nylon (PA12) or SLS** via JLC3DP or
   Xometry (~$3–6/shell, no tooling, 1-week turnaround), vapor-smoothed + dyed. This is
   the standard bridge before injection molding.
3. **Real production:** the website's brushed-titanium look = CNC or MIM titanium shell
   around a custom PCB (no headers, castellated XIAO or bare nRF52840 module) — that is a
   separate industrial-design pass, not a filament question.

## 8. Before you print 20 of these — verify with calipers

- Header pin height above the board (CAD assumes 9 mm). If yours are taller/shorter,
  change `header_pin_h` in the .scad and re-export.
- Battery thickness (CAD assumes 8.0 mm + 1 mm foam each side).
- Print ONE shell + lid first, drop the real parts in, then commit to a batch.
