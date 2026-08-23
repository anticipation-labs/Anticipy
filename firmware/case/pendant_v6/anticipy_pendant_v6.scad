/* Anticipy pendant v6 — same proven v5.1 pill body, new closures.
 *
 * Changes vs v5.1:
 *  - The separate glued seating ring is GONE. The back half now carries an
 *    integral lip (tongue) that seats into a groove in the front half.
 *    One less part, no glue, self-aligning.
 *  - Three closure mechanisms (MECH) — no snap ridges, no tiny features:
 *      "friction": plain lip with a tighter (coupon-tuned) clearance.
 *                  Clean press-together fit, pry notch to open.
 *      "magnet" : lip for alignment + 2 pairs of 5x2 mm disc magnet pockets
 *                 in the solid chain end. Silent, infinite reopen.
 *                 (Glue magnets in with CA, alternating polarity.)
 *      "screw"  : lip + 2 hidden M1.4x4 screws from the back into the solid
 *                 chain end (v5 style, but with the integral lip).
 *  - USB opening enlarged to 14.0 x 8.0 (research: real cable overmolds
 *    measure up to 13.0 x 7.4 and sit off-center in the molding).
 *  - Pry notch at the bottom end of the seam on every variant.
 *
 * PINS = false: XIAO header pins clipped flush (slim pendant).
 * PINS = true : headers left ON — the front bay is 9 mm deeper so the pins
 *               (pointing up into the front dome) clear; board still sits at
 *               the parting plane so the USB opening lines up. Back halves
 *               are IDENTICAL between the two, so any back mates with either.
 * Both halves print rim-down / visible face UP: zero supports.
 *
 * PART = "front" | "back" | "both" | "coupon"
 * BATT = "200" | "500"
 * MECH = "friction" | "magnet" | "screw"
 */

PART    = "both";
BATT    = "500";
MECH    = "friction";
PINS    = false;
XTRA_L  = 20.0;     // extra internal cavity length (user: "2 cm taller")
XTRA_W  = 10.0;     // extra internal cavity width  (user: "1 cm wider")
LID_CLR = 0.25;      // per-side lip clearance from the coupon test
fit_clr = (MECH == "friction") ? LID_CLR - 0.10 : LID_CLR;  // friction grips tighter
$fn = $preview ? 48 : 128;

/* ---------- hardware (headers CLIPPED FLUSH) ---------- */
xiao_l = 21.0;  xiao_w = 17.8;
board_stack = PINS ? 15.6 : 6.6;   // 6.6 clipped; +9.0 for standing headers
b200 = [31.0, 20.5, 6.0];
b500 = [44.0, 20.5, 8.5];
bat  = (BATT == "200") ? b200 : b500;

/* ---------- derived (identical body math to v5.1 — print-proven) ---------- */
wall    = 1.8;
lip_t   = 1.2;  lip_h = 2.2;
re      = 2.2;
dome    = 1.0;
gr      = 4.6;

cav_l   = max(xiao_l, bat[0]) + 2.5 + XTRA_L;
cav_w   = max(xiao_w, bat[1]) + 1.2 + XTRA_W;
front_d = board_stack + 0.6;
back_d  = bat[2] + 0.6;
face    = re + dome;

outer_w = cav_w + 2*(wall + lip_t);
em      = outer_w/2 - (gr - lip_t - LID_CLR);
outer_l = cav_l + 2*em;
outer_t = front_d + back_d + 2*face;
zc      = (front_d - back_d)/2;
cx      = 0;

chain_x = outer_l/2 - 5.8;
chain_d = 4.5;
bx = cx - cav_l/2 + xiao_l/2;
anchor_x = cx + cav_l/2 + 3.0;    // screw / magnet center in the solid chain end
back_t  = back_d + face;

mag_d   = 5.2;  mag_h = 2.1;      // pocket for a 5 x 2 mm disc magnet
mag_x   = cav_l/2 + lip_t + LID_CLR + 0.8 + mag_d/2;  // clears groove outer wall
mag_y   = 6.2;                    // clears the 4.5 mm chain hole by >0.8 mm

echo(str("V6 ", BATT, "mAh / ", MECH, "  ", outer_l, " x ", outer_w, " x ", outer_t));

/* ---------- primitives ---------- */
module stadium(l, w) offset(r = w/2) square([l - w, 0.01], center = true);

module body()
    translate([0, 0, zc]) minkowski() {
        hull() {
            translate([0, 0, -(outer_t/2 - re - dome)])
                linear_extrude(2*(outer_t/2 - re - dome))
                    stadium(outer_l - 2*re, outer_w - 2*re);
            for (s = [-1, 1]) {
                translate([0, 0, s*(outer_t/2 - re - dome*0.45) - 0.05]) linear_extrude(0.1)
                    stadium(outer_l - 2*re - 1.6, outer_w - 2*re - 1.6);
                translate([0, 0, s*(outer_t/2 - re - dome*0.12) - 0.05]) linear_extrude(0.1)
                    stadium(outer_l - 2*re - 4, outer_w - 2*re - 4);
                translate([0, 0, s*(outer_t/2 - re) - 0.05]) linear_extrude(0.1)
                    stadium(outer_l - 2*re - 7, outer_w - 2*re - 7);
            }
        }
        sphere(r = re);
    }

module rrect(l, w, rr) offset(r = rr) square([l - 2*rr, w - 2*rr], center = true);

module cavity() {
    translate([cx, 0, -back_d]) linear_extrude(back_d + 0.01)
        rrect(cav_l, cav_w, 4);
    translate([cx, 0, -0.01]) linear_extrude(front_d + 0.02)
        rrect(cav_l, cav_w, 4);
}

module chain_opening()
    translate([chain_x, 0, -outer_t]) cylinder(d = chain_d, h = 2*outer_t);

module usb_slot() {      // 14 x 8: passes any compliant cable overmold
    usb_w = 14.0; usb_h = 8.0;
    depth = (cx - cav_l/2) - (-outer_l/2 - 2) + 2;
    translate([-outer_l/2 - 2, -usb_w/2, 0])
        cube([depth, usb_w, usb_h]);
    // chamfered lead-in at the outer face: crisp edge, no fuzzing
    hull() {
        translate([-outer_l/2 - 2, -(usb_w + 2.4)/2, -1.2])
            cube([0.01, usb_w + 2.4, usb_h + 2.4]);
        translate([-outer_l/2 + 1.2, -usb_w/2, 0])
            cube([0.01, usb_w, usb_h]);
    }
}

module front_holes() {
    translate([bx - 2.0, 0, 0]) cylinder(d = 2.0, h = outer_t);           // LED
    translate([bx + 3.0, 4.0, 0]) cylinder(d = 1.0, h = outer_t);         // mic
    translate([bx + 3.0, 4.0, front_d - 0.1]) cylinder(d = 4.0, h = 1.0); // acoustic recess
}

module pry_notch()       // thumbnail slot at the USB end of the seam
    translate([-outer_l/2 - 1, -5, -1.0]) cube([2.2, 10, 1.0]);

/* lip cross-section; grow>0 widens both faces (used for the front groove) */
module lip_section(grow = 0)
    difference() {
        translate([cx, 0]) rrect(cav_l + 2*lip_t + 2*grow, cav_w + 2*lip_t + 2*grow, gr);
        translate([cx, 0]) rrect(cav_l - 2*grow, cav_w - 2*grow, 4);
    }

/* integral lip on the back half (tongue), with USB passage notch */
module lip_tongue() {
    difference() {
        linear_extrude(lip_h) lip_section(-0.02);
        translate([cx - cav_l/2 - 4, -7.5, -0.1]) cube([6, 15, lip_h + 1]);
    }
}

/* groove in the front half — plain, clearance set by mechanism */
module lip_groove()
    linear_extrude(lip_h + 0.05) lip_section(fit_clr);

module magnet_pockets(half)   // 2 pockets per half in the solid chain end
    for (sy = [-1, 1])
        translate([mag_x, sy*mag_y, half == "front" ? -0.05 : -mag_h + 0.05])
            cylinder(d = mag_d, h = mag_h);

/* ---------- halves ---------- */
module front_half()
    difference() {
        intersection() { body(); translate([-500, -500, 0]) cube(1000); }
        cavity();
        chain_opening();
        usb_slot();
        front_holes();
        translate([0, 0, -0.05]) lip_groove();
        pry_notch();
        if (MECH == "magnet") magnet_pockets("front");
        if (MECH == "screw")
            for (sy = [-1, 1])
                translate([anchor_x, sy*4.5, -0.1]) cylinder(d = 1.15, h = 3.0);
    }

module back_half()
    union() {
        difference() {
            intersection() { body(); translate([-500, -500, -1000]) cube(1000); }
            cavity();
            chain_opening();
            if (MECH == "magnet") magnet_pockets("back");
            if (MECH == "screw")
                for (sy = [-1, 1]) {
                    translate([anchor_x, sy*4.5, -outer_t]) cylinder(d = 1.6, h = 2*outer_t);
                    translate([anchor_x, sy*4.5, -back_t - 0.5])
                        cylinder(d = 3.0, h = back_t - 2.0 + 0.5);
                }
        }
        lip_tongue();
    }

module coupon() {   // lip-fit test: bar = the real lip wall; 3 slots
    cls = [0.15, 0.25, 0.35];
    translate([-12, -14, 0]) cube([24, lip_t - 0.04, lip_h]);
    for (i = [0:2]) translate([-12, i*10 - 8, 0])
        difference() {
            cube([24, 8, lip_h + 1.8]);
            translate([2, 4 - (lip_t/2 + cls[i]), 1.8])
                cube([20, lip_t + 2*cls[i], lip_h + 1]);
            translate([4, 5.3, lip_h + 1.2]) linear_extrude(0.7)
                text(str(cls[i]), size = 2.6);
        }
}

/* ---------- output ---------- */
if (PART == "front") front_half();
if (PART == "back")  rotate([180, 0, 0]) back_half();
if (PART == "coupon") coupon();
if (PART == "both") {
    front_half();
    color("lightpink") back_half();
}
