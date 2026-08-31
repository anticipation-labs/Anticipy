"""Anticipy R1 aluminum-unibody enclosure (PLAUD NotePin construction).

Everything the user touches is aluminum:
  - alu_body.step        CNC 6061 unibody tub (sides + rear, one piece)
  - alu_face_front_v3    1.0mm aluminum top plate, sits in a machined rebate
  - antenna_window       thin plastic sheet piece over the antenna opening
                         (same approach as PLAUD: aluminum shell with a small
                         radio-transparent plastic window over the antenna)

Envelope 51 x 22 x 11 mm (PLAUD NotePin is 51 x 21 x 11; we stay within
+1 mm). PCB 47 x 18 x 0.8. Battery bay 37.5 x 12.5 x 5.2 for a 12 mm-wide
protected pouch cell (401230 / 501235 class). The wider dated-delivery
cells (302035 / EEMB 502030) are bench-validation only, case open.

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
"""

import os
import cadquery as cq
import ezdxf

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

L, W, H = 51.0, 22.0, 11.0
FACE_T = 1.0          # aluminum top plate (SendCutSend/JLC 1.0mm)
FLOOR_T = 1.0         # machined floor of the unibody
WALL = 1.5            # unibody side wall
REBATE_W = 0.75       # rebate ledge width holding the top plate
BODY_H = H - FACE_T   # 10.0

PCB_L, PCB_W, PCB_T = 47.0, 18.0, 0.8
PCB_CLR = 0.15
BATT_L, BATT_W, BATT_T = 37.5, 12.5, 5.2
TOP_HEADROOM = 2.6

cavity_h = BATT_T + PCB_T + TOP_HEADROOM            # 9.0
assert FLOOR_T + cavity_h <= BODY_H, "stack does not fit unibody"
in_L, in_W = L - 2 * WALL, W - 2 * WALL             # 48 x 22.5
assert PCB_L + 2 * PCB_CLR <= in_L, "PCB too long"
assert PCB_W + 2 * PCB_CLR <= in_W, "PCB too wide"
assert BATT_W + 0.5 <= in_W, "battery bay too wide"

# front-plate features (enclosure-centered coords)
MIC1 = (19.7 - PCB_L / 2, -(16.37 - PCB_W / 2))
MIC2 = (23.4 - PCB_L / 2, -(16.37 - PCB_W / 2))
MIC_D = 1.2
BTN = (33.0 - PCB_L / 2, -(9.0 - PCB_W / 2))
BTN_D = 4.2
LED = (29.0 - PCB_L / 2, -(4.0 - PCB_W / 2))
LED_D = 1.6

# antenna window: rounded-rect opening at the antenna end (right, +X),
# through both the top plate and the unibody floor; closed by a flanged
# PC insert seated in a recess machined inside the floor, captured by the
# battery/PCB stack (radio-transparent, PLAUD-style, no glue).
AW_L, AW_W, AW_R = 7.0, 14.0, 2.0
AW_X = L / 2 - WALL - 1.0 - AW_L / 2                # inside the end wall

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


def capsule(length, width):
    return cq.Sketch().slot(length - width, width, angle=0)


# --- unibody tub ---
body = cq.Workplane("XY").placeSketch(capsule(L, W)).extrude(BODY_H)
pocket = (
    cq.Workplane("XY")
    .placeSketch(capsule(in_L, in_W))
    .extrude(BODY_H - FLOOR_T)
    .translate((0, 0, FLOOR_T))
)
body = body.cut(pocket)
# rebate for the top plate
rebate = (
    cq.Workplane("XY")
    .placeSketch(capsule(L - 2 * (WALL - REBATE_W), W - 2 * (WALL - REBATE_W)))
    .extrude(FACE_T)
    .translate((0, 0, BODY_H - FACE_T))
)
body = body.cut(rebate)
# clasp: T-slot undercut channels inside both long walls, below the rebate
plate_bot = BODY_H - FACE_T                   # 9.0, plate underside
ch_top = plate_bot - LIP_T                    # channel ceiling in slide zone
ch_bot = plate_bot - LEG_DROP - 0.1           # channel floor (foot clearance)
wall_in = in_W / 2                            # inner wall face y (11.25)
ch_out = wall_in + FOOT_D + HOOK_CLR / 2      # channel depth into wall
assert W / 2 - ch_out >= 0.8, "outer skin too thin at clasp channel"
for tx in HOOK_XS:
    for sy in (1, -1):
        y0 = wall_in if sy > 0 else -ch_out
        # drop-in notch: channel open up to the rebate bottom at hook X
        body = body.cut(
            cq.Workplane("XY")
            .box(HOOK_L + 2 * HOOK_CLR, ch_out - wall_in, plate_bot - ch_bot, centered=(True, False, False))
            .translate((tx, y0, ch_bot))
        )
        # covered slide channel toward -X, aluminum lip LIP_T stays above
        body = body.cut(
            cq.Workplane("XY")
            .box(HOOK_L + 2 * HOOK_CLR + SLIDE, ch_out - wall_in, ch_top - ch_bot, centered=(False, False, False))
            .translate((tx - HOOK_L / 2 - HOOK_CLR - SLIDE, y0, ch_bot))
        )
# PCB shelf ledge ring at battery-bay top
shelf = (
    cq.Workplane("XY")
    .placeSketch(capsule(in_L, in_W))
    .extrude(1.0)
    .cut(cq.Workplane("XY").placeSketch(capsule(BATT_L + 1.0, BATT_W + 0.5)).extrude(1.0))
    .translate((0, 0, FLOOR_T + BATT_T - 1.0))
)
body = body.union(shelf)
# USB-C opening in left end wall at PCB level
usb_z = FLOOR_T + BATT_T + PCB_T / 2 + 0.8
body = body.cut(
    cq.Workplane("XY")
    .box(WALL * 2 + 2, USB_W, USB_H, centered=(False, True, True))
    .translate((-L / 2 - 1, 0, usb_z))
)
# antenna window through the floor
body = body.cut(
    cq.Workplane("XY")
    .rect(AW_L, AW_W)
    .extrude(FLOOR_T)
    .edges("|Z")
    .fillet(AW_R)
    .translate((AW_X, 0, 0))
)
# flange recess inside the floor for the PC window insert (0.5 deep)
AW_FLANGE = 1.5
body = body.cut(
    cq.Workplane("XY")
    .rect(AW_L + 2 * AW_FLANGE, AW_W + 2 * AW_FLANGE)
    .extrude(0.5)
    .edges("|Z")
    .fillet(AW_R)
    .translate((AW_X, 0, FLOOR_T - 0.5))
)
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

# --- aluminum top plate (with antenna window) ---
plate_L = L - 2 * (WALL - REBATE_W) - 0.2 - SLIDE
plate_W = W - 2 * (WALL - REBATE_W) - 0.2
plate = cq.Workplane("XY").placeSketch(capsule(plate_L, plate_W)).extrude(FACE_T)
for (px, py), d in ((MIC1, MIC_D), (MIC2, MIC_D), (BTN, BTN_D), (LED, LED_D)):
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

# --- POM lock keys (fill the notch gap after the locking slide) ---
key = cq.Workplane("XY").box(SLIDE - 0.1, FOOT_D + HOOK_CLR / 2 - 0.05, LEG_DROP - 0.1, centered=(True, True, False))

plate_solids = plate.solids().vals()
assert len(plate_solids) == 1, f"plate must be one solid, got {len(plate_solids)}"

cq.exporters.export(body, os.path.join(OUT, "alu_body.step"))
cq.exporters.export(plate, os.path.join(OUT, "alu_face_front_v3.step"))
cq.exporters.export(key, os.path.join(OUT, "pom_lock_key.step"))
cq.exporters.export(aw_insert, os.path.join(OUT, "pc_antenna_window.step"))

# --- assembly ---
asm = cq.Assembly()
asm.add(body, name="alu_body")
asm.add(plate, name="alu_face_front", loc=cq.Location((-SLIDE / 2, 0, BODY_H - FACE_T)))
asm.export(os.path.join(OUT, "alu_unibody_assembly.step"))


# --- 2D mm DXFs (SendCutSend-safe, explicit mm) ---
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


dxf_out(
    os.path.join(OUT, "alu_face_front_v3_mm.dxf"),
    capsule_pts(plate_L, plate_W),
    circles=[(*MIC1, MIC_D), (*MIC2, MIC_D), (*BTN, BTN_D), (*LED, LED_D)],
    rrects=[(AW_X, 0, AW_L, AW_W, AW_R)],
)
# plastic antenna window sheet pieces (glued inside, one top one bottom):
# oversized 1.5mm per side beyond the opening for glue flange
dxf_out(
    os.path.join(OUT, "antenna_window_mm.dxf"),
    rounded_rect_pts(0, 0, AW_L + 3.0, AW_W + 3.0, AW_R),
)
print("alu unibody exports done ->", OUT)
