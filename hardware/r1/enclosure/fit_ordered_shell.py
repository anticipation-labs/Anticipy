"""Best real cell pocket inside the ALREADY-ORDERED 11.0 mm shell.

Sweeps candidate cell rectangles under the PCB, computing the local
bottom-side obstruction height for each, so a cell can be thicker where
the board happens to be clear. Antenna keepout at the +X end excluded.
"""
import part_heights

FLOOR_T, PLATE_T = 1.0, 1.0
CAV_H = 8.00
IN_L, IN_W = 48.0, 19.0
PCB_T, TOP_CLR, BATT_CLR = 0.8, 0.20, 0.25
PLATE_RELIEF = 0.70          # milled into plate underside over J1 / U1
FLOOR_POCKET = 0.40          # milled into cavity floor under the cell
ANT_X = 11.0                 # cell must stay at x <= this (module antenna end)
SKIP = ("J2", "J3")          # leads soldered straight to the pads

parts = [p for p in part_heights.placements() if p[1] == "Bottom" and p[0] not in SKIP]
MAX_TOP = max(h for _, l, h, *_ in part_heights.placements() if l == "Top")

avail = CAV_H + PLATE_RELIEF + FLOOR_POCKET
head = avail - (PCB_T + MAX_TOP + TOP_CLR)      # cell + obstruction + clearance
print(f"usable cavity {avail:.2f} mm, top side eats {PCB_T + MAX_TOP + TOP_CLR:.2f}"
      f" -> {head:.2f} mm for cell + bottom parts")


def obstruction(x0, x1, y0, y1):
    h = 0.0
    for ref, _lay, ph, x, y, ex, ey in parts:
        if x - ex / 2 < x1 and x + ex / 2 > x0 and y - ey / 2 < y1 and y + ey / 2 > y0:
            h = max(h, ph)
    return h


best = []
lo_x, hi_x = -IN_L / 2 + 0.5, ANT_X
for length in (20, 25, 28, 30, 32, 35):
    for width in (12.0, 15.0, 17.0, 18.0):
        if width > IN_W - 1.0:
            continue
        y0, y1 = -width / 2, width / 2
        for i in range(int((hi_x - lo_x - length) / 0.5) + 1):
            x0 = lo_x + i * 0.5
            x1 = x0 + length
            t = head - obstruction(x0, x1, y0, y1) - BATT_CLR
            if t <= 0:
                continue
            vol = length * width * min(t, 6.0) / 1000
            best.append((vol, t, length, width, x0, x1))
best.sort(reverse=True)
print("\n  mAh*  cell (T x W x L)         x-range        obstruction")
seen = set()
for vol, t, length, width, x0, x1 in best:
    key = (length, width)
    if key in seen:
        continue
    seen.add(key)
    mah = vol * 350 / 3.7
    print(f"  {mah:5.0f}  {t:4.2f} x {width:4.1f} x {length:4.1f} mm   "
          f"{x0:+6.1f}..{x1:+6.1f}   {obstruction(x0, x1, -width / 2, width / 2):4.2f} mm")
    if len(seen) >= 10:
        break
print("\n* mAh at 350 Wh/L, before PCM/pouch overhead (~-15%)")
