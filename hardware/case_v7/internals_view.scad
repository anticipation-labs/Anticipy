/* Internals visualization — front shell + every component in its bay.
 * Not for printing; render only. Uses the same numbers as anticipy_pendant_v7.scad.
 */
use <anticipy_pendant_v7.scad>

xiao_l = 21.0;  xiao_w = 17.8;  xiao_t = 6.6;
bat    = [30.5, 20.5, 5.6];
flash  = [14.0, 12.0, 1.6];
motor_d = 10.4; motor_t = 3.0;
gap = 1.5;
cav_l = xiao_l + gap + bat[0] + 1.5;
cx = -(4.6 + 4.0)/2;
bx = cx - cav_l/2 + xiao_l/2;          // board center
batx = cx - cav_l/2 + xiao_l + gap + bat[0]/2;

module comp(c) color(c, 0.95) children();

// XIAO nRF52840 Sense (blue PCB + shields)
comp("royalblue") translate([bx - xiao_l/2, -xiao_w/2, 0]) cube([xiao_l, xiao_w, 1.2]);
comp("silver")    translate([bx - 7, -5, 1.2]) cube([9, 10, 2.2]);       // RF shield
comp("gray")      translate([bx - xiao_l/2 - 1.2, -4.5, 0.6]) cube([7.4, 9, 3.2]); // USB-C
comp("black")     translate([bx + 3.2, -1.2, 1.2]) cube([3, 2.4, 1]);   // PDM mic
comp("orange")    translate([bx - 6.7, 3.2, 1.2]) cube([2.6, 2.6, 2.2]); // user button + stem
comp("orange")    translate([bx - 5.5, 4.0, 3.4]) cylinder(d=3.4, h=4.2, $fn=32);

// battery
comp("darkslategray") translate([batx - bat[0]/2, -bat[1]/2, 0]) cube([bat[0], bat[1], bat[2]]);
comp("yellow") translate([batx - bat[0]/2 - 4, -3, 2]) cube([4, 2, 1]);  // tabs
comp("yellow") translate([batx - bat[0]/2 - 4,  1, 2]) cube([4, 2, 1]);

// W25Q128 flash breakout on top of the cell
comp("purple") translate([batx - flash[0]/2 - 6, -flash[1]/2, bat[2]]) cube([flash[0], flash[1], flash[2]]);
// coin motor on top of the cell
comp("firebrick") translate([batx + 8, 0, bat[2]]) cylinder(d=motor_d, h=motor_t, $fn=48);

// wires (schematic ribbons)
comp("red")   translate([bx + xiao_l/2 - 1, -6, 5.2]) cube([gap + 6, 1, 0.8]);
comp("black") translate([bx + xiao_l/2 - 1, -4, 5.2]) cube([gap + 6, 1, 0.8]);
comp("green") translate([bx + xiao_l/2 - 1,  2, 5.2]) cube([gap + 14, 1, 0.8]);

// the shell, ghosted (front half opens downward at z=0; components sit inside)
%front();
