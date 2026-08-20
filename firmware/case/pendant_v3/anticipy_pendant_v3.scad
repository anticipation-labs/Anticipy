// Anticipy pendant v3 — designed around the REAL hardware photographed on 2026-08-19:
//  * XIAO nRF52840 Sense WITH soldered male headers (pins ~9 mm below the board). No
//    assumption that pins get clipped. Set PINS=false only if you actually remove them.
//  * Battery wires loop over the board -> dedicated wire bay + notch, nothing pinches.
//  * USB-C slot in the bottom edge on EVERY variant. Charge without opening.
//  * Lid closes into a machined rebate with a lip; clearance is a parameter (LID_CLR)
//    and a tolerance coupon (PART="coupon") lets you find the snug value in a 10-min
//    print BEFORE printing a full pendant. Two M1.4 screw pilots + pry notch = openable
//    and serviceable forever.
//  * Print orientation is designed in: the shell prints OPENING-DOWN so the visible
//    front face is the smooth printed top — never touching the textured plate, and no
//    supports anywhere (vertical walls, top fillet only, cavity roof bridges internally
//    where nobody sees it). The lid prints lip-down for the same reason.
//
// PART = "shell" | "lid" | "coupon" | "fitcheck" | "all"
// BATT = "200" | "500"
// PINS = true (headers on, thicker body) | false (headers clipped, slim body)
// LID_CLR = per-side lip clearance. Print the coupon, pick the snug socket, set it here.

PART    = "all";
BATT    = "200";
PINS    = true;
LID_CLR = 0.25;

$fn = 64;

/* ---------- measured / researched hardware ---------- */
xiao_l   = 21.0;   xiao_w = 17.8;  board_t = 1.6;
comp_h   = 3.8;    // USB-C + parts on the component (front) side, incl. margin
pin_h    = 9.2;    // header plastic 2.5 + pins ~6.5 sticking out the back
b200_l = 31.0; b200_w = 20.5; b200_h = 6.0;   // LP502030-class incl. swell margin
b500_l = 44.0; b500_w = 20.5; b500_h = 8.5;   // 752042 incl. swell margin

b_l = (BATT=="500") ? b500_l : b200_l;
b_w = (BATT=="500") ? b500_w : b200_w;
b_h = (BATT=="500") ? b500_h : b200_h;

/* ---------- construction ---------- */
wall    = 3.2;   // must be >= lip_t + LID_CLR + 1.2 so the rebate leaves real wall
face_t  = 1.8;                       // front skin
lid_t   = 1.8;                       // lid panel
lip_h   = 2.4;  lip_t = 1.6;         // lid lip into shell rebate
tab_l   = 8.0;  hole_d = 5.0;        // solid chain tab + through-hole

bay_board = xiao_l + 0.8;            // board bay length
divider   = 1.4;                     // wall between board bay and battery bay
bay_batt  = b_l + 1.5;
wire_notch_w = 9.0;                  // battery wires pass over the divider here

inner_l = bay_board + divider + bay_batt;
inner_w = max(xiao_w + 3.0, b_w + 0.8);          // extra width = wire room beside board
hdr_t   = 2.6;                       // header plastic strip thickness
depth   = (PINS ? comp_h + board_t + pin_h + 1.0
                : comp_h + board_t + lip_h + 1.4);  // interior depth
body_l  = inner_l + 2*wall + tab_l;
body_w  = inner_w + 2*wall;
body_t  = depth + face_t + lid_t;

cav_x   = -body_l/2 + wall + inner_l/2;           // cavity toward -X, chain tab at +X
bx      = -body_l/2 + wall + bay_board/2;         // board bay center
batx    = bx + bay_board/2 + divider + bay_batt/2;
tab_x   =  body_l/2 - tab_l/2 - 1.0;
z_roof  = body_t - face_t;                        // interior ceiling (front inside)

echo(str("V3 ", BATT, "mAh pins=", PINS, "  body ", body_l, " x ", body_w, " x ", body_t));

/* ---------- shapes (z=0 is the BACK/opening plane = print bed) ---------- */
module rrect(l, w, r) offset(r=r) square([l-2*r, w-2*r], center=true);

module body_solid() {
    fr = 3.0;                                     // front-face edge fillet
    union() {
        linear_extrude(body_t - fr) rrect(body_l, body_w, 11);
        translate([0,0,body_t - fr]) minkowski() {
            linear_extrude(0.01) rrect(body_l - 2*fr, body_w - 2*fr, 11 - fr);
            sphere(r = fr);
        }
    }
}

module cavity() {
    translate([cav_x, 0, -0.1])
        linear_extrude(z_roof + 0.1) rrect(inner_l, inner_w, 4);
}

panel_l = inner_l + 2*lip_t + 2*LID_CLR + 0.8;   // lid panel outline
panel_w = inner_w + 2*lip_t + 2*LID_CLR + 0.8;

module rebate() {   // two-step: panel sits flush in the outer step, lip seats deeper
    translate([cav_x, 0, -0.1])
        linear_extrude(lid_t + 0.15) rrect(panel_l + 0.3, panel_w + 0.3, 9);
    translate([cav_x, 0, -0.1])
        linear_extrude(lid_t + lip_h + 0.1) rrect(inner_l + 2*(lip_t + LID_CLR),
                                                  inner_w + 2*(lip_t + LID_CLR), 7);
}

module usb_slot() {   // bottom end wall, aligned to the board's USB-C
    usb_w = 10.5; usb_h = 4.6;
    translate([-body_l/2 - 1, -usb_w/2, z_roof - usb_h])
        cube([wall + 2.5, usb_w, usb_h]);
    // outside chamfer so the plug finds the hole
    translate([-body_l/2 - 0.6, 0, z_roof - usb_h/2]) rotate([0,90,0])
        linear_extrude(1.2, scale=0.8) square([usb_h + 2, usb_w + 2], center=true);
}

module front_holes() {   // mic + LED through the front face, over the board
    translate([bx - 2.5,  3.0, z_roof - 0.5]) cylinder(d=1.2, h=face_t + 1);   // mic
    translate([bx - 2.5,  3.0, z_roof - 0.9]) cylinder(d=4.0, h=1.0);          // acoustic recess
    translate([bx + 3.0, -3.5, z_roof - 0.5]) cylinder(d=2.0, h=face_t + 1);   // LED dot
}

module chain_hole() {
    translate([tab_x, 0, -1]) cylinder(d=hole_d, h=body_t + 2);
    translate([tab_x, 0, body_t - 1.2]) cylinder(d1=hole_d, d2=hole_d + 2.4, h=1.4);
    translate([tab_x, 0, -0.2])         cylinder(d1=hole_d + 2.4, d2=hole_d, h=1.4);
}

module screw_pilots()   // 2x M1.4 self-tappers through the long walls into the lip
    for (sy=[-1,1])
        translate([cav_x, sy*(body_w/2 + 1), lid_t + lip_h/2])
            rotate([sy*90, 0, 0]) cylinder(d=1.15, h=wall + 3);

module pry_notch()
    translate([-body_l/2 + wall + 4, -body_w/2 - 1, -0.1])
        cube([8, wall + 2, 0.8]);

/* board cradle: the board goes in component-side toward the front face.
   Ribs run from the bed to full height (they narrow the bay to the board width
   so it cannot wander), and a 1.0 mm ledge on each rib catches the outer edge of
   the soldered header plastic — the pins themselves hang free inboard of it.
   Everything grows from the bed plane, so the shell prints with zero supports. */
ledge_z = PINS ? z_roof - comp_h - board_t - hdr_t : z_roof - comp_h - board_t;
z0      = lid_t + lip_h + 0.2;   // interior features start above the closed lid+lip
module board_cradle() {
    for (sy=[-1,1]) {
        // guide rib between bay wall and board edge (anchored to the wall)
        translate([bx - xiao_l/2, (sy>0 ? xiao_w/2 + 0.4 : -inner_w/2), z0])
            cube([xiao_l, inner_w/2 - xiao_w/2 - 0.4, z_roof - z0 - 0.4]);
        // ledge catching the header-plastic edge (or bare board edge if PINS=false)
        translate([bx - xiao_l/2, (sy>0 ? xiao_w/2 - 0.6 : -xiao_w/2 - 0.4), z0])
            cube([xiao_l, 1.0, ledge_z - z0]);
    }
}

module divider_wall()
    difference() {
        translate([bx + bay_board/2, -inner_w/2, z0])
            cube([divider, inner_w, z_roof - z0]);
        // wire notch: battery leads cross here without being pinched
        translate([bx + bay_board/2 - 1, -wire_notch_w/2, z0 - 0.1])
            cube([divider + 2, wire_notch_w, z_roof - z0 - 2]);
    }

/* ---------- parts ---------- */
module shell() {
    union() {
        difference() {
            body_solid();
            cavity();
            rebate();
            usb_slot();
            front_holes();
            chain_hole();
            screw_pilots();
            pry_notch();
        }
        board_cradle();
        divider_wall();
    }
}

module lid() {   // modeled lip-up here; the STL is exported lip-down for printing
    lw = inner_l + 2*lip_t;  ww = inner_w + 2*lip_t;
    difference() {
        union() {
            linear_extrude(lid_t) rrect(lw + 2*LID_CLR + 0.8, ww + 2*LID_CLR + 0.8, 9);
            translate([0,0,lid_t - 0.01]) linear_extrude(lip_h)
                difference() { rrect(lw, ww, 7); rrect(lw - 2*lip_t, ww - 2*lip_t, 5.5); }
        }
        for (sy=[-1,1])   // screw pilot dimples in the lip
            translate([0, sy*(ww/2 + 1), lid_t + lip_h/2])
                rotate([sy*90, 0, 0]) cylinder(d=1.15, h=lip_t + 2);
    }
}

/* 10-minute tolerance coupon: three sockets (0.15 / 0.25 / 0.35 per-side clearance)
   and one tab. Push the tab into each socket; snuggest one that still closes = your
   LID_CLR. Numbers are embossed next to each socket. */
module coupon() {
    cls = [0.15, 0.25, 0.35];
    for (i=[0:2]) translate([i*30 - 30, 0, 0]) difference() {
        linear_extrude(5) rrect(24, 24, 4);
        translate([0,0,5 - lip_h]) linear_extrude(lip_h + 1)
            rrect(14 + 2*(lip_t + cls[i]), 14 + 2*(lip_t + cls[i]), 3);
        translate([-8, 8.2, 4.2]) linear_extrude(1)
            text(str(cls[i]), size=3.4, halign="left");
    }
    translate([0, 26, 0]) union() {
        linear_extrude(1.8) rrect(20, 20, 4);
        translate([0,0,1.79]) linear_extrude(lip_h)
            difference() { rrect(14 + 2*lip_t, 14 + 2*lip_t, 3);
                           rrect(14, 14, 2.4); }
    }
}

if (PART == "shell")        shell();
else if (PART == "lid")     lid();
else if (PART == "coupon")  coupon();
else { shell(); translate([0, body_w + 10, 0]) lid(); }
