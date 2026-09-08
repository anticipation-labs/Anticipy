# Battery counter card — no exceptions

## Ask for this exact pack first

**Renata ICP501022UPM, part 100640**

Manufacturer evidence archived in `BATTERY_DOCUMENTS/`:

- Product: https://www.renata.com/en-us/products/lithium-polymer-batteries/icp501022upm/
- Specification PDF: https://www.renata.com/en-us/downloads/?fileid=1ee829f0b5a731cd359417fdfe&product=icp501022upm
- Exact-model UN38.3 summary: https://www.renata.com/en-cn/downloadfile/icp501022upm/?fileid=97106764f0d065a93ba6f05cf0
- Renata distribution partners: https://www.renata.com/en-us/distribution-partners/

The datasheet reports 3.7 V, 80 mAh nominal, safety circuit, maximum pack body
24 x 10 x 5.5 mm, 40 mA normal/80 mA maximum CC/CV charge at 4.20 V, and
states IEC62133 certification. The UN summary names ICP501022UPM and reports
T1-T8 passed. Verify the received label/lot still matches both documents.

## Call order

1. 08:00 — Cadex, 22000 Fraserwood Way, Richmond, 604-231-7777.
2. 09:00 — Swiss Watch Parts, Suite 626, 602 W Hastings, 604-685-9949.
3. 09:00 — Vancouver Battery, 1875 Ontario St, 604-737-8463.
4. 09:00 — Lee's, 4131 Fraser St, 604-875-1993, fallback inspection only.

Ask the vendor to isolate **12 same-lot units**, sell one first article today,
and hold 11 unpaid until same-day Unit 001 qualification. Record staff name,
physical count, exact label photo, hold expiry, and pickup time. No substitution.

## Say this

> I need Renata ICP501022UPM, part 100640: a finished protected 1S Li-poly.
> Please physically verify the label, lot, maximum pack-body envelope, safety
> circuit, charge specification, and exact UN38.3 summary. Isolate 12 from one
> lot, sell me one fit article, and hold 11 unpaid until it passes today. Do
> not substitute a raw RC, earbud, drone, or generic pouch cell.

## Counter record

| Gate | Required | Actual |
|---|---|---|
| Vendor/staff/hold expiry | recorded | |
| Manufacturer / MPN / part | Renata / ICP501022UPM / 100640 preferred | |
| Lot/date code and label photo | recorded | |
| Chemistry | protected 1S Li-poly, 3.7 V / 4.20 V | |
| Pack body L x W x T | <=25 x 10 x 5.5 mm; Renata target <=24 x 10 x 5.5 | |
| Leads/interconnect | identified; separate dry-fit route and strain relief | |
| Rated capacity | record exact | |
| Normal / maximum charge | record exact | |
| Measured worst charge | record bootloader + app; below max with margin | |
| Protection | OV, UV, OC, short | |
| Exact UN38.3 summary | MPN/revision match; archived | |
| IEC/UL evidence | record exact claim/file, if any | |
| Metered polarity / connector | photographed | |
| Open-circuit voltage | stable and inside exact datasheet limits | |
| Physical condition | flat, clean, no dent/corrosion/odour | |
| Same-lot physical count | 12 isolated | |

Result: **PASS / REJECT**

Buy one first. Buy the held 11 only after documentation, gauge, lead route,
polarity, measured charging, thermal, RF, and closed-shell Unit 001 tests pass.
Do not hot-cut/shorten leads unless the battery maker supplies a written safe
procedure and the hardware builder prevents a short at every step.

Quarantine any cell above 4.21 V, below its specified cutoff, unstable, swollen,
dented, corroded, odorous, or physically altered. Never sand, fold, squeeze,
puncture, rewrap, or solder directly over a pouch.
