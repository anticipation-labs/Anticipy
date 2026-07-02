# Vision-first, 10× quality at 1/10 price — the concrete plan

## Where we are (honest, measured)
- Our homegrown DOM-first agent on the **official WebVoyager** set (30 live tasks, cold): **~28%.**
- Frontier / mature open agents: **Browser-Use ~89%, Agent-E ~73%, WebVoyager agent ~59%.**
- Root causes from the actual run:
  1. **Too slow → 300s timeouts** (Cambridge, Coursera, ArXiv).
  2. **2-step bails on JS/client-rendered pages** (Apple, ESPN) — pure-DOM serialized empty, no vision fallback.
  3. **Anti-bot / consent walls** (Amazon, Booking, Google Flights) handled poorly.
  4. **Judge false-negatives** — some correct answers rejected (our judge ≠ WebVoyager's).

**The core mistake:** we hand-rolled a from-scratch DOM-first agent instead of standing on a proven
open agent and adding our real edge (cost routing + recipe replay + authenticated Chrome). This plan
fixes that.

## The technical crux: how to be VISION-FIRST *and* 1/10 the price
Vision-first ≠ "send a full frontier-vision screenshot every step" (that's the $0.10–0.40/task flat
cost of Operator/Vy). Vision-first done *cheaply* uses four stacked techniques:

1. **Set-of-Marks (SoM) + accessibility tree.** Overlay numbered boxes on interactive elements
   (sourced from the a11y tree, not fragile DOM scraping) on ONE screenshot; the model outputs
   "click box 12". Grounding accuracy comes from the marks, so a *cheap* VLM suffices. **This alone
   fixes the 2-step JS-page bails** — the a11y tree + pixels see elements our DOM missed.
2. **Cheap VLM as the default tier.** Gemini 2.5 Flash / Flash-Lite have real vision at ~20–50×
   less than GPT-4o/Claude. Route routine grounding to it; escalate to a frontier VLM only on low
   confidence / no-progress / money steps (same routing philosophy we already have, applied to vision).
3. **Downscale + region crops.** ~768–1024px screenshots and tight element crops = 10–20× fewer
   image tokens per step (our existing DOM+regions `doCrop` work plugs in here).
4. **Distillation endgame.** Harvest successful (screenshot → action) traces → fine-tune a small
   open GUI-VLM (UI-TARS-2B/7B or Molmo, both open-weight, natively output element "points") → the
   bulk of steps run on a near-free self-hosted model. This is the curve that bends *down* while the
   labs stay flat. **Requires a GPU box — not available on this machine (flagged below).**

Net: **10× quality vs our 28%** comes from SoM+a11y vision (no empty-DOM bails) + wait/retry (no
timeouts) + frontier-on-hard. **1/10 price vs their vision-every-step** comes from cheap-VLM-default
+ SoM + downscale + recipe replay + (eventually) a distilled small model.

## Open-source we leverage (don't reinvent)
- **Browser-Use** (Apache-2.0, pip): mature harness — wait-for-load, scroll, iframe, retry, SoM DOM
  extraction, and it already drives Chrome over CDP. Use as the perception/execution backbone.
- **UI-TARS** (ByteDance, Apache-2.0): open GUI-agent VLM that takes screenshot+instruction and emits
  grounded actions — the self-hostable cheap vision tier (needs GPU).
- **Molmo** (AllenAI): open VLM with native pointing.
- **Set-of-Mark** (Microsoft): the labeling technique.
- **WebVoyager eval harness**: the official GPT-4V auto-judge — adopt it so our number is comparable.

## What stays OURS (the moat, kept from current code)
- Subgoal scratchpad + per-subgoal read-back verification + dead-loop detection (already built, works).
- **Recipe replay** (~$0 warm repeats) — bolts on top of any backbone.
- **Authenticated real-Chrome** deployment — the task class labs score ~0 on.
- Money hard-stop / never-fake-done verification.

## Target architecture (layers)
1. **Perception (vision-first, cheap):** screenshot + a11y tree → SoM numbered overlay, downscaled.
   (Browser-Use provides this.)
2. **Grounding (cost router):** cheap VLM (Gemini Flash) default → frontier VLM on hard/ambiguous.
3. **Planning/memory:** our subgoal + verify + loop-guard layers.
4. **Reliability:** wait-for-network-idle, retry, scroll-to-find, consent-wall dismiss, honest captcha hand-off.
5. **Cost flywheel:** recipe replay now; distilled small VLM later (GPU).
6. **Judge:** WebVoyager official auto-judge for honest, comparable scoring.

## Phased execution (autonomous, each gated on a real number)
- **Phase 0 (now):** install Browser-Use, run it on the SAME 30-task sample → head-to-head number on
  THIS machine (not their marketing number). Stand up the WebVoyager official judge.
  *Gate: real baseline for both agents on identical tasks.*
- **Phase 1:** adopt SoM + a11y perception + wait/retry/scroll/consent into the loop, keep our
  subgoal/verify/recipe layers. Re-run sample. *Gate: 2-step bails and timeouts gone; big jump.*
- **Phase 2:** vision router — cheap VLM default, frontier-on-hard + downscale/crops. Re-run.
  *Gate: at/near frontier quality at ≤1/5 their $/task.*
- **Phase 3:** self-host UI-TARS/Molmo as the cheap grounding tier. *Gate: same quality, ~1/10 price.*
  **BLOCKED here: no GPU on this box — needs a GPU instance.**
- **Phase 4:** distillation on accumulated traces. *Gate: cost curve bends down.* (Needs GPU.)
- **Phase 5:** full 642-task run + official judge = the defensible global number.

## Honest constraints
- **No GPU here** → Phases 3–4 (self-hosted/distilled small VLM = the literal "1/10 price via our own
  model") need a GPU instance. Until then the cheap tier is hosted Gemini Flash — still cheap, but the
  full 1/10 endgame is GPU-gated.
- **Anti-bot** (Amazon/Booking/Flights) blocks every agent; some tasks are honestly unwinnable without
  logged-in sessions — which is exactly where our authenticated-Chrome edge pays off.
- Topping frontier labs on their own benchmark is a real, multi-step build — Phases 0–2 are fast and
  autonomous here; Phase 3+ needs infra.
