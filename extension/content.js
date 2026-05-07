// Anticipy Chrome Extension — Content Script
// Executes DOM actions inside the active tab on behalf of the BrowserAgent.
// All actions arrive as { type: "DOM_ACTION", action: { type, ...params } }.

// ─── Shadow-DOM-piercing query helpers ─────────────────────────────────────────
// Generic walkers that recurse through every open shadowRoot and same-origin
// iframe.  Closed shadow roots are made open via background.js's MAIN-world
// monkey-patch of Element.prototype.attachShadow (see registerForceOpenShadow).
// No site-specific code: works on Lit, LWC, Polymer, native web components.

function pierceQuery(selector, root) {
  root = root || document;
  try {
    const direct = root.querySelector ? root.querySelector(selector) : null;
    if (direct) return direct;
  } catch (_) {}
  const all = (root.querySelectorAll ? root.querySelectorAll("*") : []);
  for (const el of all) {
    if (el.shadowRoot) {
      const hit = pierceQuery(selector, el.shadowRoot);
      if (hit) return hit;
    }
    if (el.tagName === "IFRAME") {
      try {
        const doc = el.contentDocument;
        if (doc) {
          const hit = pierceQuery(selector, doc);
          if (hit) return hit;
        }
      } catch (_) {}
    }
  }
  return null;
}

function pierceQueryAll(selector, root) {
  root = root || document;
  const out = [];
  try {
    if (root.querySelectorAll) {
      for (const el of root.querySelectorAll(selector)) out.push(el);
    }
  } catch (_) {}
  const all = (root.querySelectorAll ? root.querySelectorAll("*") : []);
  for (const el of all) {
    if (el.shadowRoot) {
      for (const hit of pierceQueryAll(selector, el.shadowRoot)) out.push(hit);
    }
    if (el.tagName === "IFRAME") {
      try {
        const doc = el.contentDocument;
        if (doc) {
          for (const hit of pierceQueryAll(selector, doc)) out.push(hit);
        }
      } catch (_) {}
    }
  }
  return out;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "DOM_ACTION") return;

  const action = message.action;
  executeAction(action).then(sendResponse).catch((err) => {
    sendResponse({ success: false, error: err.message || String(err) });
  });

  return true; // keep channel open for async response
});

async function executeAction(action) {
  switch (action.type) {

    // ── Navigation ────────────────────────────────────────────────────────────
    case "navigate": {
      if (!action.url) return { success: false, error: "No URL provided" };
      window.location.href = action.url;
      return { success: true, message: `Navigating to ${action.url}` };
    }

    // ── Click ─────────────────────────────────────────────────────────────────
    case "click": {
      const el = findElement(action.selector, action.text, action.aria);
      if (!el) {
        return { success: false, error: `Element not found: selector="${action.selector}" text="${action.text}" aria="${action.aria}"` };
      }
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      await sleep(150);
      // Generic submit-coercion: if the clicked element is a <button> with
      // type="submit" (or no type, which defaults to submit) inside a <form>,
      // call form.requestSubmit(button) so the form's submit handler fires.
      // Plain element.click() on a button isn't always sufficient when the
      // page relies on Codex/MUI/etc. submit flows.
      const form = el.closest && el.closest("form");
      const isSubmitButton =
        el.tagName === "BUTTON" &&
        (!el.type || el.type === "submit") &&
        !!form;
      if (isSubmitButton && typeof form.requestSubmit === "function") {
        try { form.requestSubmit(el); }
        catch (_) { el.click(); }
      } else {
        el.click();
      }
      return { success: true, message: `Clicked: ${action.selector || action.text || action.aria}` };
    }

    // ── Type / Fill ───────────────────────────────────────────────────────────
    case "type":
    case "fill": {
      const input = findElement(action.selector, action.label);
      if (!input) {
        return { success: false, error: `Input not found: selector="${action.selector}" label="${action.label}"` };
      }
      fillInput(input, action.value ?? "");
      // Optional one-step submit: when the LLM passes submit:true, dispatch
      // Enter and call form.requestSubmit() so a search-style flow works in a
      // single action instead of two.
      if (action.submit === true) {
        try { input.focus(); } catch (_) {}
        const opts = { key: "Enter", code: "Enter", keyCode: 13, which: 13,
                       bubbles: true, cancelable: true, composed: true };
        input.dispatchEvent(new KeyboardEvent("keydown",  opts));
        input.dispatchEvent(new KeyboardEvent("keypress", opts));
        input.dispatchEvent(new KeyboardEvent("keyup",    opts));
        const form = input.closest && input.closest("form");
        if (form && typeof form.requestSubmit === "function") {
          try { form.requestSubmit(); } catch (_) {}
        }
      }
      return { success: true, message: `Typed into: ${action.selector || action.label}${action.submit ? " + submit" : ""}` };
    }

    // ── Keypress ──────────────────────────────────────────────────────────────
    case "keypress": {
      const target = action.selector ? pierceQuery(action.selector) : document.activeElement;
      const el = target || document.body;
      try { el.focus && el.focus(); } catch (_) {}
      const key = action.key;
      // Map common key names to keyCode for sites that listen on keyCode
      const keyCode = key === "Enter" ? 13
        : key === "Tab" ? 9
        : key === "Escape" ? 27
        : key === "Backspace" ? 8
        : key === " " || key === "Space" ? 32
        : key && key.length === 1 ? key.charCodeAt(0)
        : 0;
      const opts = { key, code: key, keyCode, which: keyCode, bubbles: true, cancelable: true, composed: true };
      el.dispatchEvent(new KeyboardEvent("keydown",  opts));
      el.dispatchEvent(new KeyboardEvent("keypress", opts));
      el.dispatchEvent(new KeyboardEvent("keyup",    opts));
      // Generic Enter-on-input → submit-the-form fallback. Many SPA forms
      // listen to "submit" on the form rather than "keypress" on the input;
      // if the keydown didn't trigger a submit handler, calling
      // form.requestSubmit() ensures the form's normal submit path runs.
      if (key === "Enter") {
        const form = el.closest && el.closest("form");
        if (form && typeof form.requestSubmit === "function") {
          try { form.requestSubmit(); } catch (_) {}
        }
      }
      return { success: true, message: `Key "${action.key}" pressed` };
    }

    // ── Scroll ────────────────────────────────────────────────────────────────
    case "scroll": {
      const amount = action.amount || 500;
      window.scrollBy({ top: action.direction === "up" ? -amount : amount, behavior: "smooth" });
      return { success: true, message: `Scrolled ${action.direction || "down"} ${amount}px` };
    }

    // ── Read text ─────────────────────────────────────────────────────────────
    case "read_text": {
      const el = action.selector ? pierceQuery(action.selector) : document.body;
      return {
        success: true,
        text: (el?.innerText || el?.textContent || "").trim().substring(0, 5000)
      };
    }

    // ── Wait for element ──────────────────────────────────────────────────────
    case "waitForElement": {
      const timeout = action.timeout || 8000;
      const found = await waitForSelector(action.selector, timeout);
      return found
        ? { success: true, message: `Element appeared: ${action.selector}` }
        : { success: false, error: `Timeout: "${action.selector}" did not appear in ${timeout}ms` };
    }

    // ── Full page state (for the agent's context window) ──────────────────────
    case "getPageState": {
      const visibleText = getVisibleText();
      const elements = getInteractiveElements();
      return {
        success: true,
        data: {
          url: window.location.href,
          title: document.title,
          visibleText,
          elements
        }
      };
    }

    // ── Legacy: get_page_info (kept for backwards compat) ─────────────────────
    case "get_page_info": {
      return {
        success: true,
        data: { url: window.location.href, title: document.title, domain: window.location.hostname }
      };
    }

    // (legacy add_todo removed — the LLM agent is expected to compose generic
    //  click + type actions to add a todo on any site, with no per-site keyword
    //  hints. Hardcoded placeholder substrings are a violation of the project
    //  rule against hardcoding / regex / keyword tables.)

    // ── force_type: write value via native setter even if `type` snapped back ──
    case "force_type": {
      const input = findElement(action.selector, action.label);
      if (!input) {
        return { success: false, error: `Input not found: selector="${action.selector}" label="${action.label}"` };
      }
      forceTypeInto(input, action.value ?? "");
      return { success: true, message: `Force-typed into: ${action.selector || action.label}` };
    }

    // ── canvas_type: focus an offscreen contenteditable and use insertText ────
    // Generic: works for Google Docs/Sheets/Slides (via the
    // .docs-texteventtarget-iframe pattern) and for any other page that uses an
    // offscreen contenteditable for canvas-rendered text input.
    case "canvas_type": {
      const ok = await canvasInsertText(action.text || "");
      return ok
        ? { success: true, message: `Inserted ${(action.text||"").length} chars into canvas editor` }
        : { success: false, error: "No canvas-editor target found" };
    }

    // ── canvas_pointer: PointerEvent at viewport coords for WebGL/canvas ──────
    case "canvas_pointer": {
      const { x, y, button, clickCount } = action;
      if (typeof x !== "number" || typeof y !== "number") {
        return { success: false, error: "canvas_pointer needs numeric x,y" };
      }
      dispatchCanvasPointer(x, y, button || "left", clickCount || 1);
      return { success: true, message: `Pointer at (${x},${y})` };
    }

    // ── wait_for: page-level wait. Resolves when ANY supplied condition met ───
    case "wait_for": {
      const t0 = Date.now();
      const deadline = t0 + (action.timeout || 15000);
      while (Date.now() < deadline) {
        let matched = null;
        if (action.url && location.href.includes(action.url)) matched = "url";
        else if (action.selector && pierceQuery(action.selector)) matched = "selector";
        else if (action.text && findByVisibleText(action.text, "")) matched = "text";
        else if (action.idle === true) {
          // Cheap idle proxy: no in-flight fetch/XHR for the next 500ms
          await sleep(500);
          // If the document.readyState is complete and no <img> is still loading
          if (document.readyState === "complete") matched = "idle";
        }
        if (matched) return { success: true, message: `wait_for: ${matched} after ${Date.now()-t0}ms` };
        await sleep(250);
      }
      return { success: false, error: `wait_for timeout after ${Date.now()-t0}ms` };
    }

    // ── dismiss_modal: best-effort generic consent / cookie / overlay close ───
    // No per-site keywords; ranks candidates by visible-text affinity for
    // common confirm/dismiss verbs, which generalize across most modal UI.
    case "dismiss_modal": {
      const dismissed = dismissAnyModal();
      return dismissed
        ? { success: true, message: `Dismissed: ${dismissed}` }
        : { success: false, error: "No dismissable modal found" };
    }

    // ── pierce_query: find an element by visible text across shadow + iframes ─
    case "pierce_query": {
      const hit = findByVisibleText(action.text || "", action.role || "");
      if (!hit) return { success: false, error: "No element with that visible text" };
      const r = hit.getBoundingClientRect();
      return {
        success: true,
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2),
        tag: hit.tagName.toLowerCase(),
        role: hit.getAttribute("role") || ""
      };
    }

    default:
      return { success: false, error: `Unknown action type: ${action.type}` };
  }
}

// ─── Element finding ──────────────────────────────────────────────────────────

/**
 * Find an element using multiple strategies in priority order:
 * 1. CSS selector (pierces open shadow roots + same-origin iframes)
 * 2. Visible text content (for buttons/links/labels)
 * 3. aria-label
 * 4. placeholder
 */
function findElement(selector, text, aria) {
  // 1. CSS selector — pierce shadow + iframes
  if (selector) {
    const el = pierceQuery(selector);
    if (el && isVisible(el)) return el;
    if (el) return el;
  }

  const interactable = "a, button, input, textarea, select, label, [role='button'], [role='link'], [role='menuitem'], [role='option'], [role='tab'], [tabindex]";

  // 2. Visible text match
  if (text) {
    const needle = text.toLowerCase().trim();
    for (const el of pierceQueryAll(interactable)) {
      const elText = (el.textContent || el.value || "").trim().toLowerCase();
      if (elText.includes(needle)) return el;
    }
  }

  // 3. aria-label match
  if (aria) {
    const needle = aria.toLowerCase().trim();
    for (const el of pierceQueryAll(interactable)) {
      const label = (el.getAttribute("aria-label") || "").toLowerCase();
      if (label.includes(needle)) return el;
    }
  }

  // 4. placeholder match (useful when only label/text is known)
  if (text) {
    const needle = text.toLowerCase().trim();
    for (const el of pierceQueryAll("input, textarea")) {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const titleAttr = (el.getAttribute("title") || "").toLowerCase();
      if (ph.includes(needle) || titleAttr.includes(needle)) return el;
    }
  }

  return null;
}

// Best-effort generic modal dismissal. Walks all visible interactive
// elements (pierces shadow + iframes), scores them by how likely they are a
// "confirm/dismiss/close" affordance using common verbs that generalize
// across cookie banners, GDPR consent, paywalls, intro modals, and so on.
// Returns the matched label string (truthy) on click, "" on no match.
//
// Generic: this function uses common UI verbs as relevance hints, NOT a
// per-site whitelist. The agent prompt explicitly tells the LLM to fall
// back to clicking specific text via the `click` action when this returns
// no match.
function dismissAnyModal() {
  const VERBS = [
    "accept all", "accept cookies", "accept", "agree", "i agree", "i accept",
    "got it", "ok", "okay", "continue", "confirm", "allow",
    "dismiss", "close", "no thanks", "not now", "skip", "later", "maybe later",
  ];
  const interactable = "button, a, [role='button'], input[type='button'], input[type='submit']";
  const candidates = [];
  for (const el of pierceQueryAll(interactable)) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    const txt = ((el.innerText || el.value || el.getAttribute("aria-label") || "")
                  .trim().toLowerCase());
    if (!txt || txt.length > 60) continue;
    let score = 0;
    for (const v of VERBS) {
      if (txt === v) { score = 100; break; }
      if (txt.includes(v)) { score = Math.max(score, 50); }
    }
    // Higher z-index → more likely a modal overlay
    const z = parseInt(window.getComputedStyle(el).zIndex || "0", 10) || 0;
    if (z > 100) score += 5;
    // Aria-label / role hints
    if ((el.getAttribute("aria-label") || "").toLowerCase().includes("close")) score += 30;
    if ((el.getAttribute("role") || "") === "button") score += 5;
    if (score > 0) candidates.push({ el, score, txt });
  }
  if (candidates.length === 0) return "";
  candidates.sort((a, b) => b.score - a.score);
  const winner = candidates[0];
  try {
    winner.el.scrollIntoView({ block: "center" });
    winner.el.click();
  } catch (_) {}
  return winner.txt || "(unlabeled)";
}

// Find any element by visible text (for the LLM's pierce_query action).
// Pierces shadow + same-origin iframes; matches whole-word or substring.
function findByVisibleText(needle, role) {
  const target = (needle || "").trim().toLowerCase();
  if (!target) return null;
  const want = (role || "").toLowerCase();
  let best = null;
  let bestLen = Infinity;
  for (const el of pierceQueryAll("*")) {
    const txt = (el.innerText || el.textContent || "").trim().toLowerCase();
    if (!txt) continue;
    if (txt === target || (txt.length < 200 && txt.includes(target))) {
      if (want && (el.getAttribute("role") || "").toLowerCase() !== want) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (txt.length < bestLen) { best = el; bestLen = txt.length; }
    }
  }
  return best;
}

// ─── Input filling (React / Vue / plain HTML compatible) ──────────────────────

function fillInput(input, value) {
  input.focus();

  // Use the native setter so React's synthetic event system picks up the change
  const nativeSetter =
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set ||
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;

  if (nativeSetter) {
    nativeSetter.call(input, value);
  } else {
    input.value = value;
  }

  input.dispatchEvent(new Event("input",  { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

// ─── force_type fallback (when type doesn't visibly stick) ────────────────────
// Explicit "really write the value" path: writes via native setter, dispatches
// the broader event sequence (input + change + keyup), useful for autocomplete
// inputs that listen to keyup or for inputs whose React state didn't update on
// the first try.
function forceTypeInto(input, value) {
  try { input.focus(); } catch (_) {}
  const proto = (input instanceof HTMLTextAreaElement)
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  if (desc && desc.set) {
    desc.set.call(input, value);
  } else {
    input.value = value;
  }
  input.dispatchEvent(new Event("input",  { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  // keyup: many autocompletes only react to keyboard-style events
  input.dispatchEvent(new KeyboardEvent("keyup", {
    bubbles: true, key: value.slice(-1) || "End", cancelable: true,
  }));
}

// ─── Canvas-editor typing (Google Docs / Sheets / Slides + similar) ───────────
// Strategy:
//  1. Walk same-origin frames looking for `iframe.docs-texteventtarget-iframe`;
//     focus the inner contenteditable. (Standard Google Editors path.)
//  2. If that's not present, fall back to whatever element is currently
//     `document.activeElement` if it's a contenteditable. (Generic editors.)
//  3. Use document.execCommand('insertText') in the focused document — this
//     dispatches a `beforeinput(insertText)` + `input` sequence that
//     canvas-rendered editors accept the same way they accept emoji-picker /
//     IME composition input.  Falls back to inserting at selection if
//     execCommand isn't supported.
async function canvasInsertText(text) {
  const target = locateDocsEditTarget(document) || activeContenteditable();
  if (!target) return false;
  try { target.element.focus(); } catch (_) {}
  const doc = target.doc || document;
  // Use execCommand inside the same document the contenteditable lives in
  let ok = false;
  try {
    ok = doc.execCommand("insertText", false, text);
  } catch (_) {}
  if (!ok) {
    // Manual fallback: collapse selection inside the editable and insert text
    try {
      const sel = doc.getSelection();
      if (sel && sel.rangeCount === 0) {
        const r = doc.createRange();
        r.selectNodeContents(target.element);
        r.collapse(false);
        sel.addRange(r);
      }
      doc.execCommand("insertHTML", false, escapeHtml(text));
      ok = true;
    } catch (_) {
      ok = false;
    }
  }
  return ok;
}

function locateDocsEditTarget(doc) {
  if (!doc) return null;
  let f;
  try { f = doc.querySelector("iframe.docs-texteventtarget-iframe"); } catch (_) {}
  if (f) {
    try {
      const cd = f.contentDocument;
      if (cd) {
        const ce = cd.querySelector('[contenteditable="true"]');
        if (ce) return { element: ce, doc: cd };
      }
    } catch (_) {}
  }
  let frames = [];
  try { frames = doc.querySelectorAll("iframe"); } catch (_) {}
  for (const fr of frames) {
    try {
      const inner = fr.contentDocument && locateDocsEditTarget(fr.contentDocument);
      if (inner) return inner;
    } catch (_) {}
  }
  return null;
}

function activeContenteditable() {
  const el = document.activeElement;
  if (el && el.isContentEditable) return { element: el, doc: document };
  return null;
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ─── WebGL/canvas pointer dispatch ────────────────────────────────────────────
// Synthesized pointer events at viewport coords. isTrusted will be false from
// content-script context (only chrome.debugger gives trusted), but most WebGL
// libs and map widgets accept synthetic pointerdown/pointerup just fine. DPR
// scaling: coords come from the LLM looking at a screenshot; CSS pixels.
function dispatchCanvasPointer(x, y, button, clickCount) {
  const ratio = window.devicePixelRatio || 1;
  // Coords from the LLM's screenshot are in CSS pixels in our pipeline already,
  // but accept device pixels too: if the value looks larger than the viewport
  // by an integer ratio, scale it back.
  const cx = (x > window.innerWidth && Math.abs(x - window.innerWidth * ratio) < 4)
    ? x / ratio : x;
  const cy = (y > window.innerHeight && Math.abs(y - window.innerHeight * ratio) < 4)
    ? y / ratio : y;
  const target = document.elementFromPoint(cx, cy) || document.body;
  const buttonCode = button === "right" ? 2 : button === "middle" ? 1 : 0;
  const base = {
    bubbles: true, cancelable: true, composed: true,
    clientX: cx, clientY: cy, button: buttonCode, buttons: 1, detail: clickCount,
    pointerType: "mouse", pointerId: 1, isPrimary: true,
  };
  for (const t of ["pointerover", "pointerenter", "mouseover", "mouseenter",
                    "pointermove", "mousemove",
                    "pointerdown", "mousedown",
                    "pointerup",   "mouseup",
                    "click"]) {
    try {
      const Cls = t.startsWith("pointer") ? PointerEvent
                : t === "click" ? MouseEvent
                : MouseEvent;
      target.dispatchEvent(new Cls(t, base));
    } catch (_) {}
  }
}

// ─── Wait for selector ────────────────────────────────────────────────────────

function waitForSelector(selector, timeout) {
  return new Promise((resolve) => {
    if (pierceQuery(selector)) { resolve(true); return; }

    const observer = new MutationObserver(() => {
      if (pierceQuery(selector)) {
        observer.disconnect();
        resolve(true);
      }
    });
    observer.observe(document.body, {
      childList: true, subtree: true,
      attributes: true, characterData: true,
    });
    setTimeout(() => { observer.disconnect(); resolve(false); }, timeout);
  });
}

// ─── Page state extraction ────────────────────────────────────────────────────

function getVisibleText() {
  // Walk the DOM and collect visible text, skipping script/style/hidden nodes
  const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        const tag = parent.tagName;
        if (["SCRIPT", "STYLE", "NOSCRIPT", "META", "HEAD"].includes(tag)) return NodeFilter.FILTER_REJECT;
        const style = window.getComputedStyle(parent);
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return NodeFilter.FILTER_REJECT;
        const text = node.textContent?.trim();
        if (!text) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    }
  );

  const parts = [];
  let node;
  while ((node = walker.nextNode())) {
    const t = node.textContent.trim();
    if (t) parts.push(t);
    if (parts.join(" ").length > 4000) break;
  }
  return parts.join(" ").replace(/\s{3,}/g, "  ");
}

function getInteractiveElements() {
  const elements = [];
  const seen = new Set();

  const SELECTOR =
    'button, input:not([type="hidden"]), textarea, select, a[href], ' +
    '[role="button"], [role="link"], [role="textbox"], [role="combobox"], [role="checkbox"], [role="radio"], ' +
    '[contenteditable="true"], canvas';
  const candidates = pierceQueryAll(SELECTOR);

  for (const el of candidates) {
    if (!isVisible(el)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;

    const sel = getBestSelector(el);
    if (seen.has(sel)) continue;
    seen.add(sel);

    elements.push({
      tag: el.tagName.toLowerCase(),
      type: el.type || el.getAttribute("role") || "",
      id: el.id || "",
      name: el.getAttribute("name") || "",
      text: (el.textContent || el.value || "").trim().substring(0, 80),
      placeholder: el.getAttribute("placeholder") || "",
      aria: el.getAttribute("aria-label") || "",
      href: el.tagName === "A" ? (el.getAttribute("href") || "") : "",
      selector: sel,
      // Hint for the LLM that this surface needs vision/coordinate strategies:
      isCanvas: el.tagName === "CANVAS",
    });

    if (elements.length >= 80) break;
  }

  // If the page extracted ZERO interactive DOM elements but the user can
  // clearly see a UI in the screenshot, this signal lets the LLM switch to
  // canvas_pointer / pierce_query / canvas_type instead of looping forever.
  return elements;
}

function isVisible(el) {
  if (!el.offsetParent && el.tagName !== "BODY") return false;
  const style = window.getComputedStyle(el);
  return style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
}

function getBestSelector(el) {
  // id
  if (el.id) return `#${CSS.escape(el.id)}`;
  // name attribute
  const name = el.getAttribute("name");
  if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
  // data-testid
  const testId = el.getAttribute("data-testid");
  if (testId) return `[data-testid="${testId}"]`;
  // aria-label
  const aria = el.getAttribute("aria-label");
  if (aria) return `[aria-label="${aria}"]`;
  // class-based (first class only, sanitized)
  const cls = el.className?.toString().split(/\s+/).find(c => c && !/^\d/.test(c));
  if (cls) return `${el.tagName.toLowerCase()}.${CSS.escape(cls)}`;
  // fallback: tag
  return el.tagName.toLowerCase();
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Announce readiness + ask background to inject the MAIN-world shadow-open
// patch into this tab. Backstop in case persistent registerContentScripts
// didn't beat the page's own scripts to it.
try {
  chrome.runtime.sendMessage({ type: "CONTENT_SCRIPT_READY", url: window.location.href });
} catch {
  // Extension context may be invalidated — ignore
}
try {
  chrome.runtime.sendMessage({ type: "INJECT_SHADOW_PATCH" });
} catch {}
