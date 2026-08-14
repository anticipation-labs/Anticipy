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

  // Web components often expose a labelled host while putting the real
  // button/input inside an open shadow root. Keep the host as the stable map
  // identity, but operate the generic interactive descendant a human can
  // actually click. No component or site names are needed.
  function actionable(el) {
    if (!el || !el.shadowRoot) return el;
    return el.shadowRoot.querySelector(
      'button,input,select,textarea,a[href],[role="button"],[role="link"],[tabindex]') || el;
  }

  // Give the planner enough URL identity to distinguish two same-label links
  // without exposing query strings, fragments, credentials, or tracking
  // tokens. This is especially useful on result pages where an exact title
  // can point back to a document that already failed verification.
  function displayHref(el) {
    const target = actionable(el);
    const raw = target?.href || el?.href || "";
    if (!raw) return "";
    try {
      const url = new URL(String(raw), location.href);
      if (url.protocol !== "http:" && url.protocol !== "https:") return "";
      return `${url.protocol}//${url.host}${url.pathname}`.slice(0, 300);
    } catch (_) { return ""; }
  }

  /// When a date picker / dialog is open, that IS the page as far as the
  /// person is concerned. Mapping the whole document instead spends the
  /// element budget on the header and nav and can truncate the calendar out
  /// entirely — which is exactly why party size (a plain dropdown) worked and
  /// choosing a date did not.
  function activeOverlay() {
    // A bare role=application is not an overlay. Video players, maps and
    // rich document surfaces commonly use it while remaining ordinary page
    // content. Treating one as a dialog hid the entire surrounding page and
    // reduced a pricing page to the video's "0 seconds" accessibility text.
    // A real picker grid nested in an application is still discovered by the
    // role=grid candidate below, then expanded to its application shell.
    const candidates = [...document.querySelectorAll(
      '[role=dialog],[aria-modal=true],dialog[open],[role=grid]')]
      .filter((el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 80 || r.height < 60) return false;
        const st = getComputedStyle(el);
        return st.visibility !== "hidden" && st.display !== "none" && st.opacity !== "0";
      });
    if (!candidates.length) return null;
    // The one on top: deepest in the DOM wins ties.
    const chosen = candidates.sort((a, b) => {
      const za = +getComputedStyle(a).zIndex || 0, zb = +getComputedStyle(b).zIndex || 0;
      return zb - za || (a.contains(b) ? 1 : -1);
    })[0];
    // A date grid is often nested inside a date-picker shell whose Previous /
    // Next month controls are siblings. Returning the grid alone makes future
    // dates literally unreachable. Prefer the smallest enclosing dialog, or
    // a nearby shell with a semantic month-navigation control.
    if (chosen.getAttribute("role") === "grid") {
      const dialog = chosen.closest('[role=dialog],[aria-modal=true],dialog[open],[role=application]');
      if (dialog) return dialog;
      let shell = chosen.parentElement;
      for (let depth = 0; shell && shell !== document.body && depth < 5;
           depth++, shell = shell.parentElement) {
        const outsideButtons = [...shell.querySelectorAll('button,[role=button]')]
          .filter((button) => !chosen.contains(button) && visible(button));
        if (outsideButtons.some((button) =>
          /\b(next|previous|prev)\b.*\b(month|calendar)\b|\b(month|calendar)\b.*\b(next|previous|prev)\b/i
            .test(label(button)))) return shell;
      }
    }
    return chosen;
  }

  // Recover the missing month context for calendars whose day buttons say
  // only "17". This uses nearby DOM text/ARIA structure, not a site selector.
  // The resulting map line says calendar=September 17, allowing both the
  // model and the mechanical date guard to distinguish identical day numbers.
  function calendarDateOf(el) {
    const own = label(el).replace(/\s+\$[\d,.]+.*$/, "").trim();
    const direct = own.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([12]?\d|3[01])(?:,?\s+(20\d{2}))?\b/i);
    if (direct) return `${direct[1]} ${Number(direct[2])}${direct[3] ? `, ${direct[3]}` : ""}`;
    const day = own.match(/^([12]?\d|3[01])(?:\s|$)/);
    if (!day || !el.closest('[role=grid],[role=dialog],[aria-modal=true],[class*="calendar" i],[class*="date" i]')) return "";
    let node = el.parentElement;
    for (let depth = 0; node && node !== document.body && depth < 8;
         depth++, node = node.parentElement) {
      const text = String(node.innerText || node.getAttribute("aria-label") || "")
        .replace(/\s+/g, " ").trim();
      if (!text || text.length > 2200) continue;
      const months = [...text.matchAll(/\b(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+(20\d{2}))?\b/gi)];
      const unique = [...new Set(months.map((match) => match[1].toLowerCase()))];
      if (unique.length !== 1) continue;
      const month = months[0][1];
      const year = months.find((match) => match[2])?.[2] || "";
      return `${month} ${Number(day[1])}${year ? `, ${year}` : ""}`;
    }
    return "";
  }

  /// State a calendar cell carries but a bare label hides: is this day
  /// selectable, is it already chosen, what date does it actually mean.
  function stateOf(el) {
    const bits = [];
    const disabled = el.disabled || el.getAttribute("aria-disabled") === "true"
      || el.getAttribute("data-disabled") === "true"
      || getComputedStyle(el).pointerEvents === "none";
    if (disabled) bits.push("UNAVAILABLE");
    const nativeCheck = el instanceof HTMLInputElement
      && ["checkbox", "radio"].includes((el.type || "").toLowerCase());
    if (nativeCheck) bits.push(el.checked ? "checked" : "unchecked");
    else if (el.getAttribute("aria-selected") === "true" || el.getAttribute("aria-checked") === "true"
        || el.getAttribute("aria-current") === "date") bits.push("selected");
    for (const attr of ["data-date", "data-day", "data-time", "data-value", "datetime", "value"]) {
      const v = el.getAttribute && el.getAttribute(attr);
      if (v && v.length <= 32) { bits.push(`${attr}=${v}`); break; }
    }
    const calendarDate = calendarDateOf(el);
    if (calendarDate) bits.push(`calendar=${calendarDate}`);
    return bits.length ? ` [${bits.join(" ")}]` : "";
  }

  // A document's first few thousand characters are usually navigation and
  // the top of the page. Keeping only that prefix made scrolling useless for
  // exact-text research: the owner could be looking directly at an hours,
  // price or availability section while the model still received the header.
  // Keep a small orientation prefix, then spend most of the text budget on
  // semantic blocks that intersect the actual viewport. This is generic DOM
  // geometry, with no knowledge of any site or requested field.
  function joinTypographicMoney(before, raised) {
    const left = String(before || "").replace(/\s+/g, " ").trim();
    const cents = String(raised || "").replace(/\s+/g, "").replace(/^\./, "");
    if (!/^\d{1,2}$/.test(cents)) return "";
    const match = left.match(/((?:US|CA|AU|NZ)?[$€£¥]\s*\d[\d,]*)$/i);
    return match ? `${match[1]}.${cents}` : "";
  }
  // Exposed for a tiny pure regression test. Some sites render cents as a
  // raised child ("$14" + <sup>"16"</sup>); innerText fuses that into
  // "$1416", which is not the number a person sees.
  window.__anticipyJoinTypographicMoney = joinTypographicMoney;

  function typographicMoneyValues(root) {
    const values = [];
    for (const raised of root.querySelectorAll('sup')) {
      if (!visible(raised) || !raised.parentElement) continue;
      let before = "";
      try {
        const range = document.createRange();
        range.selectNodeContents(raised.parentElement);
        range.setEndBefore(raised);
        before = range.toString().slice(-40);
      } catch (_) { continue; }
      const value = joinTypographicMoney(before, raised.textContent);
      if (value && !values.includes(value)) values.push(value);
      if (values.length >= 20) break;
    }
    return values;
  }

  function pageText(root, overlay) {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const full = normalize((overlay || document.body).innerText);
    const typography = typographicMoneyValues(root);
    const withTypography = (value) => typography.length
      ? `${String(value || "").slice(0, 5600)}\nTYPOGRAPHIC VALUES: ${typography.join(" ")}`.slice(0, 6000)
      : String(value || "").slice(0, 6000);
    if (overlay) return withTypography(full);
    const vh = window.innerHeight || 800;
    const vw = window.innerWidth || 1200;
    const blocks = [...root.querySelectorAll(
      'h1,h2,h3,h4,h5,h6,p,li,dt,dd,td,th,pre,blockquote,address,figcaption')];
    const seen = new Set();
    const visible = [];
    for (const block of blocks) {
      const r = block.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || r.bottom <= 0 || r.top >= vh
          || r.right <= 0 || r.left >= vw) continue;
      const st = getComputedStyle(block);
      if (st.visibility === "hidden" || st.display === "none" || st.opacity === "0") continue;
      const text = normalize(block.innerText || block.textContent);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      visible.push(text);
      if (visible.join(" ").length >= 5000) break;
    }
    const viewport = visible.join(" ").slice(0, 5000);
    const orientation = full.slice(0, 900);
    return withTypography(viewport && !orientation.includes(viewport)
      ? `PAGE START: ${orientation}\nVISIBLE VIEWPORT: ${viewport}`
      : full);
  }

  window.__anticipyMapPage = () => {
    window.__anticipyMap = {};
    counter = 0;
    const lines = [];
    const fields = [];
    const sel = "a[href], button, input, select, textarea, [role=button], [role=link], " +
      "[role=option], [role=gridcell], [role=menuitem], [role=tab], [onclick], [tabindex]";
    // Scope to the open dialog/calendar when there is one, so the budget is
    // spent on what the person is actually looking at.
    const overlay = activeOverlay();
    const root = overlay || document;
    const found = [...root.querySelectorAll(sel)].filter((el) => {
      // Pages often put tabindex=-1 on large structural containers solely so
      // their own code can focus/scroll them. They are not controls a person
      // can tab to or click. Mapping one exposed an entire <main> as a button;
      // its thousands of words happened to contain "Book", so the safety
      // layer mistook a read-only availability search for a reservation.
      const raw = el.getAttribute("tabindex");
      if (raw == null || Number(raw) >= 0) return true;
      return el.matches('a[href],button,input,select,textarea,[role="button"],[role="link"],[role="option"],[role="gridcell"],[role="menuitem"],[role="tab"],[onclick]');
    });
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
      if (!isSensitive(el) && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) {
        const type = String(el.type || el.tagName).toLowerCase();
        let value = el.value;
        if (type === "checkbox" || type === "radio") value = !!el.checked;
        else if (el.tagName === "SELECT") {
          const option = el.options[el.selectedIndex];
          value = option ? String(option.textContent || option.value).trim() : String(el.value || "");
        }
        fields.push({
          index: idx,
          name: String(el.name || el.id || "").slice(0, 100),
          label: label(el).slice(0, 160),
          type,
          required: !!el.required,
          readOnly: !!el.readOnly,
          value: typeof value === "boolean" ? value : String(value || "").slice(0, 1000),
        });
      }
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
        // A readonly one is its picker's display, not a field, and telling it
        // to "use select" is advice the site will refuse. This branch used to
        // give that advice unconditionally — a native date/time input returns
        // here before the readonly hint further down is ever appended — so
        // the map sent the model at a field that snaps back, and the only way
        // to learn the truth was to spend a step being refused. On a booking
        // page that is the step that reads, to whoever is watching, as "it
        // just keeps retyping the date".
        //
        // Appending the warning was not enough: measured on 2026-08-11 the
        // model read the select instruction first and tried it anyway. Two
        // instructions in one line means the wrong one can win, so the
        // readonly case REPLACES the advice rather than arguing with it.
        extra = el.readOnly
          ? ` (${t} field, readonly — its own picker sets it; click it to open the picker and choose${el.value ? `; currently "${el.value}"` : ""})`
          : ` (${t} field — use select action with option in the exact format ${fmt}${el.value ? `; currently "${el.value}"` : ""})`;
      } else if ((el.tagName === "INPUT" || el.tagName === "TEXTAREA") && "value" in el) {
        // What the field currently holds. Without this a filled field looks
        // identical to an empty one and the model re-types it forever.
        const v = String(el.value || "").trim();
        if (v) extra = ` [contains "${v.slice(0, 40)}"]`;
        // A readonly input can only be changed through the widget it fronts —
        // shown here so the model clicks it open instead of writing to it.
        if (el.readOnly) extra += " [readonly — click to open its picker]";
      } else if (role(el) === "link") {
        const href = displayHref(el);
        if (href) extra = ` [href=${href}]`;
      }
      lines.push(`[${idx}] <${role(el)}> ${label(el)}${stateOf(el)}${extra} @(${Math.round(r.x + r.width / 2)},${Math.round(r.y + r.height / 2)})`);
      // 400, not 150: a booking page spends the first hundred on nav and menu
      // links, and the calendar was being truncated out of the map entirely.
      if (counter > 400) break;
    }
    const title = document.title;
    // The first 1,500 characters of a commercial/research page are commonly
    // all navigation. Prices, hours, specifications and source facts then
    // never reach either the agent or its verifier. Keep a still-bounded but
    // genuinely useful visible-text window; this is generic DOM evidence,
    // not a site extraction rule.
    const bodyText = pageText(root, overlay);
    return { url: location.href, title, elements: lines.join("\n"), text: bodyText, fields,
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
    const el = actionable(window.__anticipyMap[idx]);
    if (!el) return false;
    try { el.focus(); } catch (e) { return false; }
    return document.activeElement === el;
  };

  // Does the field itself reject what is now in it?
  //
  // Asked of the PAGE, never decided by us: an <input type="email"> already
  // knows that the bare word "Priya" is not an address, and type=tel, type=url,
  // pattern= and required= all know their own rules. Constraint validation is
  // the browser handing us that verdict. No site knowledge, no list of formats,
  // and it works on every page that declares anything about its fields.
  //
  // Resolved the same way as clearing and typing — through activeEditable()
  // first — because when a dialog steals focus the value went into THAT field,
  // and validating the mapped placeholder would be checking the wrong box.
  window.__anticipyValidity = (idx) => {
    const el = activeEditable() || window.__anticipyMap[idx];
    if (!el || typeof el.checkValidity !== "function") return null;
    if (el.checkValidity()) return null;
    const v = el.validity || {};
    const why = v.typeMismatch ? "is not a valid " + (el.type || "value")
      : v.patternMismatch ? "does not match the format this field requires"
      : v.valueMissing ? "is required and is empty"
      : (v.rangeUnderflow || v.rangeOverflow) ? "is outside the allowed range"
      : (v.tooShort || v.tooLong) ? "is the wrong length"
      : "is not accepted by this field";
    return { why: why,
             type: el.type || el.tagName.toLowerCase(),
             message: String(el.validationMessage || "").slice(0, 120),
             value: String(el.value || "").slice(0, 60) };
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
    const el = actionable(window.__anticipyMap[idx]);
    if (!el) return null;
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  };
})();
