# Fit, battery, motor, and driver gate

Use a 0.01 mm caliper, current-limited supply, multimeter, photographs, and the
printed gauges. A web listing and a CAD pass are not release measurements.

## Shell and board

| Measurement | Required | Actual |
|---|---:|---:|
| Cavity length | >=47.8 mm | |
| Width at all four XIAO corners | >=18.2 mm | |
| Floor to face underside, centre and both ends | record; nominal 8.0 mm before band | |
| Board identity | XIAO nRF52840 Sense, no headers | |
| Selected band | nominal / loose; fingertip seat only | |
| Face closes with no component load | yes | |
| USB-C plug enters without moving PCB | yes | |
| Straight microphone path and gasket | open, no leak around mic | |

Photograph the empty body, face hooks, USB/microphone features, measured board,
and the complete dry-fit before soldering.

## Battery body and lead route

Every answer must be yes:

- Manufacturer, complete MPN, lot/date code, and exact-model datasheet match.
- Finished **pack body** including PCM, wrap, seams, and folded tabs is no more
  than 25 x 10 x 5.5 mm and passes its gauge without friction.
- Leads, splice/connector, bend radius, and strain relief separately pass the
  explicit dry-fit route without pressing, rubbing, or pulling the pouch.
- Integrated protection covers over-charge, over-discharge, over-current, and
  short circuit.
- The exact datasheet maximum charge rating exceeds the **measured worst-case**
  battery-branch current from USB insertion, bootloader, and application, with
  engineering margin. The application target is nominally 50 mA.
- Exact-model UN38.3 test summary is archived before transport; IEC/UL evidence
  is recorded precisely, without turning a datasheet statement into a
  certification claim.
- Polarity and connector pinout are metered and photographed; wire colour and
  connector keying are never trusted.
- Pack is same-lot, flat, odourless, undamaged, stable, and within the exact
  datasheet's accepted receiving voltage range.

The documented target is Renata ICP501022UPM / 100640. The manufacturer
datasheet reports a safety circuit, maximum 24 x 10 x 5.5 mm, 80 mAh nominal,
40 mA normal and 80 mA maximum charge, and states IEC 62133 certification. The
matching UN38.3 summary identifies ICP501022UPM and reports T1-T8 passed. Local
physical stock is not confirmed. Lee PID160959/PID8834 remain unqualified
counter candidates and are rejected without every gate.

Never install a donor earbud/drone/vape cell, a raw RC cell, a generic BMS on
an undocumented pouch, or any cell requiring pressure, folding, sanding,
rewrapping, or direct pouch soldering.

## Coin motor

- Lee PID10431 is a counter candidate, not a qualified part.
- Finished sealed envelope including welds/tape/leads must pass 10 x 10 x 2.7 mm.
- Record maker/MPN, rated voltage, free-run current, startup/stall peak on a
  current-limited 3.0 V supply, and duty limit.
- The selected transistor, flyback diode, 3V3 rail, and wire must exceed the
  measured current with margin.
- Run haptic with audio and BLE; reject reset, RF loss, microphone buzz,
  rubbing, heat, or movement.

The exposed-rotor barrel PID104281 has no qualified guard in this packet and is
**not a Unit 001 shipping fallback**.

## Driver island

Use only SMD parts. Axial 1N5819 and through-hole resistors do not fit. The
fully soldered, cleaned, strain-relieved, and insulated island must pass
`MEASURE_MAX_finished_driver_island_8x4x2.stl` without friction. Verify the
exact transistor and diode pinouts and current ratings. The island has only
0.2 mm nominal wall margin in CAD, so real no-load closure is mandatory.

## No-load closure

1. Gauge every finished part separately.
2. Install <=0.05 mm floor insulation, battery, relaxed lead route, motor,
   driver, safety bridge, XIAO, optional button, and microphone gasket.
3. Keep all hard parts, joints, wire crossings, and adhesive off both broad
   battery faces and pouch edges.
4. Put 0.05 mm witness film over the cell and each board/driver high point.
5. Drop and slide the face with fingertip pressure only.
6. Reopen. Any ridge, pouch mark, board movement, wire pinch, damaged film, or
   latch/bond load needed to overcome a component is a failure.

## Powered gate

Start on a current-limited bench supply with the cell disconnected. Verify no
short and correct 3V3. Connect the qualified pack through an inline meter.
Measure charging from USB insertion through bootloader/application and through
termination/recharge. Repeat open and closed while streaming and pulsing the
haptic. Stop on reset, odour, swelling, unstable voltage, or shell/cell rise of
10 C or more above ambient.
