# Anticipy ordered-shell recovery v0.2

## Use this version

The first 4.00 mm recovery was withdrawn after an independent audit found
collisions with the historical body's internal shelf and the face hooks.
Version 0.2 fixes those problems and uses a **4.50 mm-rise mid-band**.

The corrected generator imports the packaged exact historical body and face
STEP solids. Its final report records **1,045** boolean intersection values
with a 0.0 mm3 maximum for:

- nominal and loose mid-bands against the body;
- the four-hook vertical drop at 13 positions and lock slide at 21 positions,
  against both bands and every modeled component/layout;
- XIAO, battery, motor, 8 x 4 x 2 mm driver, and safety bridge against body, band, face,
  and one another;
- 12, 15, 24, and 25 mm battery layouts with the sealed coin motor;
- the full 11.29 x 4.03 mm swept barrel-motor measurement reference; it is not
  a Unit 001 fallback because no qualified rotor guard is included.

This is a CAD result against the repository's historical reference solids.
The physical ordered nylon still must pass its gauges and no-load closure.

## Finished size

- Original historical body and recessed face: 51 x 22 x 10 mm.
- Recovered nominal outside size: **51 x 22 x 14.5 mm**.
- Main internal height: 12.5 mm.
- Maximum controlled battery-body envelope: **25 x 10 x 5.5 mm finished**,
  including PCM, wrap, seams, and folded tabs. Leads/interconnect are routed
  and dry-fit separately.
- XIAO official STEP envelope: 22.482 x 17.780 x 4.460 mm.

The band adds only a narrow perimeter seam. The ordered nylon body and face
remain the large visible surfaces.

## Print now

Print these in black PETG or PETG-HF:

1. `out/ordered_shell_midband_rise_4p50mm_nominal.stl`
2. `out/ordered_shell_midband_rise_4p50mm_loose_tongue.stl`
3. `out/PRINT_DECK_DOWN_then_FLIP_battery_safety_bridge.stl`
4. `out/mic_drill_jig_usb_end_notched.stl`
5. `out/BENCH_ONLY_xiao_plan_fit_gauge.stl`
6. the lower layout gauge matching the battery and motor selected at the
   counter;
7. the individual maximum-envelope battery, XIAO, and motor gauges.
8. `out/MEASURE_MAX_finished_driver_island_8x4x2.stl`.

### Bambu P1S settings

- 0.4 mm nozzle.
- 0.12 mm layers for bands and microphone jig.
- 0.16 mm layers for bridge and gauges.
- Five wall loops, six top/bottom layers, 40% gyroid.
- Arachne walls and thin-wall detection on; supports off.
- Add a 3 mm brim to each band; seam at the USB end.
- Put the band's locating tongue on the plate.
- Put the safety bridge's broad deck on the plate, then flip it for assembly.

Let the parts cool on the plate. Use the nominal band only if it seats fully
with fingertip pressure; otherwise try the loose tongue. Never force either
into the nylon.

## Battery/motor layouts

| Battery envelope | Preferred motor position | Notes |
|---|---|---|
| 12 x 10 x 5.5 mm max | 10 x 2.7 mm coin at USB-side end | Best RF clearance, least runtime |
| 15 x 10 x 5.5 mm max | 10 x 2.7 mm coin at USB-side end | Some antenna overlap; test |
| 24 x 10 x 5.5 mm max | 10 x 2.7 mm coin at antenna-side end | Fits documented Renata ICP501022UPM envelope; battery lies under antenna, so RF test is mandatory |
| 25 x 10 x 5.5 mm max | 10 x 2.7 mm coin at antenna-side end | Universal maximum gauge; RF test mandatory |

The bridge pads sit on the historical internal shelf rather than passing
through it. Its deck clears a true 5.5 mm pack on 0.05 mm floor insulation by
0.40 mm; the PCB cannot load the pouch.

The finished insulated SMD motor-driver envelope is 8 x 4 x 2 mm. It has only
0.2 mm nominal wall margin, so its individual gauge and physical no-load close
are hard gates. Axial diodes and through-hole resistors do not fit.

## Physical release measurements

Record caliper photographs before soldering:

| Item | Required result |
|---|---:|
| Actual cavity length | at least 47.8 mm |
| Width at all XIAO corners | at least 18.2 mm |
| Floor-to-face height at centre and both ends | record actual |
| Finished battery | passes selected gauge without friction |
| Coin motor | no more than 10 x 10 x 2.7 mm finished |
| Driver island | fully insulated assembly passes 8 x 4 x 2 mm gauge |
| Barrel reference | may be measured, but no qualified guard exists; not for Unit 001 |
| XIAO with solder/wires | passes supplied XIAO gauge |
| Face hook slide | drops and slides without component or band load |

The battery must also have an exact manufacturer/MPN, integrated protection,
permission for at least 50 mA CC/CV charging to 4.20 V, verified polarity, and
a matching UN38.3 test summary. A seller's dimensions alone are not approval.

## Assembly essentials

1. Flash/test the XIAO on USB with the battery disconnected.
2. Dry-fit the empty body, chosen band, and face.
3. Add 0.05 mm electrical floor insulation.
4. Install the qualified battery without broad-face pressure and leave a
   relaxed lead loop.
5. Bond the qualified sealed coin motor to rigid structure. Do not use the
   exposed-rotor barrel reference in Unit 001.
6. Install the SMD-only transistor/flyback/resistor driver and gauge the fully
   insulated 8 x 4 x 2 mm island; never power a motor from GPIO.
7. Put the bridge pads on the shelf and the XIAO on no more than 0.10 mm
   insulated adhesive outside the antenna zone.
8. Transfer the real USB and microphone positions; deburr and gasket.
9. Close first with witness film and fingertip pressure only.
10. Run the full electrical, thermal, RF, audio, drop, rattle, privacy, and
    cosmetic release record before bonding/packing.

## Files and regeneration

- `out/FIT_REPORT.json` contains exact arithmetic and boolean audit values.
- `out/EXACT_historical_body_face_recovery_assembly.step` is the complete
  reference assembly.
- `out/*.step` and `out/*.stl` are the manufacturing and gauge files.
- `out/SHA256SUMS.txt` records all generated artifact hashes.

The source package includes `reference/alu_body.step` and
`reference/alu_face_front_v3.step`, so it regenerates without a sibling repo.
Run `python generate_recovery.py`. Any change producing an intersection above
1e-6 mm3 aborts generation. STL and JSON outputs are byte-reproducible; STEP
export bytes may contain timestamps, so compare imported geometry, not bytes.
