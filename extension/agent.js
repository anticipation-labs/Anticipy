// Anticipy Chrome Extension — Browser Agent (LLM-powered)
// Takes a confirmed intent and executes it step-by-step using LLM decisions + DOM actions
// No localhost server required — runs entirely in the extension using the user's real browser.

// Executor LLM endpoints. Three free tiers + paid fallback:
//   1. Cerebras Qwen3-235B  — 1M tok/day, 30 RPM, ~250ms latency
//   2. Groq llama-3.3-70b   — 14400 RPD, 30 RPM (separate quota pool)
//   3. Gemini 2.5 Flash     — 1500 RPD (when AI Studio cap allows; vision-capable)
//   4. Mistral mistral-small-latest — free La Plateforme tertiary fallback
// Each tier has its own per-minute quota. By rotating across tiers we
// effectively get 90+ RPM combined, vs the 30 RPM of any single tier.
// The agent tries them in order; on 429 of one tier, the next call goes
// to the next tier with quota available.
const CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions";
const CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507";  // text-only, fast
const GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions";
// Llama-4-Scout 17B is Groq's vision-capable model on free tier — used
// for canvas/WebGL/screenshot tasks. Llama-3.3-70B-versatile (text-only)
// handles the rest. We pick by whether the user message references
// vision-required action types.
const GROQ_TEXT_MODEL = "llama-3.3-70b-versatile";
const GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct";
const MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions";

const MAX_STEPS = 60;
const TASK_TIMEOUT_MS = 600_000; // 10 minutes hard limit (multi-step flows)

// Convert a raw agent failure message into something a non-technical
// wearer can read. NO HARDCODED STRING-MATCH RULES — we route the raw
// text through the cheapest available LLM and ask it to rewrite as a
// single calm sentence. If every provider is unavailable we fall back
// to ONE generic line. That's the entire policy.
//
// Two passthroughs we keep:
//   - empty input → generic line (cheap-out)
//   - LLM-authored clarification questions (the REQUIRED-SLOT path) —
//     they end with "?" or start with a wh-word; the wearer needs to
//     SEE the actual question, not a paraphrase. This is grammatical
//     pattern-recognition, not content rule-matching.
async function friendlyAgentMessage(raw, agentInstance) {
  const msg = (raw || "").toString().trim();
  if (!msg) {
    return "I couldn't finish that one. Want to try again?";
  }
  // Preserve LLM-authored questions verbatim (REQUIRED-SLOT path).
  if (msg.endsWith("?") ||
      /^(what|where|when|which|who|how|do|does|did|is|are|can|could|should|would)\b/i.test(msg)) {
    return msg;
  }
  // Try an LLM rewrite via whatever provider has quota.
  if (agentInstance && typeof agentInstance._rewriteForUser === "function") {
    try {
      const rewritten = await agentInstance._rewriteForUser(msg);
      if (rewritten && rewritten.length >= 4 && rewritten.length <= 240) {
        return rewritten;
      }
    } catch (_) { /* fall through to generic fallback */ }
  }
  // Single generic line. NO pattern-match rules.
  return "I couldn't finish that one. Want to try again?";
}

// Escalation heuristics — keep these named/centralised so anyone reading the
// agent can reason about when Pro fires. All thresholds are conservative;
// the goal is "Pro fires on the genuinely hard step", not "Pro on every step".
const ESCALATION = Object.freeze({
  CONSECUTIVE_FAILS: 3,        // 3 fails in a row → next call goes to Pro
  STUCK_STEP_THRESHOLD: 15,    // past step 15 with no `done` → enter stuck mode
  STUCK_PRO_BUDGET: 5,         // burn 5 Pro calls trying to unstick
  RECOVERY_FAILS: 2,           // 2 fails → force getPageState + plan re-eval
  GIVEUP_FAILS: 5,             // 5 fails → graceful done(false), don't hit MAX_STEPS
});

const AGENT_SYSTEM_PROMPT = `You are a browser automation agent built into the Anticipy Chrome extension.
Your job: complete a web task by deciding ONE browser action at a time.

YOU MUST respond with valid JSON only — no markdown, no explanation, just the JSON object.

AVAILABLE ACTIONS:

Navigate to a URL:
{"action":"navigate","url":"https://..."}

Click an element (use the first matching strategy that works):
{"action":"click","selector":"#id or .class or input[name=x]","text":"visible button text (fallback)","aria":"aria-label value (fallback)"}

Type text into an input or textarea:
{"action":"type","selector":"#id or input[name=x]","text":"text to type","label":"input label text (fallback)"}

Type AND submit in one step (use this for search boxes, login forms, anywhere typing+Enter completes the task — much more reliable than typing then clicking a separate submit/search button):
{"action":"type","selector":"#id or input[name=x]","text":"text to type","submit":true}

If \`type\` did not visibly update the field (React/Vue input snapped back, autocomplete swallowed it), retry with force_type:
{"action":"force_type","selector":"#id","text":"text","label":"label fallback"}

Type into a CANVAS-RENDERED editor (Google Docs/Sheets/Slides, Figma text, custom rich editors). Click the canvas first to give it focus, then:
{"action":"canvas_type","text":"text to insert"}

Click at viewport coordinates (use ONLY when the page has zero usable interactive elements — pure WebGL/3D/map surface — and you've identified the spot from the screenshot or pierce_query):
{"action":"canvas_pointer","x":640,"y":380,"button":"left","clickCount":1}

Find an element by visible text (pierces shadow DOM and same-origin iframes; returns the element's center coordinates so you can canvas_pointer-click it):
{"action":"pierce_query","text":"visible text on the element","role":"optional ARIA role like button"}

Press a keyboard key (optionally focus a selector first):
{"action":"keypress","key":"Enter","selector":"optional selector to focus"}

Scroll the page:
{"action":"scroll","direction":"down","amount":500}

Wait for the page to settle (fixed sleep):
{"action":"wait","seconds":2}

Wait for an element to appear (useful after navigation/click):
{"action":"waitForElement","selector":"CSS_SELECTOR","timeout":8000}

Wait for ANY of: a URL substring, a selector, visible text, or network-idle:
{"action":"wait_for","url":"/results","selector":".item","text":"Loading complete","idle":true,"timeout":15000}

Dismiss a consent banner / cookie popup / "subscribe" intro modal generically:
{"action":"dismiss_modal"}

Open a new tab and navigate (use this when you need to compare/research across multiple sites):
{"action":"open_tab","url":"https://...","active":true}

List all currently open tabs (returns id, url, title, active):
{"action":"list_tabs"}

Switch focus to a different tab by id:
{"action":"switch_tab","tabId":42}

Close a tab by id:
{"action":"close_tab","tabId":42}

Extract text from an element and store it:
{"action":"extract","selector":"CSS_SELECTOR","field":"variable_name_for_result"}

Refresh understanding of the current page:
{"action":"getPageState"}

Signal that the task is complete:
{"action":"done","success":true,"message":"Human-readable summary of what was accomplished"}

Signal that the task cannot be completed:
{"action":"done","success":false,"message":"Clear explanation of what blocked the task"}

SELECTOR PRIORITY (try in order):
1. ID:       #submit-btn
2. Name:     input[name="email"]
3. Data attr:[data-testid="login-btn"]
4. Class+tag: button.primary-btn
5. Aria:     [aria-label="Submit"]

RULES:
- One action per response, valid JSON only, no surrounding text.
- After navigate: always wait 1-2s or use waitForElement before interacting.
- If a click/type fails: try a different selector strategy or getPageState to see current state.
- If the page looks wrong: use getPageState to reorient before proceeding.
- Declare done only when the task is clearly complete or definitely blocked.
- Never delete accounts, send money, make purchases, or take irreversible destructive actions unless the task explicitly requires it.

FIELD COMPLETENESS — before calling \`done\` with success:true, mentally list every distinct piece of information the user explicitly asked for. If any item is missing from your extracted data or the on-page state, do another step to find it. Never silently drop a sub-field. If a value isn't on the page, search for it — never invent.

QUOTE VERBATIM, DON'T PARAPHRASE — when the user asks to read, list, or extract content from a page (headlines, navigation labels, section names, prices, ratings, scores, dates), put the EXACT on-page strings into your final message. Do NOT answer "one of the main sections is X" or "a navigation item is X" — the user wants the actual list. Format: "The headlines are: '<exact 1>', '<exact 2>', '<exact 3>'." or "The navigation sections are: <exact 1>, <exact 2>, <exact 3>, ..." If the page shows N items and the user asked for "the sections" / "the headlines" / "the items," return ALL of them (or at least the top 5) — not one example. Single-example answers count as failure.

EVEN IF THE USER ASKS FOR "ONE" OR "AN EXAMPLE", LIST SEVERAL — when the user says "tell me one of the X" / "give me an example of X" / "what's a section name on …" the most useful answer is the FULL set you can see, not the first item picked. Quote 3-5 of the items verbatim. Pick from canonical / top-of-page / labeled-as-primary items first (e.g. the obvious site-wide nav links rather than utility links like "Search"/"Subscribe"/"Log In"). Skip items that are clearly chrome rather than content (search box label, subscribe button, account menu). The user almost always wants to recognize what's available, not be picked-for; listing several lets them pick.

MULTI-SOURCE TASKS — if the user names two or more sources ("compare X on A and B", "from Wikipedia AND Britannica", "check both Amazon and eBay"), you MUST visit each named source before \`done(success:true)\`. Open the second source via \`open_tab\` or by navigating after extracting from the first. Your final message must report a value from EACH source, even if the values agree. A single-source answer to a multi-source question is failure, not partial credit.

ANCHOR ON THE NAMED ENTITY — when the user asks for a fact about a SPECIFIC entity (e.g., "the President of Stanford", "the topic description of the React GitHub repo", "the population of Tokyo metropolitan area"), the answer must come from a page that explicitly identifies that entity. If you find a value on a page that doesn't name the entity (a generic "About" page, a list view, a sibling org's page), DO NOT extract it. Re-search with the entity's official name as the query, navigate to the page that names it, then extract. Wrong-anchor extractions ("here's some president, hope that's right") are the most common factual-failure mode and count as a hard fail, not partial credit.

GEOGRAPHIC / DISTANCE QUERIES — when the user asks for a distance, location, or "near X" lookup, the answer must explicitly cite the reference point. "5 km away" without saying from what is wrong; "5 km from the Eiffel Tower (48.8584° N, 2.2945° E)" is right. Map sites (OpenStreetMap, Google Maps) display the route or the named pin in the URL — anchor your final message to whatever the page actually shows about the reference point, not your assumption of distance.

FORM-FILL PROGRESS — when filling a form, after you submit a field check that the field's value persists (extract it back). If TWO consecutive fields fail to persist, the page is using a framework that rejects the standard input event flow (React with strict controlled components, Vue with deep proxies). Switch to \`force_type\` (which uses native value setters + dispatches React's internal event), and if THAT fails, decline with a specific reason naming the field that wouldn't accept input. Do NOT keep submitting all remaining fields hoping they'll work — observed in the Hertz / EPA / Jotform clusters as 30+ step timeouts where every field-fill silently no-op'd.

ACTUALLY TAKE ACTION — for any task that is "send / post / submit / book / buy / schedule / reply / message / order / confirm / publish", \`done(success:true)\` is ONLY valid AFTER you have actually clicked the send/submit/post/confirm button and observed the page state CHANGE (URL changed, confirmation banner appeared, the form cleared, the message appeared in the thread). Drafting / composing / generating text is NOT done. Telling me what you would have written is NOT done. If you wrote something into a compose box but never hit Send, you are NOT done — you must press Send and verify it went through. If a confirm dialog appears, you must explicitly accept it. If the action requires login you don't have, decline gracefully — do not pretend success.

CANVAS / WEBGL — when the page is canvas-rendered (Google Docs/Sheets/Slides, Figma, Canva, paint tools, WebGL maps, 3D viewers), TRY THESE before giving up:
  • canvas_type to insert text — automatically targets the offscreen iframe Docs/Sheets/Slides use, plus the active contenteditable for any other rich editor. Click into the canvas first to give it focus.
  • pierce_query for clickable spots by visible label — works inside shadow DOM and same-origin iframes.
  • canvas_pointer for coordinate clicks (DPR-corrected) — for WebGL maps, paint canvas, drag-to-draw flows.

DO NOT decline a task just because the page is canvas-rendered or the DOM looks sparse. Try canvas_type / canvas_pointer / pierce_query first. The extension's content script handles all the heavy lifting (offscreen iframe targeting, shadow DOM piercing, native value setters). Only decline as a LAST RESORT when you've genuinely exhausted these tools.

ATTEMPT BEFORE DECLINING — for any task involving "compose / draft / edit / write / type", do not refuse. The user's Chrome runs in their real session — most authenticated apps will accept actions in the existing tab. Navigate to whatever URL on the target service starts a fresh compose/create flow, give the canvas focus, and use canvas_type. If after 3+ attempts the surface genuinely won't accept input (no auth, hard captcha, etc.), only then decline with a specific reason.

LOGIN-WALL HANDLING — if the page text says "sign in", "log in to continue", or you see a password field on a path you can't bypass, end with done success:false explaining the wall. Don't loop.

REQUIRED-SLOT CHECK — BEFORE navigating or acting, ask yourself: if I had to actually carry out this task for a friend, what's the smallest set of facts I'd need to not have to come back and ask them about? Derive those from the task itself; don't follow a fixed catalog. If ANY of those facts is missing or vague in the task description and parameters, DO NOT navigate. Call \`done\` with success:false and ONE short, polite question that asks for exactly the missing facts. Never invent or guess values on the user's behalf — better to ask once than to take a wrong action.

SUBMIT FORMS THE RIGHT WAY — when the user's task is "search X for Y" or "look up Y on X" or any flow that needs typing then submitting, ALWAYS prefer \`{"action":"type","selector":"<input>","text":"<value>","submit":true}\` over typing + clicking a separate Search/Submit button. Search buttons frequently have generic class names (cdx-button, mui-button) that match multiple elements, and clicking the wrong one is the #1 cause of agent stalls. type+submit also dispatches Enter keydown/keypress/keyup and calls form.requestSubmit() so the page's own form-submit handler fires regardless of framework.

SEARCH-BOX FALLBACK — if a search input keeps rejecting typing (you see "Typed but value did not stick" or two consecutive type failures on the same selector), STOP TYPING. Most search engines and content sites accept the query directly via a URL parameter — figure out the pattern from the current page (look at the URL after a real search, or use general knowledge of how that site's search URL is structured) and \`navigate\` to it. Same outcome as typing + submit, but more reliable when an input keeps swallowing keystrokes.

CONSENT BANNERS / COOKIE POPUPS — many sites (YouTube, news sites, EU-region sites) hide the real UI behind a consent dialog. If after navigating you see "Accept all", "I agree", "Got it", or a cookie-related modal, your FIRST action should be \`{"action":"dismiss_modal"}\`. Then re-getPageState and proceed. dismiss_modal is generic — it scores candidates by visible text affinity for confirm/dismiss verbs and by z-index, no per-site list.

WAIT INTELLIGENTLY — fixed \`wait\` sleeps are for unknown latency. When you know what you're waiting for, use \`wait_for\` (URL change, selector appears, text appears, or idle:true for network quiet). Saves time on fast pages and prevents stalls on slow ones.

NEVER LOOP ON WAIT — wait_for and wait must NEVER appear back-to-back in your step history. After ONE wait that succeeded, your next action MUST be extract / click / scroll / canvas_pointer / pierce_query / done. If wait_for failed and you can already see useful content in VISIBLE TEXT, skip waiting and extract directly. If you're tempted to wait again because content "isn't loaded yet", instead try extract — most sites render the headline / first result early even when peripheral chrome is still loading.

CSS SELECTOR RULES — selectors are pure CSS, NOT jQuery. \`:contains("text")\` does NOT work. \`:has-text\` does NOT work. To find an element by visible text, use action \`pierce_query\` (which pierces shadow DOM and same-origin iframes), or use the click action's \`text\` fallback. Stick to standard CSS: tag, #id, .class, [attr=value], descendant, child, :nth-child(n). KEEP SELECTORS SHORT — never exceed 100 characters. Long selectors with chained \`:not(...):not(...):not(...)\` clauses are wrong — if you can't write a SHORT selector that targets the element, use pierce_query with the visible text instead.

READ VISIBLE TEXT DIRECTLY — values that already appear in the VISIBLE TEXT block of your page state context do not need an extract action. Just read them from the context and include them in your final \`done\` message. Use \`extract\` only when you need a specific element's text that isn't already shown to you (e.g. an attribute, or text inside a deeply-nested element that VISIBLE TEXT clipped). For Wikipedia / news / blog pages, the answer is almost always in VISIBLE TEXT — extract is rarely needed; just read and \`done\`.

MULTI-TAB / MULTI-STEP / RESEARCH TASKS — for tasks like "compare flight prices on Google Flights AND Kayak", "find the cheapest mouse on Amazon AND Best Buy", "draft an email referencing the article on TechCrunch": use \`open_tab\` to spawn a new tab, do work in it, use \`switch_tab\` to come back, and accumulate findings in extracted_data so you can reason across them at the end. \`list_tabs\` shows you all open tabs by id.

PIVOT EARLY ON MULTI-SITE TASKS — if the user's task names two or more distinct sites/services to compare or aggregate, your action sequence MUST be: (1) one extract from site A → (2) open_tab for site B IMMEDIATELY → (3) one extract from site B → (4) done. Do NOT loiter on site A re-extracting variations of the same content. The first useful extract from site A is enough — if the headline/price/title is in extracted_data, MOVE ON. Step budget is shared across sites, so wasting 20 steps on site A leaves nothing for site B.

LONG-RUNNING TASKS — you have up to 60 steps and 10 minutes per intent. For multi-step flights/booking/research flows that take a while, don't rush to declare done. After each step, check whether you've actually achieved the user's full request or just one piece of it. If you've only done part: keep going.

FOLLOW-UP HANDLING — the user may ask follow-up questions ("what about the other one?", "compare with X"). You'll receive these as new intents but with relevant context in PARAMETERS. Use list_tabs + switch_tab to revisit work you did earlier rather than starting from scratch.

EFFECT-OF-ACTION FEEDBACK — after each non-terminal action you take, the step \
history now shows a "→ effect:" line summarizing what actually changed on the \
page (URL, title, top heading, body content size, element count deltas, modal \
appeared/closed). Read this every step. Two important cases:\n\
  • "→ effect: NONE — page didn't visibly change" means your last action had \
ZERO observable effect — your click landed but fired no real handler, or the \
input rejected your text, or the navigation was a no-op. DO NOT repeat the \
exact same action; pick a different element / selector / strategy.\n\
  • A non-empty effect (URL changed, +N buttons, modal appeared) is direct \
evidence that the action moved the task forward. Use it to decide whether \
the current plan step is now satisfied.\n\
This is the single most reliable signal you have for whether you're making \
real progress vs. silently stalling. Trust it over the action's own \
success/failure return value (a click can return success while doing nothing).\n\n\
PLAN AWARENESS — at task start a strategic plan was generated for you (3-7 numbered steps). It appears in your context as PLAN. Use it as a north star: the current plan-step you're working on is shown, plus what's already done and what's still pending. If the page state contradicts the plan (the expected element isn't there, the URL went somewhere unexpected, the plan's next step depends on data you couldn't extract), ABANDON the plan for that step and pick the action that actually moves the task forward — the plan is guidance, not a script. If you've finished the plan but the user's task still isn't fully answered, keep going (the plan is a floor, not a ceiling).

OUTPUT FORMAT — chain of thought + action.
You may EITHER return the bare action object (the legacy shape, still accepted), OR — preferred — wrap it in a thought-and-action envelope that forces a brief reasoning step BEFORE you commit to the action:
{
  "thought": "<one short sentence — what you're trying to accomplish on this step and why this action moves the task forward>",
  "action": { ...one of the action shapes above... }
}
The "thought" is for your reasoning only; it never reaches the user. Keep it under 240 characters; just a single sentence about the goal of this step. The "action" object MUST match one of the action shapes specified above (navigate, click, type, force_type, etc.) — do NOT invent new fields. When in doubt, return the bare action shape — it still works.`;

// Planner prompt — fired ONCE at task start with Gemini Pro to produce a
// short, generic, JSON plan. The per-step LLM call sees this plan as
// context. Keeping the planner output small (3-7 steps) avoids over-fitting
// to one path while still giving the executor a north star.
const PLANNER_SYSTEM_PROMPT = `You are the strategic planner for a browser-automation agent.
Given a user task and the agent's starting page, produce a 3-7 step PLAN.

The agent will execute the plan step-by-step using these primitive actions:
navigate, click, type, force_type, canvas_type, canvas_pointer, pierce_query,
keypress, scroll, wait, wait_for, waitForElement, dismiss_modal, open_tab,
list_tabs, switch_tab, close_tab, extract, getPageState, done.

PLANNING RULES:
- Each step must be ONE concrete observable goal, not a primitive action.
  GOOD: "Search Wikipedia for 'cats'", "Extract the article's first paragraph", "Open Best Buy in a new tab"
  BAD:  "Type 'cats'", "Click the search button" — too granular; the executor decides clicks.
- 3-7 steps total. Fewer is better. Don't pad.
- If the task names multiple sites (compare X and Y), allocate at least one step per site.
- If the task involves writing/composing into a canvas app (Docs, Sheets, Slides, Figma), include
  a step "Open the compose surface and confirm canvas focus".
- The LAST step must be "Verify task is complete and report results" — the executor will use this
  step to self-evaluate before declaring done.
- If the task is impossible from the current page (login wall, out-of-scope), respond with
  {"plan":[{"step":1,"goal":"Decline with specific reason: <reason>"}],"required_fields":[],"unreachable":true}.

OUTPUT — JSON only, no surrounding text:
{
  "plan": [
    {"step": 1, "goal": "..."},
    {"step": 2, "goal": "..."}
  ],
  "required_fields": ["..."],
  "unreachable": false
}

required_fields is critical: list every distinct piece of info the user asked for. Examples:
  Task "search Wikipedia for cats and tell me what they eat" → ["diet"]
  Task "compare USB-C cable prices on Amazon and Best Buy"   → ["amazon_top_result", "bestbuy_top_result"]
  Task "draft an email about the meeting"                    → ["draft_visible_in_compose"]
Use snake_case names; keep the list short (1-5 entries usually). Empty array if the task is a pure
side-effect with no information to report back.`;

export class BrowserAgent {
  /**
   * @param {object} intent - The confirmed intent from Supabase
   * @param {object} apiConfig - { groqApiKey?: string, geminiApiKey?: string }
   */
  constructor(intent, apiConfig) {
    this.intent = intent;
    this.apiConfig = apiConfig;
    this.steps = []; // { action, result, timestamp }
    this.extractedData = {};
    this.startTime = Date.now();

    // Plan state — populated by the planner pass at step 0. Empty plan means
    // either the planner failed (we still run, just without strategic context)
    // or the model marked the task unreachable (we'll surface that immediately).
    this.plan = [];                  // [{step, goal}]
    this.requiredFields = [];        // [field_name, ...]
    this.unreachable = false;
    this.unreachableReason = "";
    this.currentPlanStep = 1;        // 1-indexed; advances when a plan step is satisfied

    // Escalation budget — set by heuristics, decremented in _callLLM.
    this.proCallsRemaining = 0;      // when > 0, the next call goes to Pro
    this.lastForcedRecoveryAtStep = -1;

    // Tier-2 escalation: when two CONSECUTIVE Gemini Pro calls return
    // junk (parse failures, empty bodies, or ended in a step that still
    // failed downstream), we route the next call through Claude Sonnet
    // via /api/extension/llm-proxy. Claude can't be hit directly from
    // the extension origin (Anthropic doesn't return the CORS headers
    // browser-extension contexts need), so the request is relayed by
    // anticipy.ai. proxyBaseUrl is taken from the apiConfig the popup
    // already plumbs through; falls back to anticipy.ai in case the
    // popup didn't set it.
    this.proFailureStreak = 0;
    this.claudeProxyBudget = 3;       // max Claude proxy calls per task
    this.proxyBaseUrl = (apiConfig && apiConfig.proxyBaseUrl) || "https://www.anticipy.ai";
    this.accessCode = (apiConfig && apiConfig.accessCode) || "";

    // Per-provider quota cooldown. Mirrors engine/app/models.py — when a
    // provider 429s we mark a cooldown that grows exponentially on
    // repeats (5s → 10s → 20s → 40s → 60s cap). The _callLLM loop SKIPS
    // any provider whose unblock time is in the future. When ALL
    // providers are blocked, _callLLM sleeps until the earliest unblock.
    // No hardcoded provider names beyond the keys we read from apiConfig
    // (gemini/groq/mistral/deepseek). Whichever has quota next is what we
    // use — that's the "cheapest available" policy.
    this._providerUnblockAt = {};     // { providerName: epochMs }
    this._providerFailCount = {};     // { providerName: consecutive429s }
    this._QUOTA_BASE_COOLDOWN_MS = 5000;
    this._QUOTA_MAX_COOLDOWN_MS = 60000;

    // Per-provider min spacing between calls. Cerebras free is 30 RPM
    // (2000ms spacing keeps us at the limit). Groq same. The agent waits
    // up to this much before making the next call to a given provider —
    // proactively throttles instead of reactively backing off after 429.
    this._lastProviderCallAt = {};   // { providerName: epochMs }
    this._PROVIDER_MIN_SPACING_MS = {
      cerebras: 2000,
      groq:     2000,
      mistral:  1200,
    };
  }

  async _waitForProviderSpacing(name) {
    // SERVER-DRIVEN SPACING (v7+): read per_tier[name].spacing_ms from the
    // /api/extension/agent-config response if we have a cached copy.
    // Falls back to the bundled _PROVIDER_MIN_SPACING_MS map only if the
    // server hasn't provided a spacing for this tier. This means we can
    // tune Cerebras spacing on the server (push to Vercel) and within ~60s
    // every shipped extension picks it up — NO extension reload required.
    // This is the fix for the 30 RPM burst pattern that killed the 0/35
    // benchmark: when Cerebras hits 429, we can bump server spacing to
    // 2500ms and shipped agents will respect it on next config refresh.
    let min = 0;
    const remoteSpacing = this._cachedAgentConfig?.per_tier?.[name]?.spacing_ms;
    if (typeof remoteSpacing === "number" && remoteSpacing >= 0) {
      min = remoteSpacing;
    } else {
      min = this._PROVIDER_MIN_SPACING_MS[name] || 0;
    }
    if (min <= 0) return;
    const last = this._lastProviderCallAt[name] || 0;
    const since = Date.now() - last;
    if (since < min) {
      const wait = min - since;
      await new Promise(r => setTimeout(r, wait));
    }
    this._lastProviderCallAt[name] = Date.now();
  }

  // ── Per-provider quota helpers ─────────────────────────────────────
  // Same shape as engine/app/models.py. The agent calls _isProviderBlocked
  // before every attempt and _markProvider429/_markProviderOk after each.
  _isProviderBlocked(name) {
    const until = this._providerUnblockAt[name] || 0;
    return Date.now() < until;
  }
  _markProvider429(name) {
    const fails = (this._providerFailCount[name] || 0) + 1;
    this._providerFailCount[name] = fails;
    const cooldown = Math.min(
      this._QUOTA_BASE_COOLDOWN_MS * Math.pow(2, fails - 1),
      this._QUOTA_MAX_COOLDOWN_MS
    );
    this._providerUnblockAt[name] = Date.now() + cooldown;
    console.warn(
      `[Anticipy Agent] provider ${name} quota-blocked for ${cooldown/1000}s (consecutive 429 #${fails})`
    );
  }
  _markProviderOk(name) {
    if (this._providerFailCount[name]) this._providerFailCount[name] = 0;
    delete this._providerUnblockAt[name];
  }
  _earliestUnblockMs() {
    const futures = Object.values(this._providerUnblockAt).filter(t => t > Date.now());
    return futures.length ? Math.min(...futures) : null;
  }

  /** Entry point — run the full agent loop and return { success, message } */
  async run() {
    const preview = (this.intent.summary_for_user || "task").substring(0, 80);
    console.log("[Anticipy Agent] starting:", preview);

    await chrome.storage.local.set({
      agentStatus: {
        intentId: this.intent.id,
        status: "running",
        message: "Starting…",
        startedAt: Date.now()
      }
    });

    let result;
    try {
      // Planner pass — one Gemini Pro call before the executor loop. The
      // planner reads the task + initial page state and returns a 3-7 step
      // plan + a list of required_fields the user explicitly asked for.
      // Failures here are non-fatal; the executor can still run plan-less.
      try {
        await this._planTask();
      } catch (e) {
        console.warn("[Anticipy Agent] planner failed (non-fatal):", e.message);
      }
      // If the planner declared the task unreachable, short-circuit with the
      // declared reason so the user gets a clean explanation.
      if (this.unreachable) {
        result = { success: false, message: this.unreachableReason || "Task can't be completed from this page." };
      } else {
        result = await this._loop();
      }
      // Self-eval: if the executor declared success but required_fields are
      // missing from extractedData (and not present in the success message),
      // demote to a partial-success failure so the user knows the truth.
      if (result.success) {
        result = this._selfEvalDone(result);
      }
    } catch (err) {
      result = { success: false, message: err.message || "Unexpected error" };
    }

    // On failure, build a compact debug suffix for the CONSOLE ONLY so we
    // can see what the agent actually did before giving up. The user-visible
    // message (result.message) is left clean — investors should never see
    // "| last:✗click(sel=...) | data:{...}" tails. Enable the suffix on the
    // user-visible message only behind localStorage.anticipy_debug.
    let debugTail = "";
    if (!result.success) {
      try {
        const lastSteps = this.steps.slice(-5).map(s => {
          const a = s.action || {};
          const ok = s.result?.success ? "✓" : "✗";
          const tail = a.url ? a.url.substring(0, 40)
                       : a.selector ? `sel=${a.selector}`
                       : a.text ? `text=${String(a.text).substring(0,30)}`
                       : a.tabId !== undefined ? `tab=${a.tabId}` : "";
          return `${ok}${a.action}${tail ? `(${tail})` : ""}`;
        }).join(" → ");
        const ext = Object.keys(this.extractedData || {}).length
          ? ` | data:${JSON.stringify(this.extractedData).substring(0, 200)}`
          : "";
        debugTail = ` | last:${lastSteps}${ext}`;
      } catch (_) {}

      // LLM-rewrite the raw failure message into a single calm user-
      // facing sentence. NO hardcoded pattern-match rules — see the
      // friendlyAgentMessage definition for the policy.
      try {
        result.message = await friendlyAgentMessage(result.message, this);
      } catch (_) {
        result.message = "I couldn't finish that one. Want to try again?";
      }

      // Opt-in: power users can enable the debug tail in the user-visible
      // message via `localStorage.setItem("anticipy_debug", "1")`.
      try {
        if (typeof localStorage !== "undefined" && localStorage.getItem("anticipy_debug") === "1") {
          result.message = `${result.message}${debugTail}`;
        }
      } catch (_) {}
    }

    await chrome.storage.local.set({
      agentStatus: {
        intentId: this.intent.id,
        status: result.success ? "done" : "failed",
        message: result.message,
        finishedAt: Date.now()
      }
    });

    // Console always gets the full diagnostic — separate from user-visible message.
    console.log(
      "[Anticipy Agent] finished:",
      result.success ? "✓" : "✗",
      result.message + (debugTail || "")
    );

    // Persist the trajectory for future learning. Non-fatal on failure —
    // the user has already been told the outcome; losing one trace doesn't
    // change anything they see. The /api/engine/trajectory route is a
    // best-effort write that degrades cleanly when Supabase is hiccuping.
    try {
      await this._persistTrajectory(result);
    } catch (e) {
      console.warn("[Anticipy Agent] trajectory persist failed (non-fatal):", e?.message || e);
    }

    // Reflexion: distill a 1-line GENERALIZED lesson from this run and
    // append it to chrome.storage.local.lessons. The lesson is prepended
    // to the system prompt on subsequent tasks, accumulating across runs
    // within a Chrome session. Best-effort — never blocks the result.
    try {
      await this._distillAndStoreLesson(result);
    } catch (e) {
      console.warn("[Anticipy Agent] lesson distill failed (non-fatal):", e?.message || e);
    }

    return result;
  }

  // ─── Reflexion: lesson distillation + persistence ────────────────────
  // Inline so we don't need a new HTTP endpoint. One Mistral call per task
  // end (success OR failure). Cost: ~$0.001 per task. Lessons stored in
  // chrome.storage.local.lessons (cap 5, FIFO). Loaded into the system
  // prompt by _getNextAction. NEVER site-specific — the Mistral prompt
  // demands a generalized rule that would apply across many sites.
  async _distillAndStoreLesson(result) {
    if (!this.apiConfig?.mistralApiKey || this._isProviderBlocked("mistral")) return;
    if (this.steps.length === 0) return;
    const recent = this.steps.slice(-8).map((s, i) => {
      const a = s.action || {};
      const ok = s.result?.success ? "OK" : "FAIL";
      const tail = a.url ? a.url.substring(0, 60)
                 : a.selector ? `sel="${a.selector}"`
                 : a.text ? `text="${String(a.text).substring(0, 40)}"`
                 : "";
      const eff = s.signalDiff ? ` | effect: ${String(s.signalDiff).substring(0, 80)}` : "";
      return `  ${i + 1} ${ok} ${a.action || "?"}${tail ? ` (${tail})` : ""}${eff}`;
    }).join("\n");
    const prompt =
      `You're distilling one GENERALIZED lesson from a browser-agent run.\n\n` +
      `TASK: ${(this.intent.summary_for_user || "").substring(0, 240)}\n` +
      `OUTCOME: ${result.success ? "SUCCESS" : "FAILURE"}\n` +
      `FINAL MESSAGE: ${(result.message || "").substring(0, 200)}\n\n` +
      `LAST ACTIONS:\n${recent}\n\n` +
      `Output one short lesson (<= 22 words) that would help a browser ` +
      `agent on ANY similar future task. Rules:\n` +
      `- The lesson MUST be GENERALIZED — never name a specific site or URL.\n` +
      `- Talk about CATEGORIES of pages: encyclopedias, news sites, e-commerce, social, search engines, forms, video sites.\n` +
      `- The lesson must be ACTIONABLE: name a behavior to repeat (success) or avoid (failure).\n` +
      `- If nothing useful was learned, output the literal string: SKIP.\n\n` +
      `JSON only: {"lesson": "<the lesson, or 'SKIP'>"}`;
    try {
      const resp = await fetch(MISTRAL_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${this.apiConfig.mistralApiKey}`,
        },
        body: JSON.stringify({
          model: "mistral-small-latest",
          messages: [{ role: "user", content: prompt }],
          temperature: 0.2,
          max_tokens: 120,
          response_format: { type: "json_object" },
        }),
      });
      if (!resp.ok) {
        if (/\b429\b|\b402\b/.test(`${resp.status}`)) this._markProvider429("mistral");
        return;
      }
      const data = await resp.json();
      const content = (data?.choices?.[0]?.message?.content || "").trim();
      let lesson = "";
      try { lesson = (JSON.parse(content)?.lesson || "").toString().trim(); } catch (_) {}
      if (!lesson || lesson === "SKIP") return;
      // Cap to 200 chars; store FIFO with 5-entry max
      lesson = lesson.substring(0, 200);
      const stored = await chrome.storage.local.get("lessons");
      const lessons = Array.isArray(stored?.lessons) ? stored.lessons : [];
      lessons.push({
        lesson,
        outcome: result.success ? "success" : "failure",
        addedAt: Date.now(),
        domain: this._currentDomainOrEmpty(),
      });
      while (lessons.length > 5) lessons.shift();
      await chrome.storage.local.set({ lessons });
      console.log(`[Anticipy Agent] lesson stored (${lessons.length}/5): ${lesson}`);
    } catch (_) {}
  }

  _currentDomainOrEmpty() {
    try {
      const url = (this.steps?.findLast?.(s => s.action?.url)?.action?.url) || "";
      return url ? new URL(url).hostname : "";
    } catch (_) { return ""; }
  }

  async _loadLessons() {
    try {
      const stored = await chrome.storage.local.get("lessons");
      const arr = Array.isArray(stored?.lessons) ? stored.lessons : [];
      // Newest first, capped, with the "outcome" tag preserved
      return arr.slice(-5);
    } catch (_) { return []; }
  }

  // ─── Trajectory persistence ───────────────────────────────────────────────────
  // POSTs the full step trace to /api/engine/trajectory at end of every
  // task. The backend writes to the engine_trajectories Supabase table.
  // This is the foundation for the synthetic-data flywheel — once we have
  // N tasks per domain stored, the planner can retrieve similar past
  // traces and learn from real outcomes without any fine-tuning.
  // No-op when the extension isn't authenticated (no access code yet).
  async _persistTrajectory(result) {
    if (!this.accessCode) return;

    let domain = "";
    try {
      const tab = await this._getActiveTab();
      if (tab?.url) {
        domain = new URL(tab.url).hostname || "";
      }
    } catch (_) {}
    if (!domain) {
      // No domain → no point in persisting (per-domain analytics don't apply).
      // We still POST so future summaries see the run, but tag as 'unknown'.
      domain = "unknown";
    }

    const outcome = result.success ? "success" : "fail";
    const payload = {
      intent_id: this.intent?.id ?? null,
      domain,
      task_summary: (this.intent?.summary_for_user || "").substring(0, 2000),
      steps: this.steps.map((s) => ({
        action: s.action,
        result: { success: !!s.result?.success, error: s.result?.error || null },
        signalDiff: s.signalDiff || "",
        timestamp: s.timestamp,
      })),
      outcome,
      outcome_message: (result.message || "").substring(0, 2000),
      total_steps: this.steps.length,
      duration_ms: Date.now() - this.startTime,
    };

    const url = `${this.proxyBaseUrl}/api/engine/trajectory`;
    try {
      await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Anticipy-Code": this.accessCode,
        },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      // Network error — log to console but don't surface to the user.
      console.warn("[Anticipy Agent] trajectory POST failed:", e?.message || e);
    }
  }

  // ─── Main loop ───────────────────────────────────────────────────────────────

  async _loop() {
    for (let step = 0; step < MAX_STEPS; step++) {
      if (Date.now() - this.startTime > TASK_TIMEOUT_MS) {
        return { success: false, message: "Task timed out after 5 minutes" };
      }

      // Update popup with step progress
      await chrome.storage.local.set({
        agentStatus: {
          intentId: this.intent.id,
          status: "running",
          message: `Step ${step + 1}/${MAX_STEPS}…`,
          startedAt: this.startTime
        }
      });

      const pageState = await this._getPageState();

      // ─── ESCALATION HEURISTICS ───────────────────────────────────────────
      // Apply BEFORE _getNextAction so the next call uses Pro if appropriate.
      // We only set proCallsRemaining; the actual model selection happens in
      // _callLLM, which decrements the counter.
      const consecutiveFails = this._consecutiveFailureCount();
      const interactiveCount = (pageState?.elements || []).length;

      if (consecutiveFails >= ESCALATION.CONSECUTIVE_FAILS && this.proCallsRemaining < 1) {
        console.warn(`[Anticipy Agent] ${consecutiveFails} consecutive fails — escalating next call to Pro`);
        this.proCallsRemaining = 1;
      }
      if (interactiveCount === 0 && this.proCallsRemaining < 1) {
        // Canvas/WebGL pages have zero usable elements; Pro reasons about the
        // visible-text + screenshot-implied affordances better than Flash.
        console.warn("[Anticipy Agent] zero interactive elements — escalating to Pro");
        this.proCallsRemaining = 1;
      }
      if (step >= ESCALATION.STUCK_STEP_THRESHOLD &&
          step === ESCALATION.STUCK_STEP_THRESHOLD &&
          this.proCallsRemaining < ESCALATION.STUCK_PRO_BUDGET) {
        // Hit step 15 and still going — burn Pro on the next 5 calls. We
        // gate this on `step === STUCK_STEP_THRESHOLD` so it triggers exactly
        // once per task; subsequent steps consume the budget without re-arming.
        console.warn(`[Anticipy Agent] step ${step} reached without done — burning ${ESCALATION.STUCK_PRO_BUDGET} Pro calls`);
        this.proCallsRemaining = ESCALATION.STUCK_PRO_BUDGET;
      }

      // ─── FORCED RECOVERY ────────────────────────────────────────────────
      // After 2 consecutive failures, force a getPageState + plan re-eval.
      // We inject this BEFORE asking the LLM, so the LLM gets a fresh state
      // snapshot rather than reasoning from a stale screenshot.
      let forcedAction = null;
      if (consecutiveFails >= ESCALATION.RECOVERY_FAILS &&
          this.lastForcedRecoveryAtStep !== step - 1 &&
          this.steps.length > 0 &&
          this.steps[this.steps.length - 1].action?.action !== "getPageState") {
        console.warn(`[Anticipy Agent] ${consecutiveFails} consecutive fails — forcing getPageState recovery`);
        forcedAction = { action: "getPageState", __recovery: true };
        this.lastForcedRecoveryAtStep = step;
      }

      // ─── HARD STOP ON RUNAWAY FAILURES ──────────────────────────────────
      // After GIVEUP_FAILS (5) consecutive failures, we never recover by
      // burning more steps. Summarize what went wrong and exit cleanly.
      if (consecutiveFails >= ESCALATION.GIVEUP_FAILS) {
        const summary = this._summarizeFailure();
        console.warn(`[Anticipy Agent] giving up after ${consecutiveFails} consecutive fails`);
        return { success: false, message: summary };
      }

      let action;
      if (forcedAction) {
        action = forcedAction;
      } else {
        try {
          action = await this._getNextAction(pageState);
        } catch (e) {
          // LLM response was unparseable (most often truncated CSS selector).
          // Retry once with an explicit hint to use pierce_query instead.
          if (/not valid JSON|truncated/i.test(e.message || "")) {
            console.warn("[Anticipy Agent] truncated JSON — retrying with brevity hint");
            try {
              action = await this._getNextAction({
                ...pageState,
                __hint: "Your previous response was truncated. Avoid long CSS selectors. Use pierce_query with visible text instead, or read the value directly from VISIBLE TEXT.",
              });
            } catch (e2) {
              throw e2;
            }
          } else {
            throw e;
          }
        }
      }

      if (!action) {
        return { success: false, message: "LLM did not return a valid action" };
      }

      // Hard guard against consecutive wait/wait_for actions — the LLM has
      // a tendency to chain waits when content seems missing, which burns
      // step budget without making progress. Generic; no site-specific code.
      const lastVerb = this.steps.length ? this.steps[this.steps.length - 1].action?.action : null;
      const waitVerbs = new Set(["wait", "wait_for", "waitForElement"]);
      if (waitVerbs.has(action.action) && waitVerbs.has(lastVerb)) {
        console.warn("[Anticipy Agent] consecutive wait detected — overriding to getPageState");
        action.action = "getPageState";
      }

      // Hard guard against repeated failed types on the same selector —
      // a controlled input that rejects type but accepts force_type. After
      // 2 failed types on the same selector, override the next type to
      // force_type. Generic; applies to any site.
      if (action.action === "type" && action.selector && this.steps.length >= 2) {
        const recent = this.steps.slice(-3);
        const sameSelectorFails = recent.filter(s =>
          (s.action?.action === "type" || s.action?.action === "fill") &&
          s.action?.selector === action.selector &&
          !s.result?.success
        ).length;
        if (sameSelectorFails >= 2) {
          console.warn("[Anticipy Agent] type repeatedly failed on", action.selector, "— overriding to force_type");
          action.action = "force_type";
        }
      }

      // Bigger fallback: if force_type ALSO fails on the same input, the
      // input is hostile. Pivot to navigate-to-search-URL using the current
      // tab's domain. Generic — works for every search engine that accepts
      // query params in the URL (Google/Bing/DDG/YouTube/Wikipedia/Amazon/etc.).
      if ((action.action === "type" || action.action === "force_type") &&
          action.selector && this.steps.length >= 3) {
        const last3 = this.steps.slice(-3);
        const allTypeFailsOnSameSelector =
          last3.length >= 3 &&
          last3.every(s =>
            (s.action?.action === "type" || s.action?.action === "force_type" || s.action?.action === "fill") &&
            s.action?.selector === action.selector &&
            !s.result?.success
          );
        if (allTypeFailsOnSameSelector) {
          const query = String(action.text ?? action.value ?? "").trim();
          const tab = await this._getActiveTab();
          const host = (tab?.url ? new URL(tab.url).hostname : "").toLowerCase();
          const url = this._searchUrlForHost(host, query);
          if (url && query) {
            console.warn(`[Anticipy Agent] typing keeps failing — pivoting to URL navigation: ${url}`);
            action.action = "navigate";
            action.url = url;
            delete action.selector;
          }
        }
      }

      // Hard guard against runaway CSS selectors — Gemini occasionally emits
      // 1000-char :not() chains that just truncate at the token budget, OR
      // multi-selector lists with :has()/:contains() that aren't real CSS.
      // Detect: length > 200, OR :has(, OR :contains(, OR multiple commas.
      // Override → pierce_query if there's searchable text, else getPageState.
      if (typeof action.selector === "string") {
        const sel = action.selector;
        const tooLong = sel.length > 200;
        const jqueryFake = /:contains\(|:has-text\(/i.test(sel);  // jQuery, NOT CSS
        const tooManyAlts = (sel.match(/,/g) || []).length >= 2;   // multi-alt = truncation risk
        if (tooLong || jqueryFake || tooManyAlts) {
          console.warn(`[Anticipy Agent] bad selector (len=${sel.length} fake=${jqueryFake} alts=${tooManyAlts}) — overriding`);
          if (action.text || action.label) {
            action.action = "pierce_query";
            action.text = action.text || action.label;
            delete action.selector;
          } else {
            action.action = "getPageState";
            delete action.selector;  // clear so the next iteration doesn't re-trigger override
          }
        }
      }

      console.log(`[Anticipy Agent] step ${step + 1}: ${action.action}`, this._actionPreview(action));

      // Terminal action
      if (action.action === "done") {
        return { success: action.success !== false, message: action.message || "Task completed" };
      }

      // Inline wait (no DOM call needed)
      if (action.action === "wait") {
        await this._sleep((action.seconds || 2) * 1000);
        this.steps.push({ action, result: { success: true }, timestamp: Date.now() });
        continue;
      }

      // ─── Action-effect verification: capture page signals BEFORE action ──
      // For actions that can observably change the page, capture a cheap
      // signal snapshot so we can diff before/after. SKIP_DIFF actions are
      // ones where a diff makes no sense (pure queries, tab management,
      // long-blocking waits — these don't have a "did my click work?"
      // shape).
      const SKIP_DIFF = new Set([
        "getPageState", "getSignals", "wait_for", "waitForElement",
        "list_tabs", "extract", "pierce_query",
      ]);
      const captureDiff = !SKIP_DIFF.has(action.action);
      const signalsBefore = captureDiff ? await this._capturePageSignals() : null;

      // Advance plan progress proportionally — generic and monotonic. We
      // pace currentPlanStep to track step / MAX_PLAN_STEPS_RATIO so by the
      // time the executor has burned ~half its steps, the plan tracker is
      // halfway through. The LLM uses this as a "are we on schedule?" cue.
      if (this.plan && this.plan.length > 0) {
        const expected = Math.min(
          this.plan.length,
          1 + Math.floor((this.steps.length / Math.max(1, MAX_STEPS / 2)) * this.plan.length)
        );
        if (expected > this.currentPlanStep) this.currentPlanStep = expected;
      }

      let result = await this._executeAction(action);

      // ─── AUTO-RETRY ON SELECTOR MISS ────────────────────────────────────
      // content.js returns "Element not found" when findElement(selector,
      // text, aria) all came back empty. If the original action carried a
      // visible text/label/aria hint, the model already gave us the
      // semantic anchor we need — fall back to pierce_query, which walks
      // shadow DOM and same-origin iframes by visible text. Generic; fires
      // on ANY action that takes a selector and has a fallback hint.
      const selectorMissed = !result?.success &&
        typeof result?.error === "string" &&
        /element not found/i.test(result.error);
      const semanticHint = action.text || action.label || action.aria;
      const SELECTOR_BEARING = new Set(["click", "type", "force_type", "extract", "waitForElement"]);
      if (selectorMissed && semanticHint && SELECTOR_BEARING.has(action.action)) {
        console.warn(`[Anticipy Agent] selector miss on "${action.selector}" — auto-retry with pierce_query("${semanticHint}")`);
        // Record the original failure so the LLM can see it in step history.
        this.steps.push({ action, result, timestamp: Date.now() });
        const retryAction = { action: "pierce_query", text: semanticHint, role: action.role };
        const retryResult = await this._executeAction(retryAction);
        // If pierce_query found the element, surface its coordinates as a
        // hint that the LLM's NEXT step can use directly (e.g.
        // canvas_pointer at those coordinates, or a click-by-text on the
        // same string). We don't auto-click here because the original
        // intent might have been "type into this input" not "click".
        action = retryAction;
        result = retryResult;
      }

      // ─── Action-effect verification: capture page signals AFTER action ──
      // Only if we captured a `before`. The diff is empty-string when the
      // action had no observable effect on the page, which is itself a
      // useful signal — the agent sees that and re-strategizes instead of
      // claiming progress.
      let signalDiff = "";
      let signalsAfterCaptured = null;
      if (captureDiff && signalsBefore) {
        // Settle the page before reading signals. ABP's Online-Mind2Web
        // win came from determinism: race conditions where the agent
        // reads DOM mid-render produce false stalls. Three layers:
        //   1. Network idle wait via the content script (capped at 1500ms)
        //   2. requestAnimationFrame settle so pending reflows complete
        //   3. 400ms hard floor (was 120ms — too short for SPA renders)
        try {
          await this._waitForSettle(action);
        } catch (_) {
          // Best-effort; don't let a settle failure abort the step
        }
        await this._sleep(400);
        signalsAfterCaptured = await this._capturePageSignals();
        signalDiff = this._diffSignals(signalsBefore, signalsAfterCaptured);
      }

      // ─── Verifier agent call (server-side at /api/agent/verify) ───────
      // Independent agent — same Mistral small, fresh context, no Executor
      // bias. Catches the silent-stall failure mode where the Executor
      // thinks it succeeded but the page didn't actually move. Fires only
      // on observable actions (those with a signalDiff captured) and only
      // when we have an active plan step to verify against. Best-effort:
      // if the route 502s we just continue without a verdict.
      let verifierVerdict = null;
      if (captureDiff && signalsBefore && this.accessCode && this.plan.length > 0) {
        try {
          verifierVerdict = await this._callVerifier({
            action,
            signalsBefore,
            signalsAfter: signalsAfterCaptured,
            lastStepSuccess: Boolean(result.success),
          });
        } catch (e) {
          // Verifier failure is non-fatal — the loop continues.
          console.warn(`[Anticipy Agent] verifier call failed: ${e?.message || e}`);
        }
      }

      this.steps.push({
        action,
        result,
        signalDiff,
        verifier: verifierVerdict,
        timestamp: Date.now(),
      });

      if (action.action === "extract" && result.success && action.field) {
        this.extractedData[action.field] = result.text || "";
      }

      // Track consecutive verifier "not satisfied" verdicts. Two in a row
      // → call the Critic. Critic-not-progressing twice → Reflector.
      if (verifierVerdict) {
        if (!verifierVerdict.satisfied) {
          this._verifierMissStreak = (this._verifierMissStreak || 0) + 1;
        } else {
          this._verifierMissStreak = 0;
          // If verifier said advance_plan, bump the plan tracker.
          if (verifierVerdict.advance_plan && this.plan.length > 0) {
            this.currentPlanStep = Math.min(this.currentPlanStep + 1, this.plan.length);
          }
        }
      }

      // ─── Critic invocation: 3 verifier-misses in a row ───────────────
      // Bumped from 2 → 3 after production observation: the verifier
      // sometimes rejects on transient signal flutter (SPA mid-render,
      // body fingerprint changes from a single ad reload). 3 consecutive
      // rejections is a stronger stall signal and prevents the critic
      // from firing on every other step.
      if (this._verifierMissStreak >= 3 && this.accessCode) {
        try {
          const critic = await this._callCritic({
            verifierEvidence: verifierVerdict?.evidence || "",
          });
          if (critic) {
            console.warn(`[Anticipy Agent] critic: ${critic.diagnosis?.substring(0, 120)}`);
            this._verifierMissStreak = 0;
            this._criticMissStreak = (this._criticMissStreak || 0) + 1;
            if (critic.abort) {
              return { success: false, message: critic.abort_reason || "Task can't be completed from this state." };
            }
            if (typeof critic.replan_step_index === "number" && critic.replan_step_index > 0) {
              this.currentPlanStep = Math.max(1, Math.min(critic.replan_step_index, this.plan.length));
            }
            this._lastCriticDiagnoses = (this._lastCriticDiagnoses || []).concat([critic.diagnosis || ""]).slice(-2);
            this._lastCriticNewApproach = critic.new_approach || "";
          }
        } catch (e) {
          console.warn(`[Anticipy Agent] critic call failed: ${e?.message || e}`);
        }
      }

      // ─── Reflector invocation: 2 critic invocations with no progress ──
      if ((this._criticMissStreak || 0) >= 2 && this.accessCode) {
        try {
          const reflect = await this._callReflector({
            twoCriticDiagnoses: this._lastCriticDiagnoses || [],
          });
          if (reflect) {
            this._criticMissStreak = 0;
            this._lastCriticDiagnoses = [];
            console.warn(`[Anticipy Agent] reflector: ${reflect.decision} — ${reflect.reasoning?.substring(0, 120)}`);
            if (reflect.decision === "abort") {
              return { success: false, message: reflect.abort_message || "I couldn't reach the answer this run." };
            }
            if (reflect.decision === "pivot" && Array.isArray(reflect.new_plan) && reflect.new_plan.length > 0) {
              this.plan = reflect.new_plan
                .filter(p => p && typeof p.goal === "string" && p.goal.trim())
                .map((p, i) => ({
                  step: typeof p.step === "number" ? p.step : i + 1,
                  goal: p.goal.trim(),
                  success_criteria: typeof p.success_criteria === "string" ? p.success_criteria.trim() : "",
                }));
              this.currentPlanStep = 1;
            }
          }
        } catch (e) {
          console.warn(`[Anticipy Agent] reflector call failed: ${e?.message || e}`);
        }
      }

      console.log(
        `  →`,
        result.success ? "ok" : `FAILED: ${result.error}`,
        signalDiff ? `[effect: ${signalDiff.substring(0, 100)}]` : "",
        verifierVerdict ? `[verify:${verifierVerdict.satisfied ? "✓" : "✗"} ${verifierVerdict.confidence}]` : ""
      );

      // Human-like inter-action delay
      await this._sleep(700);
    }

    return { success: false, message: `Reached max ${MAX_STEPS} steps without completing task` };
  }

  // ─── Agent-team HTTP helpers ─────────────────────────────────────────
  // These call /api/agent/{verify,critic,reflect} on anticipy.ai. Same
  // upstream Mistral small budget. Failures are non-fatal — the run continues
  // with reduced verification.

  async _callVerifier({ action, signalsBefore, signalsAfter, lastStepSuccess }) {
    const url = `${this.proxyBaseUrl.replace(/\/$/, "")}/api/agent/verify`;
    const planStep = this.plan[Math.max(0, this.currentPlanStep - 1)] || {};
    let visibleText = "";
    try {
      const state = await this._getPageState();
      visibleText = state?.visibleText || "";
    } catch (_) {}
    const body = {
      task: this.intent.summary_for_user,
      plan_step: planStep,
      action,
      before_signals: signalsBefore,
      after_signals: signalsAfter,
      last_step_success: lastStepSuccess,
      extracted_data: this.extractedData,
      visible_text_excerpt: visibleText.substring(0, 1500),
    };
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Anticipy-Code": this.accessCode },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`verify ${resp.status}`);
    return await resp.json();
  }

  async _callCritic({ verifierEvidence }) {
    const url = `${this.proxyBaseUrl.replace(/\/$/, "")}/api/agent/critic`;
    let domain = "";
    try {
      const tab = await this._getActiveTab();
      domain = tab?.url ? new URL(tab.url).hostname : "";
    } catch (_) {}
    const body = {
      task: this.intent.summary_for_user,
      plan: this.plan,
      current_step_index: this.currentPlanStep,
      history: this.steps.slice(-10).map(s => ({
        action: s.action,
        result: { success: !!s.result?.success, error: s.result?.error || null },
        signalDiff: s.signalDiff || "",
      })),
      verifier_evidence: verifierEvidence,
      domain,
    };
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Anticipy-Code": this.accessCode },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`critic ${resp.status}`);
    return await resp.json();
  }

  async _callReflector({ twoCriticDiagnoses }) {
    const url = `${this.proxyBaseUrl.replace(/\/$/, "")}/api/agent/reflect`;
    let domain = "";
    try {
      const tab = await this._getActiveTab();
      domain = tab?.url ? new URL(tab.url).hostname : "";
    } catch (_) {}
    const body = {
      task: this.intent.summary_for_user,
      plan: this.plan,
      history: this.steps.slice(-12).map(s => ({
        action: s.action,
        result: { success: !!s.result?.success, error: s.result?.error || null },
      })),
      two_critic_diagnoses: twoCriticDiagnoses,
      domain,
    };
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Anticipy-Code": this.accessCode },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`reflect ${resp.status}`);
    return await resp.json();
  }

  // ─── Failure tracking helpers ────────────────────────────────────────────────

  /** Count consecutive failed steps at the tail of this.steps. */
  _consecutiveFailureCount() {
    let n = 0;
    for (let i = this.steps.length - 1; i >= 0; i--) {
      if (this.steps[i]?.result?.success) break;
      n++;
    }
    return n;
  }

  /** Build a clean human-readable failure summary (no JSON, no selectors). */
  _summarizeFailure() {
    const recent = this.steps.slice(-5);
    const verbs = recent.map(s => s.action?.action || "?").join(", ");
    const lastErr = recent.length ? (recent[recent.length - 1].result?.error || "") : "";
    const cleanErr = String(lastErr).replace(/[`'"]/g, "").substring(0, 120);
    const dataKeys = Object.keys(this.extractedData || {});
    const got = dataKeys.length ? ` (got: ${dataKeys.join(", ")})` : "";
    if (cleanErr) {
      return `I couldn't finish — ${verbs} kept failing. Last error: ${cleanErr}${got}.`;
    }
    return `I tried ${recent.length} actions in a row (${verbs}) without progress${got}. Stopping before I burn more time.`;
  }

  /**
   * Self-evaluate a done(success:true) before returning it. If the planner
   * declared required_fields and any of them is missing from extractedData
   * AND not present in the success message, demote to done(success:false).
   *
   * Lenient matching: the planner emits snake_case fields like
   * "main_headline_summary". We strip generic linker words ("text",
   * "value", "summary", "data", "info") and require that AT LEAST ONE
   * remaining content word appears in the message OR an extracted-data
   * key. Otherwise the planner's habit of stuffing >2 generic stopwords
   * into a field name causes false demotions when the agent legitimately
   * answered the question. Generic — no per-site code.
   */
  _selfEvalDone(result) {
    if (!result?.success) return result;
    const required = (this.requiredFields || []).filter(Boolean);
    if (required.length === 0) return result;
    // Generic stopwords — these are PHRASE-FILLING words the planner often
    // includes in field names but NEVER appear in a natural-language answer.
    // Removing them lets the matcher key off the actually meaningful tokens.
    const STOP = new Set([
      "the", "a", "an", "of", "for", "from", "with", "and", "or",
      "text", "value", "name", "info", "data", "summary", "description",
      "details", "today", "current", "main", "field", "result", "results",
      "string", "content", "message", "list", "answer",
    ]);
    const haveKeys = new Set(
      Object.keys(this.extractedData || {}).map(k => String(k).toLowerCase())
    );
    const msgLower = String(result.message || "").toLowerCase();
    const missing = [];
    for (const field of required) {
      const f = String(field).toLowerCase();
      // Direct hit on extractedData key always counts as satisfied.
      if (haveKeys.has(f)) continue;
      // Split into 3+-char parts, then drop generic stopwords.
      const parts = f.split(/[_\s\-]+/)
        .filter(p => p.length >= 3 && !STOP.has(p));
      // If ALL parts are stopwords (e.g., "main_text"), trust the agent.
      if (parts.length === 0) continue;
      // Satisfied if ANY part (the meaningful token) appears in either the
      // message or any extractedData key. Lenient: one match is enough.
      const inMsg = parts.some(p => msgLower.includes(p));
      const inData = Array.from(haveKeys).some(k => parts.some(p => k.includes(p)));
      if (!inMsg && !inData) missing.push(field);
    }
    if (missing.length === 0) return result;
    // Don't demote if the message is a substantive answer — generic length
    // + content-word check protects against false-negatives on natural
    // sentences that already convey the answer.
    if (msgLower.length >= 60 && /[a-z]{4,}/.test(msgLower)) {
      console.warn(`[Anticipy Agent] self-eval: required ${missing.join(", ")} not literally present, but message is substantive — leaving success:true`);
      return result;
    }
    console.warn(`[Anticipy Agent] self-eval: missing required fields ${missing.join(", ")} — demoting to partial`);
    return {
      success: false,
      message: `${result.message} (I think I'm done but couldn't confirm: ${missing.join(", ")}.)`
    };
  }

  // ─── LLM interaction ─────────────────────────────────────────────────────────

  async _getNextAction(pageState) {
    const recentSteps = this.steps.slice(-6).map((s, i) => {
      const a = s.action;
      const parts = [a.action];
      if (a.url) parts.push(`url=${a.url}`);
      if (a.selector) parts.push(`sel="${a.selector}"`);
      if (a.text) parts.push(`text="${String(a.text).substring(0, 40)}"`);
      if (a.field) parts.push(`→${a.field}`);
      const status = s.result.success ? "✓" : `✗ ${s.result.error || "failed"}`;
      const main = `  ${i + 1}. ${parts.join(" ")} ${status}`;
      // Surface the effect-of-action diff (URL change, title change, element
      // count delta, modal appeared/closed). When the diff is empty it means
      // the action had NO observable page effect — the agent should treat
      // that as a "my last move did nothing" signal and pick a different
      // strategy on this step.
      if (typeof s.signalDiff === "string") {
        if (s.signalDiff) {
          return `${main}\n     → effect: ${s.signalDiff.substring(0, 220)}`;
        }
        // Captured but empty: tell the LLM nothing changed.
        if (s.result?.success && !["wait", "done"].includes(a.action)) {
          return `${main}\n     → effect: NONE — page didn't visibly change. Try a different element or strategy.`;
        }
      }
      return main;
    }).join("\n");

    const extractedStr = Object.keys(this.extractedData).length > 0
      ? JSON.stringify(this.extractedData, null, 2)
      : "(none)";

    // Plan section — surfaced as context for the executor. Empty when the
    // planner failed; that's fine, the per-step LLM still has the task.
    const planLines = [];
    if (this.plan && this.plan.length) {
      planLines.push(`PLAN (current step: ${this.currentPlanStep}/${this.plan.length}):`);
      for (const p of this.plan) {
        const marker = p.step < this.currentPlanStep ? "✓" :
                       p.step === this.currentPlanStep ? "→" : " ";
        planLines.push(`  ${marker} ${p.step}. ${p.goal}`);
      }
      if (this.requiredFields.length) {
        planLines.push("");
        planLines.push(`REQUIRED FIELDS (must be reported before done(success:true)): ${this.requiredFields.join(", ")}`);
      }
      planLines.push("");
    }

    const userMessage = [
      `TASK: ${this.intent.summary_for_user}`,
      `ACTION TYPE: ${this.intent.action_type || "browser_action"}`,
      `INTENT PARAMETERS: ${JSON.stringify(this.intent.parameters || {}, null, 2)}`,
      "",
      ...planLines,
      `STEPS TAKEN (${this.steps.length}/${MAX_STEPS}):`,
      recentSteps || "  (none — this is the first step)",
      "",
      `EXTRACTED DATA:`,
      extractedStr,
      "",
      `CURRENT PAGE:`,
      `URL: ${pageState.url}`,
      `TITLE: ${pageState.title}`,
      "",
      `HEADINGS (h1 → h2 → h3, top-of-page first; the "top headline" is usually the first item):`,
      JSON.stringify(pageState.headings || [], null, 2).substring(0, 1500),
      "",
      `VISIBLE TEXT (first 2500 chars):`,
      (pageState.visibleText || "(empty)").substring(0, 2500),
      "",
      `INTERACTIVE ELEMENTS:`,
      JSON.stringify(pageState.elements || [], null, 2).substring(0, 2500),
      "",
      ...(pageState.__hint ? [`HINT: ${pageState.__hint}`, ""] : []),
      `What is the single next action? Respond with JSON only.`
    ].join("\n");

    return await this._callLLM(userMessage);
  }

  /**
   * Planner pass — single Gemini Pro call at task start. Reads the task +
   * initial page state, returns a plan + required_fields. Non-fatal on
   * failure; the executor still runs without a plan.
   */
  async _planTask() {
    // Calls the Planner agent at /api/agent/plan. The route does:
    //   1. Voyage embedding of the task
    //   2. pgvector top-3 retrieval of past successful trajectories
    //   3. ONE Mistral small call with the task + retrieved examples
    //   4. Returns plan + required_facts + examples_used
    //
    // Best-effort: if the route fails (network, 502, etc.) we run plan-less.
    // The Executor still runs. Plan-less is degraded but functional.
    if (!this.accessCode) {
      // No access code → no auth → can't call the planner endpoint.
      return;
    }
    let initialState = {};
    try {
      initialState = await this._getPageState();
    } catch (_) {}
    let domain = "";
    try {
      domain = initialState.url ? new URL(initialState.url).hostname : "";
    } catch (_) {}

    const planUrl = `${this.proxyBaseUrl.replace(/\/$/, "")}/api/agent/plan`;
    let raw;
    try {
      const resp = await fetch(planUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Anticipy-Code": this.accessCode,
        },
        body: JSON.stringify({
          task: this.intent.summary_for_user,
          current_url: initialState.url || "",
          current_title: initialState.title || "",
          domain,
        }),
      });
      if (!resp.ok) {
        console.warn(`[Anticipy Agent] planner endpoint ${resp.status}; running plan-less`);
        return;
      }
      raw = await resp.json();
    } catch (e) {
      console.warn(`[Anticipy Agent] planner endpoint failed: ${e?.message || e}; running plan-less`);
      return;
    }

    if (raw && Array.isArray(raw.plan)) {
      this.plan = raw.plan
        .filter(p => p && typeof p.goal === "string" && p.goal.trim())
        .map((p, i) => ({
          step: typeof p.step === "number" ? p.step : i + 1,
          goal: p.goal.trim(),
          success_criteria: typeof p.success_criteria === "string" ? p.success_criteria.trim() : "",
        }));
    }
    if (raw && Array.isArray(raw.required_facts)) {
      this.requiredFields = raw.required_facts.filter(f => typeof f === "string" && f.trim());
    } else if (raw && Array.isArray(raw.required_fields)) {
      // Legacy alias accepted for compatibility.
      this.requiredFields = raw.required_fields.filter(f => typeof f === "string" && f.trim());
    }
    if (raw && raw.unreachable === true) {
      this.unreachable = true;
      this.unreachableReason = String(raw.unreachable_reason || this.plan[0]?.goal || "Task can't be completed from this page.");
    }
    if (Array.isArray(raw?.examples_used) && raw.examples_used.length > 0) {
      console.log(`[Anticipy Agent] planner used ${raw.examples_used.length} RAG example(s)`);
    }
    console.log(`[Anticipy Agent] plan: ${this.plan.length} steps, required_fields=${JSON.stringify(this.requiredFields)}, unreachable=${this.unreachable}`);
  }

  async _callLLM(userMessage) {
    // Two-tier Executor: Cerebras Qwen3-235B (free 1M/day, ~250ms) primary,
    // Mistral mistral-small-latest free tertiary fallback. Each tier uses up to 4 attempts
    // with exponential backoff (0s→8s→24s→60s) on 429. If Cerebras fails
    // for any non-quota reason, we fall through to Mistral immediately. If
    // both exhaust, surface ai_unavailable.
    const hasCerebras = !!this.apiConfig?.cerebrasApiKey;
    const hasGroq     = !!this.apiConfig?.groqApiKey;
    const hasMistral     = !!this.apiConfig?.mistralApiKey;
    if (!hasCerebras && !hasGroq && !hasMistral) {
      throw new Error("No LLM keys configured (need CEREBRAS, GROQ or MISTRAL).");
    }

    // If the task references vision-required action types, prefer Groq
    // (Llama-4-Scout vision) — Cerebras Qwen3-235B is text-only and
    // would waste a call.
    const needsVision = /canvas_pointer|canvas_type|screenshot|VISION HINT/i.test(userMessage);
    const tiers = [];
    if (needsVision) {
      if (hasGroq)     tiers.push({ name: "groq",     fn: () => this._callGroq(userMessage) });
      if (hasCerebras) tiers.push({ name: "cerebras", fn: () => this._callCerebras(userMessage) });
    } else {
      if (hasCerebras) tiers.push({ name: "cerebras", fn: () => this._callCerebras(userMessage) });
      if (hasGroq)     tiers.push({ name: "groq",     fn: () => this._callGroq(userMessage) });
    }
    if (hasMistral)       tiers.push({ name: "mistral",     fn: () => this._callMistral(userMessage) });

    const MAX_ATTEMPTS = 2;       // Per tier — short retry, then jump
    const MAX_TIER_WAIT_MS = 8000; // If cooldown > 8s, skip this tier
    let lastErr = null;
    for (const tier of tiers) {
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        if (this._isProviderBlocked(tier.name)) {
          const wait = Math.max(0, (this._providerUnblockAt[tier.name] || 0) - Date.now());
          if (wait > MAX_TIER_WAIT_MS) {
            console.log(`[Anticipy Agent] ${tier.name} blocked ${wait/1000}s — skipping to next tier`);
            break;  // Try next tier immediately
          }
          if (wait > 50) {
            console.log(`[Anticipy Agent] ${tier.name} cooldown — sleeping ${wait/1000}s (attempt ${attempt + 1}/${MAX_ATTEMPTS})`);
            await new Promise(r => setTimeout(r, wait));
          }
        } else if (attempt > 0) {
          await new Promise(r => setTimeout(r, 1500));
        }
        try {
          await this._waitForProviderSpacing(tier.name);
          const out = await tier.fn();
          this._markProviderOk(tier.name);
          return out;
        } catch (e) {
          lastErr = e;
          const msg = String(e?.message || e);
          if (/\b429\b/.test(msg) || /\b402\b/.test(msg)) {
            this._markProvider429(tier.name);
            // Continue inner loop; next iteration honors the cooldown / skip
          } else {
            // Non-quota error (auth, malformed, 400, etc.) — try next tier
            console.warn(`[Anticipy Agent] ${tier.name} non-quota error: ${msg}`);
            break;
          }
        }
      }
    }
    const errStr = String(lastErr?.message || lastErr || "no error captured");
    console.warn(`[Anticipy Agent] all tiers exhausted: ${errStr}`);
    // Surface the upstream error directly in chrome.storage as a top-
    // level key so the test runner can read it. agentStatus gets
    // rewritten by friendlyAgentMessage so we can't stash there.
    try {
      await chrome.storage.local.set({
        lastUpstreamError: { at: Date.now(), err: errStr.substring(0, 400) },
      });
    } catch (_) {}
    throw new Error(`ai_unavailable: ${errStr.substring(0, 200)}`);
  }

  /**
   * Single-model rewrite of a raw error/failure into one calm user-
   * facing sentence. Goes through Mistral small (the same backbone the
   * Executor uses). If Mistral is in cooldown / unavailable, returns null
   * and the surrounding caller falls back to the single generic line.
   */
  async _rewriteForUser(rawMessage) {
    const text = (rawMessage || "").toString().trim();
    if (!text) return null;
    if (!this.apiConfig?.mistralApiKey || this._isProviderBlocked("mistral")) {
      return null;
    }
    try {
      const resp = await fetch(MISTRAL_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${this.apiConfig.mistralApiKey}`,
        },
        body: JSON.stringify({
          model: "mistral-small-latest",
          messages: [{
            role: "user",
            content:
              `Rewrite this internal browser-agent error as ONE calm ` +
              `sentence (<= 22 words) for a non-technical user. No ` +
              `apologies, no jargon, no model names.\n\nINTERNAL: ${text}`,
          }],
          temperature: 0.2,
          max_tokens: 100,
        }),
      });
      if (!resp.ok) {
        const body = await resp.text().catch(() => String(resp.status));
        const msg = `Mistral ${resp.status}: ${body.substring(0, 200)}`;
        if (/\b429\b/.test(msg) || /\b402\b/.test(msg)) {
          this._markProvider429("mistral");
        }
        return null;
      }
      const data = await resp.json();
      const rewritten = (data.choices?.[0]?.message?.content || "").toString().trim();
      if (rewritten.length >= 4 && rewritten.length <= 240) {
        this._markProviderOk("mistral");
        return rewritten.replace(/^["']|["']$/g, "");
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /**
   * Build the system prompt. Fetches the LATEST AGENT_SYSTEM_PROMPT from
   * /api/extension/agent-config (server-driven so we can iterate prompts
   * without forcing extension reloads). Caches for 60s. Falls back to
   * the bundled prompt if the endpoint is unreachable. Reflexion lessons
   * prepend regardless.
   */
  async _buildSystemPrompt() {
    const remote = await this._fetchAgentConfig();
    const basePrompt = remote?.system_prompt || AGENT_SYSTEM_PROMPT;
    const lessons = await this._loadLessons();
    if (lessons.length === 0) return basePrompt;
    const lessonBlock = lessons
      .map((l, i) => `  ${i + 1}. ${l.lesson}${l.outcome === "failure" ? " (avoid)" : " (repeat)"}`)
      .join("\n");
    return (
      `LESSONS FROM RECENT TASKS (read these first; ignore lessons that don't apply to the current task):\n` +
      `${lessonBlock}\n\n` +
      basePrompt
    );
  }

  /**
   * Fetch the server-side runtime config (system prompt, tier order,
   * spacing, feature flags). Cached for 60s on the instance. Best-effort
   * — failures fall back to bundled defaults so the agent still runs.
   */
  async _fetchAgentConfig() {
    if (this._cachedAgentConfig &&
        (Date.now() - (this._cachedAgentConfigAt || 0)) < 60000) {
      return this._cachedAgentConfig;
    }
    if (!this.accessCode) return null;
    try {
      const url = `${this.proxyBaseUrl.replace(/\/$/, "")}/api/extension/agent-config`;
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 8000);
      let resp;
      try {
        resp = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Anticipy-Code": this.accessCode,
          },
          body: JSON.stringify({}),
          signal: ctl.signal,
        });
      } finally {
        clearTimeout(t);
      }
      if (!resp.ok) return this._cachedAgentConfig || null;
      const data = await resp.json();
      this._cachedAgentConfig = data;
      this._cachedAgentConfigAt = Date.now();
      return data;
    } catch (_) {
      return this._cachedAgentConfig || null;
    }
  }

  /**
   * Cerebras Qwen3-235B — Executor primary FOR TEXT-ONLY tasks.
   * Free 1M tokens/day, 30 RPM, ~250ms latency. JSON mode supported.
   *
   * IMPORTANT: Cerebras has NO vision support. When the user message
   * references vision-required action types (canvas_pointer, canvas_type,
   * screenshot context), _callLLM falls through to Groq Llama-4-Scout
   * (vision-capable) instead.
   */
  async _callCerebras(userMessage) {
    const system = await this._buildSystemPrompt();
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 20000);
    let resp;
    try {
      resp = await fetch(CEREBRAS_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${this.apiConfig.cerebrasApiKey}`,
        },
        body: JSON.stringify({
          model: CEREBRAS_MODEL,
          messages: [
            { role: "system", content: system },
            { role: "user", content: userMessage },
          ],
          temperature: 0.1,
          max_tokens: 2400,
          response_format: { type: "json_object" },
        }),
        signal: ctl.signal,
      });
    } finally {
      clearTimeout(t);
    }
    if (!resp.ok) {
      const body = await resp.text().catch(() => String(resp.status));
      throw new Error(`Cerebras ${resp.status}: ${body.substring(0, 200)}`);
    }
    const data = await resp.json();
    const content = data?.choices?.[0]?.message?.content;
    if (!content) throw new Error("Empty response from Cerebras");
    return this._parseJSON(content);
  }

  /**
   * Groq llama-3.3-70b-versatile — second free tier. 14400 RPD, 30 RPM,
   * ~500ms latency. Separate quota pool from Cerebras. Used when
   * Cerebras 429s.
   *
   * Quirk: Groq's JSON mode requires the literal word "json" appear
   * somewhere in `messages` content, otherwise it returns 400. We
   * append a one-line JSON nudge to userMessage to guarantee the
   * check passes — content is unchanged for the model.
   */
  async _callGroq(userMessage) {
    const system = await this._buildSystemPrompt();
    const userWithJsonNudge = /\bjson\b/i.test(userMessage)
      ? userMessage
      : userMessage + "\n\n(Output JSON only.)";
    // Pick the vision-capable Llama 4 Scout when the prompt references
    // an action type that needs image understanding (canvas / pierce /
    // explicit screenshot context). Text-only Llama 3.3-70B otherwise —
    // it's faster and has its own quota window.
    const needsVision = /canvas_pointer|canvas_type|screenshot|VISION HINT/i.test(userMessage);
    const model = needsVision ? GROQ_VISION_MODEL : GROQ_TEXT_MODEL;
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 20000);
    let resp;
    try {
      resp = await fetch(GROQ_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${this.apiConfig.groqApiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: [
            { role: "system", content: system },
            { role: "user", content: userWithJsonNudge },
          ],
          temperature: 0.1,
          max_tokens: 2400,
          response_format: { type: "json_object" },
        }),
        signal: ctl.signal,
      });
    } finally {
      clearTimeout(t);
    }
    if (!resp.ok) {
      const body = await resp.text().catch(() => String(resp.status));
      throw new Error(`Groq ${resp.status}: ${body.substring(0, 200)}`);
    }
    const data = await resp.json();
    const content = data?.choices?.[0]?.message?.content;
    if (!content) throw new Error("Empty response from Groq");
    return this._parseJSON(content);
  }

  // mistral-small-latest — Executor fallback. Used when Cerebras+Groq are
  // exhausted. Same JSON-only output contract.
  async _callMistral(userMessage) {
    const system = await this._buildSystemPrompt();
    const resp = await fetch(MISTRAL_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this.apiConfig.mistralApiKey}`
      },
      body: JSON.stringify({
        model: "mistral-small-latest",
        messages: [
          { role: "system", content: system },
          { role: "user", content: userMessage }
        ],
        // Deterministic: same prompt → same action. v1-128k allows it.
        temperature: 0.1,
        max_tokens: 2400,
        response_format: { type: "json_object" }
      })
    });
    if (!resp.ok) {
      const body = await resp.text().catch(() => String(resp.status));
      throw new Error(`Mistral ${resp.status}: ${body.substring(0, 200)}`);
    }
    const data = await resp.json();
    const content = data.choices?.[0]?.message?.content;
    if (!content) throw new Error("Empty response from Mistral");
    return this._parseJSON(content);
  }

  _parseJSON(text) {
    const clean = text.trim().replace(/^```json\s*/i, "").replace(/```\s*$/, "").trim();
    let parsed;
    try {
      parsed = JSON.parse(clean);
    } catch {
      // Attempt to extract JSON object from surrounding prose
      const match = clean.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          parsed = JSON.parse(match[0]);
        } catch {
          parsed = null;
        }
      }
    }
    if (!parsed) {
      throw new Error("LLM response is not valid JSON: " + clean.substring(0, 200));
    }
    // Chain-of-thought envelope: when the model returned { thought, action }
    // (the preferred shape), unwrap to the raw action so the rest of the
    // executor pipeline doesn't need to change. The thought is logged to
    // the console for debugging — never surfaced to the user.
    if (parsed && typeof parsed === "object" && parsed.action && typeof parsed.action === "object" && !parsed.action.action && parsed.thought) {
      // shape: { thought, action: {...} } where inner action lacks .action — odd, fall through
    }
    if (parsed && typeof parsed === "object" && typeof parsed.thought === "string" && parsed.action && typeof parsed.action === "object" && typeof parsed.action.action === "string") {
      const t = parsed.thought.toString().slice(0, 240);
      if (t) console.log("[Anticipy Agent] thought:", t);
      return parsed.action;
    }
    return parsed;
  }

  // ─── Action execution ─────────────────────────────────────────────────────────

  async _executeAction(action) {
    // Tab-level actions don't need a current active tab
    if (action.action === "open_tab") {
      const r = await this._bgCall({ type: "TABS_OPEN", url: action.url, active: action.active !== false });
      if (r?.success) {
        this.activeTabId = r.tabId;
        await this._waitForTabLoad(r.tabId);
      }
      return r;
    }
    if (action.action === "list_tabs") {
      return await this._bgCall({ type: "TABS_LIST" });
    }
    if (action.action === "switch_tab") {
      const r = await this._bgCall({ type: "TABS_SWITCH", tabId: action.tabId });
      if (r?.success) this.activeTabId = action.tabId;
      return r;
    }
    if (action.action === "close_tab") {
      return await this._bgCall({ type: "TABS_CLOSE", tabId: action.tabId });
    }

    const tab = await this._getActiveTab();
    if (!tab) return { success: false, error: "No active tab found" };

    // navigate: handled directly via chrome.tabs API
    if (action.action === "navigate") {
      try {
        await chrome.tabs.update(tab.id, { url: action.url });
        await this._waitForTabLoad(tab.id);
        return { success: true, message: `Navigated to ${action.url}` };
      } catch (e) {
        return { success: false, error: e.message };
      }
    }

    // getPageState: handled by fetching fresh state
    if (action.action === "getPageState") {
      const state = await this._getPageState();
      return { success: true, data: state };
    }

    // All other actions → delegate to content script
    const domAction = this._toDomAction(action);
    if (!domAction) return { success: false, error: `Unknown action type: ${action.action}` };
    return this._sendToContent(tab.id, domAction);
  }

  /** Send a message to the SW (background) and await its response. */
  _bgCall(msg) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(msg, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || { success: false, error: "Empty response" });
        }
      });
    });
  }

  /** Map agent action names to the content script DOM_ACTION format */
  _toDomAction(action) {
    switch (action.action) {
      case "click":
        return { type: "click", selector: action.selector, text: action.text, aria: action.aria };
      case "type":
        return { type: "type", selector: action.selector, value: action.text, label: action.label, submit: action.submit === true };
      case "force_type":
        return { type: "force_type", selector: action.selector, value: action.text, label: action.label };
      case "canvas_type":
        return { type: "canvas_type", text: action.text };
      case "canvas_pointer":
        return { type: "canvas_pointer", x: action.x, y: action.y, button: action.button, clickCount: action.clickCount };
      case "pierce_query":
        return { type: "pierce_query", text: action.text, role: action.role };
      case "extract":
        return { type: "read_text", selector: action.selector };
      case "scroll":
        return { type: "scroll", direction: action.direction || "down", amount: action.amount || 500 };
      case "waitForElement":
        return { type: "waitForElement", selector: action.selector, timeout: action.timeout || 8000 };
      case "keypress":
        return { type: "keypress", key: action.key, selector: action.selector };
      case "wait_for":
        return { type: "wait_for", url: action.url, text: action.text, selector: action.selector, idle: action.idle, timeout: action.timeout || 15000 };
      case "dismiss_modal":
        return { type: "dismiss_modal" };
      default:
        return null;
    }
  }

  // ─── Page state ───────────────────────────────────────────────────────────────

  async _getPageState() {
    const tab = await this._getActiveTab();
    if (!tab) return { url: "unknown", title: "unknown", visibleText: "", elements: [] };

    try {
      const result = await this._sendToContent(tab.id, { type: "getPageState" });
      if (result?.success && result.data) return result.data;
    } catch {}

    return { url: tab.url || "unknown", title: tab.title || "unknown", visibleText: "", elements: [] };
  }

  // ─── Effect-of-action verification ────────────────────────────────────────────
  // Capture a lightweight page-signal snapshot before AND after every action
  // that could have observable effect (most everything except `done`, `wait`,
  // pure-query actions). Diff the two and surface the diff to the LLM as
  // "OBSERVED EFFECT FROM LAST ACTION" so the agent sees direct evidence
  // its action moved the task — not just whether the DOM call returned ok.
  // This catches the silent-stall failure mode: click lands cleanly, fires
  // no real handler, agent thinks it's progressing while the page hasn't
  // actually changed. Cost: one extra round-trip to content.js per action,
  // ~5-15 ms each, ~bounded total <2 s on a 60-step task.

  async _capturePageSignals() {
    const tab = await this._getActiveTab();
    if (!tab) return null;
    try {
      const result = await this._sendToContent(tab.id, { type: "getSignals" });
      if (result?.success && result.data) return result.data;
    } catch (_) {}
    return null;
  }

  /**
   * Wait for the page to settle after an action — kills race conditions
   * where the agent reads DOM mid-render and the verifier wrongly
   * decides "no observable effect." ABP's Online-Mind2Web win is mostly
   * this. Three layers:
   *
   *   1. Navigate actions: tab.onUpdated 'complete' or 1500ms cap
   *   2. Other actions: ask content script to await two
   *      requestAnimationFrame ticks (lets pending reflows finish)
   *   3. Hard cap so a busy page doesn't hang the run
   *
   * Best-effort. Failures are swallowed by the caller.
   */
  async _waitForSettle(action) {
    const tab = await this._getActiveTab();
    if (!tab) return;
    if (action?.action === "navigate" || action?.action === "open_tab") {
      // Wait for navigation to actually complete (or 1500ms cap)
      await this._waitForTabLoad(tab.id, 1500);
      return;
    }
    // For DOM-mutating actions: ask content script to settle render
    try {
      await Promise.race([
        this._sendToContent(tab.id, { type: "settle" }),
        new Promise(r => setTimeout(r, 1200)),
      ]);
    } catch (_) {}
  }

  // Pure function — fed before/after signal payloads, returns a short
  // human-readable diff string the LLM can reason on. Empty string means
  // "no observable effect" — itself a signal the agent should re-strategize.
  // Static to allow easy unit testing without instantiating a BrowserAgent.
  static diffSignals(before, after) {
    if (!before || !after) return "";
    const lines = [];

    if (before.url !== after.url) {
      const oldU = (before.url || "").replace(/^https?:\/\//, "");
      const newU = (after.url || "").replace(/^https?:\/\//, "");
      lines.push(`URL: ${oldU.substring(0, 60)} → ${newU.substring(0, 60)}`);
    }

    if (before.title !== after.title) {
      const oldT = (before.title || "").substring(0, 50);
      const newT = (after.title || "").substring(0, 50);
      lines.push(`Title: "${oldT}" → "${newT}"`);
    }

    if (before.topHeading !== after.topHeading &&
        (before.topHeading || after.topHeading)) {
      const oldH = (before.topHeading || "(none)").substring(0, 50);
      const newH = (after.topHeading || "(none)").substring(0, 50);
      lines.push(`Top heading: "${oldH}" → "${newH}"`);
    }

    const bodyDelta = (after.bodyTextLen || 0) - (before.bodyTextLen || 0);
    if (Math.abs(bodyDelta) >= 100) {
      lines.push(`Body content: ${bodyDelta > 0 ? "+" : ""}${bodyDelta} chars`);
    } else if (before.url === after.url &&
               before.bodyFingerprint !== after.bodyFingerprint) {
      // Same URL, content fingerprint changed → SPA route or partial update.
      lines.push("Body content changed (SPA route or partial update)");
    }

    const counts = [
      ["buttons", "buttonCount"],
      ["inputs",  "inputCount"],
      ["links",   "linkCount"],
      ["forms",   "formCount"],
    ];
    const deltas = [];
    for (const [name, key] of counts) {
      const d = (after[key] || 0) - (before[key] || 0);
      if (d !== 0) deltas.push(`${d > 0 ? "+" : ""}${d} ${name}`);
    }
    if (deltas.length) lines.push(`Elements: ${deltas.join(", ")}`);

    if (before.hasModal !== after.hasModal) {
      lines.push(after.hasModal ? "A modal/dialog appeared" : "Modal/dialog closed");
    }

    return lines.join("; ");
  }

  // Instance wrapper so existing callers stay clean.
  _diffSignals(before, after) {
    return BrowserAgent.diffSignals(before, after);
  }

  // ─── Content script bridge ────────────────────────────────────────────────────

  async _sendToContent(tabId, domAction) {
    return new Promise((resolve) => {
      const msg = { type: "DOM_ACTION", action: domAction };

      const trySend = (attempt) => {
        chrome.tabs.sendMessage(tabId, msg, (response) => {
          if (chrome.runtime.lastError) {
            if (attempt === 0) {
              // Inject content script and retry once
              chrome.scripting.executeScript(
                { target: { tabId }, files: ["content.js"] },
                () => {
                  if (chrome.runtime.lastError) {
                    resolve({ success: false, error: "Cannot inject content script: " + chrome.runtime.lastError.message });
                    return;
                  }
                  setTimeout(() => trySend(1), 400);
                }
              );
            } else {
              resolve({ success: false, error: chrome.runtime.lastError.message || "No response" });
            }
          } else {
            resolve(response || { success: false, error: "Empty response from content script" });
          }
        });
      };

      trySend(0);
    });
  }

  // ─── Tab helpers ──────────────────────────────────────────────────────────────

  async _getActiveTab() {
    return new Promise((resolve) => {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve(tabs?.[0] ?? null));
    });
  }

  async _waitForTabLoad(tabId, timeout = 15_000) {
    return new Promise((resolve) => {
      const deadline = setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }, timeout);

      const listener = (id, changeInfo) => {
        if (id === tabId && changeInfo.status === "complete") {
          clearTimeout(deadline);
          chrome.tabs.onUpdated.removeListener(listener);
          setTimeout(resolve, 800); // let JS settle
        }
      };

      chrome.tabs.onUpdated.addListener(listener);
    });
  }

  _sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  _actionPreview(action) {
    const parts = [];
    if (action.url) parts.push(action.url.substring(0, 60));
    if (action.selector) parts.push(`sel="${action.selector}"`);
    if (action.text) parts.push(`text="${String(action.text).substring(0, 40)}"`);
    return parts.join(" ") || "";
  }
}
