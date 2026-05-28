import Link from "next/link";

export default function SchematicPage() {
  return (
    <div className="min-h-screen" style={{ background: "#0C0C0C", color: "#F5F0EB" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">

        <Link href="/internal" className="inline-flex items-center gap-2 text-sm mb-8 hover:opacity-80 transition-opacity" style={{ color: "#8A8A8A" }}>
          ← Internal Dashboard
        </Link>

        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span style={{ color: "#C8A97E" }}>⬡</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Hardware</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight mb-2">PCB Schematic</h1>
          <p style={{ color: "#8A8A8A" }}>Anticipy Pendant — Rev 1.0 · 40 × 25 mm, 2-layer, 1.0mm FR4, black HASL · Updated 2026-04-15</p>
        </div>

        {/* U1 — XIAO ESP32-S3 */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>U1 — Seeed XIAO ESP32-S3</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["XIAO Pin", "GPIO", "Net Name", "Connected To", "Notes"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { pin: "1", gpio: "GPIO1", net: "BTN_A", conn: "SW1 pin 1; pull-up to 3V3 via R3 10kΩ", notes: "Tap = toggle record; hold 3s = BLE pair" },
                  { pin: "2", gpio: "GPIO2", net: "BATT_ADC", conn: "R1/R2 voltage divider midpoint", notes: "100k/100k divider; reads 0–1.85V for 0–3.7V cell" },
                  { pin: "3", gpio: "GPIO3", net: "BTN_B", conn: "SW2 pin 1; pull-up to 3V3 via R4 10kΩ", notes: "Reserved (double-tap)" },
                  { pin: "4", gpio: "GPIO4", net: "LED_DATA", conn: "LED1 DIN pin via R5 33Ω", notes: "WS2812/SK6812 data; 33Ω series resistor" },
                  { pin: "5", gpio: "GPIO5", net: "GPIO5", conn: "—", notes: "Spare / future use" },
                  { pin: "6", gpio: "GPIO6", net: "I2S_BCLK", conn: "MIC1 SCK pin", notes: "I2S bit clock output to INMP441" },
                  { pin: "7", gpio: "GPIO7", net: "I2S_LRCK", conn: "MIC1 WS pin", notes: "I2S word select (L/R) output to INMP441" },
                  { pin: "8", gpio: "GPIO8", net: "I2S_DATA", conn: "MIC1 SD pin", notes: "I2S data input from INMP441" },
                  { pin: "9", gpio: "GPIO9", net: "GPIO9", conn: "—", notes: "Spare" },
                  { pin: "10", gpio: "GPIO10", net: "GPIO10", conn: "—", notes: "Spare" },
                  { pin: "11", gpio: "3V3", net: "PWR_3V3", conn: "C1/C2 bypass, MIC1 VDD, LED1 VDD, R3/R4 pull-ups", notes: "3.3V LDO output from XIAO onboard ME6211" },
                  { pin: "12", gpio: "GND", net: "GND", conn: "TP4056 GND, battery –, MIC1 GND, LED1 GND, SW1-2, SW2-2", notes: "System ground" },
                  { pin: "13", gpio: "5V", net: "PWR_5V", conn: "TP4056 OUT+ via SW_PWR SPDT slide switch", notes: "Battery-side 3.7V → XIAO 5V pad (accepts 3.7–5.5V)" },
                  { pin: "14", gpio: "BAT", net: "PWR_BAT", conn: "NC", notes: "Not connected — XIAO internal LiPo connector, unused" },
                  { pin: "—", gpio: "USB D+", net: "USB_DP", conn: "USB-C connector via castellated pad", notes: "Programming / debug" },
                  { pin: "—", gpio: "USB D–", net: "USB_DM", conn: "USB-C connector via castellated pad", notes: "Programming / debug" },
                ].map((row) => (
                  <tr key={row.pin + row.gpio} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#5A5A5A" }}>{row.pin}</td>
                    <td className="px-4 py-3 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.gpio}</td>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#F5F0EB" }}>{row.net}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.conn}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#5A5A5A" }}>{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* MIC1 */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>MIC1 — INMP441 I2S MEMS Microphone Breakout</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Module Pin", "Net Name", "Connected To", "Notes"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { pin: "VDD", net: "PWR_3V3", conn: "U1 3V3 pin 11", notes: "3.3V supply; module has onboard 100nF bypass cap" },
                  { pin: "GND", net: "GND", conn: "System GND", notes: "" },
                  { pin: "SCK", net: "I2S_BCLK", conn: "U1 GPIO6 (pin 6)", notes: "Bit clock" },
                  { pin: "WS", net: "I2S_LRCK", conn: "U1 GPIO7 (pin 7)", notes: "Word select / LR clock" },
                  { pin: "SD", net: "I2S_DATA", conn: "U1 GPIO8 (pin 8)", notes: "Serial data output (MISO from mic POV)" },
                  { pin: "L/R", net: "GND", conn: "System GND", notes: "MUST tie to GND — selects left channel; floating = undefined output" },
                ].map((row) => (
                  <tr key={row.pin} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.pin}</td>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#F5F0EB" }}>{row.net}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.conn}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#5A5A5A" }}>{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* LED1 */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>LED1 — SK6812 Mini-E Addressable RGB LED</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["LED Pin", "Net Name", "Connected To", "Notes"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { pin: "VDD", net: "PWR_3V3", conn: "U1 3V3 pin 11 via C3 100nF bypass", notes: "3.3V supply; SK6812 Mini-E rated 3.3–5V; brightness slightly reduced vs 5V but within spec" },
                  { pin: "GND", net: "GND", conn: "System GND", notes: "" },
                  { pin: "DIN", net: "LED_DATA", conn: "U1 GPIO4 (pin 4) via R5 33Ω", notes: "Series resistor protects ESP32 GPIO and dampens ringing" },
                  { pin: "DOUT", net: "NC", conn: "NC", notes: "No daisy-chain — single LED only" },
                ].map((row) => (
                  <tr key={row.pin} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.pin}</td>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#F5F0EB" }}>{row.net}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.conn}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#5A5A5A" }}>{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* U2 — TP4056 */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>U2 — TP4056 + DW01A Charging Module (USB-C input)</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Module Pin", "Net Name", "Connected To", "Notes"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { pin: "IN+", net: "USB_5V", conn: "USB-C connector VBUS pin", notes: "5V from USB charger" },
                  { pin: "IN–", net: "GND", conn: "System GND", notes: "" },
                  { pin: "BAT+", net: "BATT_P", conn: "Battery + terminal; SW_PWR SPDT common pin", notes: "Charge output to LiPo cell" },
                  { pin: "BAT–", net: "GND", conn: "Battery – terminal; System GND", notes: "" },
                  { pin: "OUT+", net: "PWR_5V", conn: "SW_PWR SPDT switched pin → U1 5V pad", notes: "ALWAYS connect MCU load to OUT+ (protected), never to BAT+" },
                  { pin: "OUT–", net: "GND", conn: "System GND", notes: "DW01A over-discharge protection; cuts off at ~2.8V" },
                  { pin: "CHRG LED", net: "NC", conn: "NC (LED on TP4056 module)", notes: "Red = charging" },
                  { pin: "STDBY LED", net: "NC", conn: "NC (LED on TP4056 module)", notes: "Blue = standby (charge complete)" },
                ].map((row) => (
                  <tr key={row.pin} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.pin}</td>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#F5F0EB" }}>{row.net}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.conn}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#5A5A5A" }}>{row.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Passive components */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Passive Components</h2>
          <div className="grid grid-cols-1 gap-4">

            {/* Capacitors */}
            <div>
              <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>C1–C6 — Bypass Capacitors</h3>
              <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                      {["Ref", "Value", "Package", "Placed Near", "Net"].map((h) => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { ref: "C1", val: "100nF 0402", pkg: "0402", near: "U1 3V3 pin", net: "3V3 to GND" },
                      { ref: "C2", val: "10µF 0805", pkg: "0805", near: "U1 3V3 pin", net: "3V3 to GND (bulk)" },
                      { ref: "C3", val: "100nF 0402", pkg: "0402", near: "LED1 VDD", net: "3V3 to GND" },
                      { ref: "C4", val: "100nF 0402", pkg: "0402", near: "MIC1 VDD", net: "3V3 to GND" },
                      { ref: "C5", val: "100nF 0402", pkg: "0402", near: "U2 IN+", net: "5V USB to GND" },
                      { ref: "C6", val: "10µF 0805", pkg: "0805", near: "U2 IN+", net: "5V USB to GND (bulk)" },
                    ].map((row) => (
                      <tr key={row.ref} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                        <td className="px-4 py-2 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.ref}</td>
                        <td className="px-4 py-2 text-xs font-mono" style={{ color: "#F5F0EB" }}>{row.val}</td>
                        <td className="px-4 py-2 text-xs" style={{ color: "#8A8A8A" }}>{row.pkg}</td>
                        <td className="px-4 py-2 text-xs" style={{ color: "#A0A0A0" }}>{row.near}</td>
                        <td className="px-4 py-2 text-xs" style={{ color: "#5A5A5A" }}>{row.net}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Resistors */}
            <div>
              <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>R1–R5 — Resistors</h3>
              <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                      {["Ref", "Value", "Purpose", "Net"].map((h) => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { ref: "R1", val: "100kΩ 0402", purpose: "Voltage divider upper leg", net: "Top: BATT_P → Bottom: BATT_ADC" },
                      { ref: "R2", val: "100kΩ 0402", purpose: "Voltage divider lower leg", net: "Top: BATT_ADC → Bottom: GND" },
                      { ref: "R3", val: "10kΩ 0402", purpose: "BTN_A pull-up", net: "3V3 to BTN_A" },
                      { ref: "R4", val: "10kΩ 0402", purpose: "BTN_B pull-up", net: "3V3 to BTN_B" },
                      { ref: "R5", val: "33Ω 0402", purpose: "LED signal series resistor", net: "LED_DATA: GPIO4 → R5 → LED1 DIN" },
                    ].map((row) => (
                      <tr key={row.ref} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                        <td className="px-4 py-2 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.ref}</td>
                        <td className="px-4 py-2 text-xs font-mono" style={{ color: "#F5F0EB" }}>{row.val}</td>
                        <td className="px-4 py-2 text-xs" style={{ color: "#A0A0A0" }}>{row.purpose}</td>
                        <td className="px-4 py-2 text-xs" style={{ color: "#5A5A5A" }}>{row.net}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
                Divider ratio = 0.5: at Vbatt = 3.7V → ADC reads 1.85V (within ESP32-S3 ADC range of 0–3.3V).
              </div>
            </div>

          </div>
        </section>

        {/* Net summary */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Net Summary</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Net Name", "Nodes"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { net: "PWR_5V", nodes: "U2 OUT+, SW_PWR switched output, U1 5V pad" },
                  { net: "PWR_3V3", nodes: "U1 3V3 output, C1, C2, C3, C4, R3, R4, MIC1 VDD, LED1 VDD" },
                  { net: "GND", nodes: "U1 GND, U2 GND, BT1 –, MIC1 GND, LED1 GND, SW1-2, SW2-2, R2 bottom, C1–C6 bottom" },
                  { net: "BATT_P", nodes: "BT1 +, U2 BAT+, SW_PWR common, R1 top" },
                  { net: "BATT_ADC", nodes: "R1 bottom, R2 top, U1 GPIO2" },
                  { net: "I2S_BCLK", nodes: "U1 GPIO6, MIC1 SCK" },
                  { net: "I2S_LRCK", nodes: "U1 GPIO7, MIC1 WS" },
                  { net: "I2S_DATA", nodes: "U1 GPIO8, MIC1 SD" },
                  { net: "LED_DATA", nodes: "U1 GPIO4, R5 left; R5 right, LED1 DIN" },
                  { net: "BTN_A", nodes: "SW1 pin 1, R3 bottom, U1 GPIO1" },
                  { net: "BTN_B", nodes: "SW2 pin 1, R4 bottom, U1 GPIO3" },
                ].map((row) => (
                  <tr key={row.net} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.net}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.nodes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Design notes */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Design Notes</h2>
          <div className="space-y-3">
            {[
              { n: "1", title: "L/R pin on INMP441 must be tied to GND", body: "If left floating, the I2S output is undefined. Always solder L/R to GND for left-channel selection. Verify with continuity check before powering on." },
              { n: "2", title: "SK6812 VDD at 3.3V is within spec", body: "SK6812 Mini-E is rated 3.3–5V. Running at 3.3V is fine — brightness is slightly reduced vs 5V but the LED operates correctly. 3.3V simplifies power rail design." },
              { n: "3", title: "MCU load MUST connect to OUT+ not BAT+", body: "Always route MCU power through TP4056 OUT+ (protected side), never directly to BAT+. The DW01A protection IC cuts OFF on over-discharge at ~2.8V — this only works if load is on OUT+." },
              { n: "4", title: "Series resistor R5 on LED data line", body: "33Ω resistor between GPIO4 and LED1 DIN prevents GPIO latch-up during power transitions and dampens signal ringing on the LED data line. Do not omit." },
              { n: "5", title: "No USB-C PD negotiation needed", body: "TP4056 charges at 5V/1A from any USB-A to USB-C or USB-C to USB-C charger without PD negotiation. The XIAO 5V pad receives battery power (3.7–4.2V) via slide switch — charge and run can be simultaneous." },
            ].map((note) => (
              <div key={note.n} className="flex gap-4 p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>
                  {note.n}
                </div>
                <div>
                  <div className="font-medium text-sm mb-1" style={{ color: "#F5F0EB" }}>{note.title}</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>{note.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}
