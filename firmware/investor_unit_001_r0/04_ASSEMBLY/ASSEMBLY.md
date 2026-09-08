# Unit 001 assembly

## Layout

- USB-C exits the existing USB end; XIAO microphone uses the drill-jig opening
  and closed-cell gasket.
- Give the XIAO antenna end the largest air gap. Keep battery PCM, motor,
  driver, wire bundles, and metal-backed adhesive away where the model allows.
- Battery and sealed coin motor sit on <=0.05 mm electrical floor insulation.
- The printed bridge feet stand on rigid shell structure and keep the XIAO
  from loading the pouch.
- The finished insulated SMD driver island occupies the modeled 8 x 4 x 2 mm
  side-strip envelope and must pass its gauge.
- Nothing crosses a motor, USB path, face hook, acoustic path, or pouch edge.

## Haptic circuit

| From | To |
|---|---|
| XIAO 3V3 | Motor positive |
| Motor negative | Qualified SOT-23 NPN collector |
| NPN emitter | XIAO GND |
| XIAO D0 | SMD 1 kOhm, then base |
| Base | SMD 10 kOhm, then GND |
| Qualified SMD flyback cathode | Motor positive / 3V3 |
| Flyback anode | Motor negative / collector |

Use SMD packages only. Lee's 0603/0805 resistors, SOT-23 NPN, and SOT-23
Schottky are local candidates, but the hardware builder must verify exact MPN,
pinout, motor startup/stall margin, diode pulse rating, and the finished island
size before soldering. Never drive the motor directly from D0.

## Optional D7 button

A normally-open switch connects D7 to GND. Mount it to rigid structure and use
an aligned existing face feature. Omit it rather than cut a crooked hole or
load the battery. Owner2 commissions automatically for 120 seconds whenever it
boots with zero stored bonds; without D7, deliberate owner recovery requires a
controlled full SWD erase.

## Band retention

The band-to-PA12 joint is structural. Do not use the electronics silicone as
the structural joint. Prefer an adhesive whose manufacturer explicitly
supports PA12/nylon-to-PETG; Permabond TA4550 is the documented material target,
but local stock is unconfirmed. Any substitute must pass
`ADHESIVE_AND_FINISH_GATE.md` on a sacrificial printed coupon and hidden nylon
test area before it touches Unit 001.

## Build order

1. Verify headerless XIAO nRF52840 Sense identity.
2. Full-erase, flash the owner2 candidate, commission privately, and prove app
   audio/haptic/owner behaviour on USB power.
3. Gauge shell, battery body, lead route, motor, insulated driver, and XIAO.
4. Confirm the selected empty band was bonded to the body Tuesday and has
   completed the TDS cure; verify its co-cured witness coupon before assembly.
5. Assemble/inspect the SMD driver under magnification; continuity and
   current-limit test it before attaching the motor.
6. Apply <=0.05 mm floor insulation. Retain the cell only at protected tab/PCM
   end and cushioned sides; leave a relaxed lead loop.
7. Bond the qualified sealed coin motor to rigid structure with a thin,
   electronics-safe, fully cured process. Never bond it to the cell.
8. Put bridge feet on rigid shelf, then mount XIAO with <=0.10 mm insulated
   transfer adhesive outside the antenna zone.
9. Transfer the real USB/microphone positions, minimally deburr, and fit the
   acoustic gasket/mesh without covering the microphone.
10. Add D7 only if alignment and closure are clean.
11. Complete witness-film no-load closure before closing the removable face.
12. Run powered open-case tests, then run the complete closed-case release
    record. Do not disturb or shortcut the already qualified band bond.

Keep adhesive out of microphone, USB, antenna, button, hooks, leads, and pouch.
