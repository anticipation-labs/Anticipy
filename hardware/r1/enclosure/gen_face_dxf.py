"""Aluminum face DXFs in explicit millimeters (SendCutSend-safe).

Capsule outline as a single closed LWPolyline with arc bulges,
holes as circles. Keep in sync with gen_enclosure.py constants.
"""

import os
import ezdxf

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

L, W = 51.0, 25.5
R = W / 2.0
X = L / 2.0 - R

PCB_L, PCB_W = 47.0, 18.0
HOLES_FRONT = [
    (19.7 - PCB_L / 2, -(16.37 - PCB_W / 2), 1.2),   # MK1 mic port
    (23.4 - PCB_L / 2, -(16.37 - PCB_W / 2), 1.2),   # MK2 mic port
    (33.0 - PCB_L / 2, -(9.0 - PCB_W / 2), 4.2),     # SW1 button
    (29.0 - PCB_L / 2, -(4.0 - PCB_W / 2), 1.6),     # LED window
]


def make(path, holes):
    doc = ezdxf.new("R2010", units=4)  # 4 = millimeters
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(-X, -R, 0, 0, 0), (X, -R, 0, 0, 1), (X, R, 0, 0, 0), (-X, R, 0, 0, 1)],
        format="xyseb",
        close=True,
    )
    for hx, hy, hd in holes:
        msp.add_circle((hx, hy), hd / 2)
    doc.saveas(path)
    print("wrote", path)


make(os.path.join(OUT, "alu_face_front_mm.dxf"), HOLES_FRONT)
make(os.path.join(OUT, "alu_face_rear_mm.dxf"), [])
