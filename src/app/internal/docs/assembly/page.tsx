import Link from "next/link";

export default function AssemblyPage() {
  return (
    <div className="min-h-screen" style={{ background: "#0C0C0C", color: "#F5F0EB" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">

        <Link href="/internal" className="inline-flex items-center gap-2 text-sm mb-8 hover:opacity-80 transition-opacity" style={{ color: "#8A8A8A" }}>
          ← Internal Dashboard
        </Link>

        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span style={{ color: "#C8A97E" }}>⬡</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Hardware · Orders</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight mb-2">PCB Assembly Guide</h1>
          <p style={{ color: "#8A8A8A" }}>Doc v1.0 · PCB Rev 1.0 · Updated 2026-04-15 · Contact: omar@anticipy.ai</p>
          <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
            Covers hand-solder prototype assembly (1–5 units). For SMT at JLCPCB (10+ units): upload Gerber + CPL + BOM — separate package on request.
          </div>
        </div>

        {/* PCB overview */}
        <section className="mb-10">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "PCB", value: "40 × 25mm, 2-layer, 1.0mm FR4" },
              { label: "Finish", value: "Black solder mask, HASL" },
              { label: "Assembly time", value: "45–60 min/board (experienced)" },
            ].map((s) => (
              <div key={s.label} className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="text-xs mb-1" style={{ color: "#5A5A5A" }}>{s.label}</div>
                <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>{s.value}</div>
              </div>
            ))}
          </div>
        </section>

        {/* BOM */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Bill of Materials</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Ref", "Description", "Value / Part #", "Qty", "Package", "Supplier"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { ref: "U1", desc: "XIAO ESP32-S3 MCU module", val: "113991114", qty: "1", pkg: "Castellated 21×17.5mm", supplier: "Seeed / DigiKey" },
                  { ref: "MIC1", desc: "INMP441 I2S microphone breakout", val: "INMP441-MOD", qty: "1", pkg: "6-pin 2.54mm header", supplier: "AliExpress" },
                  { ref: "LED1", desc: "SK6812 Mini-E addressable RGB LED", val: "C2890364", qty: "1", pkg: "3.5×3.5mm SMD", supplier: "LCSC" },
                  { ref: "U2", desc: "TP4056 + DW01A charger module (USB-C)", val: "TP4056-USBC-MOD", qty: "1", pkg: "Module ~18×10mm", supplier: "AliExpress" },
                  { ref: "BT1", desc: "LiPo 3.7V 400mAh", val: "LP402035", qty: "1", pkg: "4×20×35mm bare cell", supplier: "AliExpress" },
                  { ref: "SW1, SW2", desc: "Tactile button 4×4×1.5mm SMD", val: "SKRPACE010", qty: "2", pkg: "4×4mm SMD", supplier: "DigiKey" },
                  { ref: "SW_PWR", desc: "Slide switch SPDT", val: "SS-12D10", qty: "1", pkg: "Through-hole", supplier: "LCSC" },
                  { ref: "R1, R2", desc: "Resistor 100kΩ", val: "RC0402FR-07100KL", qty: "2", pkg: "0402", supplier: "LCSC" },
                  { ref: "R3, R4", desc: "Resistor 10kΩ", val: "RC0402FR-0710KL", qty: "2", pkg: "0402", supplier: "LCSC" },
                  { ref: "R5", desc: "Resistor 33Ω", val: "RC0402FR-0733RL", qty: "1", pkg: "0402", supplier: "LCSC" },
                  { ref: "C1, C3, C4, C5", desc: "Capacitor 100nF", val: "CL05B104KO5NNNC", qty: "4", pkg: "0402", supplier: "LCSC" },
                  { ref: "C2, C6", desc: "Capacitor 10µF", val: "CL21A106KAYNNNE", qty: "2", pkg: "0805", supplier: "LCSC" },
                  { ref: "J1", desc: "Lanyard hole reinforcement ring (optional)", val: "—", qty: "1", pkg: "4mm ID brass grommet", supplier: "Hardware store" },
                ].map((row) => (
                  <tr key={row.ref} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-2 text-xs font-mono font-semibold" style={{ color: "#C8A97E" }}>{row.ref}</td>
                    <td className="px-4 py-2 text-xs" style={{ color: "#F5F0EB" }}>{row.desc}</td>
                    <td className="px-4 py-2 text-xs font-mono" style={{ color: "#A0A0A0" }}>{row.val}</td>
                    <td className="px-4 py-2 text-xs" style={{ color: "#8A8A8A" }}>{row.qty}</td>
                    <td className="px-4 py-2 text-xs" style={{ color: "#8A8A8A" }}>{row.pkg}</td>
                    <td className="px-4 py-2 text-xs" style={{ color: "#5A5A5A" }}>{row.supplier}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Required tools */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Required Tools and Materials</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              "Soldering iron with fine chisel tip (T12-BC2 or T12-D08), 300–350°C",
              "Solder wire: SAC305 no-clean, 0.3mm diameter",
              "Flux pen: no-clean rosin (e.g. MG Chemicals 8341)",
              "Hot air rework station (optional, useful for LED1 and TP4056)",
              "Tweezers: fine-point ESD-safe (SA #5)",
              "Magnification: stereo microscope or 10× loupe",
              "Multimeter: continuity and DC voltage",
              "USB-C cable for power-on test",
              "Isopropyl alcohol 99% + cotton swabs (flux cleanup)",
              "Kapton tape (to hold modules during soldering)",
            ].map((tool) => (
              <div key={tool} className="flex gap-2 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#A0A0A0" }}>
                <span style={{ color: "#C8A97E" }}>·</span>
                <span>{tool}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Assembly order */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-2" style={{ color: "#C8A97E" }}>Assembly Order</h2>
          <p className="text-xs mb-5" style={{ color: "#5A5A5A" }}>Rule: solder smallest/flattest components first, tallest last. Never place BT1 (battery) until all soldering is complete.</p>

          <div className="space-y-4">
            {[
              {
                step: "Step 1 — SMD Passives: Resistors and Capacitors",
                critical: false,
                items: [
                  "Apply flux to all 0402 and 0805 pads.",
                  "Order: C1, C2, C3, C4, C5, C6 (caps), then R1, R2, R3, R4, R5 (resistors).",
                  "For 0402: apply solder to one pad → tack component → solder second pad → reflow first pad. Minimal solder — small fillet, not a blob.",
                  "Verify values before placement: R1/R2 = 100kΩ, R3/R4 = 10kΩ, R5 = 33Ω. Confirm with DMM ohmmeter.",
                  "Post-step: visual inspection under magnification for bridges and tombstoning.",
                ]
              },
              {
                step: "Step 2 — SK6812 Mini-E LED (LED1)",
                critical: true,
                criticalNote: "Tiny 3.5×3.5mm IC with 4 pads on the underside. Hardest component on the board.",
                items: [
                  "Apply flux to all 4 LED pads on PCB.",
                  "Pre-tin one pad (GND pad — largest, nearest cathode dot).",
                  "Place LED1 with correct orientation: pin 1/DIN corner matches silkscreen dot.",
                  "Pin order (from above, pads underneath): 1=DIN, 2=VDD, 3=DOUT, 4=GND.",
                  "Reflow pre-tinned pad to tack → solder remaining 3 pads with fine tip + minimal solder.",
                  "Inspect: all 4 pads visible, no bridges between adjacent pads.",
                  "GND pad (pin 4) is largest and has thermal relief — needs slightly more heat.",
                ]
              },
              {
                step: "Step 3 — Tactile Buttons (SW1, SW2)",
                critical: false,
                items: [
                  "4×4mm SMD tactile switches.",
                  "All 4 legs are ground (symmetric) — orientation matters only for fit, not electrically.",
                  "Solder one leg → check component is seated flat → solder remaining 3 legs.",
                  "Apply light pressure while soldering to prevent switch from lifting.",
                ]
              },
              {
                step: "Step 4 — Slide Switch (SW_PWR)",
                critical: false,
                items: [
                  "Through-hole SPDT SS-12D10.",
                  "Insert through PCB from top, bend leads slightly on bottom to hold in place.",
                  "Solder 3 leads on PCB bottom side.",
                  "Trim excess lead to 0.5mm above solder joint.",
                  "Verify: switch toggles cleanly with audible click, mechanism not obstructed by solder.",
                ]
              },
              {
                step: "Step 5 — TP4056 Charging Module (U2)",
                critical: false,
                items: [
                  "Module has solder pads around perimeter: IN+, IN–, BAT+, BAT–, OUT+, OUT–.",
                  "Apply flux to module pads and PCB pads.",
                  "Place module → use Kapton tape to hold → tack one corner → verify alignment → solder remaining pads.",
                  "Optional: hot air at 300°C to reflow all pads simultaneously.",
                  "Post-solder: confirm IN+ to IN– open, BAT+ to BAT– open (before cell connected).",
                ]
              },
              {
                step: "Step 6 — INMP441 Microphone Module (MIC1)",
                critical: false,
                items: [
                  "6-pin 2.54mm header (VDD, GND, SCK, WS, SD, L/R).",
                  "Option A (prototype): solder 6-pin female socket on PCB, plug module in — allows replacement without rework.",
                  "Option B (production): solder module directly — trim header pins to 3mm, insert through PCB holes.",
                  "L/R pin MUST connect to GND — verify continuity.",
                  "Ensure mic port on INMP441 faces toward PCB mic hole (bottom of pendant case).",
                ]
              },
              {
                step: "Step 7 — XIAO ESP32-S3 (U1)",
                critical: true,
                criticalNote: "Solder this last. 14 castellated pads on each long side. Bridging any pair will kill the module.",
                items: [
                  "Apply flux generously to all XIAO footprint pads on PCB.",
                  "Place XIAO module — pin 1 (GPIO1) at marked corner on silkscreen.",
                  "Tack 2 diagonal corner pads first to set alignment.",
                  "Solder each pad individually: touch iron → apply minimal 0.3mm wire → remove iron.",
                  "Work from one end to the other — do NOT skip around.",
                  "Common mistakes: bridging adjacent pads, cold joints on castellated edges.",
                  "Post-solder: wipe flux with IPA + swab. Inspect all 14+14 pads under magnification.",
                  "Continuity check: adjacent pins NOT shorted. 3V3 to GND = open. 5V to GND = open.",
                ]
              },
            ].map((section) => (
              <div key={section.step} className="p-5 rounded-xl" style={{ background: "#161616", border: section.critical ? "1px solid rgba(239,68,68,0.3)" : "1px solid #252525" }}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="font-semibold text-sm" style={{ color: "#F5F0EB" }}>{section.step}</span>
                  {section.critical && (
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}>CRITICAL</span>
                  )}
                </div>
                {section.critical && section.criticalNote && (
                  <div className="text-xs mb-3 p-2 rounded" style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444" }}>
                    ⚠ {section.criticalNote}
                  </div>
                )}
                <ul className="space-y-1.5">
                  {section.items.map((item, i) => (
                    <li key={i} className="text-xs flex gap-2" style={{ color: "#A0A0A0" }}>
                      <span className="flex-shrink-0" style={{ color: "#C8A97E" }}>{i + 1}.</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* Continuity checks */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Pre-Battery Continuity Checks</h2>
          <p className="text-xs mb-4" style={{ color: "#5A5A5A" }}>Do NOT connect any power before completing these checks.</p>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Check", "Expected", "Method"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { check: "3V3 to GND", expected: "Open (no short)", method: "DMM resistance — should be >10kΩ" },
                  { check: "5V to GND", expected: "Open (no short)", method: "DMM resistance" },
                  { check: "I2S_BCLK (GPIO6)", expected: "Connected to MIC1 SCK", method: "DMM continuity beep" },
                  { check: "I2S_LRCK (GPIO7)", expected: "Connected to MIC1 WS", method: "DMM continuity beep" },
                  { check: "I2S_DATA (GPIO8)", expected: "Connected to MIC1 SD", method: "DMM continuity beep" },
                  { check: "LED_DATA (GPIO4)", expected: "Connected to R5 → LED1 DIN", method: "DMM continuity beep" },
                  { check: "BATT_ADC midpoint", expected: "100kΩ to BATT_P, 100kΩ to GND", method: "DMM resistance ~100kΩ each way" },
                  { check: "MIC1 L/R pin", expected: "Shorted to GND", method: "DMM continuity beep" },
                  { check: "U2 IN+", expected: "Connected to USB-C VBUS pad", method: "DMM continuity" },
                  { check: "U2 OUT+", expected: "SW_PWR common pin", method: "DMM continuity" },
                ].map((row) => (
                  <tr key={row.check} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-2 text-xs font-mono" style={{ color: "#C8A97E" }}>{row.check}</td>
                    <td className="px-4 py-2 text-xs font-medium" style={{ color: "#F5F0EB" }}>{row.expected}</td>
                    <td className="px-4 py-2 text-xs" style={{ color: "#8A8A8A" }}>{row.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* First power-on */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>First Power-On Test Sequence</h2>
          <div className="space-y-4">
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="font-semibold text-sm mb-3" style={{ color: "#F5F0EB" }}>7a. USB-C Power Test (TP4056 only)</div>
              <ul className="space-y-1.5">
                {[
                  "Slide SW_PWR to OFF position.",
                  "Connect USB-C to 5V/1A charger (NOT computer — charger only).",
                  "Expected: TP4056 red CHRG LED illuminates. No smoke. No excessive heat on U2.",
                  "Measure: BATT_P rail should read ~5V briefly, then settle to 4.2V charge voltage.",
                  "Disconnect USB-C.",
                ].map((item, i) => (
                  <li key={i} className="text-xs flex gap-2" style={{ color: "#A0A0A0" }}>
                    <span style={{ color: "#C8A97E" }}>{i + 1}.</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="font-semibold text-sm mb-3" style={{ color: "#F5F0EB" }}>7b. LiPo Connection</div>
              <ul className="space-y-1.5">
                {[
                  "Confirm cell voltage with DMM: should read 3.5–4.2V.",
                  "Match polarity: red wire to BT1 +, black wire to BT1 –.",
                  "Apply small amount of solder to hold wires. Use Kapton tape as strain relief.",
                  "Do NOT use JST connectors unless footprint is present — direct solder for prototype.",
                ].map((item, i) => (
                  <li key={i} className="text-xs flex gap-2" style={{ color: "#A0A0A0" }}>
                    <span style={{ color: "#C8A97E" }}>{i + 1}.</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="font-semibold text-sm mb-3" style={{ color: "#F5F0EB" }}>7c. MCU Power-On and Serial Output</div>
              <p className="text-xs mb-3" style={{ color: "#8A8A8A" }}>Slide SW_PWR to ON. Connect USB-C from computer. Open serial monitor at 115200 baud.</p>
              <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #1A1A1A" }}>
                <pre className="text-xs p-3 overflow-x-auto" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`Anticipy v1.0.0
NVS: no WiFi credentials stored
LED: init OK
I2S: init OK (GPIO6=BCLK, GPIO7=LRCK, GPIO8=DIN)
VAD: threshold=300 RMS
BLE: advertising as "Anticipy-Pendant"`}</pre>
              </div>
            </div>
          </div>
        </section>

        {/* Functional test table */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Functional Tests</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Test", "Procedure", "Pass Criteria"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { test: "LED", proc: "Run led_test firmware", pass: "All 8 colors cycle, no stuck pixel" },
                  { test: "Microphone", proc: "Serial monitor + speak near mic", pass: "\"VAD: speech detected\" prints within 0.5s" },
                  { test: "Button A tap", proc: "Single tap SW1", pass: "Serial: \"BTN_A: tap\"" },
                  { test: "Button A hold", proc: "Hold SW1 3+ seconds", pass: "LED goes rainbow cycle" },
                  { test: "Battery ADC", proc: "Serial monitor", pass: "Battery voltage printed every 30s, ±0.1V of DMM" },
                  { test: "WiFi", proc: "BLE provision via app", pass: "Device connects, gets IP, serial shows IP" },
                  { test: "Upload", proc: "Double-tap SW1", pass: "Serial: \"HTTP 200\" after upload" },
                  { test: "BLE", proc: "Hold SW1 3s", pass: "\"Anticipy-Pendant\" visible in phone Bluetooth scan" },
                  { test: "Charging", proc: "Plug USB-C while powered", pass: "TP4056 CHRG LED on; serial: \"charging\"" },
                  { test: "Deep sleep", proc: "Idle 10 minutes", pass: "LED off, current < 1 mA on bench supply" },
                ].map((row) => (
                  <tr key={row.test} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-semibold" style={{ color: "#C8A97E" }}>{row.test}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.proc}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#F5F0EB" }}>{row.pass}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* QA checklist */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Quality Gate — All Must Pass Before Shipping</h2>
          <div className="grid grid-cols-2 gap-2">
            {[
              "All 10 functional tests in §7d pass",
              "No flux residue visible under magnification",
              "XIAO castellated pads all soldered, no bridges",
              "SK6812 LED cycles all colors correctly",
              "TP4056 charges cell to 4.2V and terminates",
              "Slide switch toggles power cleanly",
              "Both tactile buttons register in firmware",
              "Voltage divider reads correct battery voltage (±0.1V)",
              "Serial log shows clean boot, no error messages",
              "BLE advertising visible from 5+ meters",
            ].map((item) => (
              <div key={item} className="flex items-center gap-3 p-3 rounded-lg" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="w-4 h-4 rounded flex-shrink-0" style={{ border: "1px solid #C8A97E" }} />
                <span className="text-xs" style={{ color: "#A0A0A0" }}>{item}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
            Failed units: rework and retest. If rework &gt; 2 attempts, scrap the XIAO module and replace.
          </div>
        </section>

        {/* Case assembly */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Case Assembly (After QA Pass)</h2>
          <div className="space-y-2">
            {[
              "Thread lanyard through 4mm hole in top of front shell before inserting PCB.",
              "Insert PCB into front shell: XIAO USB-C aligns with bottom cutout, SW_PWR faces side cutout, MIC1 faces bottom mic port, LED1 aligns with diffuser channel.",
              "Route battery flat under PCB on foam pad in back plate.",
              "Snap back plate onto front shell. Finger-tight for prototype.",
              "Optional: 4× M1.4 screws into screw bosses for production-grade closure.",
              "Final visual: USB-C accessible, slider operable, button dimples aligned, LED glow visible through diffuser.",
            ].map((item, i) => (
              <div key={i} className="flex gap-3 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#A0A0A0" }}>
                <span className="flex-shrink-0 font-semibold" style={{ color: "#C8A97E" }}>{i + 1}.</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}
