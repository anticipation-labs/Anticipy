import Link from "next/link";

export default function BOMPage() {
  return (
    <div className="min-h-screen" style={{ background: "#0C0C0C", color: "#F5F0EB" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">

        <Link href="/internal" className="inline-flex items-center gap-2 text-sm mb-8 hover:opacity-80 transition-opacity" style={{ color: "#8A8A8A" }}>
          ← Internal Dashboard
        </Link>

        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span style={{ color: "#C8A97E" }}>⬡</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Hardware · Research</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight mb-2">Bill of Materials</h1>
          <p style={{ color: "#8A8A8A" }}>Anticipy Wearable — verified component pricing with live supplier links. Updated April 15, 2026.</p>
        </div>

        {/* Cost summary callout */}
        <div className="grid grid-cols-3 gap-4 mb-10">
          {[
            { label: "Single prototype (shipped)", usd: "~$56 USD", cad: "~$77 CAD" },
            { label: "10-unit pilot batch", usd: "~$32/unit", cad: "~$44 CAD" },
            { label: "1,000-unit production", usd: "~$19/unit", cad: "~$26 CAD" },
          ].map((s) => (
            <div key={s.label} className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="text-xs mb-2" style={{ color: "#5A5A5A" }}>{s.label}</div>
              <div className="text-xl font-semibold" style={{ color: "#C8A97E" }}>{s.cad}</div>
              <div className="text-xs mt-1" style={{ color: "#5A5A5A" }}>{s.usd}</div>
            </div>
          ))}
        </div>

        {/* Main BOM table */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-1" style={{ color: "#C8A97E" }}>Component List — Single Prototype</h2>
          <p className="text-xs mb-4" style={{ color: "#5A5A5A" }}>All prices USD. CAD conversion ×1.38. Prices verified April 2026.</p>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["#", "Component", "Part / SKU", "Supplier", "Unit Price", "Qty", "Line Total", "Buy"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 font-medium text-xs" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  {
                    n: 1, component: "MCU Module", part: "Seeed XIAO ESP32-S3 · 113991114",
                    supplier: "DigiKey", price: "$7.49", qty: "1", total: "$7.49",
                    url: "https://www.digikey.com/en/products/detail/seeed-technology-co-ltd/113991114/19285530",
                    note: "Also at seeedstudio.com for $10.33 CAD shipped"
                  },
                  {
                    n: 2, component: "MEMS Microphone", part: "INMP441 I2S breakout · INMP441-MOD",
                    supplier: "AliExpress", price: "$2.00", qty: "1", total: "$2.00",
                    url: "https://www.aliexpress.com/wholesale?SearchText=INMP441+I2S+microphone+ESP32",
                    note: "Choose store with 4.8★ + 500+ sales"
                  },
                  {
                    n: 3, component: "LiPo Battery", part: "LP402035 3.7V 400mAh, 4×20×35mm",
                    supplier: "AliExpress", price: "$3.50", qty: "1", total: "$3.50",
                    url: "https://www.aliexpress.com/wholesale?SearchText=LP402035+400mah+3.7V+lipo",
                    note: "Buy 10 for spares; declare as 'electronic component' at customs"
                  },
                  {
                    n: 4, component: "Charger + Protection", part: "TP4056 + DW01A USB-C module",
                    supplier: "AliExpress", price: "$0.85", qty: "1", total: "$0.85",
                    url: "https://www.aliexpress.com/wholesale?SearchText=TP4056+USB-C+lithium+charger",
                    note: "1A charge rate; fills 400mAh in ~30 min"
                  },
                  {
                    n: 5, component: "RGB LED", part: "SK6812 Mini-E · C2890364",
                    supplier: "LCSC", price: "$0.18", qty: "1", total: "$0.18",
                    url: "https://www.lcsc.com/product-detail/C2890364.html",
                    note: "Reverse-mount addressable; 3.3V compatible"
                  },
                  {
                    n: 6, component: "Tactile Button", part: "SKRPACE010 4×4×1.5mm SMD",
                    supplier: "DigiKey", price: "$0.33", qty: "2", total: "$0.66",
                    url: "https://www.digikey.com/en/products/detail/alps-alpine/SKRPACE010/4760743",
                    note: "SW1 (BTN_A) + SW2 (BTN_B); 260gf actuation"
                  },
                  {
                    n: 7, component: "Slide Switch", part: "SS-12D10 SPDT",
                    supplier: "LCSC", price: "$0.12", qty: "1", total: "$0.12",
                    url: "https://www.lcsc.com/search?q=SS-12D10",
                    note: "Master power switch"
                  },
                  {
                    n: 8, component: "Resistors", part: "100kΩ 0402 · RC0402FR-07100KL",
                    supplier: "LCSC", price: "$0.01", qty: "2", total: "$0.02",
                    url: "https://www.lcsc.com/search?q=RC0402FR-07100KL",
                    note: "R1/R2 voltage divider for battery ADC"
                  },
                  {
                    n: 9, component: "Resistors", part: "10kΩ 0402 · RC0402FR-0710KL",
                    supplier: "LCSC", price: "$0.01", qty: "2", total: "$0.02",
                    url: "https://www.lcsc.com/search?q=RC0402FR-0710KL",
                    note: "R3/R4 button pull-ups"
                  },
                  {
                    n: 10, component: "Resistor", part: "33Ω 0402 · RC0402FR-0733RL",
                    supplier: "LCSC", price: "$0.01", qty: "1", total: "$0.01",
                    url: "https://www.lcsc.com/search?q=RC0402FR-0733RL",
                    note: "R5 LED data line series resistor"
                  },
                  {
                    n: 11, component: "Capacitors", part: "100nF 0402 · CL05B104KO5NNNC",
                    supplier: "LCSC", price: "$0.02", qty: "4", total: "$0.08",
                    url: "https://www.lcsc.com/search?q=CL05B104KO5NNNC",
                    note: "C1/C3/C4/C5 bypass caps"
                  },
                  {
                    n: 12, component: "Capacitors", part: "10µF 0805 · CL21A106KAYNNNE",
                    supplier: "LCSC", price: "$0.02", qty: "2", total: "$0.04",
                    url: "https://www.lcsc.com/search?q=CL21A106KAYNNNE",
                    note: "C2/C6 bulk decoupling"
                  },
                  {
                    n: 13, component: "PCB", part: "2-layer 40×25mm, black HASL, 1.0mm FR4",
                    supplier: "JLCPCB (5 pcs)", price: "$2.00/unit", qty: "1", total: "$2.00",
                    url: "https://cart.jlcpcb.com/quote",
                    note: "Ships 3–5 business days; DHL Express 5–7 days total"
                  },
                  {
                    n: 14, component: "3D Case", part: "PETG matte black, 38×25×11mm",
                    supplier: "JLCPCB 3D Print", price: "$9.00 est.", qty: "1", total: "$9.00",
                    url: "https://jlcpcb.com/3d-printing",
                    note: "Front shell + back plate; SLA resin for smoother finish"
                  },
                  {
                    n: 15, component: "Lanyard Hardware", part: "4mm stainless split ring",
                    supplier: "AliExpress (10-pack)", price: "$0.30", qty: "1", total: "$0.30",
                    url: "https://www.aliexpress.com/wholesale?SearchText=4mm+stainless+split+ring",
                    note: ""
                  },
                  {
                    n: 16, component: "Misc", part: "Solder paste, flux pen, jumper wires, kapton tape",
                    supplier: "Local / Amazon", price: "$3.00", qty: "—", total: "$3.00",
                    url: "https://www.amazon.ca/s?k=SAC305+solder+paste",
                    note: "One-time cost, shared across all prototypes"
                  },
                ].map((row) => (
                  <tr key={row.n} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs" style={{ color: "#5A5A5A" }}>{row.n}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-sm" style={{ color: "#F5F0EB" }}>{row.component}</div>
                      {row.note && <div className="text-xs mt-0.5" style={{ color: "#5A5A5A" }}>{row.note}</div>}
                    </td>
                    <td className="px-4 py-3 text-xs font-mono" style={{ color: "#A0A0A0" }}>{row.part}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#8A8A8A" }}>{row.supplier}</td>
                    <td className="px-4 py-3 text-sm font-medium" style={{ color: "#C8A97E" }}>{row.price}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#8A8A8A" }}>{row.qty}</td>
                    <td className="px-4 py-3 text-sm font-medium" style={{ color: "#F5F0EB" }}>{row.total}</td>
                    <td className="px-4 py-3">
                      <a href={row.url} target="_blank" rel="noopener noreferrer"
                        className="text-xs px-2 py-1 rounded-lg whitespace-nowrap"
                        style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                        Buy ↗
                      </a>
                    </td>
                  </tr>
                ))}
                {/* Totals */}
                <tr style={{ background: "#161616", borderTop: "2px solid #252525" }}>
                  <td colSpan={6} className="px-4 py-3 text-sm font-semibold" style={{ color: "#F5F0EB" }}>Subtotal (components)</td>
                  <td className="px-4 py-3 text-sm font-semibold" style={{ color: "#C8A97E" }}>$29.24</td>
                  <td></td>
                </tr>
                <tr style={{ background: "#161616" }}>
                  <td colSpan={6} className="px-4 py-3 text-xs" style={{ color: "#5A5A5A" }}>Shipping (DigiKey ~$8 + AliExpress ~$6 + JLCPCB PCB+3D ~$13)</td>
                  <td className="px-4 py-3 text-sm font-medium" style={{ color: "#8A8A8A" }}>~$27</td>
                  <td></td>
                </tr>
                <tr style={{ background: "#1A1A1A", borderTop: "1px solid #252525" }}>
                  <td colSpan={6} className="px-4 py-4 text-sm font-bold" style={{ color: "#F5F0EB" }}>TOTAL — prototype, landed</td>
                  <td className="px-4 py-4 text-lg font-bold" style={{ color: "#C8A97E" }}>~$56 USD</td>
                  <td className="px-4 py-4 text-sm font-medium" style={{ color: "#8A8A8A" }}>~$77 CAD</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* Why these parts */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Why These Parts</h2>
          <div className="space-y-3">
            {[
              {
                title: "XIAO ESP32-S3 (not bare chip)",
                points: [
                  "USB-C native — no CH340/FTDI bridge needed",
                  "8 MB flash + 8 MB PSRAM soldered on — enough for 30-second audio ring buffer",
                  "Built-in PCB antenna, FCC/CE certified",
                  "21 × 17.5 mm — fits inside pendant case",
                  "Dual-core LX7 @ 240 MHz handles I2S DMA + VAD + WiFi upload simultaneously",
                  "$7.49 is cheaper than bare ESP32-S3-MINI-1 + antenna design",
                ]
              },
              {
                title: "INMP441 (over SPH0645LM4H)",
                points: [
                  "SPH0645LM4H is discontinued (Syntiant acquired it)",
                  "INMP441 (TDK InvenSense) is widely available, actively manufactured",
                  "61 dBA SNR — excellent for speech at 0.3–2m conversational distances",
                  "I2S 24-bit output maps cleanly to ESP32-S3 I2S peripheral",
                  "1.4 mA active current, 1 µA power-down mode",
                  "AliExpress breakout module ($2) pre-assembled with decoupling caps",
                ]
              },
              {
                title: "LP402035 400 mAh LiPo — battery life math",
                points: [
                  "Normal conversation: 20% recording (~100 mA) + 80% light sleep (~5 mA) = 24 mA average",
                  "400 mAh ÷ 24 mA = 16.7 hours typical battery life",
                  "Light-sleep-only: 400 ÷ 5 = 80 hours max standby",
                  "4×20×35mm fits inside 38×25×11mm pendant with room for PCB",
                ]
              },
            ].map((section) => (
              <div key={section.title} className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="font-medium text-sm mb-3" style={{ color: "#F5F0EB" }}>{section.title}</div>
                <ul className="space-y-1">
                  {section.points.map((p) => (
                    <li key={p} className="text-xs flex gap-2" style={{ color: "#A0A0A0" }}>
                      <span style={{ color: "#C8A97E" }}>·</span>
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* 1000-unit production delta */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>1,000-Unit Production Cost Reduction</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Change", "Prototype Cost", "Production Cost", "Savings"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { change: "MCU: XIAO → bare ESP32-S3-MINI-1-H4R2", proto: "$7.49", prod: "~$2.50", savings: "~$5/unit" },
                  { change: "Mic: INMP441 module → bare die from LCSC", proto: "$2.00", prod: "~$1.20", savings: "~$0.80/unit" },
                  { change: "PCB: gerbers only → JLCPCB SMT assembled", proto: "$2.00 + labor", prod: "~$6 assembled", savings: "labor eliminated" },
                  { change: "Case: PETG print → injection-molded ABS", proto: "$9.00", prod: "~$1.50 (tooling amortized)", savings: "~$7.50/unit" },
                  { change: "Total per unit", proto: "~$56 USD shipped", prod: "~$19 USD", savings: "~$37/unit" },
                ].map((row, i) => (
                  <tr key={row.change} className="border-b" style={{ borderColor: "#1A1A1A", background: i === 4 ? "#1A1A1A" : "transparent" }}>
                    <td className="px-4 py-3 text-sm" style={{ color: i === 4 ? "#F5F0EB" : "#A0A0A0", fontWeight: i === 4 ? 600 : 400 }}>{row.change}</td>
                    <td className="px-4 py-3 text-sm" style={{ color: "#8A8A8A" }}>{row.proto}</td>
                    <td className="px-4 py-3 text-sm font-medium" style={{ color: "#C8A97E" }}>{row.prod}</td>
                    <td className="px-4 py-3 text-sm font-semibold" style={{ color: "#C8A97E" }}>{row.savings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Quick order */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Quick Order Links</h2>
          <div className="flex flex-wrap gap-3">
            {[
              { label: "JLCPCB — PCBs + SMT Assembly", url: "https://cart.jlcpcb.com/quote" },
              { label: "JLCPCB — 3D Printing", url: "https://jlcpcb.com/3d-printing" },
              { label: "Seeed Studio — XIAO ESP32-S3", url: "https://www.seeedstudio.com/XIAO-ESP32S3-p-5627.html" },
              { label: "DigiKey — XIAO ESP32-S3", url: "https://www.digikey.com/en/products/detail/seeed-technology-co-ltd/113991114/19285530" },
              { label: "LCSC — All Passives", url: "https://www.lcsc.com" },
              { label: "Amazon.ca — INMP441 mic", url: "https://www.amazon.ca/s?k=INMP441+I2S+microphone" },
              { label: "Amazon.ca — TP4056 USB-C", url: "https://www.amazon.ca/s?k=TP4056+USB-C" },
              { label: "Amazon.ca — 400mAh LiPo", url: "https://www.amazon.ca/s?k=3.7V+400mAh+LiPo+JST" },
            ].map((btn) => (
              <a key={btn.label} href={btn.url} target="_blank" rel="noopener noreferrer"
                className="px-4 py-2 rounded-lg text-sm font-medium"
                style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>
                {btn.label} ↗
              </a>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}
