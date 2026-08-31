"""Numeric fit proof: every placed part vs the generated enclosure cavity.

Run after gen_alu_body.py; fails loudly on any negative clearance.
"""
import gen_alu_body as g
import part_heights


def check(batt_t, name):
    pcb_bot = g.FLOOR_T + batt_t + g.BATT_CLR + g.MAX_BOT
    pcb_top = pcb_bot + g.PCB_T
    plate_bot = pcb_top + g.MAX_TOP + g.TOP_CLR
    body_h = plate_bot + g.FACE_T
    print(f"\n=== {name}: cell {batt_t} mm -> {g.L} x {g.W} x {body_h:.2f} mm ===")
    print(f"floor top {g.FLOOR_T:.2f} | cell top {g.FLOOR_T + batt_t:.2f} | "
          f"PCB {pcb_bot:.2f}-{pcb_top:.2f} | plate underside {plate_bot:.2f}")

    worst = []
    for ref, layer, h, x, y, ex, ey in part_heights.placements():
        if layer == "Top":
            clr = plate_bot - (pcb_top + h)
        else:
            clr = (pcb_bot - h) - (g.FLOOR_T + batt_t)
        worst.append((clr, ref, layer, h))
        # in-plane: nothing may sit outside the cavity
        assert abs(x) + ex / 2 <= g.in_L / 2, f"{ref} outside cavity in X"
        assert abs(y) + ey / 2 <= g.in_W / 2, f"{ref} outside cavity in Y"
    worst.sort()
    for clr, ref, layer, h in worst[:6]:
        print(f"  tightest {layer:6s} {ref:4s} h={h:4.2f}  clearance {clr:+.2f} mm")
    assert worst[0][0] > 0, f"collision: {worst[0]}"

    # PCB support ledges must not touch any bottom-side part
    assert g.BOT_X0 - g.LEDGE_CLR > -g.in_L / 2, "no room for USB-end ledge"
    assert g.BOT_X1 + g.LEDGE_CLR < g.in_L / 2, "no room for antenna-end ledge"
    ledge_len = (g.BOT_X0 - g.LEDGE_CLR + g.in_L / 2) + (g.in_L / 2 - g.BOT_X1 - g.LEDGE_CLR)
    print(f"  PCB supported on {ledge_len:.1f} mm of end ledges "
          f"(x <= {g.BOT_X0 - g.LEDGE_CLR:+.2f} and x >= {g.BOT_X1 + g.LEDGE_CLR:+.2f})")

    # cell bay
    print(f"  cell bay {g.BATT_L:.1f} x {g.BATT_W:.1f} x {batt_t:.1f} mm, "
          f"side clearance {(g.in_W - g.BATT_W) / 2:.2f} mm, "
          f"end clearance {(g.in_L - g.BATT_L) / 2:.2f} mm")

    # USB-C window vs connector body
    usb_lo, usb_hi = pcb_top + 1.6 - g.USB_H / 2, pcb_top + 1.6 + g.USB_H / 2
    conn_lo, conn_hi = pcb_top, pcb_top + g.MAX_TOP
    print(f"  USB window z {usb_lo:.2f}-{usb_hi:.2f} vs connector {conn_lo:.2f}-{conn_hi:.2f}")
    assert usb_lo < conn_lo + 0.9 and usb_hi > conn_hi - 0.9, "USB window misaligned"
    assert usb_hi < plate_bot, "USB window breaks into the plate rebate"


for nm, bt in g.VARIANTS:
    check(bt, nm)
print("\nfit verified for all variants")
