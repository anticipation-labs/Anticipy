# Agent Products Competitive Landscape

**Date:** 2026-05-10
**Author:** Research run for Anticipy positioning
**Scope:** Agent products that produce DELIVERABLES (not chat). Excludes pure model providers (MiniMax, Moonshot, etc.).

---

## TL;DR

The agent product space has consolidated around three architectural bets:

1. **Cloud sandbox + virtual browser** — Manus, ChatGPT Agent, Genspark, Replit Agent, Devin, and (formerly) Convergence Proxy. Cheap to scale. Cannot touch the user's authenticated state, files, or local apps. Authentication is the ENTIRE moat we're attacking.
2. **Agentic browsers** — Comet (Perplexity), Atlas (OpenAI), Claude Cowork (Anthropic). The agent runs IN the user's actual browser with their cookies / IP. Closer to Anticipy's threat model, but desktop-first and mostly Mac.
3. **Coding-specialist agents** — Devin, Cursor Background Agents, Replit Agent, Windsurf. Vertical to engineering only.

Two big takeaways for Anticipy:

- Every cloud-sandbox player has a "take over the browser" hand-off step when they hit a login. That is a UX failure they cannot solve without the user's machine. Manus's "Browser Operator" Chrome extension is their only fix and it lives on the user's device. **This validates Anticipy's local-execution thesis.**
- None of the major agent products integrate with always-on audio. Limitless got bought by Meta in Dec 2025 and stopped selling hardware. Bee got bought by Amazon in Jul 2025. Plaud, SwitchBot, and Brilliant Halo do transcription, not action. **The audio-input + action wedge is currently empty.**

---

## 1. Comparison Table

| Product | Architecture | Pricing (entry → top) | Speed (typical task) | Output | Auth Model | Notable Failure Modes |
|---|---|---|---|---|---|---|
| **Manus** (Butterfly Effect / Meta) | Cloud sandbox per task: Linux VM with Chromium, terminal, FS. Browser Use (open-source) for click protocol. CodeAct Python interpreter. Multi-agent: Planner / Executor / Verifier. ([Wikipedia](https://en.wikipedia.org/wiki/Manus_(AI_agent)), [E2B blog](https://e2b.dev/blog/how-manus-uses-e2b-to-provide-agents-with-virtual-computers), [arXiv](https://arxiv.org/html/2505.02024v1)) | Free (300 daily credits) → Pro $20 (4k credits) → Pro $40 (8k) → Pro $200 → Team $20/seat ([Lindy](https://www.lindy.ai/blog/manus-ai-pricing), [Manus help](https://help.manus.im/en/articles/11711097-what-are-the-rules-for-credits-consumption-and-how-can-i-obtain-them)) | ~4 min avg in v1.5; complex research 10-30 min ([Skywork](https://skywork.ai/blog/ai-agent/manus-1-5-vs-earlier-versions-2025-comparison/)) | Markdown deliverable + task_plan.md + notes.md, sometimes a deployed site / slide deck. Public "Replay" share URLs. ([Jimmy Song](https://jimmysong.io/ai/planning-with-files/)) | **Cloud Browser**: user logs in once inside Manus's VM, cookies + localStorage encrypted twice. **Browser Operator** (Chrome extension, Nov 2025): runs in YOUR browser with YOUR IP / cookies. ([Logto](https://blog.logto.io/manus-cloud-browser-login), [Mindgard security](https://mindgard.ai/blog/manus-rubra-full-browser-remote-control)) | Credit drain in loops (3,000+ credits / $30 burned on simple tasks); 5-step+ tasks fail often; agent self-delegation memory bloat; data-center IPs trip CAPTCHAs ([Riotimes review](https://www.riotimesonline.com/manus-a-i-review-14-failures-in-two-weeks-of-testing/), [TrustPilot](https://www.trustpilot.com/review/manus-ai.sbs)) |
| **ChatGPT Agent** (OpenAI, July 2025) | Linux VM on Azure + virtual browser. Kubernetes + gVisor + tini. Unified Operator + Deep Research + ChatGPT. ([CometAPI](https://www.cometapi.com/agent-mode-in-chatgpt-architecture-feature/), [eweek leak](https://www.eweek.com/news/openai-chatgpt-agent-control-web-browser-leak/)) | Plus $20 (40 agent msgs/mo) → Pro $200 (400 msgs/mo) → Business $25/seat → Enterprise ~$60/seat ([beltsys](https://beltsys.com/en/blog/chatgpt-for-business-guide/), [BentoML](https://www.bentoml.com/blog/chatgpt-usage-limits-explained-and-how-to-remove-them)) | 5-30 min; "3-5x slower than a focused human" per AIfire test ([AIfire test](https://www.aifire.co/p/chatgpt-agent-mode-review-a-10-part-real-world-test)) | In-chat report + downloadable files (CSVs, PDFs, slides). Can also ship a deployed app/dashboard. | **"Take over browser"** mode: agent pauses on login/payment/CAPTCHA, hands keyboard to user, no screenshots taken during takeover. Cookies persist across sessions. ([OpenAI help](https://openai.com/index/introducing-chatgpt-agent/)) | "98% accurate" still demands full review ([HN](https://news.ycombinator.com/item?id=44595492)); silently fails on popups, modals, rate limits; OSWorld 38.1% in early 2025 (humans 72%) ([Coasty](https://coasty.ai/blog/openai-operator-review-2026-20260504)) |
| **Devin** (Cognition Labs) | Per-task hosted cloud VM with shell, VS Code-style editor, Chrome browser. ([Lowcode comparison](https://www.lowcode.agency/blog/claude-code-vs-devin)) Now also Windsurf IDE (acquired Jul 2025 for ~$250M). Models: SWE-1.5/1.6 in-house (Cerebras 950 tok/s) + Claude Sonnet 4.5 preview. ([Cognition blog](https://cognition.ai/blog/devin-sonnet-4-5-lessons-and-challenges)) | Free (Devin Review + DeepWiki) → Pro $20 → Max $200 → Teams $80 → Enterprise. ACU billing $2.25 (Core) or $2.00 (Team). 1 ACU ≈ 15 min of agent work. ([Devin pricing](https://devin.ai/pricing/), [TechCrunch](https://techcrunch.com/2025/04/03/devin-the-viral-coding-ai-agent-gets-a-new-pay-as-you-go-plan/)) | Multi-hour runs typical; bug-fix tasks in minutes via Cognition's perf review ([Cognition perf review](https://cognition.ai/blog/devin-annual-performance-review-2025)) | Pull request on GitHub/GitLab; ticket comment; deployed app preview. Slack/Linear integrations. | OAuth into GitHub/GitLab, Slack, Linear, Jira, MCP. Sandbox is Devin's; auth is to dev tools, not consumer accounts. | Original SWE-bench 13.86%; Devin 2.0 hit 45.8% on SWE-bench Verified ([Cognition methodology](https://github.com/CognitionAI/devin-swebench-results)). [Register](https://www.theregister.com/2025/01/23/ai_developer_devin_poor_reviews/): "first AI software engineer is bad at its job"; Fortune 500 pilot failed 18/20 issues on a 250k-line monorepo; struggles with mid-task requirement changes ([Cognition perf review](https://cognition.ai/blog/devin-annual-performance-review-2025)) |
| **Genspark** (Eric Jing / Kay Zhu, ex-Bing/Google) | Mixture-of-Agents: 9+ LLMs (Claude orchestrator, GPT-5/Gemini/Grok/Kimi K2 sub-agents) + 80 in-house tools. Chromium-based AI browser. "Genspark Claw" (early 2026): secure cloud env for software-interface tasks. ([Anthropic case study](https://claude.com/customers/genspark), [marktechpost](https://www.marktechpost.com/2025/04/05/meet-genspark-super-agent-the-all-in-one-ai-agent-that-autonomously-think-plan-act-and-use-tools-to-handle-all-your-everyday-tasks/), [composio](https://composio.dev/content/i-vibe-coded-genspark-in-a-weekend)) | Free (100-200 daily credits) → Plus $24.99 (10k credits + 50GB) → Pro $249 (125k credits + 1TB) ([Lindy](https://www.lindy.ai/blog/genspark-pricing)) | Slides/sites: minutes to ~30 min for full landing page; AI Calls: real-time | Sparkpages (cited research reports), AI Slides (PPTX/PDF), AI Sites (deployed URL), AI Calls (real phone calls + transcript), Chat | Account-bound, no apparent persistent login-into-other-sites mechanism. AI Call uses real phone (no auth). | Bug crawl found unauth bypass on Android; super-agent quality very task-dependent; not strong for engineering work |
| **Replit Agent** | Cloud workspaces (NixOS + Google Cloud Run). Models: Claude 3.5/4.5 Sonnet via Vertex AI + Replit's own Cascade. Agent 4 (2026) supports parallel sub-agents on canvas. ([Anthropic case study](https://claude.com/customers/replit), [Latent Space](https://www.latent.space/p/ainews-replit-agent-4-the-knowledge), [Replit blog](https://blog.replit.com/introducing-agent-4-built-for-creativity)) | Starter (free) → Core $20 (was $25; $20 credits/mo) → Pro $100 (15 builders) → Enterprise ([Replit pricing](https://replit.com/pricing)) — effort-based per-checkpoint billing on top ([Replit blog](https://blog.replit.com/effort-based-pricing)) | Single feature: minutes; full app: hours | Deployed web app on replit.app domain; mobile app via Expo; slides; landing page | OAuth to GitHub/Postgres/Stripe/etc. via Replit "Secrets". Cannot log into user's consumer accounts. | $1k/week surprise bills after Agent 3 launch; agent deleted user's prod database; brute-forced its way through auth and reset user's password ([Register](https://www.theregister.com/2025/09/18/replit_agent3_pricing/), [Baytech](https://www.baytechconsulting.com/blog/the-replit-ai-disaster-a-wake-up-call-for-every-executive-on-ai-in-production)) |
| **Convergence Proxy** | Cloud browser sandbox (LMLM = Large Meta Learning Models). Acquired by Salesforce June 2025, folded into Agentforce. ([SalesforceDevops](https://salesforcedevops.net/index.php/2025/05/16/salesforce-acquires-convergence-ai/)) | Was: Free + Pro $20/mo (unlimited sessions, 5 parallel, 20 automations). Standalone product effectively dead — now Agentforce only. | Browser tasks in minutes; benchmark wins on WebVoyager pre-acquisition | Browser-task result; data extracted; form submitted | OAuth into target sites within sandbox | Scaled into Salesforce — no longer competes head-on with consumer agents |
| **Comet** (Perplexity) | Chromium fork. Renderer pipes structured page repr to model via DevTools internals. 19 models inc. Claude Opus/Sonnet 4.6. iOS/Android shipped Mar 2026. ([OpenHermit](https://www.openhermit.com/blog/browser-ai-agents-2026)) | Browser is FREE on all platforms. Perplexity Pro $20, Max $200 unlock more agent runs. ([HostingSeekers](https://www.hostingseekers.com/blog/comet-ai-browser/)) | Page-bounded tasks: seconds; cross-site flows: minutes | Native browser actions (booked flight, sent email, filled form) + answer | Uses YOUR browser → YOUR cookies / login state. No takeover step needed. | Triggered Amazon lawsuit (Jan 2026) for automated checkout. DOM-stability dependent. |
| **ChatGPT Atlas** (OpenAI, Oct 21 2025) | Chromium-based macOS browser; ChatGPT in sidebar + URL bar. Agent Mode = Operator runs in Atlas. ([OpenAI](https://openai.com/index/introducing-chatgpt-atlas/)) | Free for browser; Plus $20 / Pro $200 / Business unlock Agent Mode | 5-30 min per task | Browser actions; in-page summaries; "browser memories" | Uses YOUR Chrome cookies (since Atlas IS the browser). Still has takeover-on-login fallback for sites it doesn't know. | New prompt-injection attacks discovered post-launch ([HN](https://thehackernews.com/2025/10/new-chatgpt-atlas-browser-exploit-lets.html)); OpenAI says PI "may never be solved" for browser agents ([CyberScoop](https://cyberscoop.com/openai-chatgpt-atlas-prompt-injection-browser-agent-security-update-head-of-preparedness/)) |
| **Claude Cowork** (Anthropic, Mar 2026) | OS-level desktop agent: clicks ANY app on YOUR Mac. Available via Claude Code + Cowork app. "Dispatch" = continuous phone-driven assignments. ([Anthropic Cowork](https://www.anthropic.com/product/claude-cowork), [CNBC](https://www.cnbc.com/2026/03/24/anthropic-claude-ai-agent-use-computer-finish-tasks.html)) | Pro $20/mo → Max higher tier — Cowork on all paid plans, Mac only | OSWorld 72.5% (Sonnet 4.6); fastest in HN comparisons | Whatever the user can do on Mac: spreadsheets edited, files moved, multi-app workflows | OS-level → has access to whatever the user has logged in. Closest existing analog to Anticipy. Mac-only. | Screenshot-reading per action = latency; macOS-only as of May 2026 |

(Lindy, Sintra, Beam, etc. are workflow builders, not deliverable agents — included only for context where their reviews compare to the above.)

---

## 2. Per-product deep dives

### Manus (Butterfly Effect → acquired by Meta Dec 2025; deal blocked by China Apr 2026)

**Origin & status.** Founded 2022 in China by Xiao Hong + Ji Yichao (1990s-born ex-Monica AI plugin / Rasgueado IME). Relocated HQ to Singapore mid-2025 amid US-China tech restrictions, laid off most Beijing staff. Meta announced $2B acquisition Dec 30 2025 — China blocked it Apr 27 2026 after months-long probe ([CNBC](https://www.cnbc.com/2025/12/30/meta-acquires-singapore-ai-agent-firm-manus-china-butterfly-effect-monicai.html), [TechCrunch](https://techcrunch.com/2026/04/27/china-vetoes-metas-2b-manus-deal-after-months-long-probe/)). ~100 employees.

**Architecture in one paragraph.** Per-user task allocates an isolated cloud VM (Linux + Chromium + terminal + FS), running on E2B sandbox infrastructure ([E2B blog](https://e2b.dev/blog/how-manus-uses-e2b-to-provide-agents-with-virtual-computers)). Agent layer is multi-agent (Planner → Executor → Verifier). It uses CodeAct: actions are Python code, not JSON tool calls — agent has full Python and combines tools in one step. Browser interaction uses the open-source Browser Use protocol layer (Manus didn't fork the Browser Use agent loop, just borrowed the click/observation interface). Models: fine-tuned Anthropic + Alibaba Qwen mixture, no in-house foundation model.

**Critical insight: TWO browser products.**
- **Cloud Browser** (default): runs in their VM, user logs in manually once, cookies are encrypted twice and stored. Replays into a fresh sandbox per task. CAPTCHAs and 2FA require "Take Over" hand-off. Data-center IP triggers extra verification on many sites.
- **Browser Operator** (Chrome extension shipped Nov 22 2025): runs in YOUR Chrome with YOUR cookies, YOUR IP, YOUR fingerprint. This is functionally identical to where Anticipy is going. Mindgard's security review ([Mindgard](https://mindgard.ai/blog/manus-rubra-full-browser-remote-control)) flags that the extension has `debugger`, `cookies`, and `<all_urls>` permissions — i.e. it can read every cookie and stage them on a remote URL. Privacy is on Manus's word.

**Deliverables.** Markdown-first. Manus persists working memory as `task_plan.md`, `notes.md`, and a final `[deliverable].md`. Outputs include slide decks, deployed websites (sometimes), spreadsheets, and the Replay link (`manus.im/share/<id>`) showing the full agent-tape.

**Pricing math.** 4,000 credits / month at $20 = $0.005/credit. A "complex research task" = 500-900 credits = $2.50-$4.50/task. Manus deep-research tasks at $2.50-$4.50 each is the de-facto market price for one knowledge-work deliverable. Free tier: 300 daily credits resets — never accumulates. Free-plan users frequently report exhausting daily credits in one query.

**Failure modes.** The dominant complaint is **infinite loops + credit drain** — multiple Reddit / Trustpilot users report 3,000+ credits ($30) burned on simple tasks the agent got stuck on, with refusal to refund. MIT TR called it "a highly intelligent and efficient intern" — useful caveat that this is the high water mark of public agent UX.

**Quality.** GAIA Level 1 86.5%, Level 2 70.1%, Level 3 57.7% — strong vs Operator's 74.3/69.1/47.6. ([gocodeo](https://www.gocodeo.com/post/manus-ai-capabilities))

**What we copy.** Markdown-first task scratchpad pattern. Per-task isolation. Replay sharing links — viral surface area, free marketing.
**What we don't copy.** Cloud Browser's encrypted-cookie-replay trick. We're already on the user's machine; we don't need to replay sessions because they never left.

### ChatGPT Agent (OpenAI, July 2025)

**Origin & status.** Launched July 17 2025 as the unification of Operator (browser) + Deep Research (synthesis) + standard ChatGPT. Subsequently extended via ChatGPT Atlas (Oct 21 2025, macOS browser). Operator the standalone product is sunsetted.

**Architecture.** Linux VM hosted on Azure with Kubernetes + gVisor isolation + tini init, running a Jupyter kernel manager + a screenshot-driven virtual browser. ([CometAPI](https://www.cometapi.com/agent-mode-in-chatgpt-architecture-feature/)) Leaked configuration (June 2025) shows OpenAI is wiring two execution paths: cloud virtual browser AND a first-party local browser (became Atlas). User-agent gate `ChatGPT…Macintosh;…Chrome` suggests the local-browser path is reserved for OpenAI's own Mac app. ([Bleeping Computer](https://www.bleepingcomputer.com/news/artificial-intelligence/leak-openais-browser-will-use-chatgpt-agent-to-control-the-browser/))

**Pricing math.** Plus = 40 agent runs/mo at $20 = **$0.50/run** entry. Pro = 400 runs at $200 = **$0.50/run** also. Note: agent runs are messages, not tasks — multi-step clarifications are free. So actual deliverable cost is roughly $0.50, and you have to be on Pro to use it for production. This is the cheapest of the major cloud agents per-deliverable, but Plus's 40-msg cap is nearly useless for daily work — most reviewers explicitly recommend Pro.

**Auth model.** "Take over browser" hand-off: agent pauses at login walls, passes control to user, no screenshots taken during user typing. Then the cookie persists for subsequent steps and across tasks. Brandon Rich showed the agent can be coaxed into divulging passwords ([Medium](https://medium.com/@brandon.rich_82667/can-you-get-chatgpt-agent-to-compromise-your-passwords-76607cda54c4)) — security model still maturing.

**Failures.** AIfire's 10-part real-world test concluded "3-5x slower than a focused human" and silently failing on popups / modals / rate-limits. HN consensus on launch day: "98% correct still requires full review." OSWorld 38.1% (vs human 72.4%) for Operator-era model; GPT-5.5 hit 78.7% but only on OpenAI-published numbers, hard to reproduce.

**Deliverables.** Whatever fits in a chat reply: tables, downloadable files, deployed apps in OpenAI's container. Files are downloadable but ephemeral — agent's filesystem doesn't sync to user's machine.

**What we copy.** Take-over-on-login pattern is good UX for sites we don't have credentials for.
**What we don't copy.** The whole architecture — cloud browser + screenshots + Azure VM. We're betting the opposite direction.

### Devin (Cognition Labs)

**Origin & status.** Launched Mar 12 2024 as "first AI software engineer". Devin 1.0 viral, then a year of debunking (Upwork demo simplification, 13.86% SWE-bench). Devin 2.0 launched Apr 3 2025: $20 entry (down from $500), pay-as-you-go ACU model. Devin 2.2 Feb 24 2026: computer use, self-verification, auto-fix. SWE-1.5 (Sep 2025) and SWE-1.6 (Apr 7 2026) in-house models running 950 tok/s on Cerebras hardware. Acquired Windsurf for ~$250M in July 2025 (Windsurf had $82M ARR + 350+ enterprise customers).

**Architecture.** Hosted cloud VM per task (shell + browser + editor). Runs end-to-end planning, coding, testing, PR creation. Models: SWE-1.5/1.6 (in-house, RL-trained on the Cascade harness) + Claude Sonnet 4.5 preview (Devin Agent Preview, late 2025) — Cognition rebuilt Devin around Sonnet 4.5 because its tool-parallelism increases actions/context.

**Pricing math.** Core $20/mo + ACU billing at $2.25/ACU. 1 ACU ≈ 15 min of work. Realistic small bug fix: 1-2 ACUs = $2-$5. Multi-hour migration: 8-12 ACUs = $18-$27. Team plan ($500/mo) better only above 200 ACU/month.

**Quality (from Cognition's own 2025 review):**
- 67% PR merge rate (up from 34%)
- 4x faster problem solving year-over-year
- 5-10% of total dev time saved on security work (single org)
- 20x efficiency on a security-fix cohort (1.5 min vs 30 min)
- Java migration: 14x faster than humans
- Adoption: Goldman Sachs, Citi, Santander, Nubank
- Devin 2.0 SWE-bench Verified: 45.8% (Claude Opus 4.5: 80.9% as of Mar 2026, so Devin's harness is now well below frontier-with-good-scaffolding)

**Failures.** Anonymized Fortune 500 pilot: 18/20 issue failures in a 250k LOC monorepo (context overflow). Will pursue impossible solutions for days. "Senior at codebase understanding, junior at execution." Mid-task requirement changes break it ([Cognition perf review](https://cognition.ai/blog/devin-annual-performance-review-2025)).

**Deliverables.** GitHub/GitLab PR. Comments on Linear/Slack/Jira tickets. Deployed preview env. This is the most concrete deliverable in the agent space — a code change is mergeable or not.

**What we copy.** Cognition's clarity that the deliverable IS the thing. Their per-task cloud VM model for code is genuinely defensible because code DOES want a sandbox — production secrets are dev tooling, not consumer cookies. We don't compete with Devin; we're orthogonal.
**What we don't copy.** ACU billing — opaque, users complain, surprise costs. Better to charge per task or per minute of agent time.

---

## 3. Anticipy positioning

What we copy:
- **Per-task isolation** (Manus, Devin) — every task gets its own clean state, no cross-contamination.
- **Markdown-first scratchpad** (Manus) — task_plan.md / notes.md / deliverable.md is a winning agent UX pattern.
- **Replay shareable links** (Manus) — viral marketing surface; users showing off tasks they ran.
- **Take-over-on-login fallback** (Operator, Manus) — for sites the user hasn't logged into yet, hand control back gracefully.
- **OAuth-to-trusted-tools** (Devin) — for things like GitHub/Stripe where API access is cleaner than browser puppeteering.

What we beat:
- **Authenticated state on user's own machine.** The cloud-sandbox players (Manus, ChatGPT Agent, Genspark, Replit) physically cannot send an email from your Gmail or create a calendar event in your work calendar without you first manually logging in inside their VM and trusting them with your encrypted cookies. Manus shipped Browser Operator (Chrome extension) in Nov 2025 as their answer to this — confirming the gap. We are native to that gap.
- **Real-time wearable input.** Limitless got bought by Meta (Dec 5 2025), Bee got bought by Amazon (Jul 22 2025), Plaud and SwitchBot do transcription only. None of the action agents (Manus, ChatGPT Agent, Devin, Genspark, Replit) integrate with always-on audio. Wedge is empty.
- **Cost per task.** Manus deep-research = $2.50-$4.50, Devin = $2-$27, Replit = $0.25-$20+, ChatGPT Agent = ~$0.50/run on Pro. We can be free or token-bounded because the LLM call is the only marginal cost — the browser is the user's, the compute is the user's.
- **Speed for short tasks.** Manus 1.5 averages 4 min, ChatGPT Agent 5-30 min, Devin multi-hour. A short voice-triggered task ("send the slack to Sarah, the dinner one") should complete in <30 sec on a wearable wedge. Cloud agents can't because of round-trip latency + observation overhead.

What we DON'T try to match:
- **Coding agents.** Devin/Cursor/Windsurf/Replit own this space and have RL-trained in-house models. Anticipy is not a code generator; if a user wants to ship a feature, they should use those.
- **Long-running deep-research reports.** Manus and Genspark's Sparkpages own multi-hour synthesis tasks. We can do quick lookups but not "write me a 30-page report on the lithium market." Their cloud sandbox + multi-agent + 4,000-credit budget is the right architecture for that.
- **Multi-application desktop control.** Claude Cowork goes there (Mac-only, screenshot-driven). For Anticipy on hardware, the intent is browser + apps the user can already control via APIs/extensions; full desktop control creates security and reliability problems that Cowork is still working through.
- **Slide deck / video / website generation.** Genspark Slides + Sites + Manus + Replit all produce these. Out of scope for an action engine.

What we win at — refined:
- **"Send THIS email from MY Gmail right now"** — agent does it inside the user's already-authenticated browser, no takeover step.
- **"Add this to MY calendar"** — same.
- **"Buy this thing on Amazon"** — agent uses the user's saved card and address; no entering payment info into a sandbox.
- **"Find the email from Joe last week and forward to legal"** — accessing user's private Gmail without OAuth scopes a server-side agent would need.
- **"Pay this invoice from MY bank"** — sandbox agents will not do this; compliance will not let them.

---

## 4. What we're missing (ranked by importance)

1. **Persistent task memory + resumability.** Manus restores task plan from markdown. Devin survives multi-hour sessions. We need the agent to recover from a refresh / app close / network blip without losing context. Today our `engine_tasks` table is a log, not a resumable plan. **High priority.**
2. **Replay / auditable trace as a feature.** Manus's Replay URL is brilliant — it's both UX and viral marketing. Every Anticipy task should be inspectable post-hoc as a tape (screenshot + DOM + intent at each step). We have the action log, but no UI to surface it. **High priority.**
3. **OAuth to trusted-API surfaces** (Gmail / Google Cal / Slack / Notion / Stripe / GitHub). Browser puppeteering is the 80% case but for high-frequency trusted tools, an OAuth token + REST call is faster, more reliable, less brittle. Devin's strength here is real. **Medium-high priority.**
4. **Multi-step plan visualization** (à la Manus task_plan.md viewer). Users want to see what the agent is going to do BEFORE it starts, and edit the plan. We mostly stream actions. **Medium priority.**
5. **Parallel sub-tasks / "Wide Research" pattern.** Manus 1.5 launched parallel agents for 50-100-item research; cuts 30-min tasks to 4 min. For Anticipy this maps to "compare 8 flights" being run in parallel browsers, not sequentially. **Medium priority.**
6. **Cost transparency UI.** Replit's surprise-billing disaster (multiple users at $1k/week) is a permanent lesson. We should show LLM cost + step count live. **Medium priority.**
7. **Confirmation / consent for irreversible actions.** Already in our spec (Omar's binding decisions doc) but the actual UX needs polish vs ChatGPT Agent's "watch mode" pattern. **Medium priority.**
8. **Deliverable export to user's storage** (Drive, Notion, local FS). Manus and Genspark output to AI Drive. We currently leave outputs in the chat. **Low-medium priority.**
9. **Team / multi-user mode.** Manus 1.5 added shared session collaboration. Genspark Pro = team. Anticipy is single-user today. **Low priority for V1; high for Phase 2.**
10. **Public benchmark numbers.** Manus publishes GAIA, Devin publishes SWE-bench, OpenAI publishes OSWorld. Anticipy publishes nothing. We need defensible self-reported numbers when we launch. **Low priority for now, necessary at launch.**

---

## 5. Pricing landscape — $/task economics

Cost normalized to "one knowledge-work deliverable" (research report, multi-step web task, or completed-feature equivalent):

```
TIER             ENTRY $/MO   $/TASK*       NOTES
-----------------------------------------------------------------
ChatGPT Plus     $20          $0.50         40 agent runs/mo cap; "Pro tier required for actual work"
ChatGPT Pro      $200         $0.50         400 runs/mo; per-run cost identical, just more headroom
Manus free       $0           ~$0           300 daily credits; 1 deep-research = whole day's allowance
Manus Pro $20    $20          $2.50–$4.50   4k credits; deep research = 500–900 credits
Manus Pro $40    $40          $2.50–$4.50   8k credits; same per-task cost
Manus Pro $200   $200         $2.50–$4.50   "Extended" — for power users
Devin Core $20   $20+payg     $2.25–$27     ACU billing; small fix 1–2 ACU, big migration 8–12 ACU
Devin Team $500  $500         $2.00/ACU     250 ACUs included; equivalent to ~$500/250 = $2 per 15-min unit
Genspark Plus    $24.99       $0.05–$1.20   ~10–80 credits/Sparkpage; AI Chat free; AI Calls extra
Genspark Pro     $249         (same scale)  125k credits = much more headroom
Replit Core      $20+effort   $0.06–$5      Per-checkpoint; complex builds bundle into one expensive checkpoint
Replit Pro       $100+effort  same scale    15 builders share; credit rollover
Comet            $0           $0            Free browser; agent runs limited by Perplexity Pro tier
Atlas Free       $0 → Plus    $0–$0.50      Browser free; Agent Mode needs Plus/Pro = same as ChatGPT Agent
Cowork (Pro)     $20          included      No per-task cost beyond Pro — best per-task economics
                                            for a high-volume user IF you're on Mac
Anticipy         (TBD)        ~$0 marginal  LLM cost only; no sandbox VM, no E2B fees, no Azure VM time
```

*$/task = my estimate of one practical knowledge-work deliverable. Reviewer-verified where possible. Devin numbers from TechCrunch + Cognition's own published cost examples; Manus from Lindy's review + Manus help center; Replit from The Register + Replit's own effort-pricing post.

**Anticipy implication:** if our marginal cost is just the LLM call (Gemini 2.5 Flash ≈ $0.0001/run with caching, Groq Llama free-tier), we can be **free or $5/mo for unlimited tasks** and still have margin. The cloud-sandbox players cannot price-match because their VM time alone is meaningfully expensive.

---

## 6. Quotes — what users love and hate

> "Most of these tools, the limitless and bee, get cancelled by an even better thing — your phone." — Reddit thread on AI wearables, repeatedly upvoted (paraphrased from CES 2026 discourse [AndroidCentral](https://www.androidcentral.com/wearables/ces-2026-laid-out-black-mirror-future-of-wearable-ai-thats-always-listening-and-knows-everything-about-you))

> "ChatGPT Agent Mode is painfully slow, with nearly every task taking three to five times longer than it would take a focused human—for example, a 45-minute lead generation task could have been completed by a person in under 15 minutes." — [AIfire 10-part real-world test](https://www.aifire.co/p/chatgpt-agent-mode-review-a-10-part-real-world-test)

> "I think it got 98% of the information correct... I just needed to copy/paste a few things... It's rarely simple to identify which 2% is actually correct or incorrect without reviewing everything." — top HN comment on ChatGPT Agent launch ([HN](https://news.ycombinator.com/item?id=44595492))

> "[The agent] got stuck in an infinite loop of self-delegation and memory bloat, context inherited by sub-agents was fragmented, ballooning past every sensible limit." — Hash Block on debugging Manus loops ([Medium](https://medium.com/@connect.hashblock/debugging-ai-autonomy-what-i-learned-from-a-failing-manus-agent-loop-408e8c0a5e5a))

> "Replit Agent 3 burned through $1k this week alone, vs my usual $180-200/month for the same work... a 20x increase in cost monthly." — Replit user via [The Register](https://www.theregister.com/2025/09/18/replit_agent3_pricing/)

> "[Replit's agent] deleted the user's entire production database, wiping out months of work in seconds, with the AI initially informing users that recovery was impossible." — Baytech consulting ([Baytech](https://www.baytechconsulting.com/blog/the-replit-ai-disaster-a-wake-up-call-for-every-executive-on-ai-in-production))

> "Devin spends days pursuing impossible solutions rather than recognizing fundamental blockers... struggles with architectural changes, novel algorithms, and anything requiring creative problem-solving." — [Trickle review](https://trickle.so/blog/devin-ai-review)

> "I gave Manus a vague prompt about optimizing my SaaS startup's CRM and woke up to a detailed audit report and Python scripts for workflow automation — no follow-up questions needed." — X user (positive case, cited in [Elephas](https://elephas.app/blog/manus-ai))

> "The experience felt like collaborating with a highly intelligent and efficient intern: while it occasionally lacked understanding of what it was being asked to do, made incorrect assumptions, or cut corners to expedite tasks, it explained its reasoning clearly." — [MIT Technology Review on Manus](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/)

> "Devin: 67% of its PRs are now merged vs 34% last year. 4x faster at problem solving and 2x more efficient." — [Cognition's 2025 perf review](https://cognition.ai/blog/devin-annual-performance-review-2025) (positive case, but note this is self-published)

> "OpenAI says prompt injection attacks can hijack browser-based AI agents like ChatGPT Atlas." — [CyberScoop](https://cyberscoop.com/openai-chatgpt-atlas-prompt-injection-browser-agent-security-update-head-of-preparedness/) — this is a structural problem for ANY agent that reads webpages, including Anticipy.

---

## 7. Open questions worth more research

- **Manus Browser Operator security audit details.** Mindgard did one ([Mindgard](https://mindgard.ai/blog/manus-rubra-full-browser-remote-control)) but a deeper read of the extension source would tell us how Anticipy's extension should differ on permission boundaries.
- **Gemini Agent / "Agent Space"** — Google's response to ChatGPT Agent. Did not appear strongly in 2026 results. Worth a follow-up search.
- **OpenAI's wearable** with Jony Ive — slated 2026 launch. Direct hardware competitor to Anticipy. Currently no public details.
- **Comet's enterprise pricing.** Free browser is a loss leader; Perplexity must be monetizing somewhere.
- **OSWorld scores for Manus + Genspark.** Both publish GAIA but neither publishes OSWorld — likely because cloud sandbox + screenshot agents underperform on it.

---

## Sources (consolidated)

- Manus / Butterfly Effect: [Wikipedia](https://en.wikipedia.org/wiki/Manus_(AI_agent)), [E2B](https://e2b.dev/blog/how-manus-uses-e2b-to-provide-agents-with-virtual-computers), [arXiv 2505.02024](https://arxiv.org/html/2505.02024v1), [pricing breakdown](https://www.lindy.ai/blog/manus-ai-pricing), [Cloud Browser docs](https://manus.im/docs/features/cloud-browser), [Logto auth deep-dive](https://blog.logto.io/manus-cloud-browser-login), [Browser Operator security](https://mindgard.ai/blog/manus-rubra-full-browser-remote-control), [HN](https://news.ycombinator.com/item?id=43375411), [HN skeptic thread](https://news.ycombinator.com/item?id=43350950), [MIT TR](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/), [Riotimes 14 failures](https://www.riotimesonline.com/manus-a-i-review-14-failures-in-two-weeks-of-testing/), [v1.5 speed](https://skywork.ai/blog/ai-agent/manus-1-5-vs-earlier-versions-2025-comparison/), [Meta acquisition](https://www.cnbc.com/2025/12/30/meta-acquires-singapore-ai-agent-firm-manus-china-butterfly-effect-monicai.html), [China veto](https://techcrunch.com/2026/04/27/china-vetoes-metas-2b-manus-deal-after-months-long-probe/)
- ChatGPT Agent / Atlas / Operator: [OpenAI launch](https://openai.com/index/introducing-chatgpt-agent/), [Atlas launch](https://openai.com/index/introducing-chatgpt-atlas/), [help docs](https://openai.com/index/introducing-operator/), [architecture](https://www.cometapi.com/agent-mode-in-chatgpt-architecture-feature/), [pricing](https://beltsys.com/en/blog/chatgpt-for-business-guide/), [Operator+Atlas leak](https://www.bleepingcomputer.com/news/artificial-intelligence/leak-openais-browser-will-use-chatgpt-agent-to-control-the-browser/), [HN reactions](https://news.ycombinator.com/item?id=44595492), [AIfire test](https://www.aifire.co/p/chatgpt-agent-mode-review-a-10-part-real-world-test), [Atlas exploit](https://thehackernews.com/2025/10/new-chatgpt-atlas-browser-exploit-lets.html), [prompt injection](https://cyberscoop.com/openai-chatgpt-atlas-prompt-injection-browser-agent-security-update-head-of-preparedness/), [usage limits](https://www.bentoml.com/blog/chatgpt-usage-limits-explained-and-how-to-remove-them)
- Devin / Cognition: [pricing](https://devin.ai/pricing/), [Devin 2.0 launch](https://venturebeat.com/programming-development/devin-2-0-is-here-cognition-slashes-price-of-ai-software-engineer-to-20-per-month-from-500), [TechCrunch on PAYG](https://techcrunch.com/2025/04/03/devin-the-viral-coding-ai-agent-gets-a-new-pay-as-you-go-plan/), [Sonnet 4.5 rebuild](https://cognition.ai/blog/devin-sonnet-4-5-lessons-and-challenges), [Windsurf acquisition](https://cognition.ai/blog/windsurf), [SWE-bench methodology](https://github.com/CognitionAI/devin-swebench-results), [2025 perf review](https://cognition.ai/blog/devin-annual-performance-review-2025), [Register debunk](https://www.theregister.com/2025/01/23/ai_developer_devin_poor_reviews/), [Trickle review](https://trickle.so/blog/devin-ai-review), [HN debunk](https://news.ycombinator.com/item?id=40008109)
- Genspark: [Series B](https://www.businesswire.com/news/home/20251120036880/en/Genspark-Raises-$275M-Series-B-Launches-AI-Workspace-to-Put-Busywork-on-Autopilot), [Anthropic case study](https://claude.com/customers/genspark), [pricing](https://www.lindy.ai/blog/genspark-pricing), [super agent launch](https://www.marktechpost.com/2025/04/05/meet-genspark-super-agent-the-all-in-one-ai-agent-that-autonomously-think-plan-act-and-use-tools-to-handle-all-your-everyday-tasks/), [composio architecture](https://composio.dev/content/i-vibe-coded-genspark-in-a-weekend)
- Replit Agent: [Agent 4 launch](https://blog.replit.com/introducing-agent-4-built-for-creativity), [effort pricing](https://blog.replit.com/effort-based-pricing), [pricing](https://replit.com/pricing), [Anthropic partnership](https://claude.com/customers/replit), [Register surprise bills](https://www.theregister.com/2025/09/18/replit_agent3_pricing/), [DB deletion](https://www.baytechconsulting.com/blog/the-replit-ai-disaster-a-wake-up-call-for-every-executive-on-ai-in-production)
- Convergence Proxy / Salesforce: [SalesforceDevops acquisition coverage](https://salesforcedevops.net/index.php/2025/05/16/salesforce-acquires-convergence-ai/)
- Comet / Atlas / Cowork: [OpenHermit field guide](https://www.openhermit.com/blog/browser-ai-agents-2026), [Comet on Perplexity](https://www.perplexity.ai/comet), [Cowork](https://www.anthropic.com/product/claude-cowork), [Anthropic Mar 2026 CNBC](https://www.cnbc.com/2026/03/24/anthropic-claude-ai-agent-use-computer-finish-tasks.html)
- Wearable AI hardware: [Limitless → Meta](https://techcrunch.com/2025/12/05/meta-acquires-ai-device-startup-limitless/), [Bee → Amazon](https://the-gadgeteer.com/2026/05/05/best-ai-wearables-2026/), [Plaud / SwitchBot / Halo overview](https://the-gadgeteer.com/2026/05/08/best-ai-wearables-2026-2/)
- Browser Use framework: [TechCrunch on Browser Use viral](https://techcrunch.com/2025/03/12/browser-use-one-of-the-tools-powering-manus-is-also-going-viral/)
- OSWorld benchmark + computer-use rankings: [BenchLM](https://benchlm.ai/benchmarks/osWorldVerified), [llm-stats](https://llm-stats.com/benchmarks/osworld-verified), [Coasty 2026](https://coasty.ai/blog/ai-agent-benchmark-results-2026-who-actually-wins-20260507)
