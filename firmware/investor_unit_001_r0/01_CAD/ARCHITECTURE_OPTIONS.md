# Architecture decision

## Build for Unit 001

Use:

- ordered nylon body and face;
- 4.50 mm printed mid-band and shelf-seated battery bridge;
- XIAO nRF52840 Sense;
- a documented protected 1S pack that passes the 25 x 10 x 5.5 mm maximum
  gauge;
- sealed 10 x 2.7 mm coin motor plus transistor driver;
- fully insulated SMD driver island no larger than 8 x 4 x 2 mm;
- live BLE audio to the Anticipy iPhone app;
- no microSD daughterboard.

The strongest documented battery target is Renata ICP501022UPM: 80 mAh,
24 x 10 x 5.5 mm maximum, safety circuit, 40 mA normal/80 mA maximum charge.
Its manufacturer datasheet states IEC 62133 certification and the matching
UN38.3 summary reports T1-T8 passed. Local stock must still be confirmed.

## Why no microSD

The Adafruit microSD BFF adds about 3 mm before solder tolerance. Keeping it
would require a visibly thicker band, more wiring, another failure surface,
and storage firmware validation. The iPhone app already supplies the actual
recording path. Unit 001 is configured as a paired-phone live-stream device
and may be handed off only after the release record passes.

The XIAO has 2 MiB onboard QSPI, but a short-cache firmware profile remains a
development artifact until encrypted-at-rest storage, owner-only access,
durable phone ACK, power-cut recovery, and loss telemetry all pass.

## Fallbacks

- If the coin motor is unavailable, hold Unit 001. The barrel envelope remains
  a measurement reference only because this packet has no qualified rotor guard.
- If no battery passes documentation and fit, do not install a donor or raw RC
  cell. Use a documented cell in a larger printed enclosure for that unit.
- If haptic causes reset, buzz, battery contact, or RF failure, remove it and
  disclose the missing function; phone haptics are not pendant haptics.

## Release language

Describe a passed Unit 001 as a **functional investor sample in the final
industrial-design direction**. Do not call it production-validated,
certified, waterproof, or customer-sale-ready until those programs exist.
