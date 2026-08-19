// Anticipy pendant v2 — flattened capsule matching the anticipy.ai product renders:
// smooth pill, one LED dot, integrated chain through-hole at the top, no visible seam
// on the front (the shell splits on the back face).
//
// Board: XIAO nRF52840 Sense with headers clipped/desoldered (5 mm thick).
//
// Variants (set from CLI with -D):
//   BATT    = "200" | "500"   502025 200 mAh (thin) or 752042 500 mAh (long)
//   STORAGE = true|false      pocket for W25Q128 SPI-flash breakout (offline audio)
//   HAPTIC  = true|false      pocket for 10x2.7 mm coin vibration motor
//   USB     = true|false      bottom USB-C slot (false = clean look; open back to charge)
//   PART    = "shell" | "back" | "all"

PART    = "all";
BATT    = "200";
STORAGE = false;
HAPTIC  = false;
USB     = false;
HOLES   = true;   // false = totally clean front; mic gets a 0.5 mm-thin membrane inside

$fn = 72;

/* ---------- components ---------- */
xiao_l = 21.0;  xiao_w = 17.8;  xiao_h = 5.0;   // headers removed
b200_l = 25.0;  b200_w = 20.0;  b200_h = 5.4;   // 502025 200 mAh
b500_l = 43.0;  b500_w = 20.0;  b500_h = 8.0;   // 752042 500 mAh
flash_l = 16.0; flash_w = 13.0; flash_h = 2.8;  // W25Q128 breakout
hap_d   = 10.5; hap_h   = 3.0;                  // 1027 coin motor
pad     = 1.0;                                  // EVA foam on battery
clr     = 0.4;

/* ---------- layout ----------
   200: battery UNDER the board (both are thin) -> short slim pendant
   500: battery beside the board lengthwise     -> longer pendant       */
b_l = (BATT == "500") ? b500_l : b200_l;
b_w = (BATT == "500") ? b500_w : b200_w;
b_h = (BATT == "500") ? b500_h : b200_h;
side_by_side = false;   // board stacked on battery for both sizes (shortest pendant)

extra_t = (STORAGE ? flash_h : 0) + (HAPTIC && !STORAGE ? hap_h : 0);

cav_l = side_by_side ? xiao_l + 1.0 + b_l + 2*clr : max(xiao_l, b_l) + 2*clr;
cav_w = max(xiao_w, b_w) + 2*clr;
cav_h = (side_by_side ? max(xiao_h, b_h + pad) : xiao_h + 0.5 + b_h + pad) + 0.6 + extra_t;

/* ---------- shell ---------- */
wall     = 1.8;
face_t   = 1.8;   // min skin front/back
lip_h    = 2.6;   // press-fit lip
lip_t    = 1.2;
lip_clr  = 0.15;

hole_d   = 5.0;   // chain through-hole
hole_gap = 8.0;   // capsule length reserved for the hole

end_m  = 4.5;                          // solid margin at the rounded -X end
body_l = cav_l + end_m + hole_gap + wall;
body_w = cav_w + 2*wall + 1.0;
body_t = cav_h + 2*face_t;

cav_x  = -(body_l/2) + end_m + cav_l/2;  // cavity toward -X; hole zone at +X
hole_x =  body_l/2 - hole_gap/2 - 1.2;
split_z = cav_h/2 - lip_h;             // back cover parts at this plane

echo(str("VARIANT batt=", BATT, " storage=", STORAGE, " haptic=", HAPTIC, " usb=", USB));
echo(str("BODY ", body_l, " x ", body_w, " x ", body_t));

/* pebble: stadium plan outline with rounded edges of radius er */
er = 4.5;
module stadium(l, w)
    offset(r = w/2) square([l - w, 0.01], center = true);
module capsule(l, w, t)
    translate([0, 0, -(t/2 - er)]) minkowski() {
        linear_extrude(height = t - 2*er) stadium(l - 2*er, w - 2*er);
        sphere(r = er, $fn = 48);
    }

module cav_outline(grow = 0)
    offset(r = 3) offset(r = -3)
        square([cav_l + 2*grow, cav_w + 2*grow], center = true);

module chain_hole() {
    translate([hole_x, 0, 0]) {
        cylinder(d = hole_d, h = body_t + 4, center = true);
        translate([0, 0,  body_t/2 - 1.0]) cylinder(d1 = hole_d, d2 = hole_d + 2.2, h = 1.4);
        translate([0, 0, -body_t/2 - 0.4]) cylinder(d1 = hole_d + 2.2, d2 = hole_d, h = 1.4);
    }
}

module screw_pilots()   // 2x M1.4 self-tapper through side walls into the lid lip
    for (sy = [-1, 1])
        translate([cav_x, 0, split_z + lip_h/2])
            rotate([-sy*90, 0, 0]) cylinder(d = 1.2, h = body_w);

module front_features() {
    bx = cav_x;   // board centered in the cavity footprint (200) or at -X end (500)
    bx2 = side_by_side ? cav_x - cav_l/2 + clr + xiao_l/2 : bx;
    if (HOLES) {
        translate([bx2 - 4, 3.5, -body_t/2 - 1]) cylinder(d = 1.0, h = face_t + 3);   // mic
        translate([bx2 + 2, 0,   -body_t/2 - 1]) cylinder(d = 1.8, h = face_t + 3);  // LED dot
    } else {
        // clean face: thin the wall to 0.5 mm from the INSIDE over the mic (sound passes)
        translate([bx2 - 4, 3.5, -body_t/2 + 0.5]) cylinder(d = 4.0, h = face_t);
        // LED glows through a 0.6 mm skin instead of an open dot
        translate([bx2 + 2, 0, -body_t/2 + 0.6]) cylinder(d = 3.0, h = face_t);
    }
}

module usb_slot()
    if (USB)
        translate([-body_l/2 - 2, -9.6/2, -1.8])
            cube([6, 9.6, 3.6]);

module shell() {
    difference() {
        capsule(body_l, body_w, body_t);
        // remove everything above the split plane except the chain-hole end
        translate([-body_l, -body_w, split_z]) cube([body_l + hole_x - hole_gap/2 + 0.2, body_w*2, body_t]);
        translate([cav_x, 0, -cav_h/2]) linear_extrude(height = cav_h + body_t) cav_outline();
        translate([cav_x, 0, split_z - 0.1]) linear_extrude(height = body_t)
            cav_outline(lip_t + lip_clr);
        chain_hole();
        front_features();
        usb_slot();
        screw_pilots();
    }
}

module back() {
    difference() {
        union() {
            intersection() {
                capsule(body_l, body_w, body_t);
                translate([-body_l, -body_w, split_z])
                    cube([body_l + hole_x - hole_gap/2 + 0.2, body_w*2, body_t]);
            }
            translate([cav_x, 0, split_z - lip_h]) linear_extrude(height = lip_h + 0.1)
                difference() { cav_outline(lip_t); cav_outline(-1.0); }
        }
        screw_pilots();
        if (STORAGE)
            translate([cav_x + (side_by_side ? cav_l/2 - flash_l/2 - 2 : 0), 0, split_z + 0.4])
                translate([-flash_l/2, -flash_w/2, 0]) cube([flash_l, flash_w, flash_h + 0.4]);
        if (HAPTIC)
            translate([cav_x - (side_by_side ? cav_l/2 - hap_d/2 - 2 : 0),
                       STORAGE ? 0 : 0, split_z + 0.4])
                cylinder(d = hap_d, h = hap_h + 0.4);
    }
}

if (PART == "shell") shell();
else if (PART == "back") back();
else { shell(); translate([0, body_w + 8, 0]) back(); }
