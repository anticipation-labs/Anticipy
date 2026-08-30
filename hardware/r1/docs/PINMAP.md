# Anticipy R1 — nRF52840 (Raytac MDBT50Q-1MV2) firmware pin map

GPIO names taken from the KiCad MDBT50Q symbol (module pin -> nRF52840 port pin).

| Signal      | Module pin | nRF52840 GPIO | Direction | Notes |
|-------------|-----------|---------------|-----------|-------|
| PDM_CLK     | 48        | P0.24         | out       | Shared clock, both mics |
| PDM_DATA    | 49        | P0.25         | in        | MK1 = one channel, MK2 = other (SELECT strapping) |
| FLASH_CS    | 37        | P0.13         | out       | W25Q128JV SPI CS, active low |
| FLASH_SCK   | 36        | P0.14         | out       | |
| FLASH_MOSI  | 39        | P0.15         | out       | |
| FLASH_MISO  | 38        | P0.16         | in        | |
| I2C_SDA     | 19        | P0.26         | io        | LIS2DH12 (addr 0x18, SDO/SA0 tied to GND) |
| I2C_SCL     | 16        | P0.27         | out       | 4.7k pull-ups to +3V3 (R8, R9) |
| ACC_INT1    | 13        | P0.28         | in        | Motion wake interrupt |
| BTN         | 57        | P1.06         | in, pull-up | SW1 to GND, active low |
| LED_RED     | 41        | P0.17         | out       | Active high via R10 470R |
| LED_BLUE    | 42        | P0.19         | out       | Active high via R11 220R |
| HAPTIC_EN   | 44        | P0.20         | out       | 2N7002 gate, high = motor on |
| VBAT_SENSE  | 10        | P0.29 (AIN5)  | analog    | 1M/1M divider (R14/R15), reads VBAT/2 |
| nCHG_STAT   | 43        | P0.21         | in, pull-up | BQ24075 CHG, open-drain, low = charging |
| nPGOOD      | 46        | P0.22         | in, pull-up | BQ24075 PGOOD, low = USB power present |
| USB_DP      | 35        | USB D+        | usb       | Through USBLC6-2SC6 ESD |
| USB_DN      | 34        | USB D-        | usb       | |
| SWDIO       | 51        | SWDIO         | debug     | Tag-Connect TC2030 J4 |
| SWDCLK      | 53        | SWDCLK        | debug     | |
| nRESET      | 40        | P0.18/RESET   | debug     | |

Power: +3V3 from AP2112K-3.3 (U3), fed by VSYS (BQ24075 power path output).
VBUS_5V comes from the USB-C receptacle (J1) with 5.1k CC pull-downs (R1, R2).
