# Source and delivery status — checked 2026-09-01 PT

| Item | Verified fact | Build decision |
|---|---|---|
| Ordered shells | User reports nylon shells physically in hand. Corrected CAD imports the exact historical 51 x 22 x 10 mm body and hooked face and records 1,045 boolean checks with 0.0 mm3 maximum overlap. Real nylon is not yet caliper-tested here. | Print gauges/bands; physical no-load closure remains mandatory. |
| XIAO boards | User reports boards in hand; exact model/header state is not photographed here. | Use only headerless XIAO nRF52840 Sense; keep one known-good spare. |
| Owner2 firmware | Two clean builds are byte-identical, 528,384 bytes, SHA-256 `f246fc79ff9925fb427585e8babf4fe106ea1ad1c32a82b2c4351d3cc55ea5d6`. No physical iPhone/hardware test has run here. | Single candidate; HOLD until QA. |
| Renata ICP501022UPM / 100640 | Official page reports 80 mAh and 24 x 10 x 5.5 mm. Archived manufacturer datasheet reports safety circuit, 40 mA normal/80 mA max charge and states IEC62133 certification. Archived exact-model UN38.3 summary reports T1-T8 passed. | First battery target; local stock remains unconfirmed. |
| Swiss Watch Parts | Renata lists the Vancouver firm as a distribution partner. Public physical stock is unconfirmed. | Call 09:00; one article plus unpaid same-lot hold. Email draft is saved, not sent. |
| Vancouver Battery / Cadex | Local contact leads only; no evidence either stocks exact pack. | Call and require exact label/photo/docs; email drafts saved, not sent. |
| Lee battery PID160959 / 8834 | Search-indexed candidates lack adequate exact manufacturer/charge/UN38.3 evidence. | Reject unless every battery counter gate passes. |
| Lee coin motor PID10431 | Local listing describes 3 V sealed 10 x 2.7 mm pager motor; maker/current/duty and physical stock are not verified. | Counter candidate; measure size/current and test before approval. |
| Lee barrel PID104281 | Exposed rotating head; no qualified guard in packet. | Not a Unit 001 shipping fallback. |
| Lee SMD driver candidates | Search-indexed BAT54 SOT-23 PID160021, 0805 1 kOhm PID914081, 0603 10 kOhm PID17426, and SOT-23 NPN candidates exist. Inventory/listings are not reservations. | Buy only exact packages; qualify ratings/pinouts and finished 8 x 4 x 2 mm island. |
| Lee technical hold | Email sent to `support@leeselectronic.com` asking them to prioritize battery PID160959, hold 12, and inspect coin motor/driver candidates. | Call; no purchase or stock confirmation exists yet. |
| Memory Express CSO006089271 | Pickup-ready notice for ten cards/cables; existing evidence says C$386.74 is due at pickup. | Not a Unit 001 dependency. Do not collect for this build without separate authorization. |
| DigiKey 101304421 | Shipment email dated Aug 29 with FedEx 539111734891; public tracker did not resolve in the last check. | Do not depend on it for Wednesday. |
| DigiKey MyoWare 101311973 | Separate shipment; not Anticipy inventory. | Ignore for this build. |
| TME 35388887 | Shipment confirmation for Raytac modules used by later custom PCB. | Not a Wednesday XIAO dependency. |

Live stock and tracking change. A call with staff name, physical count, exact
MPN photo, hold expiry, and pickup time is the required reservation evidence.
