// ═══════════════════════════════════════════════════════════════════════════
//  anticipy_proto_nrf52840.scad — Anticipy prototype pendant (v1 hardware)
//
//  Matches the ACTUAL parts in hand (verified from photos + datasheets):
//    • Seeed Studio XIAO nRF52840 Sense — PCB 21.0 x 17.8 mm, ~4.5 mm tall
//      (USB-C is the tallest part). Headers currently soldered: pins extend
//      ~9 mm below the PCB. Set with_headers=true for the as-is board.
//    • LiPo 752042 — 8.0 x 20 x 43 mm, 500 mAh, 3.7 V (leads exit short edge)
//
//  Two-part pill ("stadium") shell, jewelry-style like the machined titanium
//  unit: front shell + snap-in back lid + optional magnetic chain cap.
//
//  Internal stack (front → back):
//    front wall | XIAO (components toward front: mic/LED/RST face out)
//    | header pins (if any) | 1 mm foam | battery | 1 mm foam | back lid
//
//  Print (Bambu Lab P1S/P2S):
//    Material: PETG (recommended, LiPo-safe temps) or Silk PLA silver (looks)
//    0.12–0.16 mm layers, 4 walls, 25% gyroid, NO supports needed:
//    print front shell face-down, lid inner-face-up, chain cap flat.
//
//  Render targets (set PART below or use -D 'PART="..."' on CLI):
//    "shell"  front shell        "lid"   back lid
//    "cap"    magnetic chain cap "all"   exploded preview
// ═══════════════════════════════════════════════════════════════════════════

$fn = 90;

// ─── Config ─────────────────────────────────────────────────────────────────
PART = "all";           // "shell" | "lid" | "cap" | "all"
with_headers = true;    // true = board with soldered headers (as photographed)
                        // false = slim build (headers removed / pins clipped)

// ─── Verified component dimensions (+ printer clearances) ──────────────────
clr        = 0.35;      // per-side clearance for FDM fit

// XIAO nRF52840 Sense
xiao_l     = 21.0;      // along pendant length (USB-C exits one short edge)
xiao_w     = 17.8;
xiao_h_bare    = 5.0;   // PCB + USB-C shield toward front
header_pin_h   = 9.0;   // pins protruding behind PCB when headers stay on
xiao_zone_h    = with_headers ? xiao_h_bare + header_pin_h : xiao_h_bare + 1.0;

// LiPo 752042 (8.0 x 20 x 43, leads exit a short edge)
batt_l     = 43.0;
batt_w     = 20.0;
batt_h     = 8.0;
foam_t     = 1.0;       // 1 mm EVA foam pad each side of the battery (padding)

// Wire channel between board bay and battery bay
wire_ch_w  = 8.0;
wire_ch_d  = 3.0;

// ─── Derived shell dimensions ───────────────────────────────────────────────
wall       = 2.0;       // side wall
front_t    = 1.6;       // front face
lid_t      = 1.8;       // back lid plate
lip_h      = 2.4;       // lid friction lip height
lip_clr    = 0.20;      // lip fit clearance (tuned for PETG on P-series)

cav_l      = max(batt_l, xiao_l + 1.5) + 2*clr;              // ≈ 43.7
cav_w      = max(batt_w, xiao_w) + 2*clr;                    // ≈ 20.7
cav_h      = xiao_zone_h + foam_t + batt_h + foam_t + 0.5;   // stack depth

body_l     = cav_l + 2*wall;                                 // ≈ 47.7
body_w     = cav_w + 2*wall;                                 // ≈ 24.7
body_h     = front_t + cav_h + lip_h;                        // shell depth
edge_r     = 2.2;       // outer edge rounding (pebble feel)

// ─── Feature positions ──────────────────────────────────────────────────────
// Origin: center of front face, +Z into the case, +X toward USB-C end.
usb_w      = 10.0;      // USB-C cutout in the +X end wall
usb_h      = 4.2;
usb_z      = front_t + 1.2;      // board sits on 1.2 mm front standoff ribs

mic_x      = -3.0;      // PDM mic ~center of component side
led_x      =  3.5;      // charge/user LED window
rst_x      = -6.5;      // reset button pinhole

// Chain lug (top long edge, -Y side ... lug on the short edge opposite USB)
lug_r      = 3.6;
lug_hole_d = 4.6;       // fits 4–5 mm chain / split ring — plain fallback
magnet_d   = 6.0 + 0.3; // 6 x 2 mm N52 disc magnets (snap-on chain cap)
magnet_h   = 2.0 + 0.2;
mag_space  = 10.0;      // center-to-center of the two magnet pockets

// ─── Helpers ────────────────────────────────────────────────────────────────
// Rounded-rectangle prism (the battery is rectangular, so the cavity must be
// a rounded RECT, not a pill — a pill's round ends would clip the cell corners)
module rrect(l, w, h, r) {
    hull() for (x = [-(l/2 - r), (l/2 - r)]) for (y = [-(w/2 - r), (w/2 - r)])
        translate([x, y, 0]) cylinder(r = r, h = h);
}
module pebble(l, w, h, cr, er) {    // rounded-rect prism w/ rounded edges, z 0..h
    translate([0, 0, er]) minkowski() {
        rrect(l - 2*er, w - 2*er, h - 2*er, cr - er);
        sphere(r = er);
    }
}

// ─── Front shell ────────────────────────────────────────────────────────────
module front_shell() {
    difference() {
        // outer pebble body (corner radius 7 = jewelry pebble look)
        pebble(body_l, body_w, body_h, 7, edge_r);

        // main cavity
        translate([0, 0, front_t]) rrect(cav_l, cav_w, body_h, 3);

        // lid lip rebate (wider ledge at the back)
        translate([0, 0, body_h - lip_h])
            rrect(cav_l + wall, cav_w + wall, lip_h + 0.1, 3.5);

        // USB-C cutout, +X end wall at board level
        translate([body_l/2 - wall - 1, -usb_w/2, usb_z])
            cube([wall + 3, usb_w, usb_h]);

        // mic port: 3 x Ø1.2 through the front face over the mic
        for (dy = [-2, 0, 2])
            translate([mic_x, dy, -1]) cylinder(d = 1.2, h = front_t + 2);

        // LED light window (thin membrane: leave 0.6 mm for glow-through)
        translate([led_x, 0, 0.6]) cylinder(d = 2.6, h = front_t);

        // RST pinhole
        translate([rst_x, 0, -1]) cylinder(d = 1.6, h = front_t + 2);
    }

    // board standoff ribs: two 1.2 mm ribs under the XIAO's long edges
    for (dy = [-xiao_w/2 + 1, xiao_w/2 - 1])
        translate([xiao_l/2 - cav_l/2 + 6, dy - 0.8, front_t])
            cube([xiao_l - 4, 1.6, 1.2]);

    // battery bay corner cradles (keep cell centered; foam wraps it)
    crad_h = front_t + xiao_zone_h + foam_t;
    for (dx = [-batt_l/2 - clr, batt_l/2 + clr - 1.5])
        for (dy = [-batt_w/2 - clr, batt_w/2 + clr - 1.5])
            translate([dx, dy, crad_h - 2]) cube([1.5, 1.5, 2]);

    // chain lug with plain hole + magnet pockets, on the -X end
    translate([-body_l/2 - 1.5, 0, body_h/2]) chain_lug();
}

module chain_lug() {
    difference() {
        hull() {
            rotate([90, 0, 0]) cylinder(r = lug_r, h = 7, center = true);
            translate([3, 0, 0]) rotate([90, 0, 0])
                cylinder(r = lug_r + 1.2, h = 9, center = true);
        }
        // plain chain hole (always there — zero-failure fallback)
        rotate([90, 0, 0]) cylinder(d = lug_hole_d, h = 30, center = true);
        // magnet pockets on both flat faces (glue 6x2 magnets, N-out)
        for (s = [-1, 1])
            translate([1.5, s * 4.5, 0]) rotate([s * 90, 0, 0])
                translate([0, 0, -0.01]) cylinder(d = magnet_d, h = magnet_h);
    }
}

// ─── Back lid ───────────────────────────────────────────────────────────────
module back_lid() {
    difference() {
        union() {
            // outer plate flush with shell back
            rrect(cav_l + wall - lip_clr, cav_w + wall - lip_clr, lid_t, 3.5);
            // friction lip that drops into the cavity
            translate([0, 0, lid_t])
                rrect(cav_l - lip_clr, cav_w - lip_clr, lip_h - 0.4, 3);
        }
        // hollow the lip so it becomes a perimeter ring
        translate([0, 0, lid_t - 0.01])
            rrect(cav_l - 2*wall, cav_w - 2*wall, lip_h + 1, 2);
        // pry notch on +X edge
        translate([cav_l/2 - 2, 0, -0.01]) cylinder(d = 7, h = 0.9);
    }
    // 4 snap nubs on the lip (flex-fit into shell)
    for (dx = [-cav_l/2 + 8, cav_l/2 - 8]) for (s = [-1, 1])
        translate([dx, s * (cav_w/2 - lip_clr - 0.2), lid_t + lip_h - 1.2])
            sphere(d = 1.2);
}

// ─── Magnetic chain cap (optional snap-on for the chain) ───────────────────
// Small saddle that carries the chain; two 6x2 magnets snap it onto the lug.
module chain_cap() {
    difference() {
        hull() {
            rotate([90, 0, 0]) cylinder(r = lug_r + 2.4, h = 12, center = true);
            translate([0, 0, 5]) rotate([90, 0, 0])
                cylinder(r = 2.5, h = 12, center = true);
        }
        // clearance slot that straddles the lug
        hull() {
            rotate([90, 0, 0]) cylinder(r = lug_r + 0.3, h = 9.4 + 0.6, center = true);
            translate([0, 0, -6]) rotate([90, 0, 0])
                cylinder(r = lug_r + 0.3, h = 9.4 + 0.6, center = true);
        }
        // chain bar hole through the top
        translate([0, 0, 5]) rotate([90, 0, 0])
            cylinder(d = lug_hole_d, h = 30, center = true);
        // magnet pockets on the inner faces (mirror of lug pockets)
        for (s = [-1, 1])
            translate([1.5, s * (9.4/2 + 0.6/2), 0]) rotate([-s * 90, 0, 0])
                translate([0, 0, -0.01]) cylinder(d = magnet_d, h = magnet_h);
    }
}

// ─── Output ─────────────────────────────────────────────────────────────────
if (PART == "shell") front_shell();
else if (PART == "lid") back_lid();
else if (PART == "cap") chain_cap();
else {
    front_shell();
    translate([0, 0, body_h + 8]) rotate([0, 180, 0]) back_lid();
    translate([-body_l/2 - 18, 0, body_h/2]) chain_cap();
}

// Echo key numbers so slicer sanity-check is easy
echo(str("BODY (L x W x D mm): ", body_l, " x ", body_w, " x ", body_h));
echo(str("CAVITY: ", cav_l, " x ", cav_w, " x ", cav_h, "  with_headers=", with_headers));
