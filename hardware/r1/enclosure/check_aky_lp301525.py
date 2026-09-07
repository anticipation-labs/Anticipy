"""Fit the Akyga LP301525 (TME AKY-LP301525) into the already-ordered 11.0 mm shell.

Dimensions are the datasheet worst case, not the marketing "3 x 15 x 25":
  bare pouch      25.5 L x 15.0 W x 3.0 T   (max)
  assembled pack  27.5 L x 16.0 W x 3.5 T   (max, incl. PCM + tab + wire exit)
So the 2.0 mm PCM tab region is the thick part and needs its own check.
A positive margin only closes the nominal envelope -- physical fit stays
unconfirmed until a real shell, board and cell are in hand.
"""
import fit_ordered_shell as f

POUCH_L, POUCH_W, POUCH_T = 25.5, 15.0, 3.0
PACK_L, PACK_W, PACK_T = 27.5, 16.0, 3.5
TAB_L = PACK_L - POUCH_L
TAPE_T = 0.2


def sweep(tape=TAPE_T):
    """Best (margin, x0, orientation) with the PCM tab at either end."""
    y0, y1 = -PACK_W / 2, PACK_W / 2
    lo_x, hi_x = -f.IN_L / 2 + 0.5, f.ANT_X
    out = (-99.0, 0.0, "")
    steps = int((hi_x - lo_x - PACK_L) / 0.5) + 1
    for i in range(steps):
        x0 = lo_x + i * 0.5
        for tab_first in (True, False):
            if tab_first:
                tx0, tx1 = x0, x0 + TAB_L
                px0, px1 = tx1, tx1 + POUCH_L
            else:
                px0, px1 = x0, x0 + POUCH_L
                tx0, tx1 = px1, px1 + TAB_L
            pouch = (f.head - f.obstruction(px0, px1, y0, y1)
                     - f.BATT_CLR - POUCH_T - tape)
            tab = (f.head - f.obstruction(tx0, tx1, y0, y1)
                   - f.BATT_CLR - PACK_T - tape)
            m = min(pouch, tab)
            if m > out[0]:
                out = (m, x0, "tab at -X" if tab_first else "tab at +X")
    return out


if __name__ == "__main__":
    print(f"\ncavity {f.IN_L} x {f.IN_W} mm, {f.head:.2f} mm for cell + bottom parts")
    print(f"pack {PACK_T} x {PACK_W} x {PACK_L} mm max "
          f"(pouch {POUCH_T} x {POUCH_W} x {POUCH_L})")
    for tape in (TAPE_T, 0.0):
        margin, x0, orient = sweep(tape)
        verdict = "FITS" if margin >= 0.15 else ("tight" if margin >= 0 else "NO")
        print(f"  tape {tape:.1f} mm -> margin {margin:+.2f} mm at x {x0:+.1f}"
              f" ({orient})  {verdict}")
    print(f"\nwidth margin {f.IN_W - PACK_W:+.1f} mm, "
          f"length margin {f.ANT_X - (-f.IN_L / 2 + 0.5) - PACK_L:+.1f} mm")
