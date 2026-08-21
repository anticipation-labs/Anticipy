/* v5 verification scene: mock hardware inside the closed pill.
 * SECTION = "long" | "cross" | "none"
 */
BATT = "200";
SECTION = "long";

use <anticipy_pendant_v5.scad>

xiao_l=21.0; xiao_w=17.8; board_t=1.6;
b = (BATT=="200") ? [31.0,20.5,6.0] : [44.0,20.5,8.5];
cx = 0;                        // must match cx in the main file (cavity centered)
cav_l = max(xiao_l, b[0]) + 2.5;
bx0 = cx - cav_l/2;            // board pressed against the USB-end wall

module mocks() {
    color("green")  translate([bx0, -xiao_w/2, 0.2]) cube([xiao_l, xiao_w, board_t]);
    color("silver") translate([bx0 - 1.3, -4.5, 0.2 + board_t]) cube([7.3, 9, 3.2]);   // USB-C
    color("gray")   translate([bx0 + xiao_l/2 - 3, -1.5, 0.2 + board_t]) cube([6, 6, 2.2]);  // nRF module
    color("orange") translate([cx - b[0]/2, -b[1]/2, -0.4 - b[2]]) cube(b);             // battery
}

difference() {
    union() {
        anticipy_v5_assembly();
        mocks();
    }
    if (SECTION == "long")  translate([-60, -120, -60]) cube(120);
    if (SECTION == "cross") translate([cx, -60, -60]) cube(120);
}

module anticipy_v5_assembly() {
    front_half();
    color("lightpink") back_half();
    color("gold") translate([0, 0, -2.05]) seat_ring();
}
