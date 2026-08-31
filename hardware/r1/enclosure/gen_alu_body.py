"""Anticipy R1 aluminum-unibody enclosure (PLAUD NotePin construction).

Everything the user touches is aluminum:
  - alu_body.step        CNC 6061 unibody tub (sides + rear, one piece)
  - alu_face_front_v3    1.0mm aluminum top plate, sits in a machined rebate
  - antenna_window       thin plastic sheet piece over the antenna opening
                         (same approach as PLAUD: aluminum shell with a small
                         radio-transparent plastic window over the antenna)

Height is derived from the assembled r1 board, not chosen: the CPL is read
through `part_heights` and the z-budget is

    FLOOR_T + BATT_T + BATT_CLR + max(bottom part) + PCB_T
            + max(top part) + TOP_CLR + FACE_T

The r1 board is populated on both sides across its whole area, so the cell
cannot share a layer with the bottom-side parts (the only bottom-clear
rectangle, 11.9 x 17.2 mm, sits over the module antenna). That forces three
occupied layers - cell, bottom parts, top parts - and an outside height of
13.0 mm (slim, 3.2 mm cell) or 14.0 mm (long-run, 4.2 mm cell). Both are
generated; nylon prints of both decide it once real current draw is measured.
Getting back to 11 mm needs an r2 layout: bottom-side battery keepout, a
mid-mount USB-C, and a top-actuated button.

Retention: internal slide-and-lock clasp (no glue, no screws, no printed
parts, nothing visible from outside).
  - The top plate carries 4 L-hooks on its underside (2 per long edge):
    a leg drops 1 mm below the plate, then a 0.4 mm foot points outward.
  - Inside each long wall, below the rebate, a T-slot undercut channel is
    machined 0.7 mm into the wall (0.8 mm outer skin remains, so the
    exterior is untouched aluminum). At each hook position the channel
    opens upward through the ledge (a drop-in notch); toward the USB end
    it is covered by a 0.5 mm aluminum lip.
  - Assembly: drop the plate in with hooks through the notches, slide it
    1.5 mm toward the USB end so the feet clasp under the lips, then
    press the machined POM lock keys into the exposed notch gaps to block
    back-slide.  Disassembly: pry a key out, slide back, lift.
  - The PC antenna window has a perimeter flange and sits in a recess in
    the floor; it is captured by the battery/PCB stack when the plate is
    locked, so it also needs no glue.

The front plate has no button opening: SW1 on the r1 board is a side-push
switch sitting mid-board, so it cannot be reached through the plate at all.
r1 units use LIS2DH double-tap on the body instead, which also gives the
clean two-pinhole front.
"""

import os
import cadquery as cq
import ezdxf

import part_heights

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

L, W = 51.0, 25.0
FACE_T = 1.0          # aluminum top plate (SendCutSend/JLC 1.0mm)
FLOOR_T = 1.0         # machined floor of the unibody
WALL = 1.5            # unibody side wall
REBATE_W = 0.75       # rebate ledge width holding the top plate

PCB_L, PCB_W, PCB_T = 47.0, 18.0, 0.8
PCB_CLR = 0.15
BATT_L, BATT_W = 35.6, 20.8   # 402035-class protected pouch cell + wrap
BATT_CLR = 0.3                # cell top to nearest bottom-side part
TOP_CLR = 0.25                # tallest top-side part to plate underside
LEDGE_CLR = 0.5               # PCB support ledge to nearest bottom-side part

MAX_TOP, TOP_REF = part_heights.tallest("Top")
MAX_BOT, BOT_REF = part_heights.tallest("Bottom")
BOT_X0, BOT_X1 = part_heights.bottom_extent_x()

in_L, in_W = L - 2 * WALL, W - 2 * WALL             # 48 x 22
assert PCB_L + 2 * PCB_CLR <= in_L, "PCB too long"
assert PCB_W + 2 * PCB_CLR <= in_W, "PCB too wide"
assert BATT_W + 1.0 <= in_W, "battery bay too wide"
assert BATT_L + 1.0 <= in_L, "battery bay too long"

# front-plate features (enclosure-centered coords)
MIC1 = (19.7 - PCB_L / 2, -(16.37 - PCB_W / 2))
MIC2 = (23.4 - PCB_L / 2, -(16.37 - PCB_W / 2))
MIC_D = 1.2
LED = (29.0 - PCB_L / 2, -(4.0 - PCB_W / 2))
LED_D = 1.6

# antenna window: rounded-rect opening at the antenna end (right, +X),
# through both the top plate and the unibody floor; closed by a flanged
# PC insert seated in a recess machined inside the floor, captured by the
# battery/PCB stack (radio-transparent, PLAUD-style, no glue).
AW_L, AW_W, AW_R = 7.0, 14.0, 2.0
AW_X = L / 2 - WALL - 1.0 - AW_L / 2                # inside the end wall
AW_FLANGE = 1.5

USB_W, USB_H = 9.6, 3.6

# internal slide-and-lock clasp (L-hooks on plate underside)
HOOK_L = 3.0          # hook length along X
HOOK_CLR = 0.2        # notch clearance per side
SLIDE = 1.5           # locking slide travel toward -X (USB end)
LEG_T = 0.6           # hook vertical-leg thickness (Y)
LEG_DROP = 1.0        # leg drop below plate underside
FOOT_T = 0.4          # foot thickness (Z)
FOOT_D = 0.6          # foot outward engagement into the wall channel
LIP_T = 0.5           # aluminum lip left over the channel in slide zone
HOOK_XS = (-10.0, 10.0)  # hook center X (within the straight wall section)

VARIANTS = (("slim", 3.2), ("long_run", 4.2))


def capsule(length, width):
    return cq.Sketch().slot(length - width, width, angle=0)


def aw_cut(depth, z, grow=0.0):
    return (
        cq.Workplane("XY")
        .rect(AW_L + grow, AW_W + grow)
        .extrude(depth)
        .edges("|Z")
        .fillet(AW_R)
        .translate((AW_X, 0, z))
    )


def build(batt_t):
    """Unibody tub + top plate for a cell of thickness `batt_t`."""
    pcb_bot = FLOOR_T + batt_t + BATT_CLR + MAX_BOT
    pcb_top = pcb_bot + PCB_T
    plate_bot = pcb_top + MAX_TOP + TOP_CLR
    body_h = plate_bot + FACE_T

    body = cq.Workplane("XY").placeSketch(capsule(L, W)).extrude(body_h)
    body = body.cut(
        cq.Workplane("XY")
        .placeSketch(capsule(in_L, in_W))
        .extrude(body_h - FLOOR_T)
        .translate((0, 0, FLOOR_T))
    )
    # rebate for the top plate
    body = body.cut(
        cq.Workplane("XY")
        .placeSketch(capsule(L - 2 * (WALL - REBATE_W), W - 2 * (WALL - REBATE_W)))
        .extrude(FACE_T)
        .translate((0, 0, plate_bot))
    )
    # clasp: T-slot undercut channels inside both long walls, below the rebate
    ch_top = plate_bot - LIP_T                    # channel ceiling in slide zone
    ch_bot = plate_bot - LEG_DROP - 0.1           # channel floor (foot clearance)
    wall_in = in_W / 2
    ch_out = wall_in + FOOT_D + HOOK_CLR / 2      # channel depth into wall
    assert W / 2 - ch_out >= 0.8, "outer skin too thin at clasp channel"
    for tx in HOOK_XS:
        for sy in (1, -1):
            y0 = wall_in if sy > 0 else -ch_out
            # drop-in notch: channel open up to the rebate bottom at hook X
            body = body.cut(
                cq.Workplane("XY")
                .box(HOOK_L + 2 * HOOK_CLR, ch_out - wall_in, plate_bot - ch_bot,
                     centered=(True, False, False))
                .translate((tx, y0, ch_bot))
            )
            # covered slide channel toward -X, aluminum lip LIP_T stays above
            body = body.cut(
                cq.Workplane("XY")
                .box(HOOK_L + 2 * HOOK_CLR + SLIDE, ch_out - wall_in, ch_top - ch_bot,
                     centered=(False, False, False))
                .translate((tx - HOOK_L / 2 - HOOK_CLR - SLIDE, y0, ch_bot))
            )
    # PCB support ledges, only at the two ends where the bottom side is clear
    ledge_h = 1.0
    for x0, x1 in ((-in_L / 2 - 1.0, BOT_X0 - LEDGE_CLR),
                   (BOT_X1 + LEDGE_CLR, in_L / 2 + 1.0)):
        ledge = (
            cq.Workplane("XY")
            .placeSketch(capsule(in_L, in_W))
            .extrude(ledge_h)
            .intersect(
                cq.Workplane("XY")
                .box(x1 - x0, in_W + 2, ledge_h, centered=(False, True, False))
                .translate((x0, 0, 0))
            )
            .cut(aw_cut(ledge_h, 0.0, grow=2 * AW_FLANGE))
            .translate((0, 0, pcb_bot - ledge_h))
        )
        body = body.union(ledge)
        # PCB locating ribs above the ledge (cavity is wider than the board)
        rib_t = in_W / 2 - (PCB_W / 2 + PCB_CLR)
        for ry in (PCB_W / 2 + PCB_CLR, -in_W / 2):
            body = body.union(
                cq.Workplane("XY")
                .box(x1 - x0, rib_t, PCB_T + 0.3, centered=(False, False, False))
                .translate((x0, ry, pcb_bot))
            )
    # cell locating ribs on the floor (open at both ends for the JST lead)
    for y0 in (BATT_W / 2 + 0.3, -BATT_W / 2 - 1.1):
        body = body.union(
            cq.Workplane("XY")
            .box(BATT_L, 0.8, batt_t - 0.6, centered=(True, False, False))
            .translate((0, y0, FLOOR_T))
        )
    # USB-C opening in left end wall, centred on the connector port
    body = body.cut(
        cq.Workplane("XY")
        .box(WALL * 2 + 2, USB_W, USB_H, centered=(False, True, True))
        .translate((-L / 2 - 1, 0, pcb_top + 1.6))
    )
    # antenna window through the floor + flange recess for the PC insert
    body = body.cut(aw_cut(FLOOR_T, 0.0))
    body = body.cut(aw_cut(0.5, FLOOR_T - 0.5, grow=2 * AW_FLANGE))

    # --- aluminum top plate (with antenna window) ---
    plate_L = L - 2 * (WALL - REBATE_W) - 0.2 - SLIDE
    plate_W = W - 2 * (WALL - REBATE_W) - 0.2
    plate = cq.Workplane("XY").placeSketch(capsule(plate_L, plate_W)).extrude(FACE_T)
    for (px, py), d in ((MIC1, MIC_D), (MIC2, MIC_D), (LED, LED_D)):
        plate = plate.faces(">Z").workplane().pushPoints([(px, py)]).hole(d)
    # antenna opening runs out to the plate end: the 0.9mm rim an enclosed
    # window would leave is below any minimum feature size, and the open notch
    # keeps the plate a single solid so it instant-quotes
    notch_L = plate_L / 2 - (AW_X - AW_L / 2) + 1.0
    plate = plate.cut(
        cq.Workplane("XY")
        .box(notch_L, AW_W, FACE_T, centered=(False, True, False))
        .translate((AW_X - AW_L / 2, 0, 0))
    )
    # L-hooks on plate underside: vertical leg + outward foot
    for tx in HOOK_XS:
        for sy in (1, -1):
            # hooks in plate coords: drop-in plate offset is +SLIDE/2,
            # locked offset is -SLIDE/2 (slide travel centered in the rebate)
            hx = tx - SLIDE / 2
            leg_y = wall_in - LEG_T if sy > 0 else -wall_in
            foot_y = wall_in - LEG_T if sy > 0 else -(wall_in + FOOT_D)
            plate = plate.union(
                cq.Workplane("XY")
                .box(HOOK_L, LEG_T, LEG_DROP, centered=(True, False, False))
                .translate((hx, leg_y, -LEG_DROP))
            )
            plate = plate.union(
                cq.Workplane("XY")
                .box(HOOK_L, LEG_T + FOOT_D, FOOT_T, centered=(True, False, False))
                .translate((hx, foot_y, -LEG_DROP))
            )
    solids = plate.solids().vals()
    assert len(solids) == 1, f"plate must be one solid, got {len(solids)}"
    return body, plate, plate_L, plate_W, plate_bot, body_h


# flanged PC window insert: 0.5 body drops into the opening, 0.45 flange
# sits in the recess, held down by the battery foam / PCB stack
aw_insert = (
    cq.Workplane("XY")
    .rect(AW_L - 0.2, AW_W - 0.2)
    .extrude(0.5)
    .edges("|Z")
    .fillet(AW_R)
    .union(
        cq.Workplane("XY")
        .rect(AW_L + 2 * AW_FLANGE - 0.2, AW_W + 2 * AW_FLANGE - 0.2)
        .extrude(0.45)
        .edges("|Z")
        .fillet(AW_R)
        .translate((0, 0, 0.5))
    )
)

# --- POM lock keys (fill the notch gap after the locking slide) ---
key = cq.Workplane("XY").box(SLIDE - 0.1, FOOT_D + HOOK_CLR / 2 - 0.05,
                             LEG_DROP - 0.1, centered=(True, True, False))
cq.exporters.export(key, os.path.join(OUT, "pom_lock_key.step"))
cq.exporters.export(aw_insert, os.path.join(OUT, "pc_antenna_window.step"))


def rounded_rect_pts(cx, cy, lx, wy, r):
    x0, x1 = cx - lx / 2, cx + lx / 2
    y0, y1 = cy - wy / 2, cy + wy / 2
    b = 0.41421356  # tan(22.5deg) bulge for 90deg arcs
    return [
        (x0 + r, y0, 0, 0, 0), (x1 - r, y0, 0, 0, b), (x1, y0 + r, 0, 0, 0),
        (x1, y1 - r, 0, 0, b), (x1 - r, y1, 0, 0, 0), (x0 + r, y1, 0, 0, b),
        (x0, y1 - r, 0, 0, 0), (x0, y0 + r, 0, 0, b),
    ]


def capsule_pts(length, width):
    rr = width / 2.0
    xx = length / 2.0 - rr
    return [(-xx, -rr, 0, 0, 0), (xx, -rr, 0, 0, 1), (xx, rr, 0, 0, 0), (-xx, rr, 0, 0, 1)]


def dxf_out(path, outline_pts, circles=(), rrects=()):
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    msp.add_lwpolyline(outline_pts, format="xyseb", close=True)
    for hx, hy, hd in circles:
        msp.add_circle((hx, hy), hd / 2)
    for cx, cy, lx, wy, r in rrects:
        msp.add_lwpolyline(rounded_rect_pts(cx, cy, lx, wy, r), format="xyseb", close=True)
    doc.saveas(path)
    print("wrote", path)


print(f"tallest top {MAX_TOP} mm ({TOP_REF}), tallest bottom {MAX_BOT} mm ({BOT_REF})")
print(f"bottom-side parts span x {BOT_X0:+.2f} .. {BOT_X1:+.2f}")
for name, batt_t in VARIANTS:
    body, plate, plate_L, plate_W, plate_bot, body_h = build(batt_t)
    cq.exporters.export(body, os.path.join(OUT, f"alu_body_{name}.step"))
    cq.exporters.export(plate, os.path.join(OUT, f"alu_face_front_{name}.step"))
    asm = cq.Assembly()
    asm.add(body, name="alu_body")
    asm.add(plate, name="alu_face_front", loc=cq.Location((-SLIDE / 2, 0, plate_bot)))
    asm.export(os.path.join(OUT, f"alu_unibody_assembly_{name}.step"))
    dxf_out(
        os.path.join(OUT, f"alu_face_front_{name}_mm.dxf"),
        capsule_pts(plate_L, plate_W),
        circles=[(*MIC1, MIC_D), (*MIC2, MIC_D), (*LED, LED_D)],
        rrects=[(AW_X, 0, AW_L, AW_W, AW_R)],
    )
    print(f"{name}: cell {batt_t} mm -> outside {L} x {W} x {body_h:.2f} mm, "
          f"plate underside {plate_bot:.2f}")

# plastic antenna window sheet pieces (glued inside, one top one bottom):
# oversized 1.5mm per side beyond the opening for glue flange
dxf_out(
    os.path.join(OUT, "antenna_window_mm.dxf"),
    rounded_rect_pts(0, 0, AW_L + 3.0, AW_W + 3.0, AW_R),
)
print("alu unibody exports done ->", OUT)
