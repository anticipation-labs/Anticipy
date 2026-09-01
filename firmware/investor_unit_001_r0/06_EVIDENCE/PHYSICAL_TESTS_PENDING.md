# Physical tests pending for Unit 001

This file is intentionally red until a named builder records evidence. CAD and
static firmware verification cannot replace these checks.

- [ ] Ordered nylon body, face, and headerless XIAO measured and photographed.
- [ ] Exact battery label/lot/documents/polarity/OCV/finished dimensions pass.
- [ ] Battery lead route and strain relief dry-fit without pouch pressure.
- [ ] Exact motor and finished SMD driver pass size/current/thermal checks.
- [ ] PETG-to-nylon coupon and 24-hour structural-bond cure pass.
- [ ] Complete unpowered stack closes with clean witness film and fingertip
      pressure through the face's real drop-and-slide motion.
- [ ] Full erase, intended TestFlight version, Phone A ownership/reconnect,
      Phone B rejection, live audio, haptic, and recovery pass.
- [ ] Battery-branch charge current is measured through bootloader,
      application, termination, and recharge and is within the exact pack
      limit with margin.
- [ ] Closed-case RF/audio/runtime/thermal/system-off/wake tests pass.
- [ ] Shake, twist, drop, USB handling, reopen inspection, and final cosmetics
      pass with no pouch mark or seam movement.

Only a completely initialled `QA_RELEASE.md` changes Unit 001 from HOLD to
PASS. Units 002-012 remain blocked until that first unit passes unchanged.
