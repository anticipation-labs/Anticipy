import Link from "next/link";

export default function ManufacturingPage() {
  return (
    <div className="min-h-screen" style={{ background: "#0C0C0C", color: "#F5F0EB" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">

        <Link href="/internal" className="inline-flex items-center gap-2 text-sm mb-8 hover:opacity-80 transition-opacity" style={{ color: "#8A8A8A" }}>
          ← Internal Dashboard
        </Link>

        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span style={{ color: "#C8A97E" }}>◻</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Orders · Hardware</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight mb-2">Manufacturing Order Guide</h1>
          <p style={{ color: "#8A8A8A" }}>One-click manufacturing — upload files, confirm quote, pay, sample ships to West Vancouver in ~7 days.</p>
        </div>

        {/* Cost per unit summary */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Total Cost Per Sample Unit</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Item", "Cost USD"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { item: "PCB + assembly (JLCPCB)", cost: "~$8" },
                  { item: "3D printed case (JLCPCB 3D)", cost: "~$3" },
                  { item: "Components (ESP32, mic, battery, LED, passives)", cost: "~$15" },
                  { item: "Packaging box (Packlane)", cost: "~$6" },
                  { item: "Shipping to West Vancouver", cost: "~$5" },
                ].map((row) => (
                  <tr key={row.item} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-sm" style={{ color: "#A0A0A0" }}>{row.item}</td>
                    <td className="px-4 py-3 text-sm font-medium" style={{ color: "#C8A97E" }}>{row.cost}</td>
                  </tr>
                ))}
                <tr style={{ background: "#1A1A1A", borderTop: "2px solid #252525" }}>
                  <td className="px-4 py-4 text-sm font-bold" style={{ color: "#F5F0EB" }}>Total per unit</td>
                  <td className="px-4 py-4 text-lg font-bold" style={{ color: "#C8A97E" }}>~$37 USD (~$51 CAD)</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
            For titanium/aluminum CNC case: add ~$30–80/unit depending on finish (Shapeways titanium milling or Xometry CNC aluminum).
          </div>
        </section>

        {/* Turnkey manufacturer research */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-2" style={{ color: "#C8A97E" }}>Turnkey Manufacturer Research</h2>
          <p className="text-xs mb-5" style={{ color: "#5A5A5A" }}>All prices verified April 2026. "Turnkey" = they handle PCB fab + SMT assembly + case + shipping.</p>

          <div className="space-y-4">

            {/* JLCPCB */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "2px solid rgba(200,169,126,0.3)" }}>
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-base" style={{ color: "#F5F0EB" }}>JLCPCB</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>RECOMMENDED — Primary</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Shenzhen, China · ships DHL Express to Canada (5–7 days)</div>
                </div>
                <a href="https://cart.jlcpcb.com/quote" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap"
                  style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>
                  Order PCBs ↗
                </a>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>PCB + SMT Assembly</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· 5× assembled boards: ~$30–50 USD</li>
                    <li>· SMT setup fee: ~$25 one-time per order</li>
                    <li>· Component sourcing: JLCPCB parts library (~$1–3 extra)</li>
                    <li>· Gerber + BOM + CPL upload → instant quote</li>
                    <li>· 3–5 business day production</li>
                    <li>· DHL Express to West Vancouver: ~$15–20 (5–7 days total)</li>
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>3D Printing Service</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· PETG FDM: ~$3–5/part (standard finish)</li>
                    <li>· SLA resin black: ~$6–12/part (smooth finish)</li>
                    <li>· Upload STL → instant quote</li>
                    <li>· 10 case halves (5 fronts + 5 backs): ~$15–30 USD</li>
                    <li>· Same shipping as PCB order if combined</li>
                  </ul>
                </div>
              </div>
              <div className="p-3 rounded-lg text-xs" style={{ background: "#0C0C0C", color: "#5A5A5A" }}>
                <span className="font-medium" style={{ color: "#F5F0EB" }}>Order settings:</span> Layers: 2 · Qty: 5 · Board: 40×25mm · Surface: HASL lead-free · Assembly: Turnkey · Side: Top · Assemble qty: 5
              </div>
              <div className="mt-3 flex gap-3">
                <a href="https://cart.jlcpcb.com/quote" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                  PCB + Assembly ↗
                </a>
                <a href="https://jlcpcb.com/3d-printing" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                  3D Printing ↗
                </a>
              </div>
            </div>

            {/* PCBWay */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-base" style={{ color: "#F5F0EB" }}>PCBWay</span>
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#161616", color: "#8A8A8A", border: "1px solid #252525" }}>Box Build Service</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Shenzhen, China · offers box build (PCB + case + battery fully assembled)</div>
                </div>
                <a href="https://www.pcbway.com/pcb-assembly.html" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap"
                  style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                  Get Quote ↗
                </a>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Key capabilities</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· Box build: assemble PCB into case with battery included</li>
                    <li>· Firmware flashing service: provide binary, they flash each unit</li>
                    <li>· Functional test jig: request custom test (extra cost)</li>
                    <li>· DFM feedback before production</li>
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Pricing (estimated)</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· PCB + SMT assembly: ~$40–60 for 5 units</li>
                    <li>· Box build add-on: +$5–10/unit</li>
                    <li>· Firmware flash: +$2–3/unit</li>
                    <li>· Ships DHL/FedEx to Canada ~$20</li>
                  </ul>
                </div>
              </div>
              <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "#0C0C0C", color: "#5A5A5A" }}>
                Provide firmware/pcb/ASSEMBLY.md as assembly instructions for box build request.
              </div>
            </div>

            {/* Seeed Fusion */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-base" style={{ color: "#F5F0EB" }}>Seeed Fusion</span>
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#161616", color: "#8A8A8A", border: "1px solid #252525" }}>7-Day Turnaround</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Shenzhen, China · Seeed Studio&apos;s manufacturing arm · XIAO ESP32-S3 manufacturer</div>
                </div>
                <a href="https://www.seeedstudio.com/fusion_pcb.html" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap"
                  style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                  Get Quote ↗
                </a>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Why consider Seeed Fusion</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· Same company as XIAO ESP32-S3 — deep familiarity with the module</li>
                    <li>· 7-business-day PCB + assembly turnaround guaranteed</li>
                    <li>· Open-source hardware friendly (used by makers)</li>
                    <li>· Free DFM check with every order</li>
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Pricing</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· PCB only (5 pcs 40×25mm): ~$5–10</li>
                    <li>· SMT assembly: quote on request</li>
                    <li>· Typically 10–20% more than JLCPCB</li>
                    <li>· Worth it for guaranteed 7-day turnaround</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* MacroFab */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-base" style={{ color: "#F5F0EB" }}>MacroFab</span>
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#161616", color: "#8A8A8A", border: "1px solid #252525" }}>US-Based · No Import Duties</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Houston, TX, USA · North American manufacturing · ITAR-registered</div>
                </div>
                <a href="https://macrofab.com" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap"
                  style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                  Get Quote ↗
                </a>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Advantages</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· US-based: no customs delays, no import duties to Canada (USMCA)</li>
                    <li>· Online instant quote: upload KiCad gerbers → price in minutes</li>
                    <li>· Components sourced from Digi-Key / Mouser (US supply chain)</li>
                    <li>· Engineering review for small batches</li>
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Pricing</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· 5-unit prototype: ~$80–150 USD (2–3× JLCPCB)</li>
                    <li>· 50-unit pilot: ~$30–50/unit assembled</li>
                    <li>· 5–10 day turnaround for prototypes</li>
                    <li>· Best for if China tariffs become a problem</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Bittele */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-base" style={{ color: "#F5F0EB" }}>Bittele Electronics (7pcb.com)</span>
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.3)" }}>Toronto · Zero-Touch Option</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Toronto, ON, Canada · 5–10 day turnaround · ships within Canada</div>
                </div>
                <a href="https://www.7pcb.com/" target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap"
                  style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                  7pcb.com ↗
                </a>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Full zero-touch service</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· Ship all components to their Toronto facility</li>
                    <li>· They assemble, test, flash firmware</li>
                    <li>· Ship finished units to West Vancouver (domestic — no customs)</li>
                    <li>· 5–10 business day turnaround</li>
                    <li>· Canadian company — HST applies, no import duties</li>
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>What to provide</div>
                  <ul className="space-y-1 text-xs" style={{ color: "#A0A0A0" }}>
                    <li>· KiCad gerber files + BOM + CPL</li>
                    <li>· firmware/ directory as zip</li>
                    <li>· Flashing instructions: &quot;pio run --target upload via USB-C&quot;</li>
                    <li>· firmware/pcb/ASSEMBLY.md for assembly guide</li>
                    <li>· All components pre-purchased and shipped to them</li>
                  </ul>
                </div>
              </div>
              <div className="mt-3 p-3 rounded-lg text-xs font-medium" style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)", color: "#22c55e" }}>
                Best option for zero-touch prototype: send them everything, receive finished assembled+flashed units. No customs, no soldering, no flashing.
              </div>
            </div>

          </div>
        </section>

        {/* Fulfillment research */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-2" style={{ color: "#C8A97E" }}>Fulfillment Center Research</h2>
          <p className="text-xs mb-5" style={{ color: "#5A5A5A" }}>For when units are ready to ship to customers. Both options are within 30 min of West Vancouver.</p>
          <div className="grid grid-cols-2 gap-4">

            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "2px solid rgba(200,169,126,0.3)" }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-bold text-sm" style={{ color: "#F5F0EB" }}>ShipBob — Surrey, BC</span>
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Primary</span>
              </div>
              <div className="text-xs mb-3" style={{ color: "#5A5A5A" }}>~30 min from West Vancouver</div>
              <ul className="space-y-1 text-xs mb-4" style={{ color: "#A0A0A0" }}>
                <li>· Receives inventory from manufacturer</li>
                <li>· Stores, picks, packs, ships to customers</li>
                <li>· Integrates with Shopify, WooCommerce, Stripe</li>
                <li>· 1–2 day delivery to most of Canada</li>
                <li>· US fulfillment centers available for US orders</li>
                <li>· Create account → add SKU → provide ship-to address for manufacturer</li>
              </ul>
              <a href="https://www.shipbob.com/" target="_blank" rel="noopener noreferrer"
                className="inline-block px-3 py-1.5 rounded-lg text-xs font-medium"
                style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                shipbob.com ↗
              </a>
            </div>

            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-bold text-sm" style={{ color: "#F5F0EB" }}>Evolution Fulfillment — Delta, BC</span>
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#161616", color: "#8A8A8A", border: "1px solid #252525" }}>Backup</span>
              </div>
              <div className="text-xs mb-3" style={{ color: "#5A5A5A" }}>~40 min from West Vancouver · Canadian-owned</div>
              <ul className="space-y-1 text-xs mb-4" style={{ color: "#A0A0A0" }}>
                <li>· Smaller than ShipBob — more personal service</li>
                <li>· Better pricing at low volumes (sub-100 units/mo)</li>
                <li>· Canadian-owned — no US company data requirements</li>
                <li>· Handles Canada Post + FedEx + UPS</li>
                <li>· Contact for quote: evolutionfulfillment.ca</li>
              </ul>
              <a href="https://www.evolutionfulfillment.ca/" target="_blank" rel="noopener noreferrer"
                className="inline-block px-3 py-1.5 rounded-lg text-xs font-medium"
                style={{ background: "rgba(200,169,126,0.12)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.25)" }}>
                evolutionfulfillment.ca ↗
              </a>
            </div>

          </div>
        </section>

        {/* Step-by-step order guide */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-2" style={{ color: "#C8A97E" }}>7-Day Sample Order Checklist</h2>
          <p className="text-xs mb-5" style={{ color: "#5A5A5A" }}>Everything arrives in 5–7 days. Do steps 1–4 on the same day.</p>
          <div className="space-y-3">
            {[
              {
                step: "1",
                title: "Order PCBs + Assembly from JLCPCB",
                url: "https://cart.jlcpcb.com/quote",
                urlLabel: "cart.jlcpcb.com →",
                items: [
                  "Upload: Gerber files (export from KiCad: File → Plot → Gerber), BOM file, CPL (component placement list)",
                  "Settings: 2 layers · 5 pcs · 40×25mm · HASL lead-free · Turnkey assembly · Top side · 5 units assembled",
                  "Estimated cost: ~$30–50 USD",
                  "Production: 3–5 business days + DHL Express shipping",
                ]
              },
              {
                step: "2",
                title: "Order 3D Printed Cases from JLCPCB",
                url: "https://jlcpcb.com/3d-printing",
                urlLabel: "jlcpcb.com/3d-printing →",
                items: [
                  "Export STL from OpenSCAD: open firmware/case/anticipy_pendant.scad → Render → Export as STL",
                  "Settings: PETG black · Standard finish · 10 pieces (5 front shells + 5 back plates)",
                  "For premium samples: SLA resin black (~$12/part)",
                  "Estimated cost: ~$15–30 USD for 10 pieces",
                ]
              },
              {
                step: "3",
                title: "Order XIAO ESP32-S3 from Seeed Studio",
                url: "https://www.seeedstudio.com/XIAO-ESP32S3-p-5627.html",
                urlLabel: "seeedstudio.com →",
                items: [
                  "Qty: 5 (+ 2 spares recommended)",
                  "Price: $10.33 CAD each ($72.31 CAD for 7)",
                  "Ships from Shenzhen via DHL — arrives with JLCPCB order if ordered same day",
                ]
              },
              {
                step: "4",
                title: "Order Remaining Components from Amazon.ca",
                url: "https://www.amazon.ca",
                urlLabel: "amazon.ca →",
                items: [
                  "INMP441 I2S microphone (5-pack): search 'INMP441 I2S microphone' → ~$8 CAD",
                  "TP4056 USB-C charger module (10-pack): search 'TP4056 USB-C lithium charger' → ~$10 CAD",
                  "3.7V 400mAh LiPo JST (5-pack): search '3.7V 400mAh LiPo JST' → ~$15 CAD",
                  "SK6812 Mini-E LED (10-pack): adafruit.com/product/4960 or Amazon → ~$5 CAD",
                  "Total: ~$38 CAD via Prime (2-day delivery)",
                ]
              },
              {
                step: "5",
                title: "Flash Firmware (30 seconds per unit)",
                items: [
                  "cd firmware",
                  "pio run --target upload  # connect via USB-C, takes 30 seconds",
                  "Or: send firmware/ as zip to Bittele (7pcb.com) and they do it — add 'flash before shipping' to order notes",
                ]
              },
              {
                step: "6",
                title: "Order Packaging",
                url: "https://www.packlane.com/",
                urlLabel: "packlane.com →",
                items: [
                  "Packlane: custom printed boxes from qty 10 — ~$5–8/box",
                  "noissue.co: eco-friendly startup packaging",
                  "arka.com: custom mailer boxes from 10 units",
                  "Box specs: 100×70×35mm matte black rigid lid+base — see Packaging spec page for full details",
                ]
              },
              {
                step: "7",
                title: "Send to Fulfillment (when ready to ship customers)",
                url: "https://www.shipbob.com/",
                urlLabel: "shipbob.com →",
                items: [
                  "Create ShipBob account → add Anticipy Pendant as SKU → provide manufacturer's shipping address",
                  "ShipBob Surrey receives, stores, and ships on demand",
                  "For first prototype batch: ship direct to customers yourself",
                ]
              },
            ].map((s) => (
              <div key={s.step} className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
                    style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>
                    {s.step}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-3">
                      <span className="font-semibold text-sm" style={{ color: "#F5F0EB" }}>{s.title}</span>
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noopener noreferrer"
                          className="text-xs px-2 py-0.5 rounded"
                          style={{ background: "rgba(200,169,126,0.08)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.2)" }}>
                          {s.urlLabel}
                        </a>
                      )}
                    </div>
                    <ul className="space-y-1">
                      {s.items.map((item) => (
                        <li key={item} className="text-xs flex gap-2" style={{ color: "#A0A0A0" }}>
                          <span className="flex-shrink-0" style={{ color: "#C8A97E" }}>·</span>
                          <span className={item.startsWith("pio") || item.startsWith("cd") ? "font-mono" : ""}>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Premium case options */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Premium Case Options</h2>
          <div className="grid grid-cols-2 gap-4">
            {[
              {
                name: "Shapeways",
                material: "Titanium milling",
                price: "+$30–80/unit",
                note: "Museum-quality metal finish. Best for investor demo units.",
                url: "https://www.shapeways.com/",
              },
              {
                name: "Xometry",
                material: "CNC Aluminum, anodized",
                price: "+$40–100/unit",
                note: "North American CNC shop. Upload STEP file → instant quote.",
                url: "https://www.xometry.com/",
              },
            ].map((opt) => (
              <div key={opt.name} className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="font-semibold text-sm mb-1" style={{ color: "#F5F0EB" }}>{opt.name}</div>
                <div className="text-xs mb-1" style={{ color: "#C8A97E" }}>{opt.material} · {opt.price}</div>
                <p className="text-xs mb-3" style={{ color: "#8A8A8A" }}>{opt.note}</p>
                <a href={opt.url} target="_blank" rel="noopener noreferrer"
                  className="text-xs px-2 py-1 rounded-lg"
                  style={{ background: "rgba(200,169,126,0.08)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.2)" }}>
                  {opt.url.replace("https://www.", "")} ↗
                </a>
              </div>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}
