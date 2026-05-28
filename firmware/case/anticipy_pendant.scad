// ═══════════════════════════════════════════════════════════════════════════
//  anticipy_pendant.scad — Anticipy Pendant case design
//
//  Parametric OpenSCAD model for the wearable pendant enclosure.
//  Two-part design: front_shell() + back_plate()
//
//  Print orientation: front face DOWN on the build plate (no supports needed
//  except for mic port overhang; enable support enforcers on that feature only)
//
//  Recommended: PETG, 0.15mm layer height, 3 perimeters, 20% gyroid infill
//
//  Usage:
//    OpenSCAD → render front shell:  comment out back_plate() call
//    OpenSCAD → render back plate:   comment out front_shell() call
//    Thingiverse export: render both for preview, export separately for print
// ═══════════════════════════════════════════════════════════════════════════

$fn = 60;  // Smooth curves (increase to 120 for final render, slower)

// ─── Core dimensions ────────────────────────────────────────────────────────
body_w   = 38.0;   // Width  (left-right when worn)
body_h   = 25.0;   // Height (top-bottom)
body_d   = 11.0;   // Depth  (front to back, thinnest dimension)
corner_r = 4.0;    // Corner radius

wall_t      = 1.5;    // Shell wall thickness
floor_t     = 1.5;    // Floor/ceiling thickness
snap_depth  = 0.8;    // Snap lip depth on back plate
snap_width  = 1.0;    // Snap lip width

// ─── Component clearances ────────────────────────────────────────────────────
// XIAO ESP32-S3: 21.0 × 17.5 × 3.5mm (PCB only) + components above ~10mm total
xiao_w = 22.0;
xiao_h = 18.5;
xiao_d = 10.5;  // Clearance for tallest component (USB-C on board underside)

// LiPo 400mAh LP402035: 4.5 × 20 × 35mm
lipo_w = 21.0;
lipo_h = 36.0;
lipo_d = 5.5;

// ─── Feature positions (from center of front face) ──────────────────────────
// Positive X = right, positive Y = up (when pendant hangs normally)

mic_x        =  0.0;    // Centered horizontally
mic_y        = -8.0;    // Lower half
mic_dia      =  1.5;    // Mic port diameter

led_x        =  12.0;   // Right side
led_y        =  9.0;    // Upper area
led_dia      =  2.5;    // LED diffuser window diameter

btn_a_x      = -12.0;   // Left side (mirror of LED)
btn_a_y      =  9.0;
btn_a_dia    =  2.0;    // Button actuation hole

usbc_w       = 10.0;    // USB-C port width cutout
usbc_h       =  3.8;    // USB-C port height cutout
usbc_y_off   = body_h/2 - wall_t - 0.5;  // Bottom edge

lanyard_dia  =  4.5;    // Lanyard split-ring hole
lanyard_y    =  body_h/2 - 2.5;    // Top edge, centered in ear

// ─── Helpers ────────────────────────────────────────────────────────────────

// Rounded rectangle prism (hull of 4 cylinders)
module rounded_box(w, h, d, r) {
    hull() {
        for (xi = [-(w/2 - r), (w/2 - r)]) {
            for (yi = [-(h/2 - r), (h/2 - r)]) {
                translate([xi, yi, 0])
                    cylinder(r = r, h = d);
            }
        }
    }
}

// Rounded rectangle 2D (for extrusion)
module rounded_rect_2d(w, h, r) {
    hull() {
        for (xi = [-(w/2 - r), (w/2 - r)]) {
            for (yi = [-(h/2 - r), (h/2 - r)]) {
                translate([xi, yi])
                    circle(r = r);
            }
        }
    }
}

// ─── Interior cavity ─────────────────────────────────────────────────────────
// The hollow inside of the front shell
module interior_cavity() {
    inner_w = body_w - wall_t * 2;
    inner_h = body_h - wall_t * 2;
    inner_d = body_d - floor_t;
    inner_r = corner_r - wall_t;

    translate([0, 0, floor_t])
        rounded_box(inner_w, inner_h, inner_d + 1, max(inner_r, 0.5));
}

// ─── Front shell ─────────────────────────────────────────────────────────────
module front_shell() {
    difference() {
        // Outer body
        rounded_box(body_w, body_h, body_d, corner_r);

        // Hollow out interior
        interior_cavity();

        // ── Mic port ──────────────────────────────────────────────────────
        // Angled 30° toward front so ambient sound enters cleanly
        translate([mic_x, mic_y, 0])
            rotate([-30, 0, 0])
                cylinder(d = mic_dia, h = wall_t * 3, center = true);

        // ── LED diffuser window ───────────────────────────────────────────
        // Conical bore: wider on inside for light spread
        translate([led_x, led_y, 0]) {
            cylinder(d = led_dia, h = wall_t + 0.1);
            // Widen inner face for diffusion (cone from inside)
            translate([0, 0, wall_t * 0.4])
                cylinder(d1 = led_dia, d2 = led_dia + 1.5, h = wall_t * 0.8);
        }

        // ── Button A actuation hole ───────────────────────────────────────
        translate([btn_a_x, btn_a_y, 0])
            cylinder(d = btn_a_dia, h = wall_t + 0.1);

        // ── USB-C cutout (bottom edge) ─────────────────────────────────────
        translate([-usbc_w/2, body_h/2 - usbc_h - wall_t + 0.5, 0])
            cube([usbc_w, usbc_h + wall_t, body_d + 0.2]);

        // ── Back plate rebate (step for back plate to snap into) ──────────
        inner_r = corner_r - wall_t;
        translate([0, 0, body_d - snap_depth])
            difference() {
                rounded_box(body_w + 0.1, body_h + 0.1, snap_depth + 0.1, corner_r);
                rounded_box(body_w - wall_t * 2 + snap_width * 2,
                            body_h - wall_t * 2 + snap_width * 2,
                            snap_depth + 0.2,
                            max(inner_r + snap_width, 0.5));
            }

        // ── PCB mounting posts clearance (avoid interference) ─────────────
        // The XIAO sits in the center of the cavity; its USB-C port exits bottom
        // We cut clearance for the USB-C port on the XIAO board itself
        translate([-xiao_w/2, -xiao_h/2 + 2, floor_t - 0.1])
            cube([xiao_w, xiao_h, xiao_d + 0.1]);
    }

    // ── Lanyard ear (top center protrusion with hole) ──────────────────────
    translate([0, body_h/2, body_d/2]) {
        difference() {
            // Ear lug
            hull() {
                sphere(r = 3.5);
                translate([0, 2.5, 0]) sphere(r = 2.5);
            }
            // Lanyard hole (horizontal, parallel to front face)
            rotate([0, 90, 0])
                cylinder(d = lanyard_dia, h = body_w + 2, center = true);
        }
    }

    // ── Internal PCB standoffs ────────────────────────────────────────────
    // 4 posts in corners of XIAO footprint, 2mm high, for PCB to rest on
    standoff_h = 2.5;
    standoff_r = 1.2;
    for (xi = [-xiao_w/2 + 1.5, xiao_w/2 - 1.5]) {
        for (yi = [-xiao_h/2 + 1.5, xiao_h/2 - 1.5]) {
            translate([xi, yi, floor_t])
                cylinder(r = standoff_r, h = standoff_h);
        }
    }
}

// ─── Back plate ───────────────────────────────────────────────────────────────
module back_plate() {
    inner_w = body_w - wall_t * 2 + snap_width * 2;
    inner_h = body_h - wall_t * 2 + snap_width * 2;
    inner_r = max(corner_r - wall_t + snap_width, 0.5);
    plate_t = 1.2;    // Back plate thickness

    difference() {
        // The snap-lip that fits into the front shell rebate
        translate([0, 0, 0])
            rounded_box(inner_w, inner_h, snap_depth + plate_t, inner_r);

        // Hollow the snap lip (only a perimeter remains)
        inner2_w = inner_w - wall_t * 2;
        inner2_h = inner_h - wall_t * 2;
        translate([0, 0, plate_t])
            rounded_box(inner2_w, inner2_h, snap_depth + 1, max(inner_r - wall_t, 0.5));

        // Battery access notch (small finger indent to pry the plate off)
        translate([0, -(inner_h/2), snap_depth/2 + plate_t/2])
            rotate([90, 0, 0])
                cylinder(d = 8, h = wall_t + 0.2);
    }

    // Foam pad boss (3mm × 20mm × 30mm recess to hold adhesive foam)
    // (foam protects LiPo from vibration; add 3M VHB tape between foam and battery)
}

// ─── Assembly preview ─────────────────────────────────────────────────────────
// Render both parts slightly exploded to check fit

module assembly_preview() {
    color("black", 0.8) front_shell();
    color("gray",  0.7) translate([0, 0, body_d + 5]) back_plate();
}

// ─── Cross-section view for internal fit check ─────────────────────────────
module cross_section() {
    intersection() {
        assembly_preview();
        translate([-100, 0, -1]) cube([200, 200, 200]);
    }
}

// ─── What to render ───────────────────────────────────────────────────────────
// Uncomment ONE of the following lines:

assembly_preview();       // Full preview (both parts)
//front_shell();          // Print this first
//back_plate();           // Print this separately
//cross_section();        // Internal fit check
