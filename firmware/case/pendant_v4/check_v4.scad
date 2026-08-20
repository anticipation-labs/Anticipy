/* v4 verification scene: mock hardware inside the closed pebble.
 * SECTION = "long" | "cross" | "none"
 */
BATT = "200";
SECTION = "long";

use <anticipy_pendant_v4.scad>

xiao_l=21.0; xiao_w=17.8; board_t=1.6; comp_h=3.8;
b = (BATT=="200") ? [31.0,20.5,6.0] : [44.0,20.5,8.5];
cx = -5;   // must match cx in the main file (tab/2)

module mocks() {
    color("green")  translate([cx - xiao_l/2, -xiao_w/2, 0.2]) cube([xiao_l, xiao_w, board_t]);
    color("silver") translate([cx - xiao_l/2 - 1.3, -4.5, 0.2 + board_t]) cube([7.3, 9, 3.2]);   // USB-C
    color("gray")   translate([cx - 2, -1.5, 0.2 + board_t]) cube([6, 6, 2.2]);                  // nRF module
    color("orange") translate([cx - b[0]/2, -b[1]/2, -0.4 - b[2]]) cube(b);                      // battery
}

module scene() {
    render() {
        translate([0,0,0]) children();
    }
}

difference() {
    union() {
        anticipy_v4_assembly();
        mocks();
    }
    if (SECTION == "long")  translate([-60, -120, -60]) cube(120);
    if (SECTION == "cross") translate([cx, -60, -60]) cube(120);
}

module anticipy_v4_assembly() {
    front_half();
    color("lightpink") back_half();
    color("gold") translate([0, 0, -2.05]) seat_ring();
}
