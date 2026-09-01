# Unit 001 investor release record

Serial: __________  Builder: __________  Date/time PT: __________

Every line is initialled with evidence. One red line means **HOLD**.

## Identity and traceability

- [ ] Board visually verified: headerless XIAO nRF52840 Sense.
- [ ] Full internal erase completed before commissioning; reused external QSPI
      was sanitized or board is documented new.
- [ ] Firmware filename and SHA-256 match the packet: ______________________
- [ ] Anticipy TestFlight/app version recorded: _____________________________
- [ ] Battery manufacturer/MPN/lot and archived documents recorded: _________
- [ ] Motor and driver exact parts/packages recorded: _______________________
- [ ] Selected band, print settings, filament lot, adhesive lot/TDS/cure
      record, and builder recorded.

## Mechanical/electrical

- [ ] Actual shell, XIAO, pack body, lead route, motor, and finished insulated
      8 x 4 x 2 mm driver island pass their gauges.
- [ ] No exposed conductor, flux, sharp edge, loose hard part, or wire pinch.
- [ ] No hard part, joint, lead, or wire loads the pouch; witness film clean.
- [ ] Face drops/slides/closes with fingertip pressure; USB does not move PCB.
- [ ] Coin motor is sealed and securely bonded; motor current/current margin
      and flyback polarity are recorded.
- [ ] Band coupon passed and the fully cured seam has no peel, gap, crack,
      whitening, creep, or cosmetic contamination.

## Firmware, app, and privacy

- [ ] Release profile is **LIVE-STREAM ONLY**. No microSD/QSPI backlog exists.
- [ ] Phone A commissions in private, pairs, receives intelligible audio, and
      controls haptic. Pairing completed and settings were given >2 s to store.
- [ ] After power cycle, Phone A reconnects 20/20.
- [ ] Phone B cannot connect/read audio/issue haptic while Phone A owns unit.
- [ ] If D7 is fitted: 10 s boot hold clears owner, then Phone B can commission.
      If omitted: controlled SWD erase/recovery path was rehearsed and recorded.
- [ ] App clearly reports a disconnect and resumes live audio without claiming
      the missing interval was captured.
- [ ] App-triggered DFU is owner-gated. No claim of signed/secure boot or secure
      owner-only OTA is made.

## Functional and power

- [ ] Cold boot on qualified battery: 10/10.
- [ ] Worst battery-branch charge current from USB insertion through bootloader,
      application, termination, and recharge recorded: ______ mA; inside exact
      pack limit with margin.
- [ ] Charge from 20–30% to at least 80% with no reset, pouch change, or abnormal
      heat; polarity/current log attached.
- [ ] Intelligible closed-case live audio runs 60 continuous minutes.
- [ ] Haptic short/medium/long: 25 each, with no reset, mic noise, RF loss, heat,
      or mechanical movement.
- [ ] Button events 50/50 if fitted.
- [ ] Closed-case BLE range passes at 5 m and 10 m in the intended orientation,
      including body-worn test; result: ____________________.
- [ ] Two-hour combined audio/BLE/haptic soak passes; shell/cell rise <10 C.
- [ ] Battery percentage is plausible at full/mid/low; measured operating time
      demonstrated for this release: ______ hours.
- [ ] System-off/wake and watchdog recovery pass.

## Mechanical abuse and finish

- [ ] Six-direction 1 m drop onto plywood over concrete, powered off; seam stays
      closed and no pouch damage/loose part occurs; all functions pass afterward.
- [ ] 100 firm hand shakes and moderate hand twist: no rattle, creep, crack,
      opening, or reset.
- [ ] Normal USB side-load does not move board or damage seam.
- [ ] Reopened after abuse: pouch has no mark, dent, crease, rub, or lead strain.
- [ ] Reclosed and repeated 15-minute audio/reconnect/haptic test.
- [ ] Exterior is clean and product-like; no adhesive bloom, tool marks,
      misaligned seam, raw hole, or visible print defect.

## Handoff

- [ ] Intended recipient/account is provisioned; support and recovery contact
      included.
- [ ] Recipient is told this is a functional production-intent investor sample,
      not certified, waterproof, production-validated, or customer-sale-ready.
- [ ] Transport follows current carrier rules for lithium battery contained in
      equipment; exact UN38.3 summary travels with the build record.

Decision: **PASS / HOLD**

Released by: ____________________  Time: ____________________
