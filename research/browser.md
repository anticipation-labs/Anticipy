# Anticipy Browser-Layer Research

**Date:** 2026-05-10
**Scope:** Survey browser-agent frameworks, managed-browser services, stealth libraries, CAPTCHA solvers, and architectures for driving the user's own Chrome.
**Source verification:** Every GitHub stat below was queried via `gh api` on 2026-05-10. Every "last commit" date is what GitHub returned that day.

---

## TL;DR

1. **Keep Browser Use as the agent brain. Don't fork.** It already (a) ships an official mode that connects to a running Chrome via `--cdp-url`, (b) added a Chrome profile cloning fix on **2026-05-09** (literally the day before this report), and (c) is the only project on this list with 93k stars + still landing fixes daily. Forking trades velocity we'd never recover.
2. **Replace the brittle "reinstall the extension" pain with a CDP bridge inside an MCP-style Pilot/chrome-cdp-skill pattern.** The user installs *one* thin extension once; that extension uses `chrome.debugger` (no `--remote-debugging-port` at all, so Chrome 136+ profile lockdown doesn't apply) and bridges over WebSocket to our Python engine, which stays running Browser Use. The extension never gets reloaded; the engine on the server can be redeployed freely.
3. **Free CAPTCHA path that works in May 2026:** NopeCHA extension (100/day free, bundled with the user's own Chrome so non-residential rate limits don't trigger) + playwright-recaptcha audio fallback + Gemini 2.5 vision as a last resort. Skip 2captcha/CapSolver until volume justifies it.
4. **Stealth: Chrome 136+ killed naive `--remote-debugging-port` against the user's profile.** This actually *helps* us — it forces everyone toward the extension/`chrome.debugger` path, which is exactly the architecture below.
5. **Don't pay Browserbase/Anchor/Hyperbrowser yet.** Their stealth Chromium fleets are great, but they're cloud-side. Our story is "your own Chrome, your own session, no per-task cost." Phase-2 fallback only.

---

## B.1 — Open-source browser agent frameworks

### Verified data (gh api, 2026-05-10)

| Project | Stars | Forks | License | Last push | Language |
|---|---:|---:|---|---|---|
| browser-use/browser-use | 93,203 | 10,552 | MIT | **2026-05-09** | Python |
| browserbase/stagehand | 22,592 | 1,508 | MIT | **2026-05-09** | TypeScript |
| Skyvern-AI/skyvern | 21,557 | 1,988 | **AGPL-3.0** | **2026-05-10** | Python |
| nanobrowser/nanobrowser | 12,960 | 1,362 | Apache-2.0 | 2025-11-24 | TypeScript (extension) |
| browseros-ai/BrowserOS | 10,853 | 1,087 | **AGPL-3.0** | 2026-05-09 | TypeScript/Go (Chromium fork) |
| lavague-ai/LaVague | 6,338 | 574 | Apache-2.0 | **2025-01-21** (DEAD) | Python |
| EmergenceAI/Agent-E | 1,235 | 187 | MIT | 2026-05-04 | Python |
| web-arena-x/webarena | 1,458 | 236 | Apache-2.0 | 2025-11-26 (research benchmark) | Python |
| MinorJerry/WebVoyager | 1,082 | 119 | Apache-2.0 | **2024-03-04** (paper repo, abandoned) | Python |

### Notes per candidate

**Browser Use** (what we already use). Apache-2.0 license confusion in earlier notes — actually MIT, fork-friendly. Repo pushes daily. The 2026-05-09 commit (`#4810`) added handling for locked Chrome profiles when cloning the user's profile dir into a temp `--user-data-dir`, plus an actionable "close Chrome or connect via `--cdp-url`" error. This means upstream is *actively* solving exactly our use case. Vision: optional (DOM-first with screenshot fallback). Cookies: clones a Chrome profile or attaches via CDP. Anti-bot: relies on Patchright in cloud; vanilla Playwright locally. Their hosted "Browser Use Cloud" is $0.06/browser-hour, $10/GB proxy — irrelevant since we're going local.

**Stagehand v3.** The most credible alternative. v3 dropped Playwright and went CDP-native (44% faster on complex DOM ops per their blog). Four primitives: `act / extract / observe / agent`. TypeScript-first; Python and Go SDKs are alpha. Strong maintainer signal (Browserbase company). Hybrid model where AI generates a selector, then code executes it deterministically and *caches* the mapping — this is the right reliability model. **Why not switch:** TS-first, our engine is Python; we'd lose ~4,200 LOC of working Python and re-pay all the integration cost we already paid Browser Use. Stagehand also assumes you'll use Browserbase for cloud — its local-Chrome story is less developed than browser-use's `--cdp-url`. If we were greenfield in TS, this would be #1.

**Skyvern.** Vision-first, Playwright-based SDK. Active. **AGPL-3.0 is a blocker** — any user-facing service running Skyvern must publish all linked source on demand. We'd have to relicense Anticipy. Hard pass for embedding.

**Nanobrowser.** Pure Chrome extension, no server-side component. Multi-agent, BYO LLM key. Apache-2.0, 13k stars, last commit 2025-11-24 (5+ months stale; still alive but slowing). Architecturally interesting because it's already what we want (extension + agent loop, in user's Chrome, with their session) — but the agent runs *in JS inside the extension*, so we lose our Python toolchain (memory, judges, planner, safety floor) unless we re-implement them in TS. **Use as reference, not as base.**

**BrowserOS.** Full Chromium fork. 11k stars but **AGPL-3.0** and a fork of Chromium itself — months of compile time, distribution headache, monthly Chromium-merge tax. Wrong scope for us. Useful only as a "what does a serious agentic browser look like end-to-end" reference.

**LaVague.** Last commit 2025-01-21. **Effectively abandoned.** Skip.

**Agent-E.** Niche; HTML-distillation approach. 1.2k stars. Worth reading their `dom_distillation` module for ideas on token-efficient observation, but not a base.

**WebVoyager / WebArena.** Research/benchmark code. Not products.

### B.1 verdict — top 3
1. **Browser Use** — the obvious continuation. Already in our stack, actively shipping the exact features we need (`--cdp-url`, profile clone).
2. **Stagehand v3** — best alternative if we ever rewrite in TS.
3. **Nanobrowser** — best reference for "agent-inside-extension" pattern.

---

## B.2 — Browser-as-a-service / managed Chrome

### Pricing matrix (May 2026)

| Service | Free tier | Entry paid | Per-hour | Stealth | Captcha | Cookie passthrough |
|---|---|---|---:|---|---|---|
| **Browserbase** | 1 hr/mo | $20/mo (Developer) | $0.10–0.12 | Basic + Advanced ($) | Auto-included | "Contexts" persist across runs |
| **Hyperbrowser** | $30 free credits | $99/mo Basic | $0.10 | Stealth modes built-in | 1k incl, $0.10/solve over | Yes, sub-500ms relaunch |
| **Anchor Browser** | 5 credits/mo | $50/mo Starter | $0.05 | Captcha @ Starter, full stealth Growth+ | Included Growth+ | SSO/MFA flows supported |
| **Bright Data Scraping Browser** | None | $499/mo entry | ~$7/GB | Built-in unblocking, residential IPs | Included | Yes |
| **Apify** | $5 credits/mo | $29/mo Starter | varies (per actor) | Per actor | Per actor | Per actor |
| **E2B** | $100 one-time credit | $150/mo Pro | ~$0.05/vCPU-hr | Not its focus (general sandbox) | DIY | DIY |
| **Steel.dev** | **100 hr/mo + $10 credits** | $29/mo | $0.05–0.10 | Yes, OSS too (`steel-dev/steel-browser` AGPL fork on GH, 7k stars) | Yes | Yes |
| **Browserless** | 1k units | metered | unit-based | BQL stealth route | Free CAPTCHA | Yes |

### Notes

- **Steel.dev has the most generous free tier** (100 browser-hours/mo). Self-hostable too (Apache-2.0 OSS browser core). If we ever need a server-side fallback browser, this is the cheapest test bench.
- **Browserbase + Stagehand are the same company** — that's the "managed easy mode." Useful to know but locks us in to a TS rewrite.
- **Anchor Browser** is the cheapest per-hour ($0.05) but stealth is gated to Growth ($2000/mo), so the cheap tier is unusable for hostile sites.
- **None of these solve our actual problem** — we want the user's *real* logged-in Chrome, not a managed one. Cookie passthrough is "upload your cookies to our cloud," which we explicitly don't want.

### B.2 verdict — top 3 (only relevant for Phase-2 fallback when user's machine is offline or site is rate-limiting their IP)
1. **Steel.dev** — best free tier, OSS, easy to self-host on the same VPS as our engine.
2. **Browserbase** — best stealth + ecosystem if we ever pay.
3. **Browser Use Cloud** — same vendor as our framework; lowest friction to flip a flag.

---

## B.3 — Stealth / anti-bot

### Verified data (gh api, 2026-05-10)

| Lib | Stars | License | Last push |
|---|---:|---|---|
| Kaliiiiiiiiii-Vinyzu/patchright (NodeJS+core) | 3,152 | Apache-2.0 | **2026-05-10** |
| Kaliiiiiiiiii-Vinyzu/patchright-python | 1,330 | Apache-2.0 | **2026-05-10** |
| ultrafunkamsterdam/nodriver | 4,191 | **AGPL-3.0** | 2026-03-11 |
| ultrafunkamsterdam/undetected-chromedriver | 12,614 | GPL-3.0 | 2025-07-05 (deprecated, see nodriver) |
| rebrowser/rebrowser-patches | 1,348 | none stated | 2025-05-09 |
| playwright-extra/stealth (NodeJS) | — | MIT | **2023-03 last meaningful update** (DEAD) |

### Notes

**Patchright** (current pick). Active *yesterday*. Apache-2.0. Passes Cloudflare, DataDome, Akamai, Kasada, Bet365, F5 detection per the project's own README. Chromium-only. The project explicitly removes flags like `--disable-component-update` that fingerprint as automation. **Recommendation: stay on Patchright.**

**nodriver.** Python successor to undetected-chromedriver, AGPL-3.0. Async, no Selenium. Direct CDP. Strong technically. License is the same trap as Skyvern — embedding into Anticipy means publishing source. Hard pass.

**rebrowser-patches.** Patches Puppeteer/Playwright without a fork — toggleable. Useful as a *complement* to Patchright if we ever need a Node toolchain. No license file, so legally unsafe to embed.

**playwright-extra stealth (Node).** Unmaintained since 2023. Don't even consider.

**The bigger insight:** stealth at the library level only solves fingerprinting. It does *not* solve TLS fingerprints, IP reputation, behavioral analysis, or modern Cloudflare/Turnstile JS challenges. That's why Browserbase/Hyperbrowser charge — their stealth is a moving target maintained as a service. Our advantage when running in the user's *real* Chrome: we don't need stealth at all, because it *is* a real Chrome on a real residential IP doing real human-rate interactions. **The user's-own-Chrome architecture obsoletes most of the stealth stack.**

### B.3 verdict — top 3
1. **Patchright (Python)** — current pick, no reason to move. Use when we run our own Chromium server-side.
2. **rebrowser-patches** — backup/complement.
3. **nodriver** — only as a reference; license blocks productization.

---

## B.4 — CAPTCHA, free path

| Solution | Cost | Coverage | Architecture |
|---|---|---|---|
| **NopeCHA extension** | Free 100/day, $9/mo for more | reCAPTCHA v2/v3, hCaptcha, FunCAPTCHA, Turnstile, Cloudflare, AWS WAF | Chrome extension that auto-solves in-browser |
| **playwright-recaptcha** (Xewdy444) | Free | reCAPTCHA v2 (audio) + v3 (token wait) | Python lib, uses Google speech recognition for audio challenge |
| **Vision LLMs (Gemini 2.5 / Claude 4.5 / GPT-5)** | Per-token | Image puzzles | Feed screenshot to LLM |
| **2captcha** | $1/1000 image | All major | Human-solver API |
| **CapSolver** | $0.80–$3/1000 | All major | AI API |

### Notes

**NopeCHA extension.** Free 100/day with no API key, *only against residential IPs* (datacenter IPs are blocked) — which is exactly our setup since we're running in the user's actual Chrome on their residential connection. License MIT. Last release April 2026. Repo: `NopeCHALLC/nopecha-extension`, 10.3k stars, active. **This is the right primary path for us.**

**playwright-recaptcha** (`Xewdy444`, MIT, 533 stars, last push 2026-04-30). Free audio-challenge solver — works even when NopeCHA quota runs out. Requires FFmpeg. Audio reCAPTCHA still works (Google has not deprecated it).

**Vision-LLM solving.** Reproducible benchmarks (Roundtable Research, 2026): Claude Sonnet 4.5 ~60% on reCAPTCHA v2 image puzzles; Gemini 2.5 Pro ~56%; GPT-5 ~28%. Free with our existing Gemini quota for occasional fallback, but not first-line — too slow and unreliable as steady state.

**Why skip paid services for now.** $0.80/solve at 100 solves/day = $24/mo, fine, but in a user-Chrome architecture we should be hitting CAPTCHAs *very* rarely. If NopeCHA's 100/day plus playwright-recaptcha plus a vision-LLM Hail Mary doesn't cover us, we have an architectural problem (we're failing the residential-IP test) that more paid solving won't fix.

### B.4 verdict — top 3
1. **NopeCHA extension** in the user's own browser — free, fast, residential.
2. **playwright-recaptcha** audio fallback for reCAPTCHA v2.
3. **Gemini 2.5 vision** Hail Mary; reroute to CapSolver/2captcha only at scale.

---

## B.5 — User's-real-Chrome architectures (THE hard one)

### What's actually possible (security model, May 2026)

Three families of patterns exist, each with a sharp trade-off:

#### Pattern A: `--remote-debugging-port` against the user's profile
**Status: BROKEN as of Chrome 136 (March 2025).** Per [Chrome's own blog](https://developer.chrome.com/blog/remote-debugging-port), `--remote-debugging-port` and `--remote-debugging-pipe` are *no longer respected* against the default Chrome user-data-dir on Windows/Linux/macOS. You must point at a non-default `--user-data-dir`, which means a *separate* profile, which means *not the user's logged-in Chrome*. Browser Use even handles this: clone the profile to a temp dir.

**Implication:** Anyone telling you to "just attach to remote-debugging-port" hasn't tested in the last 12 months. This is dead.

#### Pattern B: Profile-clone (Browser Use's current upstream approach)
Copy the user's `~/.config/google-chrome/Default` (cookies, prefs, extensions) into a temp dir, launch a *separate* Chrome instance against that copy with `--remote-debugging-port` + `--user-data-dir=/tmp/anticipy-profile`. This is what `browser-use #4810` (yesterday's commit) hardens. The user's actual Chrome can stay open.

**Pros:** session/cookies preserved; no extension required; doesn't disrupt the user.
**Cons:**
- Cookies copied at launch only; user logs out in real Chrome → temp Chrome still has stale cookies (and vice versa).
- Some sites detect when a "new" device IP+fingerprint+UA combo logs in with a known cookie → forced re-auth or 2FA.
- Visible second Chrome window (or headless, but then user can't see/intervene).

#### Pattern C: Chrome extension + `chrome.debugger` API + WebSocket bridge to our engine
The user installs *one* extension once. The extension declares the `"debugger"` permission. When our engine wants to act, it sends a WebSocket message to the extension (via a relay running on `localhost:NNNN` or a cloud Realtime channel). The extension calls `chrome.debugger.attach(tabId)` and forwards CDP commands.

**This is exactly the [Pilot architecture](https://github.com/TacosyHorchata/Pilot) and [pasky/chrome-cdp-skill](https://github.com/pasky/chrome-cdp-skill) — both 2026 projects.**

**Pros:**
- Uses the user's *real* Chrome, *actual* tab, *actual* session (no profile copy, no cookie staleness).
- One-time install. The extension never has to be reloaded for our engine to ship updates — the engine is on our server, and the extension is just a thin CDP relay.
- Works on Chrome 136+ because `chrome.debugger` is *not* affected by the `--remote-debugging-port` lockdown — it's an in-process API, not a TCP endpoint.
- The user can watch what's happening (it's their tab) and override.
- Per-tab permission prompt is *one-time per tab* (not per command).

**Cons:**
- `chrome.debugger` shows a yellow "An automated test software is debugging this tab" bar across the top — *cannot be hidden, by design*. (This is actually a feature for trust.)
- `chrome.debugger` does not expose every CDP domain (e.g., can't install other extensions, can't drive `chrome://` URLs). Fine for our scope.
- Requires an extension. We have one. Locking down the extension manifest such that the engine can ship code via the WebSocket protocol *without ever updating the extension itself* is the unlock.

#### Pattern D: Native messaging host
Extension talks to a small native binary on the user's machine; native binary talks to our cloud. **Adds an installer.** Adds a per-OS binary to ship. Skip unless we need disk access or audio features the extension can't do.

#### Pattern E: Anthropic Computer Use / OpenAI Operator
A *server-side* VM the AI agent screen-controls. Not the user's Chrome at all. Sessions/cookies have to be re-established. Wrong shape for "operate the user's accounts." Skip.

### Reference implementations to read

- **[pasky/chrome-cdp-skill](https://github.com/pasky/chrome-cdp-skill)** — 3,019 stars, MIT, last push 2026-03-18. Spawns a per-tab "lightweight background daemon that holds the session open." This is the *cleanest* skeleton.
- **[TacosyHorchata/Pilot](https://github.com/TacosyHorchata/Pilot)** — 31 stars, MIT, last push 2026-04-05. Extension + MCP server, `localhost:9800` relay. Smaller but very explicit about the architecture: `AI Agent → MCP Server → WebSocket → Chrome Extension → Tab in your browser`.
- **[hangwin/mcp-chrome](https://github.com/hangwin/mcp-chrome)** — 11,580 stars, MIT, last push 2026-01-06. Production-grade Chrome MCP server with semantic search baked in.
- **[Anthropic Claude for Chrome](https://claude.com/blog/claude-for-chrome)** — closed-source but architecturally identical: extension + permission gates + classifier defenses against prompt injection. Reduced injection success 23.6% → 11.2%.
- **[Vercel agent-browser](https://github.com/vercel-labs/agent-browser)** — 32,510 stars, Apache-2.0. Rust CLI/daemon model. Auto-detects local Chrome. Good ergonomics reference.

### B.5 verdict — top 3 architectures
1. **Extension + `chrome.debugger` + WebSocket bridge to our Python engine (Pattern C).** This is the answer.
2. **Profile-clone via Browser Use `--cdp-url` (Pattern B).** As fallback for users who refuse to install an extension.
3. **Native messaging host (Pattern D).** Only if we ever need filesystem or microphone — which we don't, the wearable handles audio.

---

## SPECIFIC RECOMMENDATION FOR ANTICIPY

Given the constraints (user's-real-Chrome + no reloads + open web + stealth + free CAPTCHA), here is the stack:

### The stack

```
┌─────────────────────────────────────────────────────────────────┐
│ User's macOS / Windows                                          │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ User's ACTUAL Chrome                                    │   │
│   │  ┌──────────────────────────────────────────────────┐   │   │
│   │  │ Anticipy Bridge Extension (installed ONCE)       │   │   │
│   │  │  • chrome.debugger permission                    │   │   │
│   │  │  • WebSocket client to wss://engine.anticipy.ai  │   │   │
│   │  │  • Manifest declares ALLOWED_ORIGINS = {our cloud}│  │   │
│   │  │  • That's IT. ~200 LOC. Never needs to change.   │   │   │
│   │  └──────────────────────────────────────────────────┘   │   │
│   │                                                         │   │
│   │  Real cookies, real session, real fingerprint, real IP  │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Anticipy Wearable                                       │   │
│   │  Audio in → /ws/proactive on engine                     │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ wss://
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Anticipy Engine (our server, deploys freely)                    │
│                                                                 │
│  • Python FastAPI                                               │
│  • Browser Use (current code, MIT)                              │
│      ◦ Configured with custom CDP transport that speaks         │
│        OUR WebSocket protocol instead of localhost:9222.        │
│      ◦ This is ~150 LOC of glue inside browser-use’s            │
│        BrowserSession class — see browser-use’s                 │
│        playwright_browser.py for the seam.                      │
│  • Models pipeline (Gemini → Groq fallback, current)            │
│  • Safety floor / verifier / memory (current)                   │
│  • CAPTCHA helpers:                                             │
│      ◦ NopeCHA extension is ALREADY in the user's Chrome        │
│        (we tell them to install it once alongside our ext)      │
│      ◦ playwright-recaptcha audio solver runs server-side       │
│        when nopechastatus says “quota exceeded”                 │
│      ◦ Gemini vision Hail Mary as third fallback                │
└─────────────────────────────────────────────────────────────────┘
```

### Why this is right

1. **No reloads.** The extension is a dumb pipe. All intelligence is on the engine. We ship engine updates via `vercel deploy`, never touch the extension.
2. **User's real Chrome.** Real cookies, real fingerprint, residential IP, real account. Stealth question evaporates — this *is* a real human's browser.
3. **No screen takeover.** The user keeps using other tabs; we operate in our tab(s) only. The yellow "automated test software" bar is on those tabs, which is honest and trust-building.
4. **Open web.** No per-site code. Browser Use observes/acts via DOM + screenshot like today.
5. **Free CAPTCHA.** NopeCHA at 100/day, free, residential — should cover the vast majority. Audio-recaptcha + vision-LLM fallback are free or marginal.
6. **Cost: $0/task** for the browser layer. Our only spend is LLM inference (Gemini free tier covers a lot), which is the cost we already pay.
7. **Codespace dev path preserved.** Server-side Patchright + Xvfb stays as a dev/test backend — the engine doesn't care whether the CDP target is `chrome.debugger`-via-WebSocket or `localhost:9222`.

### What to build (concrete, in this order)

1. **Engine-side CDP transport (~1 day).** Add `engine/app/bridge_cdp.py`: speaks Browser Use's CDP transport interface, forwards to a per-user WebSocket connection. Browser Use already separates CDP from launch (per yesterday's `--cdp-url` work) — we slot in here.
2. **Bridge extension v1 (~2 days).** Manifest v3, `"debugger"` + `"tabs"` + `"storage"` permissions, ~200 LOC: open WebSocket on user-action, `attach()` on tab, forward CDP messages bidirectionally. Externally_connectable allowlist = `engine.anticipy.ai`. Sign and ship to Chrome Web Store *once*. **Lock the manifest.** Future capability comes from server side.
3. **CAPTCHA pipeline (~1 day).** Tell user to install NopeCHA at signup. Detect quota-exceeded via DOM signal. Fallback to playwright-recaptcha audio (we run that server-side, but the audio reCAPTCHA UI runs in their tab via CDP).
4. **Stop paying attention to stealth.** Remove `Patchright` from production path; keep it for local dev/testing only.
5. **Phase-2: server-side Steel.dev / Browser Use Cloud fallback** when user's machine is offline. Free tiers cover initial usage.

### Don't do

- ❌ **Don't fork Browser Use.** Yesterday's commit shows the upstream maintainer is solving our exact problem. Forking buys nothing and costs us the upgrade path.
- ❌ **Don't switch to Stagehand.** TS rewrite of Python engine = months of regression. Re-evaluate in 6 months.
- ❌ **Don't pay Browserbase yet.** Same reason — fits a different shape (server-side stealth Chromium fleet).
- ❌ **Don't use AGPL projects (Skyvern, nodriver, BrowserOS) anywhere they get linked into the engine.** License poison.
- ❌ **Don't bother with `--remote-debugging-port` against user's profile.** Chrome 136+ killed it.

### Open risks (be honest)

- **Permission UX:** `chrome.debugger` shows a yellow bar. Users may not love it. But (a) Anthropic's Claude for Chrome ships with the same bar and people accept it, (b) it's a trust feature for a wearable that can see your bank.
- **Chrome Web Store review.** The `"debugger"` permission gets extra scrutiny. Expect a 1–2 week first review. Plan for it.
- **Manifest v3 service worker WebSocket eviction.** Service workers die after 30s idle. Mitigation per Chrome 116+: send a no-op every 25s OR keep a long-poll alive from the engine. Both documented patterns; Pilot already does this.
- **Multi-tab orchestration.** `chrome.debugger.attach()` is per-tab. Extension needs a small per-tab session manager. Reference: pasky/chrome-cdp-skill's daemon model handles this exactly.
- **NopeCHA quota.** 100/day is generous but a power user could exhaust it on a bad-luck day. Audio fallback covers reCAPTCHA v2; for hCaptcha quota-out we may eventually need CapSolver at $2/1000.

---

## Sources

### GitHub repos (verified 2026-05-10 via gh api)
- [browser-use/browser-use](https://github.com/browser-use/browser-use) — 93,203★ MIT, last push 2026-05-09 (commit #4810 added Chrome profile copy + `--cdp-url` support)
- [browserbase/stagehand](https://github.com/browserbase/stagehand) — 22,592★ MIT, 2026-05-09
- [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) — 21,557★ AGPL-3.0, 2026-05-10
- [nanobrowser/nanobrowser](https://github.com/nanobrowser/nanobrowser) — 12,960★ Apache-2.0, 2025-11-24
- [browseros-ai/BrowserOS](https://github.com/browseros-ai/BrowserOS) — 10,853★ AGPL-3.0, 2026-05-09
- [lavague-ai/LaVague](https://github.com/lavague-ai/LaVague) — 6,338★ Apache-2.0, **2025-01-21 (DEAD)**
- [EmergenceAI/Agent-E](https://github.com/EmergenceAI/Agent-E) — 1,235★ MIT, 2026-05-04
- [MinorJerry/WebVoyager](https://github.com/MinorJerry/WebVoyager) — 1,082★ Apache-2.0, 2024-03-04
- [web-arena-x/webarena](https://github.com/web-arena-x/webarena) — 1,458★ Apache-2.0, 2025-11-26
- [Kaliiiiiiiiii-Vinyzu/patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) — 3,152★ Apache-2.0, 2026-05-10
- [Kaliiiiiiiiii-Vinyzu/patchright-python](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python) — 1,330★ Apache-2.0, 2026-05-10
- [ultrafunkamsterdam/nodriver](https://github.com/ultrafunkamsterdam/nodriver) — 4,191★ AGPL-3.0, 2026-03-11
- [ultrafunkamsterdam/undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver) — 12,614★ GPL-3.0, 2025-07-05
- [rebrowser/rebrowser-patches](https://github.com/rebrowser/rebrowser-patches) — 1,348★ no license, 2025-05-09
- [NopeCHALLC/nopecha-extension](https://github.com/NopeCHALLC/nopecha-extension) — 10,323★ MIT, 2026-04-20
- [Xewdy444/Playwright-reCAPTCHA](https://github.com/Xewdy444/Playwright-reCAPTCHA) — 533★ MIT, 2026-04-30
- [pasky/chrome-cdp-skill](https://github.com/pasky/chrome-cdp-skill) — 3,019★ MIT, 2026-03-18
- [TacosyHorchata/Pilot](https://github.com/TacosyHorchata/Pilot) — 31★ MIT, 2026-04-05
- [hangwin/mcp-chrome](https://github.com/hangwin/mcp-chrome) — 11,580★ MIT, 2026-01-06
- [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) — 39,050★ Apache-2.0, 2026-05-10
- [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) — 32,302★ Apache-2.0, 2026-05-09
- [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) — 32,510★ Apache-2.0, 2026-05-07
- [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser) — 7,009★ Apache-2.0, 2026-05-03
- [LvcidPsyche/auto-browser](https://github.com/LvcidPsyche/auto-browser) — 442★ MIT, 2026-05-09

### Pricing & docs
- [Browserbase pricing](https://www.browserbase.com/pricing) — Free / $20 / $99 / Custom
- [Anchor Browser pricing](https://docs.anchorbrowser.io/pricing) — Free / $50 / $2000 / Enterprise
- [Hyperbrowser pricing](https://www.hyperbrowser.ai/docs/pricing) — $99 / $299 / Enterprise; $0.10/hr compute
- [Steel.dev pricing](https://docs.steel.dev/overview/pricinglimits) — 100hr/mo free
- [Browser Use Cloud pricing](https://docs.cloud.browser-use.com/guides/proxies-and-stealth) — $0.06/hr
- [E2B pricing](https://e2b.dev/pricing)
- [Browserless pricing](https://www.browserless.io/pricing)

### Chrome platform
- [Changes to remote debugging switches (Chrome 136)](https://developer.chrome.com/blog/remote-debugging-port)
- [chrome.debugger API reference](https://developer.chrome.com/docs/extensions/reference/api/debugger)
- [Chrome Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
- [Use WebSockets in service workers](https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets)
- [Chrome DevTools MCP blog](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session)

### Vendor blogs / comparisons
- [Stagehand v3 launch](https://www.browserbase.com/blog/stagehand-v3)
- [Stagehand vs Browser Use (Scrapfly)](https://scrapfly.io/blog/posts/stagehand-vs-browser-use)
- [Best Cloud Browser APIs 2026 (Scrapfly)](https://scrapfly.io/blog/posts/best-cloud-browser-apis)
- [Anthropic Claude for Chrome](https://claude.com/blog/claude-for-chrome)
- [Open-source web agents 2026 (AIMultiple)](https://aimultiple.com/open-source-web-agents)
- [CAPTCHA benchmarking (Roundtable Research)](https://research.roundtable.ai/captcha-benchmarking/)
