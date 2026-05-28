# Anticipy Pendant — Packaging Specification

**Version:** 1.0  
**Last updated:** 2026-04-15  
**Contact:** omar@anticipy.ai

---

## 1. Overview

The Anticipy Pendant packaging is minimal, premium, and matches the brand aesthetic: matte black, cream typography, gold accents. Think Apple-meets-Field Notes. Unboxing should feel intentional and quiet — no excess plastic, no excessive padding, no promotional noise.

---

## 2. Box Specification

### Outer Box

| Dimension | Spec |
|-----------|------|
| External size | 100 × 70 × 35 mm (W × H × D) |
| Material | 350gsm kraft board, matte black laminate exterior |
| Box style | Rigid lid + base (telescope/two-piece) |
| Lid closure | Friction fit; magnetic closure optional at >$4/unit |
| Print: exterior lid top | "Anticipy" in Playfair Display serif, 18pt, cream (#F5F0EB), centered |
| Print: exterior lid bottom | Logo mark (A monogram) 8mm, gold foil stamp |
| Print: exterior lid side | "anticipy.ai" in 7pt, cream, centered on long side |
| Print: base exterior | Blank (or batch/serial number sticker on bottom) |

### Interior

| Item | Spec |
|------|------|
| Interior color | Matte black (flocked or painted) |
| Pendant tray | Die-cut foam insert, 45 × 30 × 12mm cavity, matte black |
| Cable slot | Foam channel 100 × 10 × 5mm beside pendant tray |
| Quick-start card slot | Paper slot or friction hold under pendant tray, 92 × 57mm |

### Dimensions rationale

- External 100 × 70 × 35mm is smaller than an iPhone 15 footprint — fits in a breast pocket
- Pendant cavity 45 × 30 × 12mm: 7mm clearance on all sides around 38 × 25 × 11mm pendant
- Total box volume ≈ 245 cm³ — ships as standard small parcel, no oversize

---

## 3. Branding Placement

### Box Exterior

```
┌──────────────────────────────┐  ← Lid top (100×70mm)
│                              │
│         Anticipy             │  ← Playfair Display, 18pt, cream
│                              │
│              ⬡               │  ← Gold foil A monogram, 8mm
│                              │
└──────────────────────────────┘

Side panel (100×35mm):
  anticipy.ai    (7pt, cream, centered)

Other sides: blank
```

### Box Interior (lid underside)

Single line, cream ink, 8pt:  
`"Your AI that acts, not just answers."`

### Pendant Case

The pendant itself (38 × 25 × 11mm PETG case) carries:

| Location | Mark | Method |
|----------|------|--------|
| Front face, bottom-right corner | "A" monogram, 3mm | Debossed into PETG or laser etched |
| Back plate, bottom edge | "anticipy.ai", 1.5mm tall | Debossed |
| Back plate, center | Regulatory marks (CE / FCC placeholder) | Laser etched, 1mm tall |

---

## 4. Included Accessories

Every unit ships with:

| Item | Spec | Quantity |
|------|------|----------|
| USB-C charging cable | 0.5m, braided nylon, black, USB-A to USB-C | 1 |
| Lanyard | 60cm satin cord, matte black, with stainless split ring pre-attached | 1 |
| Quick-start card | 90 × 55mm, 350gsm, matte laminate both sides | 1 |
| Anti-static poly bag | 100 × 80mm, clear, reclosable | 1 (pendant ships in this inside tray) |

### Quick-Start Card (Front)

```
[FRONT — 90×55mm]

  Anticipy

  1. Install the Chrome extension
     anticipy.ai/engine → Download

  2. Sign in and copy your access code

  3. Enter it in the extension popup

  4. Talk. Anticipy handles the rest.

  Need help? anticipy.ai/help
```

### Quick-Start Card (Back)

```
[BACK — 90×55mm, smaller text]

  Button guide:
  Tap          Toggle record on/off
  Double tap   Force upload now
  Hold 3s      Enter pairing mode
  Hold 8s      Factory reset

  LED guide:
  Slow blue pulse    Connecting to WiFi
  Rainbow cycle      Pairing mode
  Dim green blink    Ready, listening
  Solid red          Speech detected
  Fast cyan pulse    Uploading
  Slow yellow        Low battery

  Charge via USB-C. Full charge ~30 min.
  Battery life: 15–20 hours typical.

  © 2026 Anticipation Labs
  Made with care. anticipy.ai
```

---

## 5. Print Specifications for Box Manufacturer

### Color Palette

| Color | Usage | Pantone (uncoated) | CMYK |
|-------|-------|-------------------|------|
| Matte Black | Background | Pantone Black 6 C | 0/0/0/100 |
| Cream | Typography | Pantone 9182 C | 3/3/8/0 |
| Gold | Logo mark, accent | Pantone 872 C (metallic) | — (foil or metallic ink) |

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| "Anticipy" brand word | Playfair Display | 18pt | Regular (400) |
| URLs / secondary text | Inter | 7–8pt | Light (300) |
| Quick-start card body | Inter | 7pt | Regular (400) |
| Quick-start card headings | Inter | 8pt | Medium (500) |

### File Formats

- Box die line: AI or DXF, 1:1 scale, Pantone color calls
- Logo: SVG + PDF (vector only — no raster logos)
- Final print files: press-ready PDF/X-4, 3mm bleed, crop marks
- Font: embed all fonts in PDF

---

## 6. Production Quantities and Costs

### Prototype (1–5 units)

- Handmade kraft box from local print shop or custom-box.com
- Plain kraft + gold sticker label
- Estimated cost: $4–$8 per box

### Pilot (10–50 units)

- Minimum order at Packlane or ULINE custom boxes
- Full print lid + plain base
- Estimated cost: $3–$5 per box at 50 units

### Production (1,000+ units)

| Item | Unit Cost (1k units) | Lead Time |
|------|---------------------|-----------|
| Rigid 2-piece box, full print | ~$1.20 | 4–6 weeks (China) |
| Die-cut foam insert | ~$0.40 | 3–4 weeks |
| Quick-start card (4-color print) | ~$0.08 | 1–2 weeks |
| USB-C cable (braided) | ~$0.90 | Stock / AliExpress |
| Lanyard + split ring | ~$0.35 | Stock / AliExpress |
| Anti-static bag | ~$0.04 | Stock |
| **Total packaging BOM** | **~$2.97** | — |

---

## 7. Regulatory and Compliance Labels

To be added to back plate and box before commercial sale:

- **CE mark** (EU) — pending RF module certification via XIAO ESP32-S3 declarations
- **FCC ID** — inherit from XIAO ESP32-S3 module (FCC ID: 2AXX7XIAO-ESP32S3, verify on FCC database)
- **ROHS compliant** — PCB and all components
- **LiPo warning** (on box inner): "Contains lithium battery. Do not crush, puncture, or expose to fire."
- **WEEE symbol** (EU) — crossed-out wheelie bin on box exterior
- **Country of origin**: "Assembled in Canada" (prototype) / "Made in China" (production)
- **Battery capacity**: 3.7V 400mAh 1.48Wh (for air freight compliance, IATA PI 967 Section II)

---

## 8. Sustainability Notes

- Box: FSC-certified kraft board preferred
- No PVC wrapping
- Foam insert: EVA foam (recyclable) preferred over polyurethane
- Cable: omit if buyer already has USB-C cables (offer "no cable" option at checkout for $2 discount)
- Target: packaging entirely recyclable or compostable at curbside
