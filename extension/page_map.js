// Anticipy page mapper — injected into the page to build an indexed map of
// interactive elements (same mechanic as Claude in Chrome's accessibility
// tree and browser-use's element index). Sensitive values are redacted
// before anything leaves the page.
(() => {
  window.__anticipyMap = {};
  let counter = 0;

  const SENSITIVE_AUTOCOMPLETE = [
    "current-password", "new-password", "one-time-code",
    "cc-number", "cc-csc", "cc-exp", "cc-exp-month", "cc-exp-year",
  ];

  function isSensitive(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "password" || type === "hidden") return true;
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    return SENSITIVE_AUTOCOMPLETE.some((k) => ac.includes(k));
  }

  function role(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute("type");
    const map = {
      a: "link", button: "button", select: "combobox", textarea: "textbox",
      input: type === "submit" || type === "button" ? "button"
        : type === "checkbox" ? "checkbox" : type === "radio" ? "radio" : "textbox",
    };
    return map[tag] || tag;
  }

  function label(el) {
    if (isSensitive(el)) {
      const aria = el.getAttribute("aria-label");
      if (aria) return aria.trim();
      return el.value ? "[value redacted]" : (el.getAttribute("placeholder") || "").trim();
    }
    for (const attr of ["aria-label", "placeholder", "title", "alt"]) {
      const v = el.getAttribute(attr);
      if (v && v.trim()) return v.trim();
    }
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l && l.textContent.trim()) return l.textContent.trim();
    }
    const text = (el.innerText || el.value || "").trim().replace(/\s+/g, " ");
    return text.length > 80 ? text.slice(0, 80) + "..." : text;
  }

  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const st = getComputedStyle(el);
    return st.visibility !== "hidden" && st.display !== "none";
  }

  /// When a date picker / dialog is open, that IS the page as far as the
  /// person is concerned. Mapping the whole document instead spends the
  /// element budget on the header and nav and can truncate the calendar out
  /// entirely — which is exactly why party size (a plain dropdown) worked and
  /// choosing a date did not.
  function activeOverlay() {
    const candidates = [...document.querySelectorAll(
      '[role=dialog],[aria-modal=true],dialog[open],[role=listbox],[role=grid],[role=application]')]
      .filter((el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 80 || r.height < 60) return false;
        const st = getComputedStyle(el);
        return st.visibility !== "hidden" && st.display !== "none" && st.opacity !== "0";
      });
    if (!candidates.length) return null;
    // The one on top: deepest in the DOM wins ties.
    return candidates.sort((a, b) => {
      const za = +getComputedStyle(a).zIndex || 0, zb = +getComputedStyle(b).zIndex || 0;
      return zb - za || (a.contains(b) ? 1 : -1);
    })[0];
  }

  /// State a calendar cell carries but a bare label hides: is this day
  /// selectable, is it already chosen, what date does it actually mean.
  function stateOf(el) {
    const bits = [];
    const disabled = el.disabled || el.getAttribute("aria-disabled") === "true"
      || el.getAttribute("data-disabled") === "true"
      || getComputedStyle(el).pointerEvents === "none";
    if (disabled) bits.push("UNAVAILABLE");
    if (el.getAttribute("aria-selected") === "true" || el.getAttribute("aria-checked") === "true"
        || el.getAttribute("aria-current") === "date") bits.push("selected");
    for (const attr of ["data-date", "data-day", "data-time", "data-value", "datetime", "value"]) {
      const v = el.getAttribute && el.getAttribute(attr);
      if (v && v.length <= 32) { bits.push(`${attr}=${v}`); break; }
    }
    return bits.length ? ` [${bits.join(" ")}]` : "";
  }

  window.__anticipyMapPage = () => {
    window.__anticipyMap = {};
    counter = 0;
    const lines = [];
    const sel = "a[href], button, input, select, textarea, [role=button], [role=link], " +
      "[role=option], [role=gridcell], [role=menuitem], [role=tab], [onclick], [tabindex]";
    // Scope to the open dialog/calendar when there is one, so the budget is
    // spent on what the person is actually looking at.
    const overlay = activeOverlay();
    const root = overlay || document;
    const found = [...root.querySelectorAll(sel)];
    // Elements the user can actually see come first, so a truncation can
    // never hide the thing on screen behind a hundred footer links.
    const vh = window.innerHeight || 800;
    const inView = (el) => { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < vh; };
    found.sort((a, b) => (inView(b) ? 1 : 0) - (inView(a) ? 1 : 0));
    for (const el of found) {
      if (!visible(el)) continue;
      const idx = counter++;
      window.__anticipyMap[idx] = el;
      const r = el.getBoundingClientRect();
      let extra = "";
      // Sensitivity FIRST: label() redacts these, and dumping their options
      // or current value here would leak exactly what it protects — a saved
      // card expiry or date of birth would reach the model on the same line.
      if (isSensitive(el)) {
        extra = " (sensitive field — never fill)";
      } else if (el.tagName === "SELECT") {
        const opts = [...el.options].slice(0, 12).map((o) =>
          `"${(o.textContent || o.value).trim().slice(0, 40)}"${o.selected ? "*" : ""}`);
        extra = ` (use select action; options: ${opts.join(", ")}${el.options.length > 12 ? ", …" : ""})`;
      } else if (el.tagName === "INPUT" && ["date", "month", "time", "datetime-local"].includes((el.type || "").toLowerCase())) {
        // Name the EXACT format for each type: "value" is not a format, and a
        // near-miss silently blanks the field rather than failing loudly.
        const t = (el.type || "").toLowerCase();
        const fmt = t === "date" ? "YYYY-MM-DD" : t === "month" ? "YYYY-MM"
          : t === "time" ? "HH:MM" : "YYYY-MM-DDTHH:MM";
        extra = ` (${t} field — use select action with option in the exact format ${fmt}${el.value ? `; currently "${el.value}"` : ""})`;
      }
      lines.push(`[${idx}] <${role(el)}> ${label(el)}${stateOf(el)}${extra} @(${Math.round(r.x + r.width / 2)},${Math.round(r.y + r.height / 2)})`);
      // 400, not 150: a booking page spends the first hundred on nav and menu
      // links, and the calendar was being truncated out of the map entirely.
      if (counter > 400) break;
    }
    const title = document.title;
    const bodyText = ((overlay || document.body).innerText || "").replace(/\s+/g, " ").slice(0, 1500);
    return { url: location.href, title, elements: lines.join("\n"), text: bodyText,
             overlay: !!overlay };
  };

  function activeEditable() {
    const a = document.activeElement;
    if (!a) return null;
    if (a.isContentEditable) return a;
    const tag = a.tagName;
    if (tag === "TEXTAREA") return a;
    if (tag === "INPUT" && !["submit", "button", "checkbox", "radio", "hidden", "file"].includes((a.type || "").toLowerCase())) return a;
    return null;
  }

  window.__anticipyFocus = (idx) => {
    // Dialog pattern (Google Flights et al.): clicking the visible combobox
    // opens an overlay whose REAL input the page focuses itself. If an
    // editable input already has focus, keep it — refocusing the mapped
    // element would send keystrokes to the dead placeholder box.
    if (activeEditable()) return true;
    const el = window.__anticipyMap[idx];
    if (!el) return false;
    try { el.focus(); } catch (e) { return false; }
    return document.activeElement === el;
  };

  window.__anticipyClear = (idx) => {
    const el = activeEditable() || window.__anticipyMap[idx];
    if (!el) return false;
    try {
      el.focus();
      if ("value" in el) {
        el.value = "";
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else if (el.isContentEditable) {
        el.textContent = "";
      }
    } catch (e) { return false; }
    return true;
  };

  // After typing into an autocomplete field, the suggestion dropdown is a
  // freshly-rendered listbox. Surface its options so the agent can pick one
  // instead of re-typing into the same box forever.
  window.__anticipySuggestions = () => {
    const opts = [];
    const nodes = document.querySelectorAll(
      "[role=option], [role=listbox] li, .pac-item, ul[role=listbox] [role=option], li[role=option]");
    for (const n of nodes) {
      const r = n.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      const st = getComputedStyle(n);
      if (st.visibility === "hidden" || st.display === "none") continue;
      const idx = counter++;
      window.__anticipyMap[idx] = n;
      const t = (n.innerText || n.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80);
      // Trip-type / passenger dropdowns also use role=option; they pollute
      // the airport suggestion list and mislead the picker.
      if (/^(round.?trip|one.?way|multi.?city|\d+\s*(adult|child|traveler|passenger))/i.test(t)) { counter--; delete window.__anticipyMap[idx]; continue; }
      const picked = n.getAttribute("aria-selected") === "true" || n.getAttribute("aria-checked") === "true" ||
        !!n.querySelector('[aria-checked="true"], [aria-selected="true"], input:checked');
      opts.push(`[${idx}] <option> ${t}${picked ? " (ALREADY SELECTED — do NOT click again)" : ""} @(${Math.round(r.x + r.width / 2)},${Math.round(r.y + r.height / 2)})`);
      if (opts.length > 12) break;
    }
    return opts.join("\n");
  };

  window.__anticipyCenter = (idx) => {
    const el = window.__anticipyMap[idx];
    if (!el) return null;
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  };
})();
