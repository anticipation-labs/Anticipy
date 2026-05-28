import Link from "next/link";

export default function PackagingPage() {
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
          <h1 className="text-3xl font-semibold tracking-tight mb-2">Packaging Design Specification</h1>
          <p style={{ color: "#8A8A8A" }}>Anticipy Pendant — v1.0 · Updated 2026-04-15 · Contact: omar@anticipy.ai</p>
          <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
            Design philosophy: minimal, premium, matches brand aesthetic — matte black, cream typography, gold accents. Apple-meets-Field-Notes. Unboxing feels intentional and quiet. No excess plastic, no promotional noise.
          </div>
        </div>

        {/* Box spec */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Box Specification</h2>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>Outer Box</h3>
              <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
                <table className="w-full text-sm">
                  <tbody>
                    {[
                      { k: "External size", v: "100 × 70 × 35 mm (W × H × D)" },
                      { k: "Material", v: "350gsm kraft board, matte black laminate exterior" },
                      { k: "Box style", v: "Rigid lid + base (telescope / two-piece)" },
                      { k: "Lid closure", v: "Friction fit; magnetic closure optional at >$4/unit" },
                      { k: "Lid top print", v: '"Anticipy" — Playfair Display, 18pt, cream (#F5F0EB), centered' },
                      { k: "Lid bottom print", v: "Logo mark (A monogram) 8mm, gold foil stamp" },
                      { k: "Lid side print", v: '"anticipy.ai" — 7pt, cream, centered on long side' },
                      { k: "Base exterior", v: "Blank (batch/serial number sticker on bottom)" },
                    ].map((row) => (
                      <tr key={row.k} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                        <td className="px-3 py-2 text-xs font-medium" style={{ color: "#5A5A5A" }}>{row.k}</td>
                        <td className="px-3 py-2 text-xs" style={{ color: "#A0A0A0" }}>{row.v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>Interior</h3>
              <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
                <table className="w-full text-sm">
                  <tbody>
                    {[
                      { k: "Interior color", v: "Matte black (flocked or painted)" },
                      { k: "Pendant tray", v: "Die-cut foam insert, 45 × 30 × 12mm cavity, matte black" },
                      { k: "Cable slot", v: "Foam channel 100 × 10 × 5mm beside pendant tray" },
                      { k: "Card slot", v: "Paper slot or friction hold under tray, 92 × 57mm" },
                    ].map((row) => (
                      <tr key={row.k} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                        <td className="px-3 py-2 text-xs font-medium" style={{ color: "#5A5A5A" }}>{row.k}</td>
                        <td className="px-3 py-2 text-xs" style={{ color: "#A0A0A0" }}>{row.v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "#161616", border: "1px solid #252525", color: "#8A8A8A" }}>
                <div className="font-medium mb-1" style={{ color: "#F5F0EB" }}>Dimensions rationale</div>
                100×70×35mm is smaller than iPhone 15 footprint — fits in breast pocket. Pendant cavity has 7mm clearance on all sides. Ships as standard small parcel, no oversize.
              </div>
            </div>
          </div>

          {/* Box diagram */}
          <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>Branding Placement Diagram</h3>
          <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
            <pre className="text-xs p-5 overflow-x-auto leading-relaxed" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`┌──────────────────────────────┐  ← Lid top (100×70mm)
│                              │
│         Anticipy             │  ← Playfair Display, 18pt, cream
│                              │
│              ⬡               │  ← Gold foil A monogram, 8mm
│                              │
└──────────────────────────────┘

Side panel (100×35mm):
  anticipy.ai    (7pt, cream, centered)

Other sides: blank

Lid interior (underside):
  "Your AI that acts, not just answers."  (8pt, cream)`}</pre>
          </div>
        </section>

        {/* Branding on pendant */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Branding on Pendant Case</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Location", "Mark", "Method"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { loc: "Front face, bottom-right corner", mark: '"A" monogram, 3mm', method: "Debossed into PETG or laser etched" },
                  { loc: "Back plate, bottom edge", mark: '"anticipy.ai", 1.5mm tall', method: "Debossed" },
                  { loc: "Back plate, center", mark: "Regulatory marks (CE / FCC placeholder)", method: "Laser etched, 1mm tall" },
                ].map((row) => (
                  <tr key={row.loc} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.loc}</td>
                    <td className="px-4 py-3 text-xs font-medium" style={{ color: "#F5F0EB" }}>{row.mark}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#8A8A8A" }}>{row.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Accessories */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Included Accessories</h2>
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "#252525" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#161616", borderBottom: "1px solid #252525" }}>
                  {["Item", "Spec", "Qty"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#8A8A8A" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { item: "USB-C charging cable", spec: "0.5m, braided nylon, black, USB-A to USB-C", qty: "1" },
                  { item: "Lanyard", spec: "60cm satin cord, matte black, stainless split ring pre-attached", qty: "1" },
                  { item: "Quick-start card", spec: "90 × 55mm, 350gsm, matte laminate both sides", qty: "1" },
                  { item: "Anti-static poly bag", spec: "100 × 80mm, clear, reclosable (pendant ships inside)", qty: "1" },
                ].map((row) => (
                  <tr key={row.item} className="border-b" style={{ borderColor: "#1A1A1A" }}>
                    <td className="px-4 py-3 text-xs font-medium" style={{ color: "#F5F0EB" }}>{row.item}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#A0A0A0" }}>{row.spec}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "#C8A97E" }}>{row.qty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Quick-start card */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Quick-Start Card (90 × 55mm)</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Front</div>
              <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
                <pre className="text-xs p-4 leading-relaxed" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`  Anticipy

  1. Install the Chrome extension
     anticipy.ai/engine → Download

  2. Sign in and copy your access code

  3. Enter it in the extension popup

  4. Talk. Anticipy handles the rest.

  Need help? anticipy.ai/help`}</pre>
              </div>
            </div>
            <div>
              <div className="text-xs font-medium mb-2" style={{ color: "#8A8A8A" }}>Back</div>
              <div className="rounded-xl overflow-hidden" style={{ background: "#0A0A0A", border: "1px solid #252525" }}>
                <pre className="text-xs p-4 leading-relaxed" style={{ color: "#A0A0A0", fontFamily: "monospace" }}>{`  Button guide:
  Tap          Toggle record on/off
  Double tap   Force upload now
  Hold 3s      Enter pairing mode
  Hold 8s      Factory reset

  LED guide:
  Slow blue    Connecting to WiFi
  Rainbow      Pairing mode
  Dim green    Ready, listening
  Solid red    Speech detected
  Fast cyan    Uploading
  Slow yellow  Low battery

  Charge via USB-C. Full charge ~30 min.
  Battery life: 15–20 hours typical.

  © 2026 Anticipation Labs
  anticipy.ai`}</pre>
              </div>
            </div>
          </div>
        </section>

        {/* Print specs */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Print Specifications</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>Color Palette</h3>
              <div className="space-y-2">
                {[
                  { name: "Matte Black", usage: "Background", pantone: "Pantone Black 6 C", cmyk: "0/0/0/100", swatch: "#0C0C0C" },
                  { name: "Cream", usage: "Typography", pantone: "Pantone 9182 C", cmyk: "3/3/8/0", swatch: "#F5F0EB" },
                  { name: "Gold", usage: "Logo mark, accent", pantone: "Pantone 872 C (metallic)", cmyk: "— (foil)", swatch: "#C8A97E" },
                ].map((c) => (
                  <div key={c.name} className="flex items-center gap-3 p-3 rounded-lg" style={{ background: "#161616", border: "1px solid #252525" }}>
                    <div className="w-6 h-6 rounded flex-shrink-0" style={{ background: c.swatch, border: "1px solid #252525" }} />
                    <div>
                      <div className="text-xs font-medium" style={{ color: "#F5F0EB" }}>{c.name} — {c.usage}</div>
                      <div className="text-xs" style={{ color: "#5A5A5A" }}>{c.pantone} · {c.cmyk}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium mb-3" style={{ color: "#8A8A8A" }}>Typography</h3>
              <div className="space-y-2">
                {[
                  { el: '"Anticipy" brand word', font: "Playfair Display", size: "18pt", weight: "Regular (400)" },
                  { el: "URLs / secondary text", font: "Inter", size: "7–8pt", weight: "Light (300)" },
                  { el: "Quick-start card body", font: "Inter", size: "7pt", weight: "Regular (400)" },
                  { el: "Quick-start card headings", font: "Inter", size: "8pt", weight: "Medium (500)" },
                ].map((t) => (
                  <div key={t.el} className="p-3 rounded-lg" style={{ background: "#161616", border: "1px solid #252525" }}>
                    <div className="text-xs font-medium mb-1" style={{ color: "#F5F0EB" }}>{t.el}</div>
                    <div className="text-xs" style={{ color: "#5A5A5A" }}>{t.font} · {t.size} · {t.weight}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Production quantities */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Production Quantities and Costs</h2>
          <div className="space-y-4">
            {[
              {
                tier: "Prototype (1–5 units)",
                items: [
                  "Handmade kraft box from local print shop or custom-box.com",
                  "Plain kraft + gold sticker label",
                  "Estimated cost: $4–$8 per box",
                ]
              },
              {
                tier: "Pilot (10–50 units)",
                items: [
                  "Minimum order at Packlane (packlane.com) or ULINE custom boxes",
                  "Full print lid + plain base",
                  "Estimated cost: $3–$5 per box at 50 units",
                ]
              },
            ].map((tier) => (
              <div key={tier.tier} className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="font-semibold text-sm mb-2" style={{ color: "#F5F0EB" }}>{tier.tier}</div>
                <ul className="space-y-1">
                  {tier.items.map((item) => (
                    <li key={item} className="text-xs flex gap-2" style={{ color: "#A0A0A0" }}>
                      <span style={{ color: "#C8A97E" }}>·</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            <div className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="font-semibold text-sm mb-3" style={{ color: "#F5F0EB" }}>Production (1,000+ units) — Full Packaging BOM</div>
              <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "#1A1A1A" }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ background: "#0C0C0C", borderBottom: "1px solid #1A1A1A" }}>
                      {["Item", "Unit Cost (1k units)", "Lead Time"].map((h) => (
                        <th key={h} className="text-left px-3 py-2 font-medium" style={{ color: "#5A5A5A" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { item: "Rigid 2-piece box, full print", cost: "~$1.20", lead: "4–6 weeks (China)" },
                      { item: "Die-cut foam insert", cost: "~$0.40", lead: "3–4 weeks" },
                      { item: "Quick-start card (4-color print)", cost: "~$0.08", lead: "1–2 weeks" },
                      { item: "USB-C cable (braided)", cost: "~$0.90", lead: "Stock / AliExpress" },
                      { item: "Lanyard + split ring", cost: "~$0.35", lead: "Stock / AliExpress" },
                      { item: "Anti-static bag", cost: "~$0.04", lead: "Stock" },
                      { item: "Total packaging BOM", cost: "~$2.97", lead: "—" },
                    ].map((row, i) => (
                      <tr key={row.item} className="border-b" style={{ borderColor: "#1A1A1A", background: i === 6 ? "#1A1A1A" : "transparent" }}>
                        <td className="px-3 py-2" style={{ color: i === 6 ? "#F5F0EB" : "#A0A0A0", fontWeight: i === 6 ? 600 : 400 }}>{row.item}</td>
                        <td className="px-3 py-2 font-medium" style={{ color: "#C8A97E" }}>{row.cost}</td>
                        <td className="px-3 py-2" style={{ color: "#5A5A5A" }}>{row.lead}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* Regulatory */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Regulatory and Compliance Labels</h2>
          <div className="p-4 rounded-xl mb-3" style={{ background: "#161616", border: "1px solid #252525" }}>
            <p className="text-xs mb-3" style={{ color: "#8A8A8A" }}>To be added to back plate and box before commercial sale:</p>
            <ul className="space-y-2">
              {[
                { mark: "CE mark (EU)", status: "Pending RF module certification via XIAO ESP32-S3 declarations" },
                { mark: "FCC ID", status: "Inherit from XIAO ESP32-S3 module — FCC ID: 2AXX7XIAO-ESP32S3 (verify on FCC database)" },
                { mark: "ROHS compliant", status: "PCB and all components" },
                { mark: "LiPo warning (box inner)", status: '"Contains lithium battery. Do not crush, puncture, or expose to fire."' },
                { mark: "WEEE symbol (EU)", status: "Crossed-out wheelie bin on box exterior" },
                { mark: "Country of origin", status: '"Assembled in Canada" (prototype) / "Made in China" (production)' },
                { mark: "Battery capacity", status: "3.7V 400mAh 1.48Wh (for air freight, IATA PI 967 Section II)" },
              ].map((row) => (
                <li key={row.mark} className="flex gap-3 text-xs">
                  <span className="font-semibold flex-shrink-0" style={{ color: "#C8A97E" }}>{row.mark}:</span>
                  <span style={{ color: "#A0A0A0" }}>{row.status}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Packaging suppliers */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Recommended Box Suppliers</h2>
          <div className="grid grid-cols-3 gap-3">
            {[
              { name: "Packlane", desc: "Custom printed boxes, qty 10+, ~$5–8/box. Best for pilot.", url: "https://www.packlane.com/" },
              { name: "noissue", desc: "Eco-friendly startup packaging. FSC-certified kraft. Compostable.", url: "https://www.noissue.co/" },
              { name: "Arka", desc: "Custom mailer boxes from 10 units. Good for DTC shipping.", url: "https://www.arka.com/" },
            ].map((s) => (
              <div key={s.name} className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="font-semibold text-sm mb-1" style={{ color: "#F5F0EB" }}>{s.name}</div>
                <p className="text-xs mb-3" style={{ color: "#8A8A8A" }}>{s.desc}</p>
                <a href={s.url} target="_blank" rel="noopener noreferrer"
                  className="text-xs px-2 py-1 rounded-lg"
                  style={{ background: "rgba(200,169,126,0.08)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.2)" }}>
                  {s.url.replace("https://www.", "").replace("/", "")} ↗
                </a>
              </div>
            ))}
          </div>
        </section>

        {/* Sustainability */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Sustainability Notes</h2>
          <div className="p-4 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
            <ul className="space-y-2">
              {[
                "Box: FSC-certified kraft board preferred",
                "No PVC wrapping anywhere in package",
                "Foam insert: EVA foam (recyclable) preferred over polyurethane",
                "Cable: offer \"no cable\" option at checkout for $2 discount for buyers who already have USB-C cables",
                "Target: packaging entirely recyclable or compostable at curbside",
              ].map((item) => (
                <li key={item} className="flex gap-2 text-xs" style={{ color: "#A0A0A0" }}>
                  <span style={{ color: "#22c55e" }}>✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

      </div>
    </div>
  );
}
