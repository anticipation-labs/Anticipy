/* Anticipy pendant v4 — true pebble clamshell.
 *
 * REQUIRED PREP: clip the header pins flush off the XIAO (flush cutters,
 * ~2 min, no soldering). A pendant-shaped object cannot contain 9 mm pins.
 *
 * Form: continuous-curvature pebble (minkowski of a thin core with a big
 * sphere) split at the mid-plane. The seam hides in the side-profile curve,
 * exactly like the real product. Each half prints cut-face-down: domes face
 * UP, zero supports, no plate texture on any visible surface.
 *
 * Layout: board stacked over battery (front half = board, back half =
 * battery) instead of end-to-end — that is what shrinks the length.
 *
 * Closure: a separate seating RING glues into the back half's rim groove and
 * seats into the front half's groove with LID_CLR clearance. This lets BOTH
 * halves print dome-up (perfect visible surfaces, zero supports) — a lip
 * modeled onto either half would force one dome onto the plate.
 *
 * PART = "front" | "back" | "ring" | "both" | "coupon"
 * Print PART="coupon" first (~10 min) and set LID_CLR here from the slot
 * the ring bar fits snugly into.
 */

PART    = "both";
BATT    = "200";     // "200" | "500"
LID_CLR = 0.25;      // per-side lip clearance from the coupon test
$fn = $preview ? 32 : 64;

/* ---------- hardware (headers CLIPPED FLUSH) ---------- */
xiao_l = 21.0;  xiao_w = 17.8;
board_stack = 6.6;          // 1.6 pcb + 3.8 components + 1.2 clipped stubs
b200 = [31.0, 20.5, 6.0];
b500 = [44.0, 20.5, 8.5];
bat  = (BATT == "200") ? b200 : b500;

/* ---------- derived ---------- */
wall    = 1.8;
r       = 7.0;               // pebble edge radius (continuous curvature)
tab     = 10;                // extra solid at chain end (+x)
cav_l   = max(xiao_l, bat[0]) + 2.5;
cav_w   = max(xiao_w, bat[1]) + 1.2;
front_d = board_stack + 0.6; // cavity depth in the front half (board)
back_d  = bat[2] + 0.6;      // cavity depth in the back half (battery)
face    = 2.4;               // dome apex thickness over the cavity

outer_l = cav_l + 2*wall + 2 + tab;
outer_w = cav_w + 5.6;
outer_t = front_d + back_d + 2*face;
zc      = (front_d - back_d)/2;   // outer body vertical center (z=0 = seam)
cx      = -tab/2;                 // cavity center x (chain tab is on +x)

lip_t = 1.2;  lip_h = 2.2;        // ring half-height per side
chain_x = outer_l/2 - 7.5;        // chain opening center
chain_d = 4.5;

echo(str("V4 ", BATT, "mAh pebble  ", outer_l, " x ", outer_w, " x ", outer_t));

/* ---------- primitives ---------- */
module rrect(l, w, rr) offset(r=rr) square([l - 2*rr, w - 2*rr], center=true);

module pebble()   // continuous curvature everywhere
    translate([0, 0, zc]) minkowski() {
        translate([0, 0, -(outer_t/2 - r)])
            linear_extrude(outer_t - 2*r)
                rrect(outer_l - 2*r, outer_w - 2*r, 4);
        sphere(r = r);
    }

module cavity() {
    translate([cx, 0, -back_d]) linear_extrude(back_d + 0.01)
        rrect(cav_l, cav_w, 4);                       // battery bay (back)
    translate([cx, 0, -0.01]) linear_extrude(front_d + 0.02)
        rrect(cav_l, cav_w, 4);                       // board bay (front)
}

module chain_opening()   // sculpted through-opening in the solid end
    translate([chain_x, 0, -outer_t]) cylinder(d = chain_d, h = 2*outer_t);

module usb_slot() {      // -x end wall, front half, aligned to the board USB
    usb_w = 10.0; usb_h = 4.6;   // connector sits on top of the PCB: z 1.6..4.8
    translate([-outer_l/2 - 2, -usb_w/2, 1.3])
        cube([(cx - cav_l/2) - (-outer_l/2 - 2) + 2, usb_w, usb_h]);
}

module front_holes() {   // mic + LED through the front dome, over the board
    translate([cx - 5.0,  3.0, 0]) cylinder(d = 1.2, h = outer_t);      // mic
    translate([cx - 5.0,  3.0, front_d - 0.1]) cylinder(d = 4.0, h = 1.0);  // acoustic recess (inside)
    translate([cx + 4.0, -3.5, 0]) cylinder(d = 2.0, h = outer_t);      // LED
}


module ring_section(grow = 0)   // ring cross-section outline
    difference() {
        translate([cx, 0]) rrect(cav_l + 2*lip_t + 2*grow, cav_w + 2*lip_t + 2*grow, 4.6);
        translate([cx, 0]) rrect(cav_l - 2*grow, cav_w - 2*grow, 4);
    }

module ring_groove(clr)   // groove just outside the cavity wall, at the rim
    linear_extrude(lip_h + 0.05) ring_section(clr);

module seat_ring()        // the separate glued ring (prints flat, 5 min)
    difference() {
        linear_extrude(2*lip_h - 0.3) ring_section(-0.02);
        translate([cx - cav_l/2 - 4, -6, lip_h - 0.4])   // USB passage notch
            cube([6, 12, lip_h + 1.5]);
    }

module board_posts()     // corner posts locating the board in the front half
    for (sx = [-1, 1], sy = [-1, 1])
        translate([cx + sx*(xiao_l/2 + 1.0), sy*(xiao_w/2 + 1.0), 0])
            cylinder(d = 2.4, h = front_d - 0.4);

/* ---------- halves ---------- */
module front_half()      // z >= 0, rim at z=0: prints dome-up as modeled
    union() {
        difference() {
            intersection() {
                pebble();
                translate([-500, -500, 0]) cube(1000);
            }
            cavity();
            chain_opening();
            usb_slot();
            front_holes();
            translate([0, 0, -0.05]) ring_groove(LID_CLR);   // ring seat, with play
            for (sy = [-1, 1])   // screw pilots in the solid chain end
                translate([outer_l/2 - 12.5, sy*4.5, -0.1]) cylinder(d = 1.15, h = 6);
        }
        board_posts();
    }

module back_half()       // z <= 0
    difference() {
        intersection() {
            pebble();
            translate([-500, -500, -1000]) cube(1000);
        }
        cavity();
        chain_opening();
        translate([0, 0, -lip_h - 0.05]) ring_groove(0.05);   // glue-side groove
        for (sy = [-1, 1])   // screw through-holes
            translate([outer_l/2 - 12.5, sy*4.5, -outer_t])
                cylinder(d = 1.6, h = 2*outer_t);
    }

module coupon() {   // ring-fit test: bar = the real ring wall; 3 slots
    cls = [0.15, 0.25, 0.35];
    translate([-12, -14, 0]) cube([24, lip_t - 0.04, 2*lip_h - 0.3]);  // ring bar
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
if (PART == "front") front_half();                    // dome up, rim on plate
if (PART == "back")  rotate([180, 0, 0]) back_half(); // dome up, rim on plate
if (PART == "ring")  seat_ring();
if (PART == "coupon") coupon();
if (PART == "both") {
    front_half();
    color("lightpink") back_half();
    color("gold") translate([0, 0, -lip_h + 0.15]) seat_ring();
}
