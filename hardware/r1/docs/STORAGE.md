# Audio storage budget

Target: 16 h of on-device speech backup when the phone is not connected.

## Bitrate vs. capacity

16 kHz mono speech, single channel:

| Encoding | Bitrate | Bytes/hour | 16 h needs |
|---|---|---|---|
| Raw PCM 16-bit | 256 kbps | 115 MB | 1.84 GB |
| IMA/ADPCM 4-bit | 64 kbps | 28.8 MB | 461 MB |
| Opus 16 kbps | 16 kbps | 7.2 MB | 115 MB |
| Opus 12 kbps | 12 kbps | 5.4 MB | 86 MB |
| Opus 8 kbps (narrowband) | 8 kbps | 3.6 MB | 58 MB |

Reserve 1 MB for firmware DFU image staging, config and the file index; on NAND
also reserve ~4 % for bad-block replacement and ECC spare area.

## What each storage option actually delivers

| Device | Type | Capacity | Usable | Runtime @16 kbps | Runtime @8 kbps |
|---|---|---|---|---|---|
| W25Q128JVSIQ | SPI NOR, SOIC-8 208 mil | 16 MB | 15 MB | 2.1 h | 4.2 h |
| **MX25L25645GMI-08G (r1, fitted)** | SPI NOR, SOP-8 208 mil | 32 MB | 31 MB | 4.3 h | 8.6 h |
| W25Q256JVEIQ | SPI NOR, WSON-8 8x6 | 32 MB | 31 MB | 4.3 h | 8.6 h |
| W25N01KVZEIR | SPI NAND, WSON-8 8x6 | 128 MB | ~120 MB | **16.6 h** | 33 h |

**No NOR option reaches 16 h, including the one fitted.** The flash is a
streaming buffer: audio is offloaded to the phone over BLE, and 32 MB covers
4.3 h of disconnection at 16 kbps (8.6 h narrowband).

## Why the fitted part is the Macronix, not the Winbond

Every Winbond NOR above 128 Mbit changes package: `W25Q256JVEIQ` is WSON-8
8x6 mm (a 3.4x4.3 mm grounded thermal pad where the SOIC body was hollow) and
`W25Q512JVFIQ` is SOIC-16 300 mil. Dropping the WSON footprint into U5's place
was tried and rejected: its courtyard collides with both C4 and the Tag-Connect
J4 pads, and the copper that ran under the old SOIC body shorts to the thermal
pad, so it forces a placement change plus a re-route of the flash, I2C, LED and
reset nets.

`MX25L25645GMI-08G` is 256 Mbit in the standard SOP-8 208 mil pattern with the
same signal order, so it doubles usable recording time on the existing, verified
layout — zero placement or routing change. Firmware cost: addresses are 4 bytes
above 128 Mbit, so the driver must issue `EN4B` (0xB7) or use the 4-byte opcodes
(`0x13` read, `0x12` page program, `0xDC` block erase). JEDEC ID is `C2 20 19`.

## Path to 16 h (r1b)

`W25N01KVZEIR` — Winbond 1 Gbit SPI NAND, WSON-8 (8x6 mm), JLCPCB `C22472329`.

- Same 8-pin SPI signal order as the fitted NOR (`/CS, DO, /WP, GND, DI, CLK, /HOLD, VCC`),
  so the schematic net assignment and the nRF52840 pin map are unchanged.
- Footprint changes from `Package_SO:SOIC-8_5.3x5.3mm_P1.27mm` to
  `Package_SON:WSON-8-1EP_8x6mm_P1.27mm_EP3.4x4.3mm`, which is 8x6 mm instead of
  5.3x5.3 mm — U5 and its neighbours (C11, C8) move, and the six SPI traces are
  re-routed.
- Firmware needs a NAND driver: page program/read (2 kB pages), block erase
  (128 kB), bad-block table, ECC status handling and wear levelling. The NOR
  driver does not transfer.
- `W25Q256JVEIQ` (32 MB NOR, `C97522`) uses the same WSON-8 footprint and keeps
  the NOR driver, so one r1b footprint change covers both options.
- U5 has to move: the WSON courtyard (8.75 x 6.59 mm with margin) does not fit
  between C4 (right edge 24.745 mm) and J4 (left edge 33.255 mm) at y = 9 mm.

Because the NAND driver does not exist yet, the capacity would sit unused on the
first board. r1 ships with 32 MB of NOR for electrical/RF/acoustic bring-up and
BLE-offload operation; 16 h of standalone recording lands in r1b with the NAND
and the driver that can use it.
