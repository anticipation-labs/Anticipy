# FIX-11 — The scrape picks its own sites (self-expanding layers)
<!-- status: DONE (engine; live proof needs L1) | milestone: M5 | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
"Layer 2/3" used to re-scroll the SAME five sites deeper — depth on fixed inputs, not the
graph-following Omar described ("scrape two picks the sites on its own"). Now each layer unions in
the systems the dossier actually DISCOVERED inside the owner's accounts — the CRM, the Notion, the
billing dashboard — under one consent toggle, with hard safety rails.

## Human check
In onboarding's "What I may read", there's one new switch: "Sites I discover inside your accounts".
With it on, a deep read that finds your Notion link in an email reads the Notion next pass — and
tells you it did ("followed your world into notion.so").

## Step 1 — dossier.py: discoveries carry REAL URLs  [x]
`act_on_sites` → `[{name, url}]` + the prompt law: "include the exact https URL you actually SAW —
NEVER invent or guess a URL; a tool name with no link goes in tools." Writer already dict-safe.

## Step 2 — permissions.py: the ONE consent  [x]
New service `discovered` ("Sites I discover inside your accounts") — renders automatically as a
checkbox in the existing permissions UI; nothing expands without it.

## Step 3 — loop.py: the expansion  [x]
`_discovered_surfaces()`: https-only (no name→domain guessing), `nav_block_reason` money/bank wall,
host-dedup vs current+bounced, cap +4/layer; unioned into `allowed` after each layer's dossier;
`discovered` hosts recorded on the layer + glassbox `onboard_loop_expanded`.

## Step 4 — the pinned suite test  [x]
**Proof command:** `engine/scripts/test_onboard_loop_expansion.py` (in run_suite.sh)
**WIRING PROOF (2026-07-02):** `PASS onboard_loop_expansion: layer 2 follows the discovered graph;
banks + bare names refused; consent-gated` — pins: Notion(with URL) reaches layer-2's scrape call;
chase.com never enters; bare "HubSpot" never becomes a surface; consent off → zero expansion.

## Remaining
- [ ] L1 live proof: Omar's real Chrome — watch layer 2 open the system layer 1 found.
