"""Anticipy Pendant R1 — canonical electrical design.

Single source of truth: components, exact pin-to-net map, footprints, MPNs.
The schematic generator (gen_sch.py) and board generator (gen_pcb.py) both
consume this file, so the schematic, netlist and PCB can never diverge.

Board: 47 x 18 mm, 4-layer, 0.8 mm. Enclosure limit 51 x 21 x 11 mm.
"""

# ---------------------------------------------------------------------------
# Net names
# ---------------------------------------------------------------------------
GND = "GND"
P3V3 = "+3V3"          # LDO output, all peripherals + nRF module
VSYS = "VSYS"          # BQ24075 power-path output (battery or USB)
VBAT = "VBAT"          # battery terminal
VBUS = "VBUS_5V"       # USB 5 V

# Component definition: (ref, lib_symbol, footprint, value, mpn, {pin_number: net})
# Pin numbers are the physical pad numbers of the chosen footprint.

COMPONENTS = [
    # ------------------------------------------------------------------ MCU
    dict(
        ref="U1", sym="RF_Module:MDBT50Q-1MV2",
        fp="RF_Module:Raytac_MDBT50Q",
        value="MDBT50Q-1MV2", mpn="Raytac MDBT50Q-1MV2",
        pins={
            "28": P3V3,          # VDD
            "30": P3V3,          # VDDH (normal-voltage mode: tie to VDD)
            "32": VBUS,          # VBUS (USB detect + USBD PHY supply)
            "1": GND, "2": GND, "15": GND, "33": GND, "55": GND,
            "34": "USB_DN",      # D-
            "35": "USB_DP",      # D+
            "51": "SWDIO",
            "53": "SWDCLK",
            "40": "nRESET",      # P0.18 / reset
            "48": "PDM_CLK",     # P0.24
            "49": "PDM_DATA",    # P0.25
            "37": "FLASH_CS",    # P0.13
            "36": "FLASH_SCK",   # P0.14
            "39": "FLASH_MOSI",  # P0.15
            "38": "FLASH_MISO",  # P0.16
            "19": "I2C_SDA",     # P0.26
            "16": "I2C_SCL",     # P0.27
            "13": "ACC_INT1",    # P0.28
            "57": "BTN",         # P1.06
            "41": "LED_RED",     # P0.17
            "42": "LED_BLUE",    # P0.19
            "44": "HAPTIC_EN",   # P0.20
            "10": "VBAT_SENSE",  # P0.29 / AIN5
            "43": "nCHG_STAT",   # P0.21
            "46": "nPGOOD",      # P0.22
        },
        # every other GPIO pin is intentionally unconnected (NC)
    ),
    # ---------------------------------------------------------- USB-C 16 pin
    dict(
        ref="J1", sym="Connector:USB_C_Receptacle_USB2.0_16P",
        fp="Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
        value="USB4105-GF-A", mpn="GCT USB4105-GF-A",
        pins={
            "A1": GND, "A12": GND, "B1": GND, "B12": GND, "S1": GND,
            "A4": VBUS, "A9": VBUS, "B4": VBUS, "B9": VBUS,
            "A5": "USB_CC1", "B5": "USB_CC2",
            "A6": "USB_DP_CON", "B6": "USB_DP_CON",
            "A7": "USB_DN_CON", "B7": "USB_DN_CON",
            "A8": None, "B8": None,   # SBU unused
        },
    ),
    dict(ref="R1", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="5.1k", mpn="Yageo RC0402FR-075K1L",
         pins={"1": "USB_CC1", "2": GND}),
    dict(ref="R2", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="5.1k", mpn="Yageo RC0402FR-075K1L",
         pins={"1": "USB_CC2", "2": GND}),
    # USB ESD protection
    dict(
        ref="U4", sym="Power_Protection:USBLC6-2SC6",
        fp="Package_TO_SOT_SMD:SOT-23-6",
        value="USBLC6-2SC6", mpn="ST USBLC6-2SC6",
        pins={"1": "USB_DP_CON", "6": "USB_DP",
              "3": "USB_DN_CON", "4": "USB_DN",
              "5": VBUS, "2": GND},
    ),
    # ------------------------------------------------- charger / power path
    dict(
        ref="U2", sym="Battery_Management:BQ24075RGT",
        fp="Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm",
        value="BQ24075RGT", mpn="TI BQ24075RGTR",
        pins={
            "13": VBUS,            # IN
            "10": VSYS, "11": VSYS,  # OUT
            "2": VBAT, "3": VBAT,    # BAT
            "1": "BAT_TS",           # TS (battery NTC)
            "16": "ISET_R",          # ISET
            "12": "ILIM_R",          # ILIM
            "14": GND,               # TMR = GND: safety timer disabled (rev1;
                                     # battery pack is protected — see REVIEW.md)
            "6": GND,                # EN1
            "5": VSYS,               # EN2  (EN2=1/EN1=0: ILIM-programmed input limit)
            "4": GND,                # /CE charge enabled
            "15": GND,               # SYSOFF
            "7": "nPGOOD",           # /PGOOD
            "9": "nCHG_STAT",        # /CHG
            "8": GND, "17": GND,     # VSS + EP
        },
    ),
    dict(ref="R3", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="11k", mpn="Yageo RC0402FR-0711KL",   # ISET: 890/11k ~= 81 mA charge
         pins={"1": "ISET_R", "2": GND}),
    dict(ref="R4", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="3.0k", mpn="Yageo RC0402FR-073KL",   # ILIM: 1550/3k ~= 516 mA input
         pins={"1": "ILIM_R", "2": GND}),
    dict(ref="R5", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="100k", mpn="Yageo RC0402FR-07100KL",  # /CHG pull-up
         pins={"1": "nCHG_STAT", "2": P3V3}),
    dict(ref="R6", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="100k", mpn="Yageo RC0402FR-07100KL",  # /PGOOD pull-up
         pins={"1": "nPGOOD", "2": P3V3}),
    dict(ref="R7", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="10k", mpn="Yageo RC0402FR-0710KL",    # TS fallback (DNP if pack has NTC)
         pins={"1": "BAT_TS", "2": GND}, dnp=True),
    dict(ref="C1", sym="Device:C", fp="Capacitor_SMD:C_0603_1608Metric",
         value="1uF/25V", mpn="Murata GRM188R61E105KA12",
         pins={"1": VBUS, "2": GND}),
    dict(ref="C2", sym="Device:C", fp="Capacitor_SMD:C_0805_2012Metric",
         value="10uF/25V", mpn="Murata GRM21BR61E106KA73",
         pins={"1": VBUS, "2": GND}),
    dict(ref="C3", sym="Device:C", fp="Capacitor_SMD:C_0805_2012Metric",
         value="10uF/10V", mpn="Murata GRM21BR61A106KE19",
         pins={"1": VSYS, "2": GND}),
    dict(ref="C4", sym="Device:C", fp="Capacitor_SMD:C_0805_2012Metric",
         value="10uF/10V", mpn="Murata GRM21BR61A106KE19",
         pins={"1": VBAT, "2": GND}),
    # ------------------------------------------------------------ 3.3 V LDO
    dict(
        ref="U3", sym="Regulator_Linear:AP2112K-3.3",
        fp="Package_TO_SOT_SMD:SOT-23-5",
        value="AP2112K-3.3", mpn="Diodes AP2112K-3.3TRG1",
        pins={"1": VSYS, "3": VSYS, "2": GND, "5": P3V3},  # EN tied to VIN
    ),
    dict(ref="C5", sym="Device:C", fp="Capacitor_SMD:C_0603_1608Metric",
         value="1uF", mpn="Murata GRM188R61A105KA61",
         pins={"1": VSYS, "2": GND}),
    dict(ref="C6", sym="Device:C", fp="Capacitor_SMD:C_0805_2012Metric",
         value="10uF/10V", mpn="Murata GRM21BR61A106KE19",
         pins={"1": P3V3, "2": GND}),
    dict(ref="C7", sym="Device:C", fp="Capacitor_SMD:C_0402_1005Metric",
         value="100nF", mpn="Murata GRM155R71C104KA88",
         pins={"1": P3V3, "2": GND}),   # module VDD local decoupling
    dict(ref="C8", sym="Device:C", fp="Capacitor_SMD:C_0805_2012Metric",
         value="10uF/10V", mpn="Murata GRM21BR61A106KE19",
         pins={"1": P3V3, "2": GND}),   # module bulk
    # ------------------------------------------------------------- microphones
    dict(
        ref="MK1", sym="Sensor_Audio:SPH0641LU4H-1",
        fp="Sensor_Audio:Knowles_LGA-5_3.5x2.65mm",
        value="SPH0641LU4H-1", mpn="Knowles SPH0641LU4H-1",
        pins={"5": P3V3, "3": GND, "2": GND,          # SEL=GND: left channel
              "4": "PDM_CLK", "1": "PDM_DATA"},
    ),
    dict(
        ref="MK2", sym="Sensor_Audio:SPH0641LU4H-1",
        fp="Sensor_Audio:Knowles_LGA-5_3.5x2.65mm",
        value="SPH0641LU4H-1", mpn="Knowles SPH0641LU4H-1",
        pins={"5": P3V3, "3": GND, "2": P3V3,         # SEL=VDD: right channel
              "4": "PDM_CLK", "1": "PDM_DATA"},
    ),
    dict(ref="C9", sym="Device:C", fp="Capacitor_SMD:C_0402_1005Metric",
         value="100nF", mpn="Murata GRM155R71C104KA88",
         pins={"1": P3V3, "2": GND}),   # MK1 decoupling
    dict(ref="C10", sym="Device:C", fp="Capacitor_SMD:C_0402_1005Metric",
         value="100nF", mpn="Murata GRM155R71C104KA88",
         pins={"1": P3V3, "2": GND}),   # MK2 decoupling
    # ------------------------------------------------------------ SPI flash
    dict(
        ref="U5", sym="Memory_Flash:MX25L3233FM2",
        fp="Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
        value="MX25L25645GMI-08G", mpn="Macronix MX25L25645GMI-08G",
        # 256 Mbit (32 MB) in the standard SOP-8 208-mil pattern, so this is
        # the only >16 MB NOR that needs no layout change: Winbond's 32/64 MB
        # parts are WSON-8 8x6 or SOIC-16 300-mil.  Above 128 Mbit the address
        # is 4 bytes — firmware must use 4-byte-address opcodes (see
        # docs/STORAGE.md).  /WP and /HOLD are tied high, so quad/QPI modes
        # stay disabled.
        pins={"1": "FLASH_CS", "2": "FLASH_MISO", "3": P3V3,   # /WP
              "4": GND, "5": "FLASH_MOSI", "6": "FLASH_SCK",
              "7": P3V3, "8": P3V3},                            # /HOLD, VCC
    ),
    dict(ref="C11", sym="Device:C", fp="Capacitor_SMD:C_0402_1005Metric",
         value="100nF", mpn="Murata GRM155R71C104KA88",
         pins={"1": P3V3, "2": GND}),
    # -------------------------------------------------------- accelerometer
    dict(
        ref="U6", sym="Sensor_Motion:LIS2DH",
        fp="Package_LGA:LGA-14_2x2mm_P0.35mm_LayoutBorder3x4y",
        value="LIS2DH12TR", mpn="ST LIS2DH12TR",
        pins={"1": "I2C_SCL", "2": "I2C_SDA",
              "3": GND,          # SDO/SA0 -> addr 0x18
              "4": P3V3,         # CS high = I2C mode
              "6": "ACC_INT1", "5": None,
              "7": P3V3, "8": P3V3,
              "9": GND, "10": GND, "11": GND, "12": GND, "13": GND, "14": GND},
    ),
    dict(ref="R8", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="4.7k", mpn="Yageo RC0402FR-074K7L",
         pins={"1": "I2C_SCL", "2": P3V3}),
    dict(ref="R9", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="4.7k", mpn="Yageo RC0402FR-074K7L",
         pins={"1": "I2C_SDA", "2": P3V3}),
    dict(ref="C12", sym="Device:C", fp="Capacitor_SMD:C_0402_1005Metric",
         value="100nF", mpn="Murata GRM155R71C104KA88",
         pins={"1": P3V3, "2": GND}),
    # ----------------------------------------------------------------- LEDs
    dict(ref="D1", sym="Device:LED", fp="LED_SMD:LED_0603_1608Metric",
         value="RED", mpn="Lite-On LTST-C193KRKT-5A",
         pins={"1": GND, "2": "LED_RED_K"}),        # pin1=K, pin2=A
    dict(ref="R10", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="470R", mpn="Yageo RC0402FR-07470RL",
         pins={"1": "LED_RED", "2": "LED_RED_K"}),
    dict(ref="D2", sym="Device:LED", fp="LED_SMD:LED_0603_1608Metric",
         value="BLUE", mpn="Lite-On LTST-C193TBKT-5A",
         pins={"1": GND, "2": "LED_BLUE_K"}),
    dict(ref="R11", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="220R", mpn="Yageo RC0402FR-07220RL",
         pins={"1": "LED_BLUE", "2": "LED_BLUE_K"}),
    # --------------------------------------------------------------- button
    dict(ref="SW1", sym="Switch:SW_Push",
         fp="Button_Switch_SMD:SW_SPST_EVQP7C",
         value="EVQ-P7C01P", mpn="Panasonic EVQ-P7C01P",
         pins={"1": "BTN", "2": GND}),
    # --------------------------------------------------------------- haptic
    dict(ref="Q1", sym="Transistor_FET:2N7002",
         fp="Package_TO_SOT_SMD:SOT-23",
         value="2N7002", mpn="onsemi 2N7002LT1G",
         pins={"1": "HAPTIC_G", "2": GND, "3": "MOTOR_N"}),
    dict(ref="R12", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="100R", mpn="Yageo RC0402FR-07100RL",
         pins={"1": "HAPTIC_EN", "2": "HAPTIC_G"}),
    dict(ref="R13", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="100k", mpn="Yageo RC0402FR-07100KL",
         pins={"1": "HAPTIC_G", "2": GND}),
    dict(ref="D3", sym="Device:D_Schottky", fp="Diode_SMD:D_SOD-323",
         value="B5819WS", mpn="Vishay B5819WS-TP",   # flyback across motor
         pins={"1": VSYS, "2": "MOTOR_N"}),          # 1=K at VSYS, 2=A at MOTOR_N
    dict(ref="J3", sym="Connector_Generic:Conn_01x02",
         fp="Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal",
         value="MOTOR", mpn="JST SM02B-SRSS-TB",
         pins={"1": VSYS, "2": "MOTOR_N"}),
    # -------------------------------------------------------------- battery
    dict(ref="J2", sym="Connector_Generic:Conn_01x03",
         fp="Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal",
         value="BATT", mpn="JST SM03B-SRSS-TB",
         pins={"1": VBAT, "2": "BAT_TS", "3": GND}),
    # battery voltage sense divider (VBAT/2 -> AIN5)
    dict(ref="R14", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="1M", mpn="Yageo RC0402FR-071ML",
         pins={"1": VBAT, "2": "VBAT_SENSE"}),
    dict(ref="R15", sym="Device:R", fp="Resistor_SMD:R_0402_1005Metric",
         value="1M", mpn="Yageo RC0402FR-071ML",
         pins={"1": "VBAT_SENSE", "2": GND}),
    dict(ref="C13", sym="Device:C", fp="Capacitor_SMD:C_0402_1005Metric",
         value="100nF", mpn="Murata GRM155R71C104KA88",
         pins={"1": "VBAT_SENSE", "2": GND}),
    # ------------------------------------------------------------------ SWD
    dict(ref="J4", sym="Connector:Conn_ARM_SWD_TagConnect_TC2030",
         fp="Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",
         value="TC2030-IDC-NL", mpn="Tag-Connect TC2030-IDC-NL",
         pins={"1": P3V3, "2": "SWDIO", "3": "nRESET",
               "4": "SWDCLK", "5": GND, "6": None}),  # 6 = SWO unused
]

BATTERY = dict(
    mpn="EEMB LP451235 (150 mAh, 4.5 x 12 x 35 mm, protected, 10k NTC, JST SH-3)",
    note="Order with protection circuit + 10k NTC + JST SH 3-pin pigtail "
         "(VBAT / NTC / GND). Alternate: EEMB LP401230 105 mAh.",
)

MOTOR = dict(
    mpn="Seeed/Jinlong Z4TL2B0640001 or generic 8mm x 3.4mm ERM coin, 3V, JST SH-2",
    note="8 mm coin vibration motor, 3 V rated, terminated JST SH 2-pin.",
)
