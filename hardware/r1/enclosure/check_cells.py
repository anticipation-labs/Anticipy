"""Check concrete off-the-shelf LiPo cells against the already-ordered 11.0 mm shell.

Reports, for each candidate, the best placement under the PCB and the vertical
margin left after the local bottom-side obstruction. The pouch and the thinner
protection-board tab are checked separately, since the tab can slide under a
taller component that the pouch cannot clear. Positive margin only means the
nominal envelope closes -- physical fit stays unconfirmed until a real shell and
board are in hand.
"""
import fit_ordered_shell as f

PCM_L = 3.0          # protection board tab beyond the pouch
PCM_T = 1.3          # tab thickness incl. kapton wrap
TAPE_T = 0.2         # pouch wrap / mounting tape penalty

# (label, pouch thickness, width, pouch length, typ mAh)
CANDIDATES = (
    ("301225 (LP301225)", 3.0, 12.0, 25.0, 70),
    ("301525", 3.0, 15.0, 25.0, 85),
    ("301230 (LP301230)", 3.0, 12.0, 30.0, 90),
    ("302025 (LP302025)", 3.0, 20.0, 25.0, 100),
    ("241838 (LP241838)", 2.4, 18.0, 38.0, 100),
    ("241730", 2.4, 17.0, 30.0, 90),
    ("241732", 2.4, 17.0, 32.0, 100),
    ("201730", 2.0, 17.0, 30.0, 75),
    ("251730", 2.5, 17.0, 30.0, 95),
    ("401230 (LP401230)", 4.0, 12.0, 30.0, 105),
    ("501235", 5.0, 12.0, 35.0, 250),
)


def best_margin(t, w, length):
    """Best (margin, x0) over placements; pouch and PCM tab checked separately."""
    if w > f.IN_W - 1.0:
        return None, None
    y0, y1 = -w / 2, w / 2
    lo_x, hi_x = -f.IN_L / 2 + 0.5, f.ANT_X
    if length + PCM_L > hi_x - lo_x:
        return None, None
    out = (-99.0, 0.0)
    steps = int((hi_x - lo_x - length - PCM_L) / 0.5) + 1
    for i in range(steps):
        x0 = lo_x + i * 0.5
        x1 = x0 + length
        pouch = f.head - f.obstruction(x0, x1, y0, y1) - f.BATT_CLR - t
        tab = f.head - f.obstruction(x1, x1 + PCM_L, y0, y1) - f.BATT_CLR - PCM_T
        m = min(pouch, tab)
        if m > out[0]:
            out = (m, x0)
    return out


def report():
    print(f"\nhead room for cell + obstruction: {f.head:.2f} mm"
          f"   cavity {f.IN_L} x {f.IN_W} mm\n")
    print(f"{'cell':22} {'T x W x L pouch +tab':24} {'mAh':>5}  margin   verdict")
    for label, t, w, length, mah in CANDIDATES:
        tt = t + TAPE_T
        margin, x0 = best_margin(tt, w, length)
        dims = f"{tt:.1f} x {w:.0f} x {length:.0f} +{PCM_L:.0f}"
        if margin is None:
            why = "too wide" if w > f.IN_W - 1.0 else "too long for cavity"
            print(f"{label:22} {dims:24} {mah:5d}      --   NO ({why})")
            continue
        verdict = "FITS" if margin >= 0.15 else ("tight" if margin >= 0 else "NO")
        at = "" if margin < 0 else f"  at x {x0:+.1f}"
        print(f"{label:22} {dims:24} {mah:5d}  {margin:+6.2f}   {verdict}{at}")


if __name__ == "__main__":
    report()
