// Proof for the two surfaces a person actually looks at: popup.html and
// onboarding.html.
//
// Three defects this defends against, none of which crashes anything — which
// is exactly why they need a test.
//
// 1. DRIFT. The palette is duplicated in the two pages on purpose: build-zip.sh
//    derives what it packages from the manifest, from <script src> and from JS
//    imports, and it does NOT resolve <link rel=stylesheet>. A shared .css file
//    would therefore ship as a page with no design at all and nothing would
//    fail loudly. (That is not hypothetical — the zip once shipped without
//    workflow_state.js.) Both files carried a comment claiming the token block
//    was "byte-identical", and nothing checked it.
//
// 2. A DARK-ONLY RULE, added later, in the page's own half. The theme is a
//    value swap, so every rule outside the shared block must read a ROLE.
//    One `color: #f5f0eb` is invisible on paper and no test of behaviour will
//    ever notice.
//
// 3. THE DEFAULT MOVING. Light is the default deliberately: this page opens
//    itself in somebody's browser and is walked through over a phone call, so
//    it has to be the same page for everyone rather than a different one for
//    whoever runs their Mac dark. A well-meant
//    `@media (prefers-color-scheme: dark)` hands that decision back to a
//    setting nobody chose for this product.
//
// It also checks the DOM contract, because this pair of files was rewritten by
// hand: popup.js and onboarding.js reach for ~40 ids and every one of them is
// an unguarded `el(id).something`, so a single renamed id is a TypeError in
// the first repaint and a popup that is simply blank.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ext = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => readFileSync(join(ext, f), "utf8");

const popup = read("popup.html");
const onboarding = read("onboarding.html");
const themeJs = read("theme.js");

const START = "/* ===== shared: theme + scale + the toggle.";
const END = "/* ===== end shared ===== */";
function sharedBlock(name, text) {
  const i = text.indexOf(START);
  const j = text.indexOf(END);
  assert.ok(i !== -1 && j > i, `${name} must carry the shared theme block`);
  assert.equal(text.indexOf(START, i + 1), -1, `${name} must carry it exactly once`);
  return text.slice(i, j + END.length);
}

// ------------------------------------------------------------------ 0: drift
const shared = sharedBlock("popup.html", popup);
assert.equal(shared, sharedBlock("onboarding.html", onboarding),
  "the shared theme block in popup.html and onboarding.html has drifted — " +
  "edit both, or neither");
console.log("PASS 0: both surfaces carry a byte-identical theme block");

// ------------------------------------------------------- 1: light is default
// The FIRST :root in the block is the default palette, and it must be the
// light one — a browser with no stored choice paints whatever this says.
const firstRoot = shared.slice(shared.indexOf(":root {"), shared.indexOf("}", shared.indexOf(":root {")));
assert.match(firstRoot, /color-scheme: light/,
  "the default :root must declare color-scheme: light");
assert.match(firstRoot, /--bg: #ffffff/,
  "the default :root must paint the light ground, not ink");
assert.match(shared, /:root\[data-theme="dark"\][\s\S]*--bg: #000000/,
  "dark must be an opt-in attribute palette, not the default");
// Prose is dropped for the checks that ask "does this code DO the thing": the
// theme block and theme.js both EXPLAIN at length that prefers-color-scheme is
// deliberately not consulted, and that explanation is the opposite of a
// regression.
const stripProse = (text) => text
  .replace(/<!--[\s\S]*?-->/g, "")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");
for (const [name, text] of [["popup.html", popup], ["onboarding.html", onboarding], ["theme.js", themeJs]]) {
  const code = stripProse(text);
  assert.equal(/prefers-color-scheme/.test(code), false,
    `${name} must not consult prefers-color-scheme: light is the default for everyone`);
  assert.equal(/matchMedia/.test(code), false,
    `${name} must not ask the machine what theme to use`);
}
console.log("PASS 1: light is the default and the OS is not consulted");

// --------------------------------------------------------- 2: no stray colour
// Prose is stripped here too: both pages EXPLAIN the palette ("flat #0c0c0c
// reads as an absence of pixels"), and an explanation is not a rule.
for (const [name, text] of [["popup.html", popup], ["onboarding.html", onboarding]]) {
  const own = stripProse(text.replace(shared, ""));
  const hex = own.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
  // currentColor keeps the two toggle glyphs and the mark on role colours; a
  // literal fill= or stroke= would be a dark-only logo.
  const rgba = (own.match(/rgba?\([^)]*\)/g) || []);
  assert.deepEqual(hex, [],
    `${name} names a colour outside the shared block (${hex.join(", ")}) — every ` +
    "rule out there must read a role token, or it has no light mode");
  assert.deepEqual(rgba, [],
    `${name} names a colour outside the shared block (${rgba.join(", ")})`);
}
console.log("PASS 2: outside the theme block neither page names a colour");

// ------------------------------------------------------ 3: applied pre-paint
// A deferred script paints the default palette first and the chosen one a
// frame later, which is the most visible thing that can happen on a page whose
// job is to be calm. So: classic script, in <head>, no defer/async, and ahead
// of the <style> it themes.
for (const [name, text] of [["popup.html", popup], ["onboarding.html", onboarding]]) {
  const tag = text.match(/<script[^>]*theme\.js[^>]*>/);
  assert.ok(tag, `${name} must load theme.js`);
  assert.equal(/type=|defer|async/.test(tag[0]), false,
    `${name} must load theme.js as a blocking classic script (${tag[0]})`);
  assert.ok(text.indexOf(tag[0]) < text.indexOf("<style>"),
    `${name} must load theme.js before the stylesheet it themes`);
  assert.ok(text.indexOf(tag[0]) < text.indexOf("<body"),
    `${name} must load theme.js in <head>`);
  // MV3's extension_pages CSP is script-src 'self': an inline bootstrap would
  // be refused outright and the page would have no theme control at all.
  assert.equal(/<script(?![^>]*src)[^>]*>[^<]/.test(text), false,
    `${name} must have no inline <script> — MV3 refuses to run it`);
  const toggles = text.match(/data-theme-toggle/g) || [];
  assert.equal(toggles.length, 1, `${name} must offer exactly one theme control`);
}
// The default is expressed in one place, and it fails toward light.
assert.match(themeJs, /theme === "dark" \? "dark" : "light"/,
  "theme.js must treat anything that is not the string dark as light");
console.log("PASS 3: the theme is applied before the first frame, from one place");

// -------------------------------------------------------- 4: the DOM contract
// Every id these two modules reach for, taken from the source rather than from
// a list somebody has to remember. `el(id)` is unguarded at every call site.
const ids = (js) => {
  const found = new Set();
  for (const re of [/\bel\("([\w-]+)"\)/g, /\bsay\("([\w-]+)"/g, /\bshow\("([\w-]+)"/g,
                    /getElementById\("([\w-]+)"\)/g, /\bbeat\("([\w-]+)"/g, /\bhint\(/g]) {
    let m;
    while ((m = re.exec(js))) if (m[1]) found.add(m[1]);
  }
  return [...found];
};
for (const [page, script, html] of [
  ["popup.html", "popup.js", popup],
  ["onboarding.html", "onboarding.js", onboarding],
]) {
  const wanted = ids(read(script));
  assert.ok(wanted.length > 10, `${script}: id scan found only ${wanted.length} — the scan itself is broken`);
  const missing = wanted.filter((id) => !html.includes(`id="${id}"`));
  assert.deepEqual(missing, [],
    `${script} reaches for id(s) ${missing.join(", ")} that ${page} does not have`);
}
// hint() writes into a live region whose id is only ever a literal inside the
// helper, so it is named here rather than scanned.
assert.ok(popup.includes('id="copyhint"'), "popup.html must keep the hint region");
assert.ok(onboarding.includes('id="codehint"'), "onboarding.html must keep the hint region");
console.log("PASS 4: every id the two modules reach for exists on its page");

// ------------------------------------------------- 5: one palette everywhere
// The product is four surfaces in three deployments — this extension, the
// pages PocketBase serves, and the marketing site — and each one has to carry
// its own copy of the palette, because they ship separately and the extension
// cannot even use a stylesheet (see the top of this file). Copies drift: the
// two hosted pages had already diverged from each other (--stroke #2b2b2b vs
// #252525, --gray #a09b96 vs #8A8A8A) and both had diverged from the app's
// serif. So the copies are compared here rather than trusted.
//
// This check lives in the extension's suite because run_all.mjs is the only
// JS suite in the repo; tests/ is packaged into neither the zip nor the Chrome
// sync, so reaching a directory up is free.
const repo = join(ext, "..");
const sources = {
  "extension (popup.html/onboarding.html)": shared,
  "backend/pb_public/site.css": readFileSync(join(repo, "backend/pb_public/site.css"), "utf8"),
  "website/index.html": readFileSync(join(repo, "website/index.html"), "utf8"),
};
// The light palette is the FIRST :root, dark is the attribute palette, and a
// later plain :root holds what both themes share — so its values belong to
// both maps.
function palette(css) {
  const clean = stripProse(css);
  const out = { light: {}, dark: {} };
  const block = /:root(\[data-theme="dark"\])?\s*\{([^}]*)\}/g;
  let m;
  let seenLight = false;
  while ((m = block.exec(clean))) {
    const decls = [...m[2].matchAll(/(--[\w-]+):\s*([^;]+);/g)]
      .map(([, k, v]) => [k, v.trim()]);
    if (m[1]) {
      for (const [k, v] of decls) out.dark[k] = v;
    } else if (!seenLight) {
      seenLight = true;
      for (const [k, v] of decls) out.light[k] = v;
    } else {
      // Theme-invariant: true in both.
      for (const [k, v] of decls) { out.light[k] = v; out.dark[k] = v; }
    }
  }
  return out;
}
const palettes = Object.fromEntries(Object.entries(sources).map(([n, css]) => [n, palette(css)]));
// Present on every surface, or the surfaces are not the same product.
const CORE = ["--bg", "--surface", "--card", "--edge", "--text", "--text-2",
              "--text-3", "--accent", "--alarm", "--fill", "--on-fill"];
for (const [name, p] of Object.entries(palettes)) {
  for (const theme of ["light", "dark"]) {
    const missing = CORE.filter((t) => !p[theme][t]);
    assert.deepEqual(missing, [], `${name} is missing ${missing.join(", ")} in its ${theme} palette`);
  }
}
// Light must actually be light, everywhere, and it must be the palette a
// browser with no stored choice gets.
for (const [name, p] of Object.entries(palettes)) {
  assert.equal(p.light["--bg"], "#ffffff", `${name}'s default palette must be the light ground`);
  assert.equal(p.dark["--bg"], "#000000", `${name}'s dark palette must be the app's ink`);
}
// Any token two surfaces both name must agree. Tokens only one surface needs
// (--dot-off, --grain-blend) are its own business.
const names = Object.keys(palettes);
for (let i = 0; i < names.length; i++) {
  for (let j = i + 1; j < names.length; j++) {
    for (const theme of ["light", "dark"]) {
      const a = palettes[names[i]][theme], b = palettes[names[j]][theme];
      for (const token of Object.keys(a)) {
        if (!(token in b)) continue;
        assert.equal(a[token], b[token],
          `${token} is ${a[token]} in ${names[i]} but ${b[token]} in ${names[j]} (${theme})`);
      }
    }
  }
}
const compared = Object.keys(palettes["extension (popup.html/onboarding.html)"].light).length;
console.log(`PASS 5: ${names.length} surfaces agree on the palette (${compared} light tokens)`);

console.log("test_theme_contract: all passed");
