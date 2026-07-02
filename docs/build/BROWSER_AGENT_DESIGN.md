# The Best Browser Agent — design (grounded in 2025 SOTA)

*Researched against: Browser-Use (SOTA, ~89% WebVoyager), WebVoyager paper (vision-only ~59%),
OpenAI Operator/CUA, Anthropic Computer-Use, Google Project Mariner + Gemini computer-use API,
Manus (multi-agent planner/executor), Stagehand/Browserbase, and the arXiv survey
"Building Browser Agents: Architecture, Security, and Practical Considerations" (2511.19477).*

---

## 0. The realization that changes everything

Our architecture is already the *rare, correct* one. We drive the user's **own logged-in Chrome
via CDP** (a Chrome MV3 extension + `chrome.debugger`). That is the ONE thing the famous cloud
agents (Operator, Browser-Use-cloud, Mariner) **cannot** do — they run a fresh remote browser with
no access to your real Gmail/Amazon/bank sessions. So they make the user re-auth, or they can't do
personal tasks at all.

**Our moat = real authenticated Chrome.** The job is not to copy their transport — it's to put a
world-class *brain* on top of the transport we already have, and rip out the demo crutches.

---

## 1. The six pillars

### Pillar 1 — Hybrid perception: DOM/accessibility-tree FIRST, vision as backup
This is the single strongest finding in the field. Vision-only (WebVoyager) tops out ~59%;
hybrid (Browser-Use) hits ~89% on the same benchmark.

- **Primary input = a compact interactive-element tree** extracted from the page: every
  clickable/typeable/selectable node with its role, accessible name, value, and bounding box,
  indexed `[1]…[n]`. One request shows the whole page (nav, forms, dialogs, errors) with no
  scrolling, and it's ~10× cheaper in tokens than a screenshot.
- **Vision only when needed**: take a set-of-marks screenshot (we already build this) when the
  DOM is ambiguous — canvas apps, custom widgets, visual disambiguation, or a verification step.
- Net: cheaper, faster, more accurate, and it generalizes to any site.

### Pillar 2 — Planner + Actor split (Observe → Plan → Act, the Manus/Mariner pattern)
- **Planner** (smart model): holds the goal, decomposes into subgoals, re-plans on failure,
  decides "are we done / blocked / need the human?".
- **Actor** (cheap model): given the current observation + current subgoal, emit exactly one
  action. Fast, narrow, replaceable.
- **Working memory**: a running scratchpad of what's been tried, what worked, current subgoal —
  so the agent doesn't loop or forget mid-task.

### Pillar 3 — Model routing (the #1 cost lever: 40–70% savings)
Never use the frontier model for every step.
- Cheap/fast model (Gemini Flash / Qwen-class) for routine per-step actions.
- Smart model (Claude / Gemini Pro) only for planning, ambiguity, and recovery.
- We already have `ANTICIPY_MODEL_CHEAP` + `ANTICIPY_MODEL_SMART` wired — use both deliberately.

### Pillar 4 — LEARNED recipes + caching (Amazon-recipe speed without Amazon-recipe hardcoding)
The cardinal sin was a hand-written Amazon script. The correct version:
- After a task succeeds, **record the action trace** keyed by (site, task-type) as a *discovered*
  skill the agent can **replay deterministically next time without calling the LLM**.
- On replay, if the page diverges from the recorded trace → fall back to live reasoning
  (self-healing). Recipes are *discovered live and general*, never authored per-site.
- Plus: **prompt-cache** the static system prompt (~90% savings on cache hits), and
  **context-compaction** (drop stale observations) to keep the window small (50–70% token cut).
- arXiv survey §7.3: for a 100-request workflow, caching is the difference between viable and not.

### Pillar 5 — The robust execution layer (the unglamorous 80% where agents actually fail)
- wait-for-stable-DOM (not fixed sleeps), retries with backoff, scroll-to-find-element.
- iframes, shadow DOM, new tabs/windows, native JS dialogs (we handle these).
- **Wall detection**: login / 2FA / captcha / paywall → **pause + ask the human, never fake done.**
- CDP is the right substrate: real `isTrusted` input events that hard sites accept (we have it).

### Pillar 6 — Verification + trajectory memory (gets smarter, asks less over time)
- **Completion = read-back, not self-report.** After acting, re-read the resulting page state and
  judge whether the goal is actually met. A wall is `needs_human`, never "done".
- Store the trajectory + outcome in memory (ties into the Phase-4 memory system) so the agent
  reuses what worked and asks fewer questions next time.

---

## 2. The action space (small + universal, like Gemini computer-use / CUA)
`navigate(url)` · `click(idx)` · `type(idx, text)` · `select(idx, value)` · `scroll(dir)` ·
`key(name)` · `wait(ms)` · `ask_human(question)` · `done(result)`.
**No per-site verbs. Ever.** The URL comes from the planner inferring it (or a live search),
never a keyword→site lookup table.

---

## 3. What we keep / rip from the current `webvoyager.py`
**Keep:** CDP/extension transport (excellent, rare), the set-of-marks screenshot (now the *vision
fallback*), the honesty (never fake done), the SSRF/private-IP nav guard (real security).
**Rip:** every hardcoded recipe (Amazon return, commerce/cart, keyword→site map, owner-TLD baking,
demo-Amazon subsystem); the over-aggressive money/credential *refusals* (per Omar — these are not
hard stops); vision-on-every-step cost.

---

## 4. Build order (each step provable on video on the VM)
1. **VM test harness** — load the unpacked extension into my VM Chrome, prove it connects + drives
   a real site end-to-end, record it. (Dev loop first.)
2. **Rip hardcoding + remove the refusals** behind one `ANTICIPY_BROWSER_UNLOCKED` flag.
3. **Add DOM/a11y perception** and make it primary; screenshot becomes fallback.
4. **Planner/Actor split + model routing.**
5. **Learned-recipe cache + prompt caching + compaction.**
6. **Robustness pass** (walls, iframes, retries) + **read-back verification.**
7. **Prove generic**: a return-style task AND a brand-new site it's never seen, back-to-back,
   zero site-specific code.

---

## 5. Cost posture (the "most cost-effective" answer)
- DOM-first perception ≈ 10× cheaper than screenshot-every-step.
- Cheap model per step, smart model only on plan/recover ≈ 40–70% off.
- Prompt-cache the system prompt ≈ 90% off the static portion.
- Replay learned recipes ⇒ **zero LLM calls** on repeat tasks.
- Compaction keeps the context window flat on long tasks.
Stacked, these are the difference between pennies and dollars per task.
