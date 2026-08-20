/* Anticipy pendant v5 — website-accurate stadium pill.
 *
 * Shape is taken directly from the product images in /public/images:
 *   - vertical stadium outline: straight sides, full semicircular ends
 *   - gently domed faces, radiused edges (brushed-metal slab, not a blob)
 *   - chain hole drilled THROUGH the faces near the top (jump ring passes
 *     front-to-back), chamfered on both faces like the hero shot
 *   - ONE small LED dot on the upper face; mic is a 1.0 mm pinhole
 *   - nothing else on any surface
 *
 * REQUIRED PREP: clip the header pins flush off the XIAO (flush cutters,
 * ~2 min, no soldering).
 *
 * Layout: board stacked over battery (front = board, back = battery).
 * Board sits pressed against the USB-end cavity wall so a real cable
 * reaches the connector through the end slot.
 *
 * Closure: separate seating ring glued into the back half, presses into the
 * front half with LID_CLR from the coupon; 2 hidden M1.4 screws through the
 * back into the solid chain end. Reopenable. Both halves print rim-down /
 * face-UP: zero supports, no plate texture on visible surfaces.
 *
 * PART = "front" | "back" | "ring" | "both" | "coupon"
 */

PART    = "both";
BATT    = "200";     // "200" | "500"
LID_CLR = 0.25;      // per-side ring clearance from the coupon test
$fn = $preview ? 48 : 128;

/* ---------- hardware (headers CLIPPED FLUSH) ---------- */
xiao_l = 21.0;  xiao_w = 17.8;
board_stack = 6.6;          // 1.6 pcb + 3.8 components + 1.2 clipped stubs
b200 = [31.0, 20.5, 6.0];
b500 = [44.0, 20.5, 8.5];
bat  = (BATT == "200") ? b200 : b500;

/* ---------- derived ---------- */
wall    = 1.8;               // outer skin outside the ring groove
lip_t   = 1.2;  lip_h = 2.2; // seating ring wall / half-height
tab     = 9;                 // solid material at the chain end (+x)
re      = 3.2;               // edge radius (slab edge, not a ball)
dome    = 1.4;               // face dome height

cav_l   = max(xiao_l, bat[0]) + 2.5;
cav_w   = max(xiao_w, bat[1]) + 1.2;
front_d = board_stack + 0.6; // board bay depth (front half)
back_d  = bat[2] + 0.6;      // battery bay depth (back half)
face    = 2.2;               // face thickness over the cavity

outer_l = cav_l + 2*(wall + lip_t) + 1 + tab;
outer_w = cav_w + 2*(wall + lip_t);
outer_t = front_d + back_d + 2*face;
zc      = (front_d - back_d)/2;   // body vertical center (z=0 = seam plane)
cx      = -(tab + 1)/2;           // cavity center x (chain end is +x)

chain_x = outer_l/2 - 5.8;        // chain hole center (through the faces)
chain_d = 4.5;
bx = cx - cav_l/2 + xiao_l/2;     // board center: pressed against USB wall

echo(str("V5 ", BATT, "mAh pill  ", outer_l, " x ", outer_w, " x ", outer_t));

/* ---------- primitives ---------- */
module stadium(l, w) offset(r = w/2) square([l - w, 0.01], center = true);

module body()   // straight-sided stadium slab, radiused edges, domed faces
    translate([0, 0, zc]) minkowski() {
        hull() {
            // straight side band
            translate([0, 0, -(outer_t/2 - re - dome)])
                linear_extrude(2*(outer_t/2 - re - dome))
                    stadium(outer_l - 2*re, outer_w - 2*re);
            // domed faces (uniformly inset -> silhouette stays a stadium)
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
        rrect(cav_l, cav_w, 4);                       // battery bay (back)
    translate([cx, 0, -0.01]) linear_extrude(front_d + 0.02)
        rrect(cav_l, cav_w, 4);                       // board bay (front)
}

module chain_opening() {  // through the faces, chamfered on both, like hero
    translate([chain_x, 0, -outer_t]) cylinder(d = chain_d, h = 2*outer_t);
    translate([chain_x, 0,  outer_t/2 + zc - 1.2 + 0.01])
        cylinder(d1 = chain_d, d2 = chain_d + 2.4, h = 1.2);
    translate([chain_x, 0, -(outer_t/2 - zc) - 0.01])
        cylinder(d1 = chain_d + 2.4, d2 = chain_d, h = 1.2);
}

module usb_slot() {      // -x end wall: sized for a real cable OVERMOLD
    usb_w = 12.6; usb_h = 7.0;   // typical plug overmold 12 x 6.5 + play
    translate([-outer_l/2 - 2, -usb_w/2, 0])   // floor = seam plane
        cube([(cx - cav_l/2) - (-outer_l/2 - 2) + 2, usb_w, usb_h]);
}

module front_holes() {   // LED dot + mic pinhole, over the board. Nothing else.
    translate([bx - 2.0, 0, 0]) cylinder(d = 2.0, h = outer_t);          // LED
    translate([bx + 3.0, 4.0, 0]) cylinder(d = 1.0, h = outer_t);        // PDM mic
    translate([bx + 3.0, 4.0, front_d - 0.1]) cylinder(d = 4.0, h = 1.0); // acoustic recess (inside)
}

module ring_section(grow = 0)
    difference() {
        translate([cx, 0]) rrect(cav_l + 2*lip_t + 2*grow, cav_w + 2*lip_t + 2*grow, 4.6);
        translate([cx, 0]) rrect(cav_l - 2*grow, cav_w - 2*grow, 4);
    }

module ring_groove(clr) linear_extrude(lip_h + 0.05) ring_section(clr);

module seat_ring()
    difference() {
        linear_extrude(2*lip_h - 0.3) ring_section(-0.02);
        translate([cx - cav_l/2 - 4, -6.5, -0.1])   // USB passage notch
            cube([6, 13, 2*lip_h + 1]);
    }

/* ---------- halves ---------- */
module front_half()
    difference() {
        intersection() { body(); translate([-500, -500, 0]) cube(1000); }
        cavity();          // one clean flat-floored bay, nothing inside it
        chain_opening();
        usb_slot();
        front_holes();
        translate([0, 0, -0.05]) ring_groove(LID_CLR);
        for (sy = [-1, 1])   // screw pilots in the solid chain end
            translate([outer_l/2 - 12.0, sy*4.5, -0.1]) cylinder(d = 1.15, h = 6);
    }

module back_half()
    difference() {
        intersection() { body(); translate([-500, -500, -1000]) cube(1000); }
        cavity();
        chain_opening();
        translate([0, 0, -lip_h - 0.05]) ring_groove(0.05);
        for (sy = [-1, 1]) {  // screw through-holes + head recess
            translate([outer_l/2 - 12.0, sy*4.5, -outer_t])
                cylinder(d = 1.6, h = 2*outer_t);
            translate([outer_l/2 - 12.0, sy*4.5, -(outer_t/2 - zc) - 0.01])
                cylinder(d = 3.0, h = 1.2);
        }
    }

module coupon() {   // ring-fit test: bar = the real ring wall; 3 slots
    cls = [0.15, 0.25, 0.35];
    translate([-12, -14, 0]) cube([24, lip_t - 0.04, 2*lip_h - 0.3]);
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
if (PART == "front") front_half();                    // face up, rim on plate
if (PART == "back")  rotate([180, 0, 0]) back_half(); // face up, rim on plate
if (PART == "ring")  seat_ring();
if (PART == "coupon") coupon();
if (PART == "both") {
    front_half();
    color("lightpink") back_half();
    color("gold") translate([0, 0, -lip_h + 0.15]) seat_ring();
}
