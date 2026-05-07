// Anticipy Chrome Extension — Browser Agent (LLM-powered)
// Takes a confirmed intent and executes it step-by-step using LLM decisions + DOM actions
// No localhost server required — runs entirely in the extension using the user's real browser.

const GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions";
// gemini-2.5-flash is the current generally-available flash model with the
// free-tier daily quota the extension uses. The previous gemini-2.0-flash
// returns 404 ("no longer available to new users") as of 2026-Q1.
const GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent";

const MAX_STEPS = 60;
const TASK_TIMEOUT_MS = 600_000; // 10 minutes hard limit (multi-step flows)

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

CANVAS / WEBGL — when the page is canvas-rendered (Google Docs/Sheets/Slides, Figma, Canva, paint tools, WebGL maps, 3D viewers), TRY THESE before giving up:
  • canvas_type to insert text — automatically targets the offscreen iframe Docs/Sheets/Slides use, plus the active contenteditable for any other rich editor. Click into the canvas first to give it focus.
  • pierce_query for clickable spots by visible label — works inside shadow DOM and same-origin iframes.
  • canvas_pointer for coordinate clicks (DPR-corrected) — for WebGL maps, paint canvas, drag-to-draw flows.

DO NOT decline a task just because the page is canvas-rendered or the DOM looks sparse. Try canvas_type / canvas_pointer / pierce_query first. The extension's content script handles all the heavy lifting (offscreen iframe targeting, shadow DOM piercing, native value setters). Only decline as a LAST RESORT when you've genuinely exhausted these tools.

ATTEMPT BEFORE DECLINING — for any task involving "compose / draft / edit / write / type", do not refuse. The user's Chrome runs in their real session — Gmail, Notion, Google Docs, etc. are usually already authenticated. Navigate to the relevant compose URL (mail.google.com/mail/u/0/#inbox?compose=new for Gmail, docs.google.com/document/u/0/create for a new Doc, etc.), give the canvas focus, and use canvas_type. If after 3+ attempts the surface genuinely won't accept input (no auth, hard captcha, etc.), only then decline with a specific reason.

LOGIN-WALL HANDLING — if the page text says "sign in", "log in to continue", or you see a password field on a path you can't bypass, end with done success:false explaining the wall. Don't loop.

SUBMIT FORMS THE RIGHT WAY — when the user's task is "search X for Y" or "look up Y on X" or any flow that needs typing then submitting, ALWAYS prefer \`{"action":"type","selector":"<input>","text":"<value>","submit":true}\` over typing + clicking a separate Search/Submit button. Search buttons frequently have generic class names (cdx-button, mui-button) that match multiple elements, and clicking the wrong one is the #1 cause of agent stalls. type+submit also dispatches Enter keydown/keypress/keyup and calls form.requestSubmit() so the page's own form-submit handler fires regardless of framework.

SEARCH-BOX FALLBACK — if a search input keeps rejecting typing (you see "Typed but value did not stick" or two consecutive type failures on the same selector), STOP TYPING. Most search engines accept the query directly in the URL: Google = https://www.google.com/search?q=ENCODED, Bing = https://www.bing.com/search?q=ENCODED, DuckDuckGo = https://duckduckgo.com/?q=ENCODED, YouTube = https://www.youtube.com/results?search_query=ENCODED, Wikipedia = https://en.wikipedia.org/w/index.php?search=ENCODED, Amazon = https://www.amazon.com/s?k=ENCODED. Use the navigate action with the URL — same outcome, more reliable.

CONSENT BANNERS / COOKIE POPUPS — many sites (YouTube, news sites, EU-region sites) hide the real UI behind a consent dialog. If after navigating you see "Accept all", "I agree", "Got it", or a cookie-related modal, your FIRST action should be \`{"action":"dismiss_modal"}\`. Then re-getPageState and proceed. dismiss_modal is generic — it scores candidates by visible text affinity for confirm/dismiss verbs and by z-index, no per-site list.

WAIT INTELLIGENTLY — fixed \`wait\` sleeps are for unknown latency. When you know what you're waiting for, use \`wait_for\` (URL change, selector appears, text appears, or idle:true for network quiet). Saves time on fast pages and prevents stalls on slow ones.

NEVER LOOP ON WAIT — wait_for and wait must NEVER appear back-to-back in your step history. After ONE wait that succeeded, your next action MUST be extract / click / scroll / canvas_pointer / pierce_query / done. If wait_for failed and you can already see useful content in VISIBLE TEXT, skip waiting and extract directly. If you're tempted to wait again because content "isn't loaded yet", instead try extract — most sites render the headline / first result early even when peripheral chrome is still loading.

CSS SELECTOR RULES — selectors are pure CSS, NOT jQuery. \`:contains("text")\` does NOT work. \`:has-text\` does NOT work. To find an element by visible text, use action \`pierce_query\` (which pierces shadow DOM and same-origin iframes), or use the click action's \`text\` fallback. Stick to standard CSS: tag, #id, .class, [attr=value], descendant, child, :nth-child(n). KEEP SELECTORS SHORT — never exceed 100 characters. Long selectors with chained \`:not(...):not(...):not(...)\` clauses are wrong — if you can't write a SHORT selector that targets the element, use pierce_query with the visible text instead.

READ VISIBLE TEXT DIRECTLY — values that already appear in the VISIBLE TEXT block of your page state context do not need an extract action. Just read them from the context and include them in your final \`done\` message. Use \`extract\` only when you need a specific element's text that isn't already shown to you (e.g. an attribute, or text inside a deeply-nested element that VISIBLE TEXT clipped). For Wikipedia / news / blog pages, the answer is almost always in VISIBLE TEXT — extract is rarely needed; just read and \`done\`.

MULTI-TAB / MULTI-STEP / RESEARCH TASKS — for tasks like "compare flight prices on Google Flights AND Kayak", "find the cheapest mouse on Amazon AND Best Buy", "draft an email referencing the article on TechCrunch": use \`open_tab\` to spawn a new tab, do work in it, use \`switch_tab\` to come back, and accumulate findings in extracted_data so you can reason across them at the end. \`list_tabs\` shows you all open tabs by id.

PIVOT EARLY ON MULTI-SITE TASKS — if the user's task names two or more distinct sites/services to compare or aggregate, your action sequence MUST be: (1) one extract from site A → (2) open_tab for site B IMMEDIATELY → (3) one extract from site B → (4) done. Do NOT loiter on site A re-extracting variations of the same content. The first useful extract from site A is enough — if the headline/price/title is in extracted_data, MOVE ON. Step budget is shared across sites, so wasting 20 steps on site A leaves nothing for site B.

LONG-RUNNING TASKS — you have up to 60 steps and 10 minutes per intent. For multi-step flights/booking/research flows that take a while, don't rush to declare done. After each step, check whether you've actually achieved the user's full request or just one piece of it. If you've only done part: keep going.

FOLLOW-UP HANDLING — the user may ask follow-up questions ("what about the other one?", "compare with X"). You'll receive these as new intents but with relevant context in PARAMETERS. Use list_tabs + switch_tab to revisit work you did earlier rather than starting from scratch.`;

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
      result = await this._loop();
    } catch (err) {
      result = { success: false, message: err.message || "Unexpected error" };
    }
    // On failure, append a compact debug suffix so the user (and tests) can
    // see what the agent actually did before giving up. Generic — just the
    // last few action verbs and any extracted data.
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
        result.message = `${result.message} | last:${lastSteps}${ext}`;
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

    console.log("[Anticipy Agent] finished:", result.success ? "✓" : "✗", result.message);
    return result;
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
      let action;
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

      const result = await this._executeAction(action);
      this.steps.push({ action, result, timestamp: Date.now() });

      if (action.action === "extract" && result.success && action.field) {
        this.extractedData[action.field] = result.text || "";
      }

      console.log(`  →`, result.success ? "ok" : `FAILED: ${result.error}`);

      // Human-like inter-action delay
      await this._sleep(700);
    }

    return { success: false, message: `Reached max ${MAX_STEPS} steps without completing task` };
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
      return `  ${i + 1}. ${parts.join(" ")} ${status}`;
    }).join("\n");

    const extractedStr = Object.keys(this.extractedData).length > 0
      ? JSON.stringify(this.extractedData, null, 2)
      : "(none)";

    const userMessage = [
      `TASK: ${this.intent.summary_for_user}`,
      `ACTION TYPE: ${this.intent.action_type || "browser_action"}`,
      `INTENT PARAMETERS: ${JSON.stringify(this.intent.parameters || {}, null, 2)}`,
      "",
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

  async _callLLM(userMessage) {
    // Gemini primary (higher free-tier daily quota than Groq's per-org limits),
    // Groq fallback (very fast when not rate-limited).
    const errors = [];
    if (this.apiConfig?.geminiApiKey) {
      try {
        return await this._callGemini(userMessage);
      } catch (e) {
        errors.push(`Gemini: ${e.message || e}`);
        console.warn("[Anticipy Agent] Gemini failed, trying Groq:", e.message);
      }
    }
    if (this.apiConfig?.groqApiKey) {
      try {
        return await this._callGroq(userMessage);
      } catch (e) {
        errors.push(`Groq: ${e.message || e}`);
        console.warn("[Anticipy Agent] Groq failed:", e.message);
      }
    }
    if (errors.length === 0) {
      throw new Error("No API keys configured. Sign in via the extension popup.");
    }
    throw new Error("LLM call failed — " + errors.join(" | "));
  }

  async _callGroq(userMessage) {
    const resp = await fetch(GROQ_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this.apiConfig.groqApiKey}`
      },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        messages: [
          { role: "system", content: AGENT_SYSTEM_PROMPT },
          { role: "user", content: userMessage }
        ],
        temperature: 0.1,
        max_tokens: 2000,
        response_format: { type: "json_object" }
      })
    });

    if (!resp.ok) {
      const body = await resp.text().catch(() => String(resp.status));
      throw new Error(`Groq ${resp.status}: ${body.substring(0, 200)}`);
    }

    const data = await resp.json();
    const content = data.choices?.[0]?.message?.content;
    if (!content) throw new Error("Empty response from Groq");
    return this._parseJSON(content);
  }

  async _callGemini(userMessage) {
    const resp = await fetch(
      `${GEMINI_API_URL}?key=${this.apiConfig.geminiApiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: `${AGENT_SYSTEM_PROMPT}\n\n${userMessage}` }] }],
          generationConfig: {
            temperature: 0.1,
            maxOutputTokens: 2000,
            responseMimeType: "application/json"
          }
        })
      }
    );

    if (!resp.ok) {
      const body = await resp.text().catch(() => String(resp.status));
      throw new Error(`Gemini ${resp.status}: ${body.substring(0, 200)}`);
    }

    const data = await resp.json();
    const content = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!content) throw new Error("Empty response from Gemini");
    return this._parseJSON(content);
  }

  _parseJSON(text) {
    const clean = text.trim().replace(/^```json\s*/i, "").replace(/```\s*$/, "").trim();
    try {
      return JSON.parse(clean);
    } catch {
      // Attempt to extract JSON object from surrounding prose
      const match = clean.match(/\{[\s\S]*\}/);
      if (match) return JSON.parse(match[0]);
      throw new Error("LLM response is not valid JSON: " + clean.substring(0, 200));
    }
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

  /** Construct a search URL for the current host. Returns "" if unknown. */
  _searchUrlForHost(host, query) {
    const q = encodeURIComponent(query);
    if (!q) return "";
    if (host.endsWith("google.com")) return `https://www.google.com/search?q=${q}`;
    if (host.endsWith("bing.com")) return `https://www.bing.com/search?q=${q}`;
    if (host.endsWith("duckduckgo.com")) return `https://duckduckgo.com/?q=${q}`;
    if (host.endsWith("youtube.com")) return `https://www.youtube.com/results?search_query=${q}`;
    if (host.includes("wikipedia.org")) return `https://en.wikipedia.org/w/index.php?search=${q}`;
    if (host.endsWith("amazon.com")) return `https://www.amazon.com/s?k=${q}`;
    if (host.endsWith("ebay.com")) return `https://www.ebay.com/sch/i.html?_nkw=${q}`;
    if (host.endsWith("reddit.com")) return `https://www.reddit.com/search/?q=${q}`;
    if (host.endsWith("github.com")) return `https://github.com/search?q=${q}`;
    return "";
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
