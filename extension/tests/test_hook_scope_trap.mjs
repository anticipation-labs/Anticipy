// A HANDLER CANNOT SEE THE MODULE IT LIVES IN — a static analyser over every
// backend/pb_hooks/*.pb.js, run offline, that fails the build on the two ways
// this repo has already gotten that wrong.
//
// The rule, measured against PocketBase 0.30.4 (not theorised): a callback
// registered with routerAdd / routerUse / onRecord* / cronAdd is handed to the
// Go side and executed in its OWN JSVM execution context. The module body that
// declared it is NOT its lexical environment. Only the runtime globals ($os,
// $security, require, console, __hooks, Record, ...) and `require()`d modules
// cross that boundary. Two consequences, and both have bitten this tree:
//
//   1. A `const` / `let` / `var` / `function` declared at column 0 is gone by
//      the time a request arrives. Reading it throws
//      `ReferenceError: <name> is not defined`.
//   2. There is no module-scope `app`. Inside a handler the app is the `app`
//      PROPERTY of the event argument: `e.app`. Bare `app.` throws
//      `ReferenceError: app is not defined`.
//
// What that costs, on 2026-08-22, in production:
//   - account_delete.pb.js declared `const OWNER_TABLES` at top level and read
//     it inside `routerAdd("POST","/me/delete", ...)`, and called bare `app.`
//     at five sites. "Delete everything on my server" was completely broken:
//     every authenticated delete died on the first loop.
//   - agent_key.pb.js had the identical bare-`app.` bug at three sites inside
//     `/agent/llm`, silently voiding the model-call audit trail — no error
//     reached the caller at all, the writes just never happened.
//
// WHY A TEST AND NOT A CODE REVIEW. PocketBase reports the ReferenceError to
// the caller as a bare 400 "Something went wrong while processing your
// request." — no scope, no file, no line. And the broken line sits PAST every
// cheap probe: /me/delete answers 401 with no token and 400 with no confirm
// token, so it looks healthy from the outside, and only a fully authenticated
// delete-with-confirmation ever reaches it. It shipped. It sat there. Then it
// happened a second time in a second file. So the CLASS is what is guarded
// here, statically, over the whole directory — not the two instances.
//
// The analyser is proven against known-bad and known-good input in the same
// run: the fixtures at the bottom reproduce both original bugs as strings and
// assert they are caught, then assert the corrected forms are not. An analyser
// that cannot fail is decoration.
//
// Dependency-free on purpose: the repo has no JS parser and this must run from
// a bare `node extension/tests/run_all.mjs`. The lexer below is small but it is
// a real lexer, not a line filter — comments, single/double-quoted strings,
// template literals (with `${}` interiors kept as code) and regex literals are
// blanked before any pattern is applied, so the word "app." in a comment or a
// string is invisible to it.
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const hookDir = join(here, "..", "..", "backend", "pb_hooks");

// ---------------------------------------------------------------------------
// 1. Lexer: same-length copy of the source with every non-code region blanked.
// ---------------------------------------------------------------------------
// Same length matters: every offset the analyser reports is an offset into the
// ORIGINAL file, so line numbers in failure messages point at real lines.
// Newlines are preserved for the same reason.
//
// Template literals keep their `${...}` interiors as code, because those ARE
// code — `${OWNER_TABLES.length}` inside a message string is a live reference
// to a module binding and must be caught like any other.
const REGEX_OK_AFTER = new Set(
  "(,=:[!&|?{};+-*%~^<>\n\t ".split(""));
const REGEX_OK_KEYWORDS = new Set([
  "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
  "case", "do", "else", "yield", "await", "throw",
]);

function blankNonCode(src) {
  const out = src.split("");
  const n = src.length;
  const blank = (k) => { if (out[k] !== "\n") out[k] = " "; };
  const blankRange = (from, to) => { for (let k = from; k < to; k++) blank(k); };

  const tpl = [];        // one frame per template literal we are inside
  let depth = 0;         // `{` nesting in the current code region
  let inTpl = false;
  let prev = "";         // last significant code character
  let i = 0;

  const regexAllowedHere = () => {
    if (prev === "") return true;
    if (REGEX_OK_AFTER.has(prev)) return true;
    // `return /re/` — prev is a word char, so look back for the keyword.
    const back = src.slice(Math.max(0, i - 12), i).match(/([A-Za-z$_][\w$]*)\s*$/);
    return !!back && REGEX_OK_KEYWORDS.has(back[1]);
  };

  while (i < n) {
    const c = src[i];

    if (inTpl) {
      if (c === "\\") { blank(i); if (i + 1 < n) blank(i + 1); i += 2; continue; }
      if (c === "`") { blank(i); i++; tpl.pop(); inTpl = tpl.length > 0 && tpl[tpl.length - 1].reentered; prev = '"'; continue; }
      if (c === "$" && src[i + 1] === "{") {
        blank(i);                          // the `$` is not code
        tpl[tpl.length - 1].sub = true;
        tpl[tpl.length - 1].subDepth = depth;
        inTpl = false;                     // the `{` is handled in code mode
        i += 1;
        continue;
      }
      blank(i); i++; continue;
    }

    // ---- code mode ----
    if (c === "/" && src[i + 1] === "/") {
      let j = i; while (j < n && src[j] !== "\n") j++;
      blankRange(i, j); i = j; continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      let j = i + 2;
      while (j < n && !(src[j] === "*" && src[j + 1] === "/")) j++;
      j = Math.min(n, j + 2);
      blankRange(i, j); i = j; continue;
    }
    if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < n) {
        if (src[j] === "\\") { j += 2; continue; }
        if (src[j] === c || src[j] === "\n") break;
        j++;
      }
      j = Math.min(n, j + 1);
      blankRange(i, j); i = j; prev = '"'; continue;
    }
    if (c === "`") {
      blank(i); i++;
      tpl.push({ sub: false, subDepth: depth, reentered: false });
      inTpl = true; continue;
    }
    if (c === "/" && regexAllowedHere()) {
      // A regex literal. Blank it whole: `/["'`{}]/` must not desync the lexer.
      let j = i + 1, cls = false, closed = false;
      while (j < n && src[j] !== "\n") {
        if (src[j] === "\\") { j += 2; continue; }
        if (cls) { if (src[j] === "]") cls = false; j++; continue; }
        if (src[j] === "[") { cls = true; j++; continue; }
        if (src[j] === "/") { closed = true; break; }
        j++;
      }
      if (closed) {
        while (j + 1 < n && /[a-z]/.test(src[j + 1])) j++;   // flags
        blankRange(i, j + 1); i = j + 1; prev = '"'; continue;
      }
      // Unterminated — it was division after all. Fall through.
    }
    if (c === "{") { depth++; prev = c; i++; continue; }
    if (c === "}") {
      depth--;
      const top = tpl[tpl.length - 1];
      if (top && top.sub && depth === top.subDepth) {
        top.sub = false; top.reentered = true; inTpl = true; prev = c; i++; continue;
      }
      prev = c; i++; continue;
    }
    if (!/\s/.test(c)) prev = c;
    i++;
  }
  return out.join("");
}

// ---------------------------------------------------------------------------
// 2. Where the handlers are.
// ---------------------------------------------------------------------------
// Every PocketBase registration that takes a callback: the two router hooks,
// the cron scheduler, and the whole `on*` event family (onRecordAfterCreate-
// Success, onBootstrap, onMailerSend, onModelUpdate, ...). `on[A-Z]...` covers
// the family without having to track PocketBase's release notes, and an
// optional `$app.` prefix covers the `$app.onRecordCreate(...)` spelling.
const REGISTRAR = /(^|[^\w$.])(?:\$app\s*\.\s*)?(routerAdd|routerUse|cronAdd|on[A-Z][A-Za-z0-9]*)\s*\(/g;

const lineOf = (src, index) => src.slice(0, index).split("\n").length;

function matchDelim(code, open, openCh, closeCh) {
  let d = 0;
  for (let i = open; i < code.length; i++) {
    const c = code[i];
    if (c === openCh) d++;
    else if (c === closeCh) { d--; if (d === 0) return i; }
  }
  return -1;
}

// The callback bodies in a range of code. OUTERMOST only: a closure nested
// inside one of them is a scope of its own and is walked separately, because a
// nested closure can legitimately bind a name the enclosing handler must not.
// agent_key.pb.js is exactly that shape — `auditBegin` and `auditFinish` each
// take an explicit `app` PARAMETER and the caller passes `e.app` in — so a flat
// "does this handler mention a local app anywhere" test exempted all 415 lines
// of it. Scope walking is not gold-plating here; without it this file is
// unguarded.
function functionBodies(code, from, to) {
  const bodies = [];
  let i = from;
  while (i < to) {
    // `function (...) {`  /  `function name(...) {`
    if (/^function\b/.test(code.slice(i, i + 9))) {
      const p = code.indexOf("(", i);
      const pEnd = p === -1 ? -1 : matchDelim(code, p, "(", ")");
      const brace = pEnd === -1 ? -1 : code.indexOf("{", pEnd);
      const bEnd = brace === -1 ? -1 : matchDelim(code, brace, "{", "}");
      if (bEnd !== -1 && bEnd <= to) {
        bodies.push({ params: code.slice(p + 1, pEnd), start: brace + 1, end: bEnd });
        i = bEnd + 1; continue;
      }
    }
    if (code[i] === "=" && code[i + 1] === ">") {
      // Params are whatever preceded the arrow: `(e)`, `e`, `(app, rec)`.
      // Walked backwards rather than sliced: `code.slice(0, i)` per arrow is a
      // full copy of the file, and once the analyser recurses into nested
      // scopes that is quadratic — it took this suite from 0.4s to 3.9s.
      let k = i - 1;
      while (k >= 0 && /\s/.test(code[k])) k--;
      let params = "";
      if (code[k] === ")") {
        const p = matchBackwards(code, k);
        params = p === -1 ? "" : code.slice(p + 1, k);
      } else {
        let s = k;
        while (s >= 0 && /[\w$]/.test(code[s])) s--;
        params = code.slice(s + 1, k + 1);
      }
      let j = i + 2;
      while (j < to && /\s/.test(code[j])) j++;
      if (code[j] === "{") {
        const bEnd = matchDelim(code, j, "{", "}");
        if (bEnd !== -1 && bEnd <= to) {
          bodies.push({ params, start: j + 1, end: bEnd });
          i = bEnd + 1; continue;
        }
      }
      // A concise body runs to the end of the statement or argument. Stopping
      // at `;` as well as `,` matters: an over-long body would swallow the
      // sibling statements after it into this arrow's scope, and its params
      // would then wrongly excuse a bug in them.
      const end = exprEnd(code, j, to);
      bodies.push({ params, start: j, end });
      i = end; continue;
    }
    i++;
  }
  return bodies;
}

function matchBackwards(code, close) {
  let d = 0;
  for (let i = close; i >= 0; i--) {
    if (code[i] === ")") d++;
    else if (code[i] === "(") { d--; if (d === 0) return i; }
  }
  return -1;
}

function exprEnd(code, from, limit) {
  let d = 0;
  for (let i = from; i < limit; i++) {
    const c = code[i];
    if (c === "(" || c === "[" || c === "{") d++;
    else if (c === ")" || c === "]" || c === "}") d--;
    else if ((c === "," || c === ";") && d === 0) return i;
  }
  return limit;
}

// ---------------------------------------------------------------------------
// 3. Declarations.
// ---------------------------------------------------------------------------
// Module top level == column 0. That is the whole definition and it is the
// right one for this directory: a pb_hooks file is a flat list of registration
// calls, so anything starting at column 0 that is not a registration is either
// a module binding (the bug) or a comment.
function topLevelDeclarations(code) {
  const found = [];
  const lines = code.split("\n");
  let offset = 0;
  for (const line of lines) {
    const kw = /^(const|let|var|class|(?:async\s+)?function\s*\*?)\s+/.exec(line);
    if (kw) {
      for (const name of bindingNames(line.slice(kw[0].length))) {
        found.push({ name, line: lineOf(code, offset), col: 0 });
      }
    }
    offset += line.length + 1;
  }
  return found;
}

// `X`, `X = 1, Y = 2`, `{ a, b } = ...`, `[a, b] = ...`. Only the head of the
// declaration is on the column-0 line, which is all that is needed: a
// multi-line `const OWNER_TABLES = [` still declares OWNER_TABLES on line one.
function bindingNames(rest) {
  const names = [];
  const head = rest.split("=")[0];
  if (/^[{[]/.test(head.trim())) {
    for (const m of head.matchAll(/([A-Za-z_$][\w$]*)\s*(?::\s*([A-Za-z_$][\w$]*))?/g)) {
      names.push(m[2] || m[1]);
    }
    return names;
  }
  for (const part of rest.split(",")) {
    const m = /^\s*([A-Za-z_$][\w$]*)/.exec(part);
    if (m) names.push(m[1]);
    if (/[[{(]/.test(part)) break;   // an initialiser can hold commas
  }
  return names;
}

// The names ONE scope binds for itself. Deliberately NOT the parameter lists of
// nested functions: those belong to the nested scope, and folding them in here
// is the mistake that made this analyser blind to agent_key.pb.js. Callers pass
// text with the nested bodies already blanked out, so a `const` inside a
// closure does not leak upwards either.
//
// A shadowing declaration is exactly the fix for trap 2 — account_delete.pb.js
// was repaired by moving `const OWNER_TABLES` into the handler — so a name
// bound here must silence the report for that name.
function ownBindings(text) {
  const names = new Set();
  for (const m of text.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
  for (const m of text.matchAll(/\b(?:const|let|var)\s*([{[][^}\]]*[}\]])/g)) addNames(names, m[1]);
  for (const m of text.matchAll(/\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
  for (const m of text.matchAll(/\bclass\s+([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
  for (const m of text.matchAll(/\bcatch\s*\(\s*([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
  return names;
}

// Over-inclusive on purpose: `{ a, b = 1 }` and `...rest` all contribute every
// identifier they mention. A parameter list is the one place where naming a
// binding that is not really bound costs nothing, and missing one costs a false
// positive on correct code.
function addNames(into, text) {
  for (const m of String(text).matchAll(/([A-Za-z_$][\w$]*)/g)) into.add(m[1]);
  return into;
}

// ---------------------------------------------------------------------------
// 4. The analyser.
// ---------------------------------------------------------------------------
const WHY_HANDLER_SCOPE =
  "    Why: in the PocketBase JSVM (measured on 0.30.4) a registered callback\n" +
  "    runs in its OWN execution context. The module body that declared it is\n" +
  "    not its lexical environment, so a module binding read at request time\n" +
  "    throws a ReferenceError. PocketBase surfaces that to the caller as a\n" +
  "    bare 400 \"Something went wrong while processing your request.\" — no\n" +
  "    file, no line, no mention of scope — and only on a request that gets\n" +
  "    far enough to reach it, so auth checks and argument validation above it\n" +
  "    keep answering correctly and every cheap probe passes.";

function analyseHookSource(file, src) {
  const code = blankNonCode(src);
  const findings = [];
  const topLevel = topLevelDeclarations(code);
  const byName = new Map(topLevel.map((d) => [d.name, d]));

  REGISTRAR.lastIndex = 0;
  let m;
  while ((m = REGISTRAR.exec(code)) !== null) {
    const registrar = m[2];
    const argOpen = m.index + m[0].length - 1;
    const argClose = matchDelim(code, argOpen, "(", ")");
    if (argClose === -1) {
      findings.push({
        file, line: lineOf(code, argOpen), identifier: registrar,
        message: `${file}:${lineOf(code, argOpen)}: unbalanced argument list on `
          + `\`${registrar}(\` — the scope analyser in extension/tests/`
          + `test_hook_scope_trap.mjs could not read this file, so it is NOT `
          + `covered. Fix the syntax, or fix the analyser's lexer.`,
      });
      continue;
    }

    for (const body of functionBodies(code, argOpen + 1, argClose)) {
      walkScope(body, new Set(), registrar);
    }
  }

  // One lexical scope: the checks run on this scope's OWN text (nested function
  // bodies blanked out), with the names visible here = inherited from enclosing
  // scopes + this scope's parameters + this scope's own declarations. Then
  // recurse, so a nested closure is judged against its own parameter list and
  // the enclosing handler is not excused by it.
  function walkScope(scope, inherited, registrar) {
    const nested = functionBodies(code, scope.start, scope.end);
    const chars = code.slice(scope.start, scope.end).split("");
    for (const nb of nested) {
      for (let k = nb.start; k < nb.end; k++) {
        const idx = k - scope.start;
        if (chars[idx] !== "\n") chars[idx] = " ";
      }
    }
    const text = chars.join("");
    const visible = new Set(inherited);
    addNames(visible, scope.params);
    for (const n of ownBindings(text)) visible.add(n);

    // ---- trap 1: bare `app.` where `e.app.` is meant ----
    // The lookbehind is zero-width ON PURPOSE. A leading character CLASS
    // consumes the delimiter in front of the identifier, and a consumed
    // delimiter is not available to the next match — so `of OWNER_TABLES`
    // silently skipped OWNER_TABLES entirely and the analyser called the
    // known-bad fixture clean. Same reason the trap-2 scan below is a
    // lookbehind. `e.app.`, `$app.`, `e?.app.` and `myapp.` are all excluded
    // by it, and a scope that binds its own `app` (`const app = e.app`, or a
    // parameter named `app` as in agent_key.pb.js's audit closures) is reading
    // that binding, not a missing global, so it is correct code.
    if (!visible.has("app")) {
      for (const hit of text.matchAll(/(?<![\w$.])app\s*\./g)) {
        const at = scope.start + hit.index;
        const line = lineOf(code, at);
        const method = (src.slice(at, at + 60).match(/^app\s*\.\s*([\w$]+)/) || [])[1];
        findings.push({
          file, line, identifier: "app", registrar, kind: "bare-app",
          message: `${file}:${line}: bare \`app.\` inside the \`${registrar}\` `
            + `handler — write \`e.app.\` instead.\n`
            + `    There is no module-scope \`app\` in a handler context. The `
            + `app is a\n    property of the event argument, so `
            + `\`app.${method || "findRecordsByFilter"}(...)\` must be\n`
            + `    \`e.app.${method || "findRecordsByFilter"}(...)\`. `
            + `guard.pb.js gets this right at five call sites;\n`
            + `    account_delete.pb.js and agent_key.pb.js both got it wrong `
            + `and lost, respectively,\n    the entire account-delete feature `
            + `and the whole model-call audit trail.\n${WHY_HANDLER_SCOPE}`,
        });
      }
    }

    // ---- trap 2: a module-scope binding read inside the handler ----
    if (byName.size) {
      for (const hit of text.matchAll(/(?<![\w$.])[A-Za-z_$][\w$]*/g)) {
        const name = hit[0];
        const decl = byName.get(name);
        if (!decl || visible.has(name)) continue;
        // `{ OWNER_TABLES: x }` is a key, not a read. Shorthand
        // `{ OWNER_TABLES }` has no colon and stays a read, correctly.
        if (/^\s*:(?!:)/.test(text.slice(hit.index + name.length))) continue;
        const at = scope.start + hit.index;
        const line = lineOf(code, at);
        findings.push({
          file, line, identifier: name, registrar, kind: "top-level-binding",
          message: `${file}:${line}: \`${name}\` is read inside the `
            + `\`${registrar}\` handler but declared at module top level `
            + `(${file}:${decl.line}) — move the declaration INSIDE the `
            + `handler body.\n`
            + `    At request time this throws \`ReferenceError: ${name} is `
            + `not defined\`. This is\n    the exact bug that broke `
            + `"delete everything on my server": account_delete.pb.js\n`
            + `    held \`const OWNER_TABLES\` at column 0 and looped over it `
            + `in the handler.\n    Fix: declare \`${name}\` inside every `
            + `handler that needs it (duplicate it if two\n    handlers need `
            + `it — that duplication is the price of the runtime, not a smell),`
            + `\n    or, for helper functions, put it in a module under `
            + `pb_hooks/ and \`require()\` it\n    inside the handler the way `
            + `sms.pb.js:101 requires twilio_signature.js.\n`
            + `${WHY_HANDLER_SCOPE}`,
        });
      }
    }

    for (const nb of nested) walkScope(nb, visible, registrar);
  }

  return findings;
}

// ---------------------------------------------------------------------------
// 5. The suite.
// ---------------------------------------------------------------------------
let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${name}`);
  if (!ok) failures++;
};

// ---- the analyser against known-bad input ----
// Held as strings, NOT as files in pb_hooks/: a fixture on disk there would be
// loaded by a real PocketBase at boot, and a deliberately broken hook in the
// hooks directory is a production hazard for the sake of a test.

const BAD_TOP_LEVEL_CONST = `
// account_delete.pb.js as it shipped on 2026-08-22.
const OWNER_TABLES = [
  { name: "jobs", legacy: "owner" },
  { name: "events", legacy: null },
];

routerAdd("POST", "/me/delete", (e) => {
  const auth = e.auth;
  if (!auth) return e.json(401, { ok: false, message: "Sign in first." });
  const deleted = {};
  for (const table of OWNER_TABLES) {
    const rows = e.app.findRecordsByFilter(table.name, "owner_ref = {:r}", "", 0, 0, { r: auth.id });
    for (const row of rows) e.app.delete(row);
    deleted[table.name] = rows.length;
  }
  return e.json(200, { ok: true, deleted: deleted });
});
`;

const BAD_BARE_APP = `
// agent_key.pb.js as it shipped: the audit write that never happened.
routerAdd("POST", "/agent/llm", (e) => {
  const ownerRef = String(e.request.header.get("X-Anticipy-Owner") || "");
  const rows = app.findRecordsByFilter("agent_llm_audit", "owner_ref = {:r}", "", 1, 0, { r: ownerRef });
  const rec = new Record(app.findCollectionByNameOrId("agent_llm_audit"));
  rec.set("owner_ref", ownerRef);
  app.save(rec);
  return e.json(200, { ok: true, seen: rows.length });
});
`;

const badConst = analyseHookSource("fixture_bad_const.pb.js", BAD_TOP_LEVEL_CONST);
const badApp = analyseHookSource("fixture_bad_app.pb.js", BAD_BARE_APP);

check("the analyser catches the OWNER_TABLES top-level-const bug",
  badConst.some((f) => f.kind === "top-level-binding" && f.identifier === "OWNER_TABLES"));
check("it reports the OWNER_TABLES bug on the line that reads it, not the "
  + "line that declares it",
  badConst.some((f) => f.identifier === "OWNER_TABLES" && f.line === 12));
check("the OWNER_TABLES message names the file, the line and the identifier",
  badConst.some((f) => f.identifier === "OWNER_TABLES"
    && /fixture_bad_const\.pb\.js:12/.test(f.message)
    && /OWNER_TABLES/.test(f.message)));
check("the OWNER_TABLES message says what to do instead",
  badConst.some((f) => f.identifier === "OWNER_TABLES"
    && /INSIDE the handler body/.test(f.message)
    && /ReferenceError/.test(f.message)));
check("the OWNER_TABLES fixture is not also accused of a bare `app.` — it "
  + "uses e.app throughout",
  !badConst.some((f) => f.kind === "bare-app"));

check("the analyser catches every bare `app.` call site",
  badApp.filter((f) => f.kind === "bare-app").length === 3);
check("it names the method that would have thrown",
  ["findRecordsByFilter", "findCollectionByNameOrId", "save"].every((mth) =>
    badApp.some((f) => f.kind === "bare-app" && f.message.includes(`app.${mth}(`))));
check("the bare-`app.` message names the file, the line and the fix",
  badApp.some((f) => f.kind === "bare-app"
    && /fixture_bad_app\.pb\.js:\d+/.test(f.message)
    && /write `e\.app\.` instead/.test(f.message)));

// ---- the analyser against the CORRECTED forms of the same two files ----
// This is the half that keeps the analyser honest: a checker that flags
// everything would pass every test above.
const GOOD_TOP_LEVEL_CONST = BAD_TOP_LEVEL_CONST
  .replace(/const OWNER_TABLES = \[[\s\S]*?\];\n/, "")
  .replace("routerAdd(\"POST\", \"/me/delete\", (e) => {\n",
    "routerAdd(\"POST\", \"/me/delete\", (e) => {\n"
    + "  const OWNER_TABLES = [\n"
    + "    { name: \"jobs\", legacy: \"owner\" },\n"
    + "    { name: \"events\", legacy: null },\n"
    + "  ];\n");
const GOOD_BARE_APP = BAD_BARE_APP.replace(/(^|[^\w$.])app\./g, "$1e.app.");

check("the fixture rewrite actually moved the declaration inside",
  !/^const OWNER_TABLES/m.test(GOOD_TOP_LEVEL_CONST)
  && /^  const OWNER_TABLES/m.test(GOOD_TOP_LEVEL_CONST));
check("the fixture rewrite actually replaced every bare `app.`",
  GOOD_BARE_APP.includes("e.app.save(rec)")
  && !/(^|[^\w$.])app\./.test(GOOD_BARE_APP));

const goodConst = analyseHookSource("fixture_good_const.pb.js", GOOD_TOP_LEVEL_CONST);
const goodApp = analyseHookSource("fixture_good_app.pb.js", GOOD_BARE_APP);
check("the corrected OWNER_TABLES form is clean",
  goodConst.length === 0);
check("the corrected e.app form is clean", goodApp.length === 0);

// ---- the shapes the analyser must NOT trip over ----
// Every one of these is legal, appears in this tree or in PocketBase's own
// examples, and would be a false positive that gets the whole check deleted.
const DECOYS = `
// A comment naming app.findRecordsByFilter and app.save is not a call.
/* Nor is a block comment: app.delete(row); OWNER_TABLES.length */
routerAdd("POST", "/decoy", (e) => {
  const advice = "use e.app. and never bare app.findRecordsByFilter";
  const tmpl = \`app.save() in a template is still just text\`;
  const path = e.request.url.path;                 // e.app is fine
  const col = e.app.findCollectionByNameOrId("events");
  const also = $app;                               // the JSVM global, legal
  const snap = e?.app?.findRecordsByFilter ? 1 : 0;
  const mine = { app: 1, wrapped: e.app };         // a property named app
  const myapp = { save: () => 0 };
  myapp.save();                                    // not \`app.\`
  const app2 = e.app; app2.save(col);
  const pattern = /app\\.save\\(/;                  // a regex, not a call
  if (pattern.test(advice)) console.log(tmpl, path, mine, snap, also, app2);
  return e.json(200, { ok: true });
});
routerAdd("POST", "/decoy2", (e) => {
  const app = e.app;                               // rebound locally: legal
  app.save(new Record(app.findCollectionByNameOrId("events")));
  return e.json(200, { ok: true });
});
onRecordAfterCreateSuccess((e) => {
  const KEEP = 300;                                // declared in here: legal
  const surplus = e.app.findRecordsByFilter("events", "1=1", "-created", 0, KEEP);
  for (const row of surplus) e.app.delete(row);
}, "events");
`;
check("comments, strings, template text, regex literals, `$app`, `e?.app?.`, "
  + "a property named app, `myapp.`, `app2.` and a locally rebound `app` are "
  + "all left alone",
  analyseHookSource("fixture_decoys.pb.js", DECOYS).length === 0);

// A module binding used at MODULE level is not a bug — only reads inside a
// handler are. The registration arguments themselves are module-level too.
const MODULE_LEVEL_USE = `
const ROUTE = "/ok";
console.log("registering", ROUTE);
routerAdd("POST", ROUTE, (e) => e.json(200, { ok: true }));
`;
check("a module binding read at module level (including as a registration "
  + "argument) is not flagged",
  analyseHookSource("fixture_module_level.pb.js", MODULE_LEVEL_USE).length === 0);

// The two shapes most likely to slip past a naive line-based check.
const SNEAKY = `
const LIMIT = 50;
function helper(x) { return x + 1; }
routerAdd("GET", "/sneaky", function (e) {
  return e.json(200, { n: helper(LIMIT), msg: \`limit is \${LIMIT}\` });
});
cronAdd("sweep", "*/5 * * * *", () => {
  app.findRecordsByFilter("events", "1=1");
});
`;
const sneaky = analyseHookSource("fixture_sneaky.pb.js", SNEAKY);
check("a `function (e) {}` handler is analysed like an arrow handler",
  sneaky.some((f) => f.identifier === "helper" && f.registrar === "routerAdd")
  && sneaky.some((f) => f.identifier === "LIMIT" && f.registrar === "routerAdd"));
check("a module binding referenced from inside a `${}` substitution is caught "
  + "— that is live code, not string text",
  sneaky.filter((f) => f.identifier === "LIMIT").length === 2);
check("a cronAdd callback is covered too — it has the same isolated context",
  sneaky.some((f) => f.kind === "bare-app" && f.registrar === "cronAdd"));

// A concise-body arrow handler, which has no braces to match.
check("a concise-body arrow handler is covered",
  analyseHookSource("fixture_concise.pb.js",
    `const T = 1;\nrouterUse((e) => e.json(200, { t: T }));\n`)
    .some((f) => f.identifier === "T"));

// ---- the two real files, deliberately re-broken in memory ----
// A fifteen-line fixture proves the analyser handles a fifteen-line file. The
// files that actually shipped broken are 214 and 415 lines of nested try/catch,
// template literals, closures and prose comments quoting the very identifiers
// being searched for — so the real proof is to take those files AS THEY STAND
// ON DISK, put the original bug back with a string replace, and require a hit.
// Nothing is written: the mutation lives in a local variable.
const realSrc = (f) => readFileSync(join(hookDir, f), "utf8");

{
  const src = realSrc("account_delete.pb.js");
  // Hoist the OWNER_TABLES declaration back out of the handler, which is
  // exactly the diff that broke the feature.
  const block = /\n( *)(const OWNER_TABLES = \[[\s\S]*?\n\1\];\n)/.exec(src);
  check("the OWNER_TABLES declaration is still findable in the real file — if "
    + "this fails the re-break below proves nothing and must be re-derived",
    !!block);
  if (block) {
    const hoisted = src.replace(block[0], "\n")
      .replace(/^routerAdd\("POST", "\/me\/delete"/m,
        block[2].replace(/^ +/gm, "") + '\nrouterAdd("POST", "/me/delete"');
    check("re-breaking the real account_delete.pb.js moved the const to "
      + "column 0", /^const OWNER_TABLES = \[/m.test(hoisted)
      && !/^ +const OWNER_TABLES/m.test(hoisted));
    const found = analyseHookSource("account_delete.pb.js", hoisted);
    check("the analyser catches the OWNER_TABLES bug in the REAL 214-line "
      + "file, and flags the loop that reads it exactly once",
      found.length === 1 && found[0].kind === "top-level-binding"
      && found[0].identifier === "OWNER_TABLES");
    check("it is not distracted by the two comment lines in that file that "
      + "spell OWNER_TABLES out in prose",
      found.length === 1
      && /for \(const table of OWNER_TABLES\)/.test(
        hoisted.split("\n")[found[0].line - 1]));
  }
}

// A closure that binds its own `app` is CORRECT code, and the enclosing handler
// must still be checked. This is the exact shape of agent_key.pb.js after the
// fix: `auditBegin`/`auditFinish` take an `app` parameter and the handler calls
// them with `e.app`. A blanket "this handler mentions a local app somewhere"
// exemption reported all 415 lines of that file clean — this fixture is here so
// that regression cannot come back.
const SCOPED = `
routerAdd("POST", "/scoped", (e) => {
  const write = (app, rec) => { app.save(rec); };
  const rec = new Record(e.app.findCollectionByNameOrId("events"));
  write(e.app, rec);
  app.save(rec);
  return e.json(200, { ok: true });
});
`;
{
  const found = analyseHookSource("fixture_scoped.pb.js", SCOPED);
  check("a nested closure's own `app` PARAMETER excuses only that closure, "
    + "and the enclosing handler is still checked",
    found.length === 1 && found[0].kind === "bare-app" && found[0].line === 6);
}

{
  // The agent_key.pb.js bug: `e.app.` demoted to a bare `app.`. Because the
  // audit closures legitimately take an `app` parameter, demoting `e.app.`
  // alone leaves those three sites reading a real binding — so the re-break
  // removes that parameter too, which is what makes all eight sites genuine
  // ReferenceErrors. All eight must be reported: a checker that stops at the
  // first hit sends somebody back for seven more rounds of the same bare 400.
  const src = realSrc("agent_key.pb.js");
  const sites = (src.match(/(?<![\w$])e\.app\./g) || []).length;
  check("the real agent_key.pb.js still calls e.app — the re-break needs "
    + "something to demote", sites > 0);
  const broken = src
    .replace(/(?<![\w$])e\.app\./g, "app.")
    .replace(/\(app,\s*/g, "(");
  check("the re-break demoted every e.app and removed the closures' own `app` "
    + "parameter, so all of them are genuinely unbound",
    !/(?<![\w$])e\.app\./.test(broken) && !/\(app,/.test(broken));
  const found = analyseHookSource("agent_key.pb.js", broken);
  check(`the analyser catches all ${sites} demoted call sites in the REAL `
    + `415-line file, across both handlers and inside the nested closures`,
    found.length === sites && found.every((f) => f.kind === "bare-app"));
  check("every report points at a line that really does call bare `app.`",
    found.every((f) => /(?<![\w$.])app\s*\./.test(broken.split("\n")[f.line - 1])));
  check("the unmodified agent_key.pb.js is clean, so the re-break is what "
    + "produced those hits and not the file itself",
    analyseHookSource("agent_key.pb.js", src).length === 0);
}

// ---- and now the real directory ----
// Nine hook files at the time the OWNER_TABLES bug was found; fourteen now.
// Enumerated from disk rather than listed, so a new hook file is covered the
// moment it lands instead of the moment somebody remembers this suite.
const hookFiles = readdirSync(hookDir).filter((f) => f.endsWith(".pb.js")).sort();
check("the hook directory is where it is expected to be and is not empty",
  hookFiles.length > 0);

const realFindings = [];
for (const file of hookFiles) {
  const src = readFileSync(join(hookDir, file), "utf8");
  const found = analyseHookSource(file, src);
  realFindings.push(...found);
  const code = blankNonCode(src);
  let handlers = 0;
  REGISTRAR.lastIndex = 0;
  let m;
  while ((m = REGISTRAR.exec(code)) !== null) {
    const open = m.index + m[0].length - 1;
    const close = matchDelim(code, open, "(", ")");
    if (close !== -1) handlers += functionBodies(code, open + 1, close).length;
  }
  console.log(`     checked ${file}: ${handlers} handler `
    + `${handlers === 1 ? "body" : "bodies"}, `
    + `${found.length === 0 ? "clean" : `${found.length} PROBLEM(S)`}`);
}

// A file with no registration at all is a file this suite silently ignores, so
// say so out loud rather than reporting reassuring coverage of nothing.
const noHandlers = hookFiles.filter((file) => {
  const code = blankNonCode(readFileSync(join(hookDir, file), "utf8"));
  REGISTRAR.lastIndex = 0;
  return REGISTRAR.exec(code) === null;
});
check(`every *.pb.js file registers at least one handler `
  + `(otherwise it is not covered here)${noHandlers.length ? `: ${noHandlers.join(", ")}` : ""}`,
  noHandlers.length === 0);

check(`all ${hookFiles.length} hook files are free of both scope traps`,
  realFindings.length === 0);
if (realFindings.length) {
  console.error("\n--- backend/pb_hooks scope violations ---");
  for (const f of realFindings) console.error(f.message + "\n");
}

if (failures) {
  console.error(`test_hook_scope_trap: ${failures} check(s) failed`);
  process.exit(1);
}
console.log("test_hook_scope_trap: all passed");
