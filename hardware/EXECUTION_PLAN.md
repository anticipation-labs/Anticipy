# 2-week execution plan — your unit Day 7, customers Day 14

Batch: 15 built → 12 shippable (2 yours, 10 customers, 3 yield spares).

| Day | Action | Owner |
|---|---|---|
| 0 | Pay carts 1, 2, 4 (`ORDERING.md`); print v7 fronts+backs on the P2S (PETG Pro) | You |
| 0 | Upload v7 STLs to JLC3DP → pay Ti + resin backup cart | You (files ready) |
| 1 | Fork Omi firmware → Anticipy overlay + haptic patch; build UF2 | Devin |
| 1–2 | Fork Omi Flutter app → Anticipy branding; submit TestFlight (review 1–2 days) | Devin |
| 2–3 | RobotShop + Amazon parts land → hand-wire units #001–#002 per `case_v7/BUILD_GUIDE.md`, flash, pair | You |
| 4–6 | QA on #001: stream soak, offline/backlog test, measure real current draw (updates the runtime claims) | You + Devin |
| **7** | **You wear Anticipy #001 (PETG shell)** | ✅ |
| 7–9 | Ti shells land (3-day SLM build + DHL); fit-check lip, re-export at LID_CLR 0.40 if tight | — |
| 9–11 | Assemble 12–15 units (~45 min each), flash, run `qa/QA_CHECKLIST.md` on every unit | You |
| 11–12 | Chains, packaging, charge to ~50 %, quick-start card with TestFlight link | You |
| 12–14 | Ship Xpresspost/Purolator (UN3481 "lithium batteries in equipment" label) | ✅ |

## Risks + pre-decided answers

- **Ti QC/shipping slip** → resin backups in the same cart; wave 1 ships
  resin, Ti follows free.
- **TestFlight review slow** → ad-hoc install for the 10 wave-1 customers;
  stock Omi app is protocol-compatible day 1.
- **Runtime below 16 h measured** → drop stream bitrate / duty-cycle VAD gate;
  worst case second 250 mAh cell in parallel (case has 0.4 mm slack over the
  cell bay only — verify before promising).
- **Compliance**: XIAO's FCC modular grant covers the radio, but full
  host-device FCC/ISED verification is NOT done in 2 weeks. Wave-1 units ship
  labeled "Engineering sample / beta — not for resale"; book ISED/FCC testing
  weeks 3–6 (~$3–5k) before public retail. Website's wireless-charging claim
  is NOT in V1 — don't ship copy that says it is.
- **Privacy**: always-on mic — quick-start card must state recording-consent
  law basics (one-party consent varies by state/province; BC is one-party).

## V2 (weeks 3–6, true Plaud envelope + titanium look at scale)

Custom board: nRF52840-QIAA (stocked at LCSC, unlike nRF5340-CLAA) + PDM mic
+ W25Q01JV 128 MB + DRV2605L/LRA haptic on one 48 × 20 mm PCB, cell stacked
over — hits 58.7 × 24.2 × 12.65. JLCPCB 24–48 h PCBA. Start the KiCad design
Day 4 so V2 boards land as wave 1 ships.
