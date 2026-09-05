// A hand-built document for running page_map.js outside a browser: enough of
// the DOM for the injected mapper to run against a node tree a test declares
// in a few lines. querySelectorAll with a tiny selector matcher (tag, .class,
// #id, [attr], [attr=v], [attr~=v], [attr*=v i], :checked, the descendant
// combinator, comma lists), closest / matches / contains, rects from stored
// geometry, computed style from stored style, activeElement, getElementById,
// and elementFromPoint from stored z-order. No site names, no library, no
// dependency. A helper for the page_map suites, not a test itself.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

export class FakeShadowRoot {
  constructor(host) {
    this.host = host;
    this.nodeType = 11;
    this.children = [];
    this.parentNode = null;
    this.parentElement = null;
  }
  append(child) { child.parentNode = this; child.parentElement = null; this.children.push(child); return child; }
  querySelectorAll(selector) { return descendants(this).filter((n) => n.matches(selector)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

export class FakeNode {
  constructor(tag, attrs = {}, children = [], extra = {}) {
    this.tagName = String(tag).toUpperCase();
    this.nodeType = 1;
    this.attrs = { ...attrs };
    this.children = [];
    this.parentNode = null;
    this.parentElement = null;
    this.ownText = String(extra.text || "");
    this.rect = { x: 0, y: 0, width: 100, height: 20, ...(extra.rect || {}) };
    this.style = { visibility: "visible", display: "block", opacity: "1", zIndex: "auto",
                   pointerEvents: "auto", ...(extra.style || {}) };
    this.shadowRoot = null;
    this._value = extra.value;
    this.checked = !!extra.checked;
    this.selectedFlag = !!extra.selected;
    for (const c of children) this.append(c);
  }
  append(child) { child.parentNode = this; child.parentElement = this; this.children.push(child); return child; }
  attachShadow() { this.shadowRoot = new FakeShadowRoot(this); return this.shadowRoot; }
  get id() { return this.attrs.id || ""; }
  get name() { return this.attrs.name || ""; }
  get className() { return this.attrs.class || ""; }
  getAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n) ? String(this.attrs[n]) : null; }
  hasAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n); }
  setAttribute(n, v) { this.attrs[n] = String(v); }
  get innerText() { return [this.ownText, ...this.children.map((c) => c.innerText)].filter(Boolean).join(" "); }
  get textContent() { return this.innerText; }
  get type() {
    if (this.attrs.type) return this.attrs.type;
    if (this.tagName === "SELECT") return this.hasAttribute("multiple") ? "select-multiple" : "select-one";
    if (this.tagName === "TEXTAREA") return "textarea";
    if (this.tagName === "INPUT") return "text";
    return "";
  }
  get href() { return this.attrs.href || ""; }
  get required() { return this.hasAttribute("required"); }
  get readOnly() { return this.hasAttribute("readonly"); }
  get disabled() { return this.hasAttribute("disabled"); }
  get hidden() { return this.hasAttribute("hidden"); }
  get isContentEditable() { return this.attrs.contenteditable === "true"; }
  get form() { return this.parentElement ? this.parentElement.closest("form") : null; }
  get options() { return this.tagName === "SELECT" ? this.children.filter((c) => c.tagName === "OPTION") : []; }
  get explicitlySelected() { return this.selectedFlag || this.hasAttribute("selected"); }
  // An option's selectedness: explicit, or — with nothing explicit in its
  // select — the one the browser picks by default (see selectedIndex).
  get selected() {
    if (this.explicitlySelected) return true;
    const sel = this.parentElement;
    if (!sel || sel.tagName !== "SELECT") return false;
    return !sel.options.some((o) => o.explicitlySelected) && sel.options[sel.selectedIndex] === this;
  }
  set selected(v) { this.selectedFlag = !!v; }
  // The browser's rule for a single-select: an explicitly selected option,
  // else the first option that is not disabled, else nothing (-1).
  get selectedIndex() {
    const opts = this.options;
    const explicit = opts.findIndex((o) => o.explicitlySelected);
    if (explicit >= 0) return explicit;
    return opts.findIndex((o) => !o.disabled);
  }
  get value() {
    if (this.tagName === "OPTION") return this.hasAttribute("value") ? String(this.attrs.value) : this.innerText;
    if (this.tagName === "SELECT") { const o = this.options[this.selectedIndex]; return o ? o.value : ""; }
    return this._value === undefined ? "" : String(this._value);
  }
  set value(v) { this._value = v; }
  getBoundingClientRect() {
    const r = this.rect;
    return { x: r.x, y: r.y, width: r.width, height: r.height,
             top: r.y, left: r.x, right: r.x + r.width, bottom: r.y + r.height };
  }
  contains(other) { for (let n = other; n; n = n.parentNode) if (n === this) return true; return false; }
  matches(selector) { return String(selector).split(",").some((s) => matchComplex(this, s.trim())); }
  closest(selector) { for (let n = this; n; n = n.parentElement) if (n.matches(selector)) return n; return null; }
  querySelectorAll(selector) { return descendants(this).filter((n) => n.matches(selector)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  scrollIntoView() {}
  focus() { if (globalThis.document) globalThis.document.activeElement = this; }
  dispatchEvent() { return true; }
  checkValidity() { return true; }
}

// Light DOM only, like the real thing: a shadow tree is never reached from
// the document. FakeShadowRoot.querySelectorAll is the way in.
function descendants(root) {
  const out = [];
  const walk = (n) => { for (const c of n.children) { out.push(c); walk(c); } };
  walk(root);
  return out;
}

function splitOutsideBrackets(selector) {
  const parts = [];
  let cur = "", depth = 0;
  for (const ch of selector) {
    if (ch === "[") depth++;
    if (ch === "]") depth--;
    if (/\s/.test(ch) && depth === 0) { if (cur) parts.push(cur); cur = ""; continue; }
    cur += ch;
  }
  if (cur) parts.push(cur);
  return parts;
}

// Descendant combinator only, matched right to left.
function matchComplex(node, selector) {
  const parts = splitOutsideBrackets(selector);
  if (!parts.length || !matchCompound(node, parts[parts.length - 1])) return false;
  let anc = node.parentElement;
  for (let i = parts.length - 2; i >= 0; i--) {
    while (anc && !matchCompound(anc, parts[i])) anc = anc.parentElement;
    if (!anc) return false;
    anc = anc.parentElement;
  }
  return true;
}

const TOKEN = /\.([\w-]+)|#([\w-]+)|\[([\w-]+)(?:([~|^$*]?=)"?([^"\]]*?)"?(\s+i)?)?\]|:([\w-]+)/g;

function matchCompound(node, compound) {
  const m = compound.match(/^([a-zA-Z][\w-]*|\*)?(.*)$/);
  const tag = m[1];
  if (tag && tag !== "*" && node.tagName !== tag.toUpperCase()) return false;
  const rest = m[2];
  let consumed = 0, t;
  TOKEN.lastIndex = 0;
  while ((t = TOKEN.exec(rest))) {
    consumed += t[0].length;
    if (t[1] !== undefined) {
      if (!String(node.attrs.class || "").split(/\s+/).includes(t[1])) return false;
    } else if (t[2] !== undefined) {
      if (node.id !== t[2]) return false;
    } else if (t[3] !== undefined) {
      const attr = t[3], op = t[4], fold = !!t[6];
      if (!node.hasAttribute(attr)) return false;
      let have = node.getAttribute(attr), want = t[5] ?? "";
      if (fold) { have = have.toLowerCase(); want = want.toLowerCase(); }
      if (op === "=") { if (have !== want) return false; }
      else if (op === "~=") { if (!have.split(/\s+/).includes(want)) return false; }
      else if (op === "*=") { if (!have.includes(want)) return false; }
      else if (op) throw new Error(`fake_page: unsupported attribute operator in ${compound}`);
    } else if (t[7] !== undefined) {
      if (t[7] === "checked") { if (!node.checked) return false; }
      else throw new Error(`fake_page: unsupported pseudo-class in ${compound}`);
    }
  }
  if (consumed !== rest.length) throw new Error(`fake_page: unsupported selector ${compound}`);
  return true;
}

// The stacking order a browser would paint: the largest z-index on the
// node's ancestor chain wins, later in document order breaks ties.
function effectiveZ(node) {
  let z = 0;
  for (let n = node; n && n.nodeType === 1; n = n.parentElement) {
    const own = Number(n.style.zIndex);
    if (Number.isFinite(own)) z = Math.max(z, own);
  }
  return z;
}

// Install window/document/getComputedStyle/CSS/location for one page. Returns
// the document and a restore() that removes the globals again.
export function installFakePage({ body, active = null, viewport = { w: 1280, h: 800 },
                                  url = "https://fixture.test/", title = "Fixture" } = {}) {
  const light = () => descendants(body);
  const document = {
    nodeType: 9,
    body, title,
    activeElement: active,
    querySelectorAll: (selector) => light().filter((n) => n.matches(selector)),
    querySelector: (selector) => light().find((n) => n.matches(selector)) || null,
    getElementById: (id) => light().find((n) => n.id === id) || null,
    createRange: () => { throw new Error("fake_page: no ranges"); },
    // Topmost LIGHT-DOM element at a point — what a browser returns after
    // retargeting a hit inside a shadow tree to its host. Off-viewport is
    // null, like a browser.
    elementFromPoint: (x, y) => {
      if (x < 0 || y < 0 || x >= viewport.w || y >= viewport.h) return null;
      let best = null, bestZ = -Infinity;
      for (const n of light()) {
        if (n.style.display === "none" || n.style.visibility === "hidden") continue;
        const r = n.getBoundingClientRect();
        if (x < r.left || x >= r.right || y < r.top || y >= r.bottom) continue;
        const z = effectiveZ(n);
        if (z >= bestZ) { best = n; bestZ = z; }
      }
      return best;
    },
  };
  const previous = {};
  const install = (name, value) => { previous[name] = globalThis[name]; globalThis[name] = value; };
  install("window", { innerWidth: viewport.w, innerHeight: viewport.h });
  install("document", document);
  install("getComputedStyle", (el) => el.style);
  install("CSS", { escape: (s) => String(s) });
  install("location", { href: url });
  install("HTMLInputElement", class HTMLInputElement {});
  return {
    document,
    restore: () => {
      for (const name of Object.keys(previous)) {
        if (previous[name] === undefined) delete globalThis[name];
        else globalThis[name] = previous[name];
      }
    },
  };
}

// Evaluate the real page_map.js against whatever installFakePage installed.
// Returns the window object the mapper populated.
export function evalPageMap() {
  const source = readFileSync(join(here, "..", "page_map.js"), "utf8");
  (0, eval)(source);
  return globalThis.window;
}
