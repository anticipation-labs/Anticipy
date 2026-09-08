# Anticipy in real life: the replacement guide

Use [the new PDF](../../output/pdf/Anticipy-in-real-life-100-conversation-exemplars.pdf) to understand the customer experience. It replaces the earlier timed engineer brief for this purpose. There is no work schedule or points system.

The guide contains 100 distinct fictional conversations, grouped into ten areas of life. Each shows the prior context, dialogue, useful response, actual work required, memory to preserve and a changed circumstance that changes the right response. Results are illustrative: these are not completed test transcripts or proof of 100 working capabilities.

Read the conversations, install the app on your own phone, use it like a customer, reproduce failures, fix their causes and ship the verified experience. The instruction to the engineer is on pages 55-56. The earlier 500-case catalogue is optional supporting material, not the replacement guide's work order.

Editable sources are `guide.md` and `exemplars.txt`. `exemplars.json` preserves all 100 records for review or controlled test preparation; it is not wired into production or a phrase-based router. `validation.json` records document checks only.

Rebuild with Python, ReportLab and pypdf:

```sh
python3 docs/100-lived-exemplars-2026-09-07/build_guide.py
```

Render and visually inspect the PDF after changing its text or layout. The delivered guide contains 56 pages: four introduction/index pages, fifty pages of exemplars and two closing instruction/reference pages.
