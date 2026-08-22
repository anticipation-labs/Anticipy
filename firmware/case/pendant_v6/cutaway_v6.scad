/* Cutaway view of the assembled v6 pendant with component mocks.
 * Render: openscad -D 'BATT="200"' -D 'MECH="snap"' -o out.png cutaway_v6.scad
 */
include <anticipy_pendant_v6.scad>
PART = "none";   // suppress the main file's output

rotate([-90, 0, 0]) {   // tip the cut plane up so the section faces the camera
    difference() {
        union() {
            color("silver") front_half();
            color("lightsteelblue") back_half();
        }
        translate([-200, -400, -200]) cube(400);   // cut at y=0, keep +y half
    }
    color("green")  intersection() {
        translate([bx - xiao_l/2, 0, 0.3]) cube([xiao_l, xiao_w/2, board_stack]);
        translate([-250, 0, -250]) cube([500, 500, 500]);
    }
    color("orange") translate([-bat[0]/2, 0, -bat[2] - 0.3]) cube([bat[0], bat[1]/2, bat[2]]);
}
