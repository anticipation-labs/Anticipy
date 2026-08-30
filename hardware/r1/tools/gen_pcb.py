"""Generate anticipy_r1.kicad_pcb from design.py using the pcbnew API.

Board: 47 x 18 mm, 4-layer (F.Cu / In1.Cu GND / In2.Cu 3V3 / B.Cu),
rounded corners r=3 mm, RF antenna keepout on the right end.
"""
import os
import sys

import pcbnew
from pcbnew import VECTOR2I, FromMM

import design

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "pcb", "anticipy_r1.kicad_pcb"))
LIB = "/usr/share/kicad/footprints"

W, H, R = 47.0, 18.0, 3.0          # board mm
ANT_X = 41.5                        # antenna keepout: x > ANT_X, all layers

# ref -> (x_mm, y_mm, rot_deg, side)  side: "F" or "B"
PLACEMENT = {
    # BLE module (front, right), antenna end extends into the keepout zone
    "U1":  (33.5, 9.0, 270, "F"),
    # USB-C on the left edge
    "J1":  (4.7, 9.0, 90, "F"),
    "R1":  (9.3, 2.0, 0, "F"),    # CC1 5.1k
    "R2":  (9.3, 16.0, 0, "F"),   # CC2 5.1k
    "U4":  (11.2, 9.5, 0, "F"),   # USB ESD
    # charger + LDO cluster (front, top-left)
    "U2":  (14.5, 5.5, 0, "F"),
    "R3":  (14.6, 2.2, 0, "F"),   # ISET
    "R4":  (16.8, 2.2, 0, "F"),   # ILIM
    "R5":  (19.0, 2.2, 0, "F"),   # /CHG pull-up
    "R6":  (18.5, 5.5, 90, "F"),  # /PGOOD pull-up
    "R7":  (10.5, 4.0, 0, "F"),   # TS 10k (DNP)
    "C1":  (11.8, 2.2, 0, "F"),   # VBUS in
    "C2":  (19.0, 8.5, 0, "F"),   # VSYS
    "C3":  (10.5, 13.2, 90, "F"),  # VBAT
    "U3":  (23.2, 5.3, 90, "F"),  # LDO
    "C4":  (23.0, 8.5, 0, "F"),   # 3V3 out
    "C5":  (21.6, 2.2, 0, "F"),   # LDO in
    # module decoupling (bottom, near module vias)
    "C6":  (33.0, 3.5, 0, "B"),
    "C7":  (33.0, 14.0, 0, "B"),
    "C8":  (26.5, 13.5, 0, "B"),
    # PDM microphones (front, bottom edge ports)
    "MK1": (19.7, 15.6, 0, "F"),
    "MK2": (23.4, 15.6, 0, "F"),
    "C9":  (19.7, 15.6, 0, "B"),
    "C10": (23.4, 15.6, 0, "B"),
    # SPI flash (bottom side, under module area)
    "U5":  (28.5, 9.0, 0, "B"),
    "C11": (29.2, 4.5, 0, "B"),
    # accelerometer (bottom)
    "U6":  (22.2, 9.0, 0, "B"),
    "R8":  (21.5, 6.5, 0, "B"),   # SDA pu
    "R9":  (21.5, 11.5, 0, "B"),  # SCL pu
    "C12": (23.6, 5.4, 0, "B"),
    # LEDs (front, centre, under light pipe)
    "D1":  (20.0, 10.4, 0, "F"),
    "R10": (17.4, 10.4, 0, "F"),
    "D2":  (20.0, 12.6, 0, "F"),
    "R11": (17.4, 12.6, 0, "F"),
    # user button (front, bottom edge left of mics)
    "SW1": (15.1, 15.4, 0, "F"),
    # haptic driver (bottom)
    "Q1":  (17.5, 9.5, 0, "B"),
    "R12": (15.6, 6.8, 0, "B"),
    "R13": (16.5, 13.5, 0, "B"),
    "D3":  (20.5, 13.5, 0, "B"),
    # connectors (bottom side): battery JST-SH-3, haptic JST-SH-2
    "J2":  (11.3, 7.5, 270, "B"),
    "J3":  (12.0, 14.9, 180, "B"),
    "R14": (4.5, 14.5, 0, "B"),   # VBAT sense divider
    "R15": (4.5, 16.3, 0, "B"),
    "C13": (7.0, 15.5, 90, "B"),
    # Tag-Connect pads (bottom, under module)
    "J4":  (35.3, 8.6, 90, "B"),
}


def build():
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(4)
    ds.SetBoardThickness(FromMM(0.8))

    # nets
    netmap = {}

    def net(name):
        if name not in netmap:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            netmap[name] = n
        return netmap[name]

    # footprints
    for c in design.COMPONENTS:
        lib, fpname = c["fp"].split(":")
        fp = pcbnew.FootprintLoad(os.path.join(LIB, lib + ".pretty"), fpname)
        fp.SetReference(c["ref"])
        fp.SetValue(c["value"])
        x, y, rot, side = PLACEMENT[c["ref"]]
        board.Add(fp)
        fp.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        if side == "B":
            fp.Flip(fp.GetPosition(), False)
        fp.SetOrientationDegrees(rot)
        pins = c["pins"]
        for pad in fp.Pads():
            name = pad.GetName()
            if name in pins and pins[name]:
                pad.SetNet(net(pins[name]))
    board.BuildListOfNets()

    # board outline: rounded rect
    def seg(x1, y1, x2, y2):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(VECTOR2I(FromMM(x1), FromMM(y1)))
        s.SetEnd(VECTOR2I(FromMM(x2), FromMM(y2)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(FromMM(0.1))
        board.Add(s)

    def arc(cx, cy, sx, sy, angle):
        a = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        a.SetCenter(VECTOR2I(FromMM(cx), FromMM(cy)))
        a.SetStart(VECTOR2I(FromMM(sx), FromMM(sy)))
        a.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T), False)
        a.SetLayer(pcbnew.Edge_Cuts)
        a.SetWidth(FromMM(0.1))
        board.Add(a)

    seg(R, 0, W - R, 0)
    seg(W, R, W, H - R)
    seg(W - R, H, R, H)
    seg(0, H - R, 0, R)
    arc(R, R, 0, R, 90)
    arc(W - R, R, W - R, 0, 90)
    arc(W - R, H - R, W, H - R, 90)
    arc(R, H - R, R, H, 90)

    # antenna keepout zone (all copper layers), x > ANT_X
    kz = pcbnew.ZONE(board)
    kz.SetIsRuleArea(True)
    kz.SetDoNotAllowCopperPour(True)
    kz.SetDoNotAllowTracks(True)
    kz.SetDoNotAllowVias(True)
    kz.SetDoNotAllowPads(False)
    kz.SetDoNotAllowFootprints(False)
    lset = pcbnew.LSET()
    for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        lset.AddLayer(l)
    kz.SetLayerSet(lset)
    pts = [(ANT_X, 0.0), (W, 0.0), (W, H), (ANT_X, H)]
    outline = kz.Outline()
    outline.NewOutline()
    for x, y in pts:
        outline.Append(FromMM(x), FromMM(y))
    board.Add(kz)

    # copper pours: GND on In1 + F + B, +3V3 on In2
    def pour(layer, netname, prio):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(net(netname))
        z.SetAssignedPriority(prio)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL
                           if layer in (pcbnew.In1_Cu, pcbnew.In2_Cu)
                           else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetMinThickness(FromMM(0.15))
        z.SetLocalClearance(FromMM(0.2))
        o = z.Outline()
        o.NewOutline()
        for x, y in [(0, 0), (W, 0), (W, H), (0, H)]:
            o.Append(FromMM(x), FromMM(y))
        board.Add(z)
        return z

    pour(pcbnew.In1_Cu, "GND", 0)
    pour(pcbnew.In2_Cu, "+3V3", 0)
    pour(pcbnew.F_Cu, "GND", 0)
    pour(pcbnew.B_Cu, "GND", 0)

    # design rules
    ds.m_TrackMinWidth = FromMM(0.127)
    ds.m_ViasMinSize = FromMM(0.45)
    ds.m_MinThroughDrill = FromMM(0.2)
    ds.m_MinClearance = FromMM(0.127)
    ds.m_CopperEdgeClearance = FromMM(0.1)
    ds.m_NetSettings.GetDefaultNetclass().SetClearance(FromMM(0.127))
    ds.m_NetSettings.GetDefaultNetclass().SetTrackWidth(FromMM(0.15))
    ds.m_NetSettings.GetDefaultNetclass().SetViaDiameter(FromMM(0.5))
    ds.m_NetSettings.GetDefaultNetclass().SetViaDrill(FromMM(0.25))

    board.SetFileName(OUT)
    pcbnew.SaveBoard(OUT, board)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
