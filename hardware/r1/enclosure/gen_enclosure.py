"""Anticipy R1 pendant enclosure generator.

Outputs (into hardware/r1/enclosure/out/):
  - pc_center.step / pc_center.stl / pc_center.3mf   polycarbonate center frame (Bambu-printable)
  - alu_face_front.dxf / alu_face_rear.dxf           0.8mm 5052 aluminum face profiles (flat cut)
  - alu_face_front.step / alu_face_rear.step
  - enclosure_assembly.step                          assembled model
  - enclosure_exploded.step / enclosure_exploded.svg exploded view

Envelope: 51 x 21 x 11 mm capsule. PCB: 47 x 18 x 0.8 mm.
Stack (bottom to top):
  0.8 alu rear face
  4.7 battery bay (EEMB LP451235: 4.5 thick + 0.2 clearance)
  0.8 PCB
  2.6 top-component headroom (MDBT50Q ~2.0 + margin)
  0.8 alu front face
  = 9.7 of 11.0 (1.3 mm in PC frame lips)
"""

import os
import cadquery as cq

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# envelope
L, W, H = 51.0, 21.0, 11.0
END_R = 9.0          # capsule end radius
FACE_T = 0.8         # aluminum face thickness
WALL = 1.2           # PC perimeter wall
LIP = 0.65           # PC lip holding each alu face

# PCB
PCB_L, PCB_W, PCB_T = 47.0, 18.0, 0.8
PCB_CLR = 0.15
BATT_L, BATT_W, BATT_T = 35.5, 12.5, 4.7   # LP451235 + clearance
TOP_HEADROOM = 2.6
BOT_BAY = BATT_T

# derived stack
center_h = H - 2 * FACE_T                  # 9.4
cavity_h = BOT_BAY + PCB_T + TOP_HEADROOM  # 8.1
assert cavity_h <= center_h - 0.2, "stack does not fit PC center"
assert PCB_L + 2 * PCB_CLR <= L - 2 * WALL, "PCB too long for cavity"
assert PCB_W + 2 * PCB_CLR <= W - 2 * WALL, "PCB too wide for cavity"

# features (PCB coordinate origin = PCB top-left corner; enclosure centered)
USB_W, USB_H = 9.6, 3.6                    # USB-C opening in left end wall
MIC1_X, MIC1_Y = 19.7 - PCB_L / 2, 16.37 - PCB_W / 2   # MK1 port (front face)
MIC2_X, MIC2_Y = 23.4 - PCB_L / 2, 16.37 - PCB_W / 2   # MK2 port
MIC_HOLE_D = 1.2
BTN_X, BTN_Y = 33.0 - PCB_L / 2, 9.0 - PCB_W / 2       # SW1 area (front face)
BTN_HOLE_D = 4.2
LED_X, LED_Y = 29.0 - PCB_L / 2, 4.0 - PCB_W / 2       # LED light-pipe window
LED_HOLE_D = 1.6


def capsule(length, width):
    return (
        cq.Sketch()
        .slot(length - width, width, angle=0)
    )


def face_outline():
    return cq.Workplane("XY").placeSketch(capsule(L, W)).extrude(FACE_T)


def face_2d_wires():
    return cq.Workplane("XY").placeSketch(capsule(L, W))


# --- aluminum front face (mic ports, button hole, LED window) ---
front = (
    face_outline()
    .faces(">Z").workplane()
    .pushPoints([(MIC1_X, -MIC1_Y), (MIC2_X, -MIC2_Y)])
    .hole(MIC_HOLE_D)
    .faces(">Z").workplane()
    .pushPoints([(BTN_X, -BTN_Y)])
    .hole(BTN_HOLE_D)
    .faces(">Z").workplane()
    .pushPoints([(LED_X, -LED_Y)])
    .hole(LED_HOLE_D)
)

# --- aluminum rear face (plain) ---
rear = face_outline()

# --- polycarbonate center frame ---
outer = cq.Workplane("XY").placeSketch(capsule(L, W)).extrude(center_h)
cavity = (
    cq.Workplane("XY")
    .placeSketch(capsule(L - 2 * WALL, W - 2 * WALL))
    .extrude(center_h)
    .translate((0, 0, 0))
)
center = outer.cut(cavity)
# lips: rebate top and bottom inner edge so alu faces sit recessed
lip_cut_top = (
    cq.Workplane("XY")
    .placeSketch(capsule(L - 2 * (WALL - LIP), W - 2 * (WALL - LIP)))
    .extrude(FACE_T)
    .translate((0, 0, center_h - FACE_T))
)
lip_cut_bot = (
    cq.Workplane("XY")
    .placeSketch(capsule(L - 2 * (WALL - LIP), W - 2 * (WALL - LIP)))
    .extrude(FACE_T)
)
# PCB shelf: ledge ring at battery-bay top on which the PCB rests
shelf = (
    cq.Workplane("XY")
    .placeSketch(capsule(L - 2 * WALL, W - 2 * WALL))
    .extrude(1.0)
    .cut(
        cq.Workplane("XY")
        .placeSketch(capsule(BATT_L + 1.0, BATT_W + 1.0))
        .extrude(1.0)
    )
    .translate((0, 0, BOT_BAY - 1.0))
)
center = center.union(shelf).cut(lip_cut_top).cut(lip_cut_bot)
# USB-C opening in left end wall at PCB level
usb_z = BOT_BAY + PCB_T / 2
usb_cut = (
    cq.Workplane("XY")
    .box(WALL * 2 + 2, USB_W, USB_H, centered=(False, True, True))
    .translate((-L / 2 - 1, 0, usb_z + 0.8))
)
center = center.cut(usb_cut)
# lanyard hole through the antenna-end wall (radio-transparent PC end)
lanyard = (
    cq.Workplane("XZ")
    .cylinder(4.0, 1.25)
    .translate((L / 2 - 3.0, 2.0, center_h / 2))
)
center = center.cut(lanyard)

# --- exports ---
cq.exporters.export(center, os.path.join(OUT, "pc_center.step"))
cq.exporters.export(center, os.path.join(OUT, "pc_center.stl"))
cq.exporters.export(front, os.path.join(OUT, "alu_face_front.step"))
cq.exporters.export(rear, os.path.join(OUT, "alu_face_rear.step"))

for name, holes in (
    ("alu_face_front.dxf", [(MIC1_X, -MIC1_Y, MIC_HOLE_D), (MIC2_X, -MIC2_Y, MIC_HOLE_D),
                            (BTN_X, -BTN_Y, BTN_HOLE_D), (LED_X, -LED_Y, LED_HOLE_D)]),
    ("alu_face_rear.dxf", []),
):
    w = face_2d_wires()
    for hx, hy, hd in holes:
        w = w.moveTo(hx, hy).circle(hd / 2)
    cq.exporters.export(w.consolidateWires(), os.path.join(OUT, name))

asm = cq.Assembly()
asm.add(rear, name="alu_rear", loc=cq.Location((0, 0, 0)))
asm.add(center, name="pc_center", loc=cq.Location((0, 0, FACE_T)))
asm.add(front, name="alu_front", loc=cq.Location((0, 0, FACE_T + center_h)))
asm.export(os.path.join(OUT, "enclosure_assembly.step"))

exp = cq.Assembly()
exp.add(rear, name="alu_rear", loc=cq.Location((0, 0, -12)))
exp.add(center, name="pc_center", loc=cq.Location((0, 0, 0)))
exp.add(front, name="alu_front", loc=cq.Location((0, 0, center_h + 12)))
exp.export(os.path.join(OUT, "enclosure_exploded.step"))
cq.exporters.export(
    center.union(rear.translate((0, 0, -12))).union(front.translate((0, 0, center_h + 12))),
    os.path.join(OUT, "enclosure_exploded.svg"),
    opt={"projectionDir": (1, -1, 0.6), "width": 1200, "height": 800},
)
print("enclosure exports done ->", OUT)
