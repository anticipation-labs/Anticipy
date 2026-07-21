# Deep dive: how the big browser agents actually work — and how Anticipy adapts each mechanism

Sources: Anthropic's Claude-in-Chrome help center + Claude Code Chrome docs
(primary), OpenAI Codex-for-Chrome coverage, browser-use docs (primary), plus
industry reporting. Facts below marked [P] came from the vendor's own pages.

---

## 1. Claude in Chrome (Anthropic)

**Form:** Chrome Web Store extension + side panel. Desktop Chrome/Edge/Brave/
Arc/Vivaldi/Opera; not mobile. [P]

**How it sees the page:** two channels — `scripting` permission to read text/
DOM, and the `debugger` permission (Chrome's internal DevTools Protocol) for
screenshots, console output, network requests, and DOM state. [P]

**How it acts:** the same `debugger` API performs trusted clicks/typing —
"this is what allows Claude to actually control your browser — clicking
buttons, typing text, and taking screenshots." [P] This is stronger than
`scripting` injection: debugger-driven input is browser-level (works on
canvas apps, iframes, keyboard shortcuts), and `system.display` is requested
so click coordinates map correctly to the real screen. [P]

**Background operation:** tabs it opens go into a **separate color-coded tab
group** (`tabGroups` + `tabs` permissions) so the agent's tabs are visually
segregated from yours and it can work while you browse elsewhere. [P]
`alarms` gives scheduled recurring tasks; `notifications` + `offscreen`
(sound) alert you when it finishes or needs help. [P]

**Session model:** it acts inside your logged-in profile — no separate API
keys or accounts. At login pages and CAPTCHAs it *pauses and asks you to
handle it manually* (never bypasses). [P — Claude Code Chrome docs]

**Safety:** per-site permission grants, confirmation before consequential
actions (publish/purchase), category blocks (banking/investment),
`webNavigation` to intervene on high-risk sites, plus server-side
prompt-injection classifiers. Anthropic still labels it "risky" — the core
threat is prompt injection: a malicious page instructing the agent, which
then acts as *you*. [P]

**Extras:** workflow recording ("teach it once, replay later"), scheduled
tasks, native messaging to Claude Desktop/Code, session GIF recording. [P]

**Model routing:** works with all public Claude models; lighter models
(Haiku) for simple page reading, heavier for multi-step. [P]

## 2. Codex for Chrome (OpenAI)

**Form:** also an official Chrome extension (launched after Claude's) that
operates inside the user's signed-in Chrome session — email, LinkedIn,
Salesforce-type workflows. Invoked with `@Chrome` from the Codex app; per-site
allowlist and approval prompts before actions. Same architectural conclusion
as Anthropic: extension + user's own session.

**Their other lanes:** ChatGPT Agent = a *cloud VM browser* on OpenAI's
servers (their "computer use" stack — screenshots + model choosing actions,
no local install); Atlas = an entire Chromium-based browser with the agent
built into the chrome itself.

## 3. Kimi (Moonshot) and Comet (Perplexity)

Kimi's agentic browsing runs the loop server-side against a managed browser
(closer to ChatGPT Agent), exposed inside their chat product. Comet is a
full Chromium fork — the agent ships as the browser, giving deepest control
but requiring users to switch browsers. Nobody has cracked "agent in YOUR
browser" without either an extension (Anthropic, OpenAI) or replacing the
browser (Perplexity, Atlas).

## 4. browser-use (what our cloud engine runs)

Open-source Python. Playwright launches/attaches to Chromium; each step it
extracts a compact DOM representation (interactive elements indexed and
labeled), optionally a screenshot, and feeds them to the LLM, which returns
the next action (`click element 12`, `type ...`, `scroll`, `done`). Loop
repeats to `max_steps`. Model-agnostic (we point it at OpenRouter/DeepSeek).
Their hosted cloud adds stealth browsers, proxies, CAPTCHA handling — we
self-host the library instead (free, and we keep the no-CAPTCHA-bypass rule).

---

# How Anticipy adapts each mechanism

| Mechanism (theirs) | Anticipy adaptation |
|---|---|
| Extension + `debugger` API for trusted input (Claude, Codex) | Upgrade our MV3 extension from `scripting`-only templates to the `debugger`-driven act loop — same permission set (debugger, tabs, tabGroups, scripting, alarms, notifications) |
| Color-coded background tab group | Anticipy opens all its tabs `active:false` inside an "Anticipy" tab group — it works silently while you browse |
| LLM step loop with compact DOM (browser-use) | Reuse browser-use's proven representation: index interactive elements, send to DeepSeek via OpenRouter, execute returned action — but inside the extension via debugger commands |
| Per-site permission + confirm-before-consequential | Already designed in: jobs stop at `awaiting_confirm`; add per-site grant list stored in extension storage |
| Pause at login/CAPTCHA, never bypass | Already our hard rule; extension notifies the phone: "need you at this page" |
| Cloud VM browser for off-machine work (ChatGPT Agent) | Our browser-use + Playwright worker on the backend — already live and proven |
| Prompt-injection defense | Two layers: page text is treated as data (never merged into the system prompt), and irreversible actions are gated by the job queue *outside* the model — an injected page can't skip the SMS/app confirm |
| Scheduled tasks (`alarms`) | Same API — recurring Anticipy jobs (daily check portals, weekly reports) |
| Workflow recording | Phase 2: record user's clicks via debugger events, store as replayable recipe — big cost saver (no LLM for known flows) |
| Model routing (cheap→heavy) | Triage on cheap DeepSeek; escalate multi-step browsing to a stronger model only when the cheap one stalls; cache page-structure summaries per site |
| Search API instead of browsing for research | Research goals route to a web-search API (fast, cheap); the browser is reserved for *actions* (fill, book, send) |

**Where Anticipy is different from all of them:** their trigger is you typing
into a panel. Ours is your *life* — the pendant hears a commitment, the brain
triages it, and the job arrives in your Chrome already scoped and gated. Same
hands, different nervous system.
