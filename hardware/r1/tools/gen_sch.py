"""Generate hardware/r1/pcb/anticipy_r1.kicad_sch from design.py.

Every symbol is placed on an A3 sheet; each connected pin gets a global label
at the exact pin coordinate (labels connect at their anchor).  Unconnected
pins get no_connect markers.  PWR_FLAGs are attached to GND and VBUS_5V so
ERC passes with zero errors.
"""
import uuid, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from kicad_sym import flatten_symbol, symbol_pins, sx
import design

OUT = os.path.join(os.path.dirname(__file__), "..", "pcb", "anticipy_r1.kicad_sch")

def U():
    return str(uuid.uuid4())

used_syms = {}
for c in design.COMPONENTS:
    used_syms.setdefault(c["sym"], None)
used_syms["power:PWR_FLAG"] = None

for full in list(used_syms):
    lib, name = full.split(":")
    used_syms[full] = flatten_symbol(lib, name)

body = []
body.append('(kicad_sch (version 20250114) (generator "anticipy_gen") (generator_version "9.0")')
body.append('  (uuid "%s")' % U())
body.append('  (paper "A3")')
body.append('  (title_block (title "Anticipy Pendant R1") (company "Anticipy") (rev "R1.0") (comment 1 "47x18mm 4-layer wearable BLE audio pendant"))')

# lib_symbols
body.append("  (lib_symbols")
for full, node in used_syms.items():
    body.append(sx(node, 2))
body.append("  )")

# --- placement -------------------------------------------------------------
X0, Y0 = 30.0, 40.0
x, y = X0, Y0
row_h = 0.0
SHEET_W = 380.0

def snap(v):
    return round(v / 1.27) * 1.27

placements = []  # (comp, sx, sy, pins)
for comp in design.COMPONENTS:
    node = used_syms[comp["sym"]]
    pins = symbol_pins(node)
    if not pins:
        raise RuntimeError("no pins for %s" % comp["sym"])
    xs = [p[3] for p in pins]; ys = [p[4] for p in pins]
    w = max(xs) - min(xs) + 30
    h = max(ys) - min(ys) + 22
    if x + w > SHEET_W:
        x = X0; y += row_h; row_h = 0
    sxp = snap(x - min(xs)); syp = snap(y + max(ys))
    placements.append((comp, sxp, syp, pins))
    x += w; row_h = max(row_h, h)

def label_angle(lib_ang):
    outward = (lib_ang + 180.0) % 360.0
    # lib y-up -> sch y-down flips vertical directions
    if outward == 90: return 270
    if outward == 270: return 90
    return outward

for comp, sxp, syp, pins in placements:
    ref = comp["ref"]
    fields = [("Reference", ref, 0), ("Value", comp["value"], 1),
              ("Footprint", comp["fp"], 2), ("Datasheet", "", 3),
              ("MPN", comp["mpn"], 4)]
    body.append('  (symbol (lib_id "%s") (at %g %g 0) (unit 1)' % (comp["sym"], sxp, syp))
    body.append('    (in_bom yes) (on_board yes) (dnp %s)' % ("yes" if comp.get("dnp") else "no"))
    body.append('    (uuid "%s")' % U())
    for fname, fval, fid in fields:
        hide = "" if fname in ("Reference", "Value") else "(hide yes)"
        body.append('    (property "%s" "%s" (at %g %g 0) (effects (font (size 1.27 1.27)) %s))'
                    % (fname, fval, sxp, syp - 20 - 3 * fid, hide))
    body.append('    (instances (project "anticipy_r1" (path "/" (reference "%s") (unit 1))))' % ref)
    body.append('  )')
    netmap = comp["pins"]
    for (num, name, ptype, px, py, pang) in pins:
        gx, gy = snap(sxp + px), snap(syp - py)
        net = netmap.get(num, "__NC__")
        if net is None or net == "__NC__":
            body.append('  (no_connect (at %g %g) (uuid "%s"))' % (gx, gy, U()))
        else:
            ang = label_angle(pang)
            body.append('  (global_label "%s" (shape passive) (at %g %g %g) '
                        '(effects (font (size 1.27 1.27))) (uuid "%s"))'
                        % (net, gx, gy, ang, U()))

# PWR_FLAG anchors for ERC: attach flag + label at same point via a stub wire
flag_y = y + row_h + 20
for i, net in enumerate(["GND", "VBUS_5V"]):
    fx = snap(X0 + i * 40); fy = snap(flag_y)
    body.append('  (symbol (lib_id "power:PWR_FLAG") (at %g %g 0) (unit 1) (in_bom no) (on_board no) (dnp no)' % (fx, fy))
    body.append('    (uuid "%s")' % U())
    body.append('    (property "Reference" "#FLG%02d" (at %g %g 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (i, fx, fy - 5))
    body.append('    (property "Value" "PWR_FLAG" (at %g %g 0) (effects (font (size 1.27 1.27))))' % (fx, fy - 3))
    body.append('    (property "Footprint" "" (at %g %g 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (fx, fy))
    body.append('    (instances (project "anticipy_r1" (path "/" (reference "#FLG%02d") (unit 1))))' % i)
    body.append('  )')
    body.append('  (wire (pts (xy %g %g) (xy %g %g)) (uuid "%s"))' % (fx, fy, fx, fy + 2.54, U()))
    body.append('  (global_label "%s" (shape passive) (at %g %g 270) (effects (font (size 1.27 1.27))) (uuid "%s"))'
                % (net, fx, fy + 2.54, U()))

body.append('  (sheet_instances (path "/" (page "1")))')
body.append(')')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(body) + "\n")
print("wrote", OUT)
