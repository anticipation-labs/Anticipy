"""Datasheet-maximum mounted heights per footprint, and CPL-driven stack query.

The enclosure z-budget is derived from the real BOM instead of hand-entered
constants, so a component swap cannot silently break the fit.
"""
import csv
import os

CPL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "fab", "assembly", "anticipy_r1_cpl.csv",
)

# height above the mounting surface, datasheet max, mm
HEIGHT_BY_FOOTPRINT = {
    "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal": 3.31,
    "Raytac_MDBT50Q": 2.05,
    "Knowles_LGA-5_3.5x2.65mm": 0.98,
    "SW_SPST_EVQP7C": 1.35,
    "SOIC-8_5.3x5.3mm_P1.27mm": 2.16,
    "JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal": 3.00,
    "JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal": 3.00,
    "LGA-14_2x2mm_P0.35mm_LayoutBorder3x4y": 1.00,
    "VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm": 1.00,
    "SOT-23": 1.45,
    "SOT-23-5": 1.45,
    "SOT-23-6": 1.45,
    "D_SOD-323": 1.10,
    "LED_0603_1608Metric": 0.80,
    "C_0805_2012Metric": 1.45,
    "C_0603_1608Metric": 0.95,
    "C_0402_1005Metric": 0.55,
    "R_0402_1005Metric": 0.45,
}

# plan-view body extents per footprint, mm (used for keepout maths)
EXTENT_BY_FOOTPRINT = {
    "JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal": (6.0, 5.6),
    "JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal": (5.0, 5.6),
    "SOIC-8_5.3x5.3mm_P1.27mm": (5.4, 8.2),
    "LGA-14_2x2mm_P0.35mm_LayoutBorder3x4y": (2.2, 2.2),
    "SOT-23": (3.0, 3.0),
    "D_SOD-323": (2.7, 1.9),
    "C_0805_2012Metric": (2.4, 1.6),
    "C_0603_1608Metric": (1.9, 1.2),
    "C_0402_1005Metric": (1.3, 0.9),
    "R_0402_1005Metric": (1.3, 0.9),
}


def placements(pcb_l=47.0, pcb_w=18.0):
    """Yield (ref, layer, height, x, y, ex, ey) in enclosure-centered coords."""
    cx, cy = pcb_l / 2, -pcb_w / 2
    with open(os.path.normpath(CPL)) as f:
        for r in csv.DictReader(f):
            fp = r["Package"]
            if fp not in HEIGHT_BY_FOOTPRINT:
                raise KeyError(f"no height for footprint {fp} ({r['Designator']})")
            ex, ey = EXTENT_BY_FOOTPRINT.get(fp, (0.0, 0.0))
            if 45 < float(r["Rotation"]) % 180 < 135:
                ex, ey = ey, ex
            yield (
                r["Designator"], r["Layer"], HEIGHT_BY_FOOTPRINT[fp],
                float(r["Mid X"].replace("mm", "")) - cx,
                float(r["Mid Y"].replace("mm", "")) - cy,
                ex, ey,
            )


def tallest(layer):
    """(height, ref) of the tallest part on `layer` ("Top" / "Bottom")."""
    return max((h, ref) for ref, lay, h, *_ in placements() if lay == layer)


def bottom_extent_x():
    """(min_x, max_x) covered by bottom-side parts, incl. body extents."""
    xs = [(x - ex / 2, x + ex / 2)
          for _, lay, _, x, _, ex, _ in placements() if lay == "Bottom"]
    return min(a for a, _ in xs), max(b for _, b in xs)
