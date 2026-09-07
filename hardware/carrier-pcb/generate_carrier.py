#!/usr/bin/env python3
"""Generate the Anticipy V1 carrier PCB (KiCad 6, pcbnew scripting).

Board: 53.0 x 19.5 mm, 2-layer. The XIAO nRF52840 Sense solders on via its
14 header pins (2 rows of 7, 2.54 mm pitch, 15.24 mm row spacing) at the left
end; the 502030 cell is taped over the bare right tail. On-board parts:
W25Q128JVSIQ (SOIC-8) SPI flash, S8050 (SOT-23) haptic driver, 1 kOhm base
resistor (0805), 1N4148W flyback (SOD-123), 100n decoupler (0805), plus wire
pads for the side button and the coin motor. Battery wires go directly to the
XIAO underside BAT pads (charging stays on the XIAO's BQ25101).

Routing discipline: GND zone on F.Cu, 3V3 zone on B.Cu; signal verticals on
B.Cu, signal horizontals on F.Cu, via at every corner; SMD pads approached on
F.Cu, THT pads joined on either layer.

Run: python3 generate_carrier.py -> anticipy_carrier.kicad_pcb + drc_report.txt
"""
import os
import pcbnew
from pcbnew import wxPointMM, wxSizeMM, FromMM

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "anticipy_carrier.kicad_pcb")
FP_LIB = "/usr/share/kicad/footprints"

BOARD_L, BOARD_W = 53.0, 19.5

board = pcbnew.BOARD()

net_names = ["GND", "3V3", "BTN", "HAP_CTRL", "NPN_B", "MOT_SW",
             "CS", "SCK", "MISO", "MOSI"]
nets = {}
for n in net_names:
    ni = pcbnew.NETINFO_ITEM(board, n)
    board.Add(ni)
    nets[n] = ni

# ---------------- outline ----------------
pts = [(0, 0), (BOARD_L, 0), (BOARD_L, BOARD_W), (0, BOARD_W)]
for i in range(4):
    seg = pcbnew.PCB_SHAPE(board)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(wxPointMM(*pts[i])); seg.SetEnd(wxPointMM(*pts[(i + 1) % 4]))
    seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(FromMM(0.1))
    board.Add(seg)

# ---------------- XIAO header footprint ----------------
def tht_pad(fp, num, x, y, net, drill=0.8, dia=1.6):
    pad = pcbnew.PAD(fp)
    pad.SetNumber(str(num))
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetSize(wxSizeMM(dia, dia))
    pad.SetDrillSize(wxSizeMM(drill, drill))
    pad.SetLayerSet(pad.PTHMask())
    pad.SetPosition(wxPointMM(x, y))
    fpos = fp.GetPosition()
    pad.SetPos0(pcbnew.wxPoint(FromMM(x) - fpos.x, FromMM(y) - fpos.y))
    if net: pad.SetNet(nets[net])
    fp.Add(pad)
    return pad

xiao = pcbnew.FOOTPRINT(board)
xiao.SetReference("U1"); xiao.SetValue("XIAO nRF52840 Sense")
xiao.SetPosition(wxPointMM(12.0, BOARD_W / 2))
XIAO_TOP = [("D0", None), ("D1", "BTN"), ("D2", "CS"), ("D3", "HAP_CTRL"),
            ("D4", None), ("D5", None), ("D6", None)]
XIAO_BOT = [("5V", None), ("GND", "GND"), ("3V3", "3V3"), ("D10", "MOSI"),
            ("D9", "MISO"), ("D8", "SCK"), ("D7", None)]
x0, yc = 4.38, BOARD_W / 2
ty, by = yc - 7.62, yc + 7.62         # 2.13 and 17.37
for i, (name, net) in enumerate(XIAO_TOP):
    tht_pad(xiao, name, x0 + i * 2.54, ty, net)
for i, (name, net) in enumerate(XIAO_BOT):
    tht_pad(xiao, name, x0 + i * 2.54, by, net)
board.Add(xiao)
xp = lambda i: x0 + i * 2.54

# ---------------- library footprints ----------------
def load(lib, name, ref, value, x, y, rot=0):
    fp = pcbnew.FootprintLoad(os.path.join(FP_LIB, lib + ".pretty"), name)
    assert fp, f"footprint {lib}:{name} not found"
    fp.SetReference(ref); fp.SetValue(value)
    fp.Reference().SetVisible(True); fp.Value().SetVisible(False)
    fp.SetPosition(wxPointMM(x, y)); fp.SetOrientationDegrees(rot)
    board.Add(fp)
    return fp

def set_pad_net(fp, padnum, net):
    for p in fp.Pads():
        if p.GetNumber() == str(padnum):
            p.SetNet(nets[net]); return
    raise KeyError(padnum)

def pad_xy(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == str(num):
            pos = p.GetPosition()
            return pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    raise KeyError(num)

u2 = load("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", "U2", "W25Q128JVSIQ",
          28.0, 9.75, 0)
for pad, net in [(1, "CS"), (2, "MISO"), (3, "3V3"), (4, "GND"),
                 (5, "MOSI"), (6, "SCK"), (7, "3V3"), (8, "3V3")]:
    set_pad_net(u2, pad, net)

r1 = load("Resistor_SMD", "R_0805_2012Metric", "R1", "1k", 20.5, 15.5, 0)
set_pad_net(r1, 1, "HAP_CTRL"); set_pad_net(r1, 2, "NPN_B")

q1 = load("Package_TO_SOT_SMD", "SOT-23", "Q1", "S8050", 24.0, 17.0, 90)
# SOT-23: 1 B, 2 E, 3 C
for pad, net in [(1, "NPN_B"), (2, "GND"), (3, "MOT_SW")]:
    set_pad_net(q1, pad, net)

d1 = load("Diode_SMD", "D_SOD-123", "D1", "1N4148W", 29.0, 17.0, 0)
set_pad_net(d1, 1, "MOT_SW"); set_pad_net(d1, 2, "3V3")

c1 = load("Capacitor_SMD", "C_0805_2012Metric", "C1", "100n", 24.0, 3.0, 0)
set_pad_net(c1, 1, "3V3"); set_pad_net(c1, 2, "GND")

# ---------------- wire pads ----------------
wp = pcbnew.FOOTPRINT(board)
wp.SetReference("J1"); wp.SetValue("wires")
wp.SetPosition(wxPointMM(45.5, BOARD_W / 2))
tht_pad(wp, "BTN1", 44.0, 3.0, "BTN", drill=1.0, dia=1.9)
tht_pad(wp, "BTN2", 47.0, 3.0, "GND", drill=1.0, dia=1.9)
tht_pad(wp, "MOT+", 44.0, 16.5, "3V3", drill=1.0, dia=1.9)
tht_pad(wp, "MOT-", 47.0, 16.5, "MOT_SW", drill=1.0, dia=1.9)
wp.Reference().SetVisible(False); wp.Value().SetVisible(False)
xiao.Value().SetVisible(False)
board.Add(wp)

# ---------------- tracks ----------------
def track(net, pts, layer, w=0.3):
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(wxPointMM(*a)); t.SetEnd(wxPointMM(*b))
        t.SetLayer(layer); t.SetWidth(FromMM(w)); t.SetNet(nets[net])
        board.Add(t)

def via(net, x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(wxPointMM(x, y))
    v.SetDrill(FromMM(0.4)); v.SetWidth(FromMM(0.8))
    v.SetNet(nets[net]); board.Add(v)

F, B = pcbnew.F_Cu, pcbnew.B_Cu
p = {n: pad_xy(u2, i) for n, i in
     [("CS", 1), ("MISO", 2), ("WP", 3), ("GNDF", 4),
      ("MOSI", 5), ("SCK", 6), ("HOLD", 7), ("VCC", 8)]}

# CS: D2 top row -> U2.1 (left column). B vertical, via, F horizontal into pad.
cs = p["CS"]
track("CS", [(xp(2), ty), (xp(2), cs[1])], B); via("CS", xp(2), cs[1])
track("CS", [(xp(2), cs[1]), cs], F)
# MISO: D9 bottom row -> U2.2
mi = p["MISO"]
track("MISO", [(xp(4), by), (xp(4), mi[1])], B); via("MISO", xp(4), mi[1])
track("MISO", [(xp(4), mi[1]), mi], F)
# MOSI: D10 -> U2.5 (right column, wrap right). corners: (12,13.6)F,(33.5,13.6)B up,(33.5,p5y)F left
mo = p["MOSI"]
track("MOSI", [(xp(3), by), (xp(3), 13.6)], B); via("MOSI", xp(3), 13.6)
track("MOSI", [(xp(3), 13.6), (33.5, 13.6)], F); via("MOSI", 33.5, 13.6)
track("MOSI", [(33.5, 13.6), (33.5, mo[1])], B); via("MOSI", 33.5, mo[1])
track("MOSI", [(33.5, mo[1]), mo], F)
# SCK: D8 -> U2.6, wrap farther right
sk = p["SCK"]
track("SCK", [(xp(5), by), (xp(5), 14.4)], B); via("SCK", xp(5), 14.4)
track("SCK", [(xp(5), 14.4), (35.0, 14.4)], F); via("SCK", 35.0, 14.4)
track("SCK", [(35.0, 14.4), (35.0, sk[1])], B); via("SCK", 35.0, sk[1])
track("SCK", [(35.0, sk[1]), sk], F)
# BTN: D1 -> BTN1 pad. corners (6.92,5.6)
track("BTN", [(xp(1), ty), (xp(1), 5.6)], B); via("BTN", xp(1), 5.6)
track("BTN", [(xp(1), 5.6), (44.0, 5.6)], F); via("BTN", 44.0, 5.6)
track("BTN", [(44.0, 5.6), (44.0, 3.0)], B)
# HAP_CTRL: D3 -> R1.1. jog to x=13.3 on B, down, via, F to pad.
r1a = pad_xy(r1, 1); r1b = pad_xy(r1, 2)
track("HAP_CTRL", [(xp(3), ty), (13.3, ty), (13.3, r1a[1])], B)
via("HAP_CTRL", 13.3, r1a[1])
track("HAP_CTRL", [(13.3, r1a[1]), r1a], F)
# NPN_B: R1.2 -> Q1.1 (all F, short)
q1b = pad_xy(q1, 1); q1c = pad_xy(q1, 3)
track("NPN_B", [r1b, (q1b[0], r1b[1]), q1b], F)
# MOT_SW: Q1.3 -> D1.1 -> MOT- (all F, along y=18.4 for the wire pad leg)
d1a = pad_xy(d1, 1)
track("MOT_SW", [q1c, (d1a[0], q1c[1]), d1a], F)
track("MOT_SW", [d1a, (d1a[0], 18.4), (47.0, 18.4), (47.0, 16.5)], F)
# 3V3 stubs from B zone to F SMD pads (via + short F stub)
for tgt, vx, vy in [(p["WP"], p["WP"][0] - 1.8, p["WP"][1]),
                    (p["HOLD"], p["HOLD"][0] + 1.8, p["HOLD"][1]),
                    (p["VCC"], p["VCC"][0] + 1.8, p["VCC"][1]),
                    (pad_xy(c1, 1), pad_xy(c1, 1)[0], 1.4),
                    (pad_xy(d1, 2), pad_xy(d1, 2)[0] + 1.6, pad_xy(d1, 2)[1])]:
    via("3V3", vx, vy)
    track("3V3", [(vx, vy), tgt], F)

# ---------------- zones: GND on F.Cu, 3V3 on B.Cu ----------------
def zone(net, layer):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer); z.SetNet(nets[net])
    z.SetLocalClearance(FromMM(0.25))
    z.SetMinThickness(FromMM(0.25))
    pl = pcbnew.wxPoint_Vector()
    for x, y in [(0.3, 0.3), (BOARD_L - 0.3, 0.3),
                 (BOARD_L - 0.3, BOARD_W - 0.3), (0.3, BOARD_W - 0.3)]:
        pl.append(wxPointMM(x, y))
    z.AddPolygon(pl)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    board.Add(z)
    return z

zones = [zone("GND", F), zone("3V3", B)]

# ---------------- silkscreen ----------------
def silk(textstr, x, y, size=1.5):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(textstr); t.SetPosition(wxPointMM(x, y))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(wxSizeMM(size, size)); t.SetTextThickness(FromMM(0.25))
    board.Add(t)

silk("ANTICIPY", 46.0, 9.0, 1.8)
silk("V1", 46.0, 11.5, 1.0)
silk("BTN", 45.5, 1.2, 0.8)
silk("MOT", 45.5, 14.8, 0.8)

pcbnew.SaveBoard(OUT, board)
print("saved", OUT)

# Zone fill segfaults on an in-memory board in headless KiCad 6; reload first.
board2 = pcbnew.LoadBoard(OUT)
board2.BuildConnectivity()
filler = pcbnew.ZONE_FILLER(board2)
filler.Fill(board2.Zones())
pcbnew.SaveBoard(OUT, board2)
print("zones filled")

rep = os.path.join(HERE, "drc_report.txt")
pcbnew.WriteDRCReport(board2, rep, pcbnew.EDA_UNITS_MILLIMETRES, True)
txt = open(rep).read()
print(txt[-3000:])

# ---------------- gerbers + drill ----------------
GERBER_DIR = os.path.join(HERE, "gerbers")
os.makedirs(GERBER_DIR, exist_ok=True)
pc = pcbnew.PLOT_CONTROLLER(board2)
po = pc.GetPlotOptions()
po.SetOutputDirectory(GERBER_DIR)
po.SetPlotFrameRef(False)
po.SetUseGerberProtelExtensions(False)
po.SetUseAuxOrigin(False)
po.SetSubtractMaskFromSilk(True)
for layer, name in [(pcbnew.F_Cu, "F_Cu"), (pcbnew.B_Cu, "B_Cu"),
                    (pcbnew.F_SilkS, "F_Silkscreen"),
                    (pcbnew.B_SilkS, "B_Silkscreen"),
                    (pcbnew.F_Mask, "F_Mask"), (pcbnew.B_Mask, "B_Mask"),
                    (pcbnew.Edge_Cuts, "Edge_Cuts")]:
    pc.SetLayer(layer)
    pc.OpenPlotfile(name, pcbnew.PLOT_FORMAT_GERBER, name)
    pc.PlotLayer()
pc.ClosePlot()

drl = pcbnew.EXCELLON_WRITER(board2)
drl.SetMapFileFormat(pcbnew.PLOT_FORMAT_PDF)
drl.SetOptions(False, False, pcbnew.wxPoint(0, 0), False)
drl.SetFormat(True)
drl.CreateDrillandMapFilesSet(GERBER_DIR, True, False)
print("gerbers + drill written to", GERBER_DIR)

# ---------------- SVG render ----------------
po.SetOutputDirectory(HERE)
for layer, name in [(pcbnew.F_Cu, "render_F_Cu"), (pcbnew.B_Cu, "render_B_Cu")]:
    pc.SetLayer(layer)
    pc.OpenPlotfile(name, pcbnew.PLOT_FORMAT_SVG, name)
    pc.PlotLayer()
pc.ClosePlot()
print("done")
