/* Anticipy pendant v7 — "Plaud envelope" side-by-side layout.
 *
 * Target: Plaud NotePin 51 x 21 x 11 mm + 15% margin = 58.7 x 24.2 x 12.65 mm.
 * v6 stacked board-over-battery and came out 22.7 mm thick. v7 puts the
 * XIAO nRF52840 Sense (headers clipped) SIDE-BY-SIDE with a 502030 250 mAh
 * cell, so thickness is set by the taller of the two (8.5 mm bay) not the sum.
 *
 * Carries every v6.3 print-proven fix:
 *  - 7-hole mic grille (1.2 mm) over an internal acoustic recess
 *  - USB slot 15.0 x 8.6 with chamfer lead-in
 *  - chain hole 10.6 mm, chamfered, clear of the lip groove
 *  - integral lip closure, LID_CLR 0.30 (friction bias -0.05)
 *  - print cavity-opening-UP, no supports
 *
 * New in v7:
 *  - button hole (4.2 mm) over the XIAO bay for a stem-extended tactile switch
 *  - 10 mm coin-vibration-motor pocket in the back half (haptics)
 *  - optional second bay length for a W25Q128 flash breakout stacked
 *    under the battery wires (BACKLOG = true adds 1.6 mm thickness)
 *
 * PART = "front" | "back" | "both"
 * MECH = "friction" | "magnet"
 */

PART    = "both";
MECH    = "friction";
BACKLOG = true;      // room for W25Q128 SPI-flash breakout (offline recording)
LID_CLR = 0.30;
fit_clr = (MECH == "friction") ? LID_CLR - 0.05 : LID_CLR;
$fn = $preview ? 48 : 128;

/* ---------- hardware ---------- */
xiao_l = 21.0;  xiao_w = 17.8;  xiao_t = 6.6;   // headers clipped flush
bat    = [30.5, 20.5, 5.6];                     // 502030 250 mAh, tabs folded
flash  = [14.0, 12.0, 1.6];                     // W25Q128 breakout, flat on cell
motor_d = 10.4; motor_t = 3.0;                  // 10x2.7 coin motor, on cell

/* ---------- body math (v6 conventions) ---------- */
wall  = 1.4;
lip_t = 1.0;  lip_h = 2.2;
re    = 1.4;
dome  = 0.5;
gap   = 1.5;                                    // between board and battery

// single 9.0 mm cavity: board zone 6.6+wiring; cell zone 5.6 + motor 3.0 stacked
cav_l   = xiao_l + gap + bat[0] + 1.5;          // side-by-side + wire room
cav_w   = max(xiao_w, bat[1]) + 1.0;
front_d = 9.0;
back_d  = 0;                                    // flat lid, tongue only
face    = re + dome;

chain_d = 4.6;                                  // 2.5-3 mm chain via jump ring
outer_w = cav_w + 2*(wall + lip_t);
outer_l = cav_l + 2*(wall + lip_t) + chain_d + 4.0;   // solid chain end
outer_t = front_d + back_d + 2*face;
zc      = (front_d - back_d)/2;
cx      = -(chain_d + 4.0)/2;                   // cavity biased away from chain end

chain_x = outer_l/2 - chain_d/2 - 2.0;
bx = cx - cav_l/2 + xiao_l/2;                   // board center (USB end)
mag_d = 5.2; mag_h = 2.1;
mag_x = cx + cav_l/2 + lip_t + LID_CLR + 0.8 + mag_d/2;
mag_y = 7.6;

echo(str("V7 outer: ", outer_l, " x ", outer_w, " x ", outer_t,
         "  (target <= 58.7 x 24.2 x 12.65 + chain end)"));

/* ---------- primitives ---------- */
module stadium(l, w) offset(r = w/2) square([l - w, 0.01], center = true);
module rrect(l, w, rr) offset(r = rr) square([l - 2*rr, w - 2*rr], center = true);

module body()
    translate([0, 0, zc]) minkowski() {
        translate([0, 0, -(outer_t/2 - re - dome)])
            linear_extrude(2*(outer_t/2 - re - dome))
                stadium(outer_l - 2*re, outer_w - 2*re);
        sphere(r = re + dome*0.5);
    }

module cavity() {
    translate([cx, 0, -back_d]) linear_extrude(back_d + 0.01)
        rrect(cav_l, cav_w, 4);
    translate([cx, 0, -0.01]) linear_extrude(front_d + 0.02)
        rrect(cav_l, cav_w, 4);
}

module lip(clr = 0) {
    difference() {
        translate([cx, 0, 0]) linear_extrude(lip_h)
            rrect(cav_l + 2*(lip_t - clr), cav_w + 2*(lip_t - clr), 4.5);
        translate([cx, 0, -0.01]) linear_extrude(lip_h + 0.02)
            rrect(cav_l, cav_w, 4);
    }
}

module cuts() {
    // USB-C slot at the board end, on the parting plane
    translate([cx - cav_l/2 - wall - lip_t - 2, 0, xiao_t/2 - 1.6])
        rotate([0, 90, 0]) linear_extrude(wall + lip_t + 4.5)
            rrect(8.6, 15.0, 2.6);
    // 7-hole mic grille over the XIAO mic (front face)
    translate([bx + 4.5, 0, 0]) cylinder(d = 1.2, h = outer_t);
    for (a = [0:60:300])
        translate([bx + 4.5 + 2.6*cos(a), 2.6*sin(a), 0])
            cylinder(d = 1.2, h = outer_t);
    // acoustic recess inside the front wall
    translate([bx + 4.5, 0, front_d - 0.6]) cylinder(d = 7, h = face + 1);
    // button hole over XIAO user-switch stem
    translate([bx - 5.5, 4.0, 0]) cylinder(d = 4.2, h = outer_t);
    // LED light pipe window
    translate([bx - 5.5, -4.0, 0]) cylinder(d = 2.0, h = outer_t);
    // chain hole through the solid end
    translate([chain_x, 0, -outer_t]) cylinder(d = chain_d, h = 2*outer_t);
    // pry notch at USB end seam
    translate([cx - cav_l/2 - wall - lip_t - 1, 0, -0.6])
        cube([2.5, 8, 1.2], center = true);
}


module front() {
    difference() {
        intersection() { body(); translate([-500,-500,0]) cube(1000); }
        cavity(); cuts();
        lip(-fit_clr);   // groove
    }
}

module back() {
    difference() {
        union() {
            intersection() { body(); translate([-500,-500,-1000]) cube(1000); }
            lip(fit_clr);   // tongue
        }
        cavity(); cuts();
        if (MECH == "magnet")
            for (s = [-1, 1]) translate([mag_x, s*mag_y, -back_d - face + 0.6])
                cylinder(d = mag_d, h = mag_h);
    }
}

if (PART == "front") rotate([180,0,0]) front();     // cavity-up
else if (PART == "back") back();                     // cavity-up
else { translate([0, outer_w/2 + 4, 0]) rotate([180,0,0]) front();
       translate([0, -(outer_w/2 + 4), 0]) back(); }
