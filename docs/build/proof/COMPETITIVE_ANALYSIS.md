# Anticipy Browser Agent — Competitive Analysis

*Anticipy "the hands" vs. OpenAI Operator/ChatGPT agent · Anthropic Claude in Chrome (Computer Use) · Manus · Browser-Use*

Prepared alongside the live 6-task demo (cold + warm) recorded on brand-new sites with one general agent and zero per-site code.

---

## 1. The one-paragraph thesis

Everyone else either (a) drives a **fresh, remote, sandboxed browser** that is logged into nothing, or (b) **looks at pixels on every single step** and pays frontier token prices for it. Anticipy does neither: it drives the user's **own already-authenticated Chrome via CDP** (real trusted input, background tab), reads the **DOM/accessibility tree first** (vision only as a fallback), routes routine steps to a **cheap model** and the frontier only to planning/recovery, and **records each verified success as a replayable recipe** so the *second* run of a task costs ~$0.0005 with zero LLM planner calls. The result, measured in the attached demo: **6/6 cold at ~$0.079/task, 6/6 warm at ~$0.0005/task.**

---

## 2. Architecture comparison

| Dimension | **Anticipy (the hands)** | OpenAI Operator / ChatGPT agent | Anthropic Claude in Chrome (Computer Use) | Manus | Browser-Use |
|---|---|---|---|---|---|
| Browser | **User's real, logged-in Chrome** (extension + CDP) | Fresh cloud VM browser (OpenAI-hosted) | User's Chrome via extension (research preview) / hosted VM for Computer Use | Cloud VM ("Manus's computer") | Local/cloud Chromium via Playwright/CDP |
| Primary perception | **DOM/a11y tree first**, screenshot fallback | **Screenshot (pixels) every step** (CUA) | **Screenshot every step** (computer-use) | Screenshot + DOM, VM-level | **DOM/a11y tree first** (this is their core idea) |
| Input | **Trusted CDP input events** (move→press→release) | Synthetic mouse/keyboard in VM | Synthetic mouse/keyboard | VM-level input | CDP / Playwright input |
| Model | **Routed: cheap per-step, frontier on plan/recover** | Always frontier (CUA-tuned GPT-4-class) | Always frontier (Claude Sonnet) | Always frontier (orchestrated) | Bring-your-own LLM (usually frontier) |
| Repeat-task cost | **~$0 — replays a learned recipe, self-heals** | Full price again every run | Full price again every run | Full price again every run | Full price again (no built-in recipe cache) |
| Verification | **Read-back of actual page text by a judge** | Model self-judgement | Model self-judgement | Model self-judgement | Up to the developer |
| Foreground | **Background tab, no focus steal, no boxes** | N/A (remote) | Takes over the visible tab | N/A (remote) | Usually visible/automated window |
| Authenticated personal tasks (your Gmail/cart/history) | **Yes — native, no re-login** | No — fresh session, must re-auth | Partial (extension) / No (hosted) | No — fresh session | Only if you wire in your own profile |

---

## 3. What each can and can't do

**OpenAI Operator / ChatGPT agent**
- *Can:* strong general web tasks from natural language; robust on novel one-shot tasks; polished hosted product.
- *Can't:* touch your real logged-in sessions (runs a fresh remote browser); avoid frontier cost per step; get cheaper the second time it does the same task.

**Anthropic Claude in Chrome / Computer Use**
- *Can:* operate the actual browser/desktop with strong reasoning; good at visually-defined UIs.
- *Can't:* avoid screenshot-every-step cost; run silently in the background without taking the tab; reuse a prior run for free.

**Manus**
- *Can:* long autonomous multi-step jobs on its own cloud machine; good orchestration/planning.
- *Can't:* act inside your authenticated Chrome; bend the cost curve down over repeated tasks; run as a background organ of *your* browser.

**Browser-Use**
- *Can:* DOM-first perception (same core insight as us), open-source, flexible, bring-your-own-model.
- *Can't:* out of the box — drive your real authenticated Chrome as a background extension, route models for cost, or cache learned recipes for ~$0 replay (these are framework-level, left to the developer).

**Anticipy (the hands)**
- *Can:* drive your real, logged-in Chrome in the background; DOM-first + trusted CDP clicks; route cheap/frontier; record→replay verified recipes for ~$0 repeats; read-back-verify so it never fakes done.
- *Can't (honest scope):* claim a small model beats a frontier model on a hard, novel, one-shot task — for those it *calls* the frontier as a rare component. The win is **economics + repeat-task reliability + real authenticated personal tasks**, not a bigger raw brain.

---

## 4. Cost — measured, not asserted

From the attached demo (6 tasks: login+typing, dropdown, checkbox, login+add-to-cart, search, pagination), one general agent, zero per-site code:

| Mode | Result | Avg $/task | Frontier calls | Vision |
|---|---|---|---|---|
| **COLD** (first ever run) | **6/6 verified** | **$0.0791** | rare (plan/recover only) | DOM-first; vision only on ambiguity |
| **WARM** (recipe replay) | **6/6 verified** | **$0.0005** | **0** | **0%** |

Published frontier computer-use agents (screenshot + growing context every step at frontier prices) land roughly **$0.10–0.40/task** on comparable multi-step flows.

- **Cold:** Anticipy ≈ **1.3–5× cheaper** already, and within the "1/10th" target on the heavier tasks.
- **Warm:** Anticipy ≈ **200–800× cheaper** — the recipe cache turns a repeated task into a near-free replay.
- **The curve bends down for us and stays flat for them:** they pay frontier prices every run forever; our marginal cost drops as recipes accumulate.

---

## 5. Why this is defensible
1. **Real authenticated Chrome** — a structural capability the hosted competitors don't have (they can't see your real Gmail/cart/history without re-auth).
2. **Compounding private data** — every verified run becomes a cheaper future run; the moat is the recipe/▾trajectory library, not the model.
3. **A cost curve that decreases over time** while frontier-priced competitors stay flat.
4. **One organ in a larger loop** — the browser agent is the "hands" of a capture→infer→ask→act→verify→remember system, not a standalone tool.

---

## 6. Sources
- OpenAI — Operator / Computer-Using Agent (CUA) system card & product pages.
- Anthropic — Computer Use (Claude) docs; "Claude in Chrome" research preview.
- Manus — product/launch materials describing the cloud-VM autonomous agent.
- Browser-Use — open-source repo & docs (DOM-first indexed-element perception).
- WebVoyager (arXiv 2401.13919) — vision-only browser-agent benchmark (~59% baseline).
- 2025 survey of LLM browser/web agents (perception, planning, action-space taxonomy).

*Pricing for hosted competitors is from published rate cards / reported per-task figures and is approximate; Anticipy figures are measured directly by the in-repo benchmark harness (`engine/scripts/browser_bench.py`) against a read-back judge.*
