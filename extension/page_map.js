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

  window.__anticipyMapPage = () => {
    window.__anticipyMap = {};
    counter = 0;
    const lines = [];
    const sel = "a[href], button, input, select, textarea, [role=button], [role=link], [onclick], [tabindex]";
    for (const el of document.querySelectorAll(sel)) {
      if (!visible(el)) continue;
      const idx = counter++;
      window.__anticipyMap[idx] = el;
      const r = el.getBoundingClientRect();
      lines.push(`[${idx}] <${role(el)}> ${label(el)} @(${Math.round(r.x + r.width / 2)},${Math.round(r.y + r.height / 2)})`);
      if (counter > 150) break;
    }
    const title = document.title;
    const bodyText = (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 1500);
    return { url: location.href, title, elements: lines.join("\n"), text: bodyText };
  };

  window.__anticipyCenter = (idx) => {
    const el = window.__anticipyMap[idx];
    if (!el) return null;
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  };
})();
