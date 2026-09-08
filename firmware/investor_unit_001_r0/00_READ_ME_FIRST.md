# Anticipy Unit 001 — read this first

> **STATUS: HOLD FOR PHYSICAL RELEASE TESTS**
>
> The CAD and firmware candidate are complete and reproducible. The physical
> investor unit is not released until the real nylon, battery, motor, iPhone,
> charging, radio, audio, thermal, drop, and privacy gates in this packet pass.

## The simple version

Use the two ordered nylon pieces as the visible body. Print one narrow black
4.50 mm perimeter band that sits between them. Put a protected battery and a
sealed coin vibration motor on the insulated floor, put the printed safety
bridge above the battery, put a **headerless XIAO nRF52840 Sense** on the
bridge, then close the ordered face.

The finished nominal size is **51 x 22 x 14.5 mm**. There is no microSD board
and no onboard audio backlog in Unit 001. Audio streams live to the Anticipy
iPhone app. If the phone disconnects, that interval is not recorded.

CAD reports zero modeled overlap against the exact historical body and hooked
face, including the face drop/slide path. That authorizes printing and a dry
fit; the real nylon and finished parts remain the authority.

## Print now

Open `01_CAD/README_BUILD.md`. Print only the files in
`01_CAD/PRINT_THESE/`, starting with both band variants and all gauges. Use
black PETG or PETG-HF. The nominal and loose bands are alternatives; use only
the one that seats with fingertip pressure.

## Tuesday, September 1

1. At 08:00 PT call Cadex. At 09:00 call Swiss Watch Parts and Vancouver
   Battery for exact **Renata ICP501022UPM / part 100640**. Ask each supplier
   to isolate 12 same-lot packs, sell one fit article, and hold 11 unpaid until
   Unit 001 passes. Record the staff name, physical count, and hold expiry.
2. At 09:00 call Lee's, 604-875-1993, for the sealed coin motor and SMD driver
   candidates. A technical hold request was emailed, but stock is unconfirmed.
3. Do not buy a battery or motor from its web description. Apply
   `03_PROCUREMENT/BATTERY_COUNTER_CARD.md` and the current/size gates.
4. Print the bands, bridge, drill jig, and gauges while calls are in progress.
5. Verify the in-hand board says **XIAO nRF52840 Sense** and has no pin headers.
   The CAD does not fit an ESP32-S3 Sense or a headered XIAO.
6. The Memory Express SD-card order is not a Unit 001 dependency and is due at
   pickup. Do not collect it for this build without separate authorization.
7. To make Wednesday afternoon possible, qualify the structural adhesive on a
   PETG coupon bonded to a sacrificial spare nylon shell Tuesday morning. After
   the TDS working-strength time, destructively test one coupon. If it passes,
   bond the selected **empty** band to the Unit 001 body by noon Tuesday and
   leave it undisturbed for the complete 24-hour cure. Keep a co-cured witness
   coupon for Wednesday's pre-assembly check.

## Wednesday, September 2

1. Full-erase one XIAO, flash the single owner2 firmware candidate, and
   commission it to the intended test iPhone in a private room during its
   120-second zero-bond window.
2. Prove app audio, haptic, reconnect, and second-phone rejection on USB power.
3. While the band completes its cure, measure every finished component, including the insulated driver island and
   battery lead route. Dry-fit the complete unpowered stack with witness film.
4. Build exactly as `04_ASSEMBLY/ASSEMBLY.md` specifies. Keep the cell
   disconnected until continuity, polarity, and current-limited checks pass.
5. At or after the recorded 24-hour cure, destructively check the witness
   coupon, inspect the seam, then assemble into the bonded body. The original
   face remains removable for powered open-case checks.
6. Run every line in `05_RELEASE/QA_RELEASE.md`. A failed line means HOLD,
   repair, and full retest.

## Thursday/Friday replication

Build no batch until Unit 001 passes unchanged. Then freeze the exact battery
lot, motor part, SMD driver packages, band variant, adhesive process, firmware
hash, and app version. Build nine units plus two spares with a per-unit release
record. A substitution sends the design back through Unit 001 qualification.

## Honest handoff language

A passed unit is a **functional investor sample in the final industrial-design
direction**. Say only what that serial-numbered unit proved: live app audio,
battery operation, charging, haptic, reconnect behaviour, two-hour closed-case
operation, and recorded mechanical tests. It is not yet certified,
waterproof, production-validated, or customer-sale-ready.
