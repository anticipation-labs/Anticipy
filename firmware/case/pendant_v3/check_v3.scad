// Visual verification: shell + lid closed + mock hardware, cross-sectioned.
BATT = "200";
PINS = true;
SECTION = "long";   // "long" | "cross" | "none"

use <anticipy_pendant_v3.scad>

// re-derive the same layout numbers (keep in sync with the main file)
xiao_l=21.0; xiao_w=17.8; board_t=1.6; comp_h=3.8; pin_h=9.2; hdr_t=2.6;
b200_l=31.0; b200_w=20.5; b200_h=6.0; b500_l=44.0; b500_w=20.5; b500_h=8.5;
b_l=(BATT=="500")?b500_l:b200_l; b_w=(BATT=="500")?b500_w:b200_w; b_h=(BATT=="500")?b500_h:b200_h;
wall=3.2; face_t=1.8; lid_t=1.8; lip_h=2.4; lip_t=1.6; tab_l=8.0;
bay_board=xiao_l+0.8; divider=1.4; bay_batt=b_l+1.5;
inner_l=bay_board+divider+bay_batt;
inner_w=max(xiao_w+3.0,b_w+0.8);
depth=(PINS?comp_h+board_t+pin_h+1.0:comp_h+board_t+lip_h+1.4);
body_l=inner_l+2*wall+tab_l; body_w=inner_w+2*wall; body_t=depth+face_t+lid_t;
bx=-body_l/2+wall+bay_board/2;
batx=bx+bay_board/2+divider+bay_batt/2;
z_roof=body_t-face_t;

module mock_hw() {
    color("green") translate([bx-xiao_l/2, -xiao_w/2, z_roof-comp_h-board_t])
        cube([xiao_l, xiao_w, board_t]);                       // PCB
    color("silver") translate([bx-xiao_l/2, -6, z_roof-comp_h]) // USB-C
        cube([7.5, 9, 3.2]);
    for (sy=[-1,1]) color("black")                              // header plastic
        translate([bx-8.9, sy*(xiao_w/2)-(sy>0?2.54:0), z_roof-comp_h-board_t-hdr_t])
            cube([17.8, 2.54, hdr_t]);
    for (sy=[-1,1]) for (i=[0:6]) color("gold")                 // pins
        translate([bx-8.9+2.54*i+1.27, sy*(xiao_w/2-1.27), z_roof-comp_h-board_t-hdr_t-6.6])
            cylinder(d=0.64, h=6.6+hdr_t+board_t+2);
    color("orange") translate([batx-b_l/2, -b_w/2, z_roof-b_h]) // battery vs FRONT
        cube([b_l, b_w, b_h]);
}

module assembly() {
    shell_import();
    translate([0,0,0]) mirror([0,0,0]) lid_closed();
    mock_hw();
}
module shell_import() color("lightsteelblue", 0.85)
    import(str("stl/shell_", BATT, "mah", PINS?"":"_slim", ".stl"));
module lid_closed() color("plum", 0.85)
    translate([-body_l/2 + wall + inner_l/2, 0, 0])   // drops straight into the rebate
        import(str("stl/lid_", BATT, "mah", PINS?"":"_slim", ".stl"));

difference() {
    assembly();
    if (SECTION=="long")  translate([-200,0,-50]) cube([400,200,200]);
    if (SECTION=="cross") translate([bx,-200,-50]) cube([400,400,200]);
}
