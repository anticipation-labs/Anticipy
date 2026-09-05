// THE SPIKE FENCE.
//
// The owner's rule for week 1 is one sentence: "nothing here touches the
// backend until week 2." A rule with no leg is not a rule — it is a paragraph
// in a README that stops being true on the afternoon somebody needs one
// function from brain/ and takes it.
//
// The fence has two sides and both of them have to hold:
//
//   OUTBOUND  nothing under spike/two-hands may import from brain/,
//             extension/, migration/ or backend/, or from anywhere else
//             outside this directory. That includes npm packages: this spike
//             is `node --experimental-strip-types` with no build step and no
//             install, and the day one dependency appears the "clone it and
//             run the tests" claim in the README is false.
//
//   INBOUND   nothing outside spike/two-hands may import anything inside it.
//             This is the side that actually matters, and it is the one a
//             `git grep` alone gets wrong: a research note that NAMES the
//             directory is Law 4 working as intended, and an import of it is a
//             production system quietly depending on a spike. Only the second
//             fails here.
//
// WHAT THIS FILE DELIBERATELY DOES NOT DO: forbid reading a file outside the
// spike. `test/signature.test.ts` reads `docs/BRIEF.html` to prove the five
// recipe scenes are verbatim from the brief, and that check is the reason a
// paraphrased requirement goes red instead of shipping. A fence that grepped
// for three dots and a slash would kill it, so this one is scoped to IMPORT
// SPECIFIERS — and leg 3 then covers the hole that scoping leaves, by
// resolving escaping path literals and failing only when one lands in
// production CODE.
//
// COMMENTS ARE STRIPPED BEFORE ANY SPECIFIER IS READ. An import written inside
// a comment is not an import, and the first draft of this file failed on its
// own header for explaining which shapes it catches. A fence that fails on
// prose gets deleted by the next person in a hurry, which is a worse outcome
// than the one it was guarding against.
//
// The pattern matching below is the legal kind twice over: it reads JavaScript
// syntax, not anybody's words, and it lives in a deterministic gate
// (HARNESS-LAWS law 1, clauses "senses" and "gates and evals").

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, resolve, sep } from "node:path";

const SPIKE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(SPIKE, "..", "..");

/** The four directories the owner's rule names. Written as a list on purpose:
 *  this is a gate, and a gate is the one place HARNESS-LAWS law 1 allows a list
 *  of names to decide an outcome. It decides nothing at run time — it fails a
 *  test. */
const PRODUCTION_DIRS = ["brain", "extension", "migration", "backend"];

// Directories that are not part of the repo's source even though they sit
// inside the checkout. `.claude/worktrees` holds full copies of this same tree
// made for other agents; scanning them would report this spike's own files as
// outsiders importing themselves.
const SKIP_DIRS = new Set([
  ".git",
  ".claude",
  "node_modules",
  "__pycache__",
  ".venv",
  "venv",
  "dist",
  "build",
  ".pytest_cache",
]);

const CODE_EXTENSIONS = new Set([".ts", ".js", ".mjs", ".cjs", ".py"]);
// Docs are scanned too, so leg 4 can say "every mention outside the spike is
// prose" rather than the weaker "every mention in code is prose".
const TEXT_EXTENSIONS = new Set([".md", ".html", ".json", ".yml", ".yaml", ".sh", ".toml"]);

// A file big enough to be data rather than source. Reading a 40MB jsonl into a
// string to look for an import statement costs more than the check is worth.
const MAX_SCAN_BYTES = 2_000_000;

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot);
}

function walk(dir: string, keep: (path: string) => boolean, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      walk(full, keep, out);
      continue;
    }
    if (!entry.isFile()) continue;
    if (!keep(full)) continue;
    if (statSync(full).size > MAX_SCAN_BYTES) continue;
    out.push(full);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Comments out, code in.
// ---------------------------------------------------------------------------
/**
 * Replace every comment with spaces, tracking string state so a URL's "//" or
 * an apostrophe in prose cannot swallow the rest of a line.
 *
 * Spaces rather than deletion: line and column offsets stay put, so an error
 * message that quotes a line still quotes the right one.
 */
function stripComments(source: string): string {
  const out: string[] = [];
  let quote: string | null = null;
  let comment: "line" | "block" | null = null;

  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    const next = source[i + 1];

    if (comment === "line") {
      if (ch === "\n") {
        comment = null;
        out.push(ch);
      } else out.push(" ");
      continue;
    }
    if (comment === "block") {
      if (ch === "*" && next === "/") {
        comment = null;
        out.push("  ");
        i++;
      } else out.push(ch === "\n" ? ch : " ");
      continue;
    }
    if (quote !== null) {
      out.push(ch);
      // A backslash escapes the next character, including the closing quote.
      // Without this, "a\"b" ends the string early and the rest of the file is
      // read as code — which would make the fence report imports that are text.
      if (ch === "\\") {
        if (next !== undefined) out.push(next);
        i++;
        continue;
      }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      out.push(ch);
      continue;
    }
    if (ch === "/" && next === "/") {
      comment = "line";
      out.push(" ");
      continue;
    }
    if (ch === "/" && next === "*") {
      comment = "block";
      out.push(" ");
      continue;
    }
    out.push(ch);
  }
  return out.join("");
}

// ---------------------------------------------------------------------------
// Import specifiers, of every shape this runtime honours.
// ---------------------------------------------------------------------------
// `import`-with-`from`, side-effect `import`, `export`-with-`from`, dynamic
// `import(...)` and `require(...)`. Missing one of these is how a fence gets
// walked around without anybody lying: dynamic import is the natural way to
// reach for something you know you are not supposed to reach for.
//
// The captured specifier may not contain a newline. A real module specifier
// never does, and allowing one lets a lazy match run from a stray keyword
// through half a file and report a paragraph as an import.
//
// WHAT THE KEYWORD MAY BE FOLLOWED BY, and why it is three characters and not
// `\s`. This pattern used to require whitespace, which is how `import{x}from`
// and `import*as x from` — both legal, neither unusual in hand-written code —
// were not imports as far as this fence was concerned: an adversary planted
// five of them inside the spike and all five legs stayed green. Whitespace, `{`
// and `*` are the only three things that may follow the keyword in a
// specifier-bearing form, and naming all three is what makes the leg true; a
// bare `\s*` instead would read `importantThing from "x"` as an import and the
// fence would start failing on prose, which is how a fence gets deleted.
const SPECIFIER_PATTERNS: RegExp[] = [
  /(?:^|[\s;})])(?:import|export)(?:\s|(?=[*{]))[^;'"]*?from\s*["']([^"'\n]+)["']/g,
  /(?:^|[\s;})])import\s*["']([^"'\n]+)["']/g,
  /\bimport\s*\(\s*["']([^"'\n]+)["']\s*\)/g,
  /\brequire\s*\(\s*["']([^"'\n]+)["']\s*\)/g,
  // A dynamic import or require whose specifier is a TEMPLATE LITERAL. Legal,
  // static, and the next shape to reach for once the quoted forms are fenced.
  // `[^`$\n]` excludes interpolation on purpose: `${base}/x.ts` is a path this
  // file cannot resolve, and a fence that guessed at it would go red on code
  // that is importing nothing — which is how a fence gets deleted rather than
  // fixed. An interpolated escape is left to leg 3, which reads raw text.
  /\b(?:import|require)\s*\(\s*`([^`$\n]+)`\s*\)/g,
];

function specifiersIn(rawSource: string): string[] {
  const source = stripComments(rawSource);
  const found = new Set<string>();
  for (const pattern of SPECIFIER_PATTERNS) {
    // `lastIndex` is per-RegExp-object state and these are module-level
    // literals, so a second call would otherwise start mid-file and miss the
    // imports at the top — the fence would pass by skipping the very lines it
    // exists to read.
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(source)) !== null) found.add(match[1]);
  }
  return [...found];
}

/** Python's import forms, for the inbound leg. `import spike.two_hands` cannot
 *  happen (the directory name has a hyphen), but a `sys.path` insertion or an
 *  `importlib` call reaching a path can. */
const PY_IMPORT_LINE = /^\s*(?:from\s+\S+\s+import\s|import\s|importlib|__import__|sys\.path)/;

function isImportishLine(line: string): boolean {
  if (PY_IMPORT_LINE.test(line)) return true;
  return specifiersIn(line).length > 0;
}

// Every extension `node` will load as a module. `.ts` alone was the second half
// of the hole leg 6 covers: a `.js`, `.mjs` or `.cjs` file in the spike was
// never opened, so it could import brain/ in the plainest possible syntax with
// every leg green. The spike is `--experimental-strip-types` and has no build
// step, so nothing here SHOULD be anything but `.ts` — which is the argument
// for scanning the rest, not against it: the file that turns up in a language
// the fence does not read is exactly the one nobody meant to write.
const SPIKE_MODULE_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]);

function spikeSources(): string[] {
  const files = walk(SPIKE, (p) => SPIKE_MODULE_EXTENSIONS.has(extensionOf(p)));
  // The walker IS the leg. A renamed directory or a swallowed readdir would
  // leave an empty list, and an empty list passes every assertion below while
  // proving nothing at all.
  assert.ok(
    files.length >= 8,
    `the walker found ${files.length} module files under the spike; it should see every module and every test`,
  );
  return files;
}

// ---------------------------------------------------------------------------
// The two outbound legs, as functions the tests call.
// ---------------------------------------------------------------------------
// Extracted from the `test(...)` bodies they used to live in for one reason:
// leg 6 runs them over a PLANTED violation. A detector that has only ever been
// run against a clean tree is indistinguishable from a detector that returns
// the empty list unconditionally — and both of the holes leg 6 now covers
// (a specifier with no space after the keyword, a file that is not `.ts`) were
// exactly that: five real imports of brain/ sat inside the spike with all five
// legs green.
function outsideSpikeViolations(files: string[]): string[] {
  const violations: string[] = [];

  for (const file of files) {
    for (const spec of specifiersIn(readFileSync(file, "utf8"))) {
      const where = `${relative(REPO, file)} -> ${spec}`;

      // Node builtins, and only under the `node:` prefix. The bare form ("fs",
      // "path") is also legal JavaScript, and refusing it is deliberate: a bare
      // "crypto" is indistinguishable at a glance from an npm package of the
      // same name, and this spike must have no packages.
      if (spec.startsWith("node:")) continue;

      if (!spec.startsWith(".") && !spec.startsWith("/")) {
        violations.push(`${where} (bare specifier: this spike has no dependencies and no install step)`);
        continue;
      }

      const target = resolve(dirname(file), spec);
      const inside = target === SPIKE || target.startsWith(SPIKE + sep);
      if (!inside) violations.push(`${where} (resolves to ${relative(REPO, target)}, outside the spike)`);
    }
  }
  return violations;
}

function productionDirViolations(files: string[]): string[] {
  const violations: string[] = [];

  for (const file of files) {
    for (const spec of specifiersIn(readFileSync(file, "utf8"))) {
      const target = spec.startsWith(".") || spec.startsWith("/") ? resolve(dirname(file), spec) : null;
      const rel = target === null ? spec : relative(REPO, target);
      const head = rel.split(sep)[0].split("/")[0];
      if (PRODUCTION_DIRS.includes(head)) {
        violations.push(`${relative(REPO, file)} imports ${spec} (${rel})`);
      }
    }
  }
  return violations;
}

// ---------------------------------------------------------------------------
// LEG 1 — nothing in the spike imports anything outside the spike.
// ---------------------------------------------------------------------------
test("every specifier in the spike is a node builtin or a file inside the spike", () => {
  const violations = outsideSpikeViolations(spikeSources());
  assert.deepEqual(
    violations,
    [],
    `week 1 is a spike and imports nothing outside itself:\n  ${violations.join("\n  ")}`,
  );
});

// ---------------------------------------------------------------------------
// LEG 2 — the owner's four directories, named.
// ---------------------------------------------------------------------------
// Redundant with leg 1 by construction, and kept anyway. Leg 1 is a general
// rule that a future edit could loosen for a defensible reason ("let the spike
// import one shared type"); this leg is the specific promise, so loosening the
// general rule does not silently take the specific promise with it.
test("no file in the spike names brain/, extension/, migration/ or backend/ in an import", () => {
  const violations = productionDirViolations(spikeSources());
  assert.deepEqual(violations, [], `the spike reached into production:\n  ${violations.join("\n  ")}`);
});

// ---------------------------------------------------------------------------
// LEG 3 — the hole leg 1's scoping leaves.
// ---------------------------------------------------------------------------
// Leg 1 reads import specifiers only, so a readFileSync of a production path
// walks straight through it. That is not a hypothetical shape: signature.test.ts
// already reads a file outside the spike on purpose. So the rule is not "never
// escape" — it is "escaping is for DATA, never for production code".
//
// This leg reads the RAW source, comments included. A commented-out path is
// nobody's dependency, but it is a note about where the next person should
// look, and this is the cheap place to catch that intention.
test("a path literal that escapes the spike may not land in production code", () => {
  const violations: string[] = [];
  // Any quoted literal that climbs out of its own directory. Deliberately
  // loose: this leg would rather look at a harmless string twice than miss the
  // one that matters.
  const escaping = /["'`](\.\.\/[^"'`\n]*)["'`]/g;

  for (const file of spikeSources()) {
    const source = readFileSync(file, "utf8");
    escaping.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = escaping.exec(source)) !== null) {
      const target = resolve(dirname(file), match[1]);
      if (target === SPIKE || target.startsWith(SPIKE + sep)) continue;
      const head = relative(REPO, target).split(sep)[0].split("/")[0];
      if (PRODUCTION_DIRS.includes(head)) {
        violations.push(`${relative(REPO, file)} reaches ${relative(REPO, target)}`);
      }
    }
  }

  assert.deepEqual(
    violations,
    [],
    `a spike file reads production code by path:\n  ${violations.join("\n  ")}`,
  );
});

// ---------------------------------------------------------------------------
// LEG 4 — nothing outside the spike imports the spike.
// ---------------------------------------------------------------------------
interface RepoEntry {
  label: string;
  source: string;
}

/** Read lazily rather than into one array: the repo walk is several hundred
 *  files and this leg needs one at a time. */
function* repoEntries(files: string[]): Generator<RepoEntry> {
  for (const file of files) yield { label: relative(REPO, file), source: readFileSync(file, "utf8") };
}

const SPIKE_NEEDLE = ["spike", "two-hands"].join("/");

/** Split every line that NAMES the spike into the two piles the fence exists to
 *  tell apart: an import of it, and a sentence about it. */
function inboundImportScan(entries: Iterable<RepoEntry>): { importedBy: string[]; mentions: number } {
  const importedBy: string[] = [];
  let mentions = 0;

  for (const entry of entries) {
    if (!entry.source.includes(SPIKE_NEEDLE)) continue;
    const lines = entry.source.split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (!lines[i].includes(SPIKE_NEEDLE)) continue;
      if (isImportishLine(lines[i])) {
        importedBy.push(`${entry.label}:${i + 1}: ${lines[i].trim().slice(0, 120)}`);
      } else {
        mentions++;
      }
    }
  }
  return { importedBy, mentions };
}

function assertInboundHolds(scan: { importedBy: string[]; mentions: number }): void {
  assert.deepEqual(
    scan.importedBy,
    [],
    `production code imports the week-1 spike:\n  ${scan.importedBy.join("\n  ")}`,
  );
  // THE CONTROL, and it is the whole reason this line is an assertion rather
  // than a comment. `importedBy` is empty in two different worlds: one where
  // every mention outside the spike is prose, and one where the scanner read no
  // line at all — a renamed directory, a walker that returned nothing, a needle
  // that no longer matches. Both look green. This line separates them by
  // requiring that at least one real line outside the spike was classified.
  // It stood here for a week as `assert.ok(mentions >= 0)`, which is true of a
  // `let mentions = 0` counter no matter what happened, on the side the header
  // of this file calls "the side that actually matters".
  assert.ok(
    scan.mentions > 0,
    "nothing outside the spike so much as names it, so this leg classified no line and proved nothing; " +
      "plant a control mention (research/ notes about the spike are the natural one) or delete the leg " +
      "and say in RESULTS.md that the inbound side is unchecked",
  );
}

test("the repo mentions spike/two-hands only in prose, never in an import", () => {
  const files = walk(REPO, (p) => {
    const ext = extensionOf(p);
    if (!CODE_EXTENSIONS.has(ext) && !TEXT_EXTENSIONS.has(ext)) return false;
    return !(p === SPIKE || p.startsWith(SPIKE + sep));
  });
  assert.ok(files.length >= 200, `the repo walker found only ${files.length} files; it is not looking at the repo`);
  assert.ok(
    files.some((f) => relative(REPO, f) === join("brain", "orchestrator.py")),
    "the repo walker cannot see brain/orchestrator.py, so it could not see brain/ importing the spike either",
  );

  assertInboundHolds(inboundImportScan(repoEntries(files)));
});

// ---------------------------------------------------------------------------
// LEG 5 — the fence can still go red.
// ---------------------------------------------------------------------------
// Every leg above passes today. A leg that has never failed and cannot be shown
// to fail is indistinguishable from a leg that is broken, and this repo has the
// receipts for that exact mistake (tejas_gate leg 2, read as an expiry for
// months while it was a regression pin). So the detector is run against a
// planted violation of each shape it claims to catch.
//
// The fixtures are ASSEMBLED AT RUN TIME from parts. Writing them as literal
// import lines would put a real import of brain/ in this file, legs 1 to 3
// would fail on the fence's own test data, and the fix somebody reached for
// would be an exemption — after which the fence no longer checks itself.
test("the detector catches every import shape it claims to", () => {
  const q = '"';
  const up = ["..", "..", ""].join("/");
  const prod = (dir: string, file: string) => `${up}${dir}/${file}`;

  const shapes: string[] = [
    `import { hear } from ${q}${prod("brain", "llm.ts")}${q};`,
    `import ${q}${prod("extension", "agent_loop.js")}${q};`,
    `export { thing } from ${q}${prod("backend", "api.ts")}${q};`,
    `const m = await import(${q}${prod("migration", "workers/x.ts")}${q});`,
    `const n = require(${q}${prod("backend", "db.js")}${q});`,
    `import fetchImpl from ${q}undici${q};`,
    // THE SHAPES THAT WALKED THROUGH. The scanner used to demand whitespace
    // after the keyword (`import\s`), so a prettier-free hand-written line with
    // no space — the four below — was not an import as far as this fence was
    // concerned, and an adversary planted five of them in the spike with all
    // five legs green. They are the natural way to write an import you know you
    // are not supposed to write.
    `import{hear}from${q}${prod("brain", "llm.ts")}${q};`,
    `import*as brain from${q}${prod("brain", "llm.ts")}${q};`,
    `export{thing}from${q}${prod("backend", "api.ts")}${q};`,
    `export*from${q}${prod("backend", "api.ts")}${q};`,
    // A dynamic import whose specifier is a template literal. Legal, static,
    // and the natural next thing to try once the quoted form is fenced. Only
    // the interpolation-free form is read: `${...}` inside one is a path this
    // check cannot resolve, and guessing at it would fail the fence on code
    // that is not importing anything.
    `const m = await import(\`${prod("brain", "llm.ts")}\`);`,
  ];
  for (const line of shapes) {
    assert.equal(specifiersIn(line).length, 1, `the specifier scanner did not see the import in: ${line}`);
  }

  // The inbound side: an import of the spike from outside must read as an
  // import, while the research note that names it must read as prose.
  const spikePath = ["spike", "two-hands", "src", "index.ts"].join("/");
  assert.ok(isImportishLine(`import { makeTwoHands } from ${q}../${spikePath}${q};`));
  assert.ok(
    isImportishLine(`import{makeTwoHands}from${q}../${spikePath}${q};`),
    "the inbound side is the one that matters, and it reads specifiers with the same scanner as the outbound one",
  );
  assert.ok(isImportishLine(`import*as twoHands from${q}../${spikePath}${q};`));
  assert.ok(isImportishLine("from spike.two_hands import router"));
  assert.ok(
    !isImportishLine("The exercise was deliberate and the hashes live in spike/two-hands/tasks/."),
    "a research note that names the spike is Law 4 working, not a violation",
  );

  // Comment stripping must not become a way through the fence: a REAL import
  // on a line that also carries a comment is still an import.
  assert.equal(specifiersIn(`import x from ${q}./router.ts${q}; // the five rules`).length, 1);
  // ...and prose about importing is not one.
  assert.equal(specifiersIn(`// nothing here imports from ${q}brain${q}`).length, 0);
  // The boundary the three allowed follow-characters buy. Loosening them to a
  // bare `\s*` reads this line as an import of ./x.ts, the fence starts failing
  // on code that is not importing anything, and the next person in a hurry
  // deletes it rather than the rule.
  assert.equal(specifiersIn(`const importantly = from ${q}./x.ts${q};`).length, 0);
  // A protocol's slashes are not a comment. Without the string tracking in
  // stripComments this line loses its tail, and with it any import beside it.
  assert.equal(specifiersIn(`const u = ${q}https://x.invalid/a${q}; import y from ${q}./ledger.ts${q};`).length, 1);
});

// ---------------------------------------------------------------------------
// LEG 5b — leg 4's control is a control.
// ---------------------------------------------------------------------------
// Leg 4 passes when nothing outside the spike imports it. It ALSO passes when
// nothing outside the spike was read at all, and those two worlds are the whole
// difference between a fence and a decoration. So the assertion leg 4 makes is
// exercised here directly, in both directions, against entries this test writes
// rather than against the tree.
test("the inbound leg fails on a scan that classified nothing, and on a real import", () => {
  const q = '"';
  const spikePath = ["spike", "two-hands", "src", "index.ts"].join("/");

  // A prose mention is what the leg wants to find, and finding one is what
  // makes its silence about imports mean anything.
  const prose = inboundImportScan([
    { label: "research/note.md", source: `The hashes live in ${spikePath.split("/").slice(0, 2).join("/")}/tasks/.` },
  ]);
  assert.equal(prose.mentions, 1);
  assert.deepEqual(prose.importedBy, []);
  assertInboundHolds(prose);

  // Nothing read: the leg must refuse rather than report green.
  assert.throws(
    () => assertInboundHolds(inboundImportScan([])),
    /proved nothing/,
    "a scan that classified no line is the vacuous pass this leg exists to make impossible",
  );

  // And a real inbound import must still take it red.
  const imported = inboundImportScan([
    { label: "brain/orchestrator.py", source: `import{makeTwoHands}from${q}../${spikePath}${q};` },
  ]);
  assert.equal(imported.mentions, 0);
  assert.equal(imported.importedBy.length, 1);
  assert.throws(() => assertInboundHolds(imported), /imports the week-1 spike/);
});

// ---------------------------------------------------------------------------
// LEG 6 — the fence, run against a violation that is really in the tree.
// ---------------------------------------------------------------------------
// Leg 5 proves the SCANNER sees a line. This leg proves the WALKER hands it the
// file: it writes one violating module at a time inside the spike, runs legs 1
// and 2 over the real tree, and requires each one to go red naming that file.
// Both holes it covers were live — an adversary planted five imports of brain/
// and this suite stayed green — and they were different holes: two of the
// shapes were invisible to the scanner, and every non-`.ts` file was invisible
// to the walker, which is the more dangerous of the two because it does not
// matter how the import is written.
//
// The bodies are assembled from parts, and the quote character is interpolated,
// for the reason leg 5 gives: a literal import of brain/ in this file would put
// the fence's own test data in front of legs 1 to 3.
//
// The planted file is real and is in the tree for the few milliseconds each
// assertion takes, removed in a `finally` either way. That is deliberate — the
// walker is half of what this leg proves, and a fixture in a temp directory
// would not exercise it — and it is the one reason a SECOND copy of this suite,
// run against this checkout at the same instant, could see a violation that is
// not the checkout's. If leg 1 or 2 ever goes red naming `fence-probe/`, that
// is what happened; re-run before believing it.
test("a planted import of production code is caught in every shape and every file type", () => {
  const q = '"';
  // Out of fence-probe/, out of two-hands/, out of spike/ — the repo root.
  const up = ["..", "..", "..", ""].join("/");
  const prod = (dir: string, file: string) => `${up}${dir}/${file}`;
  const probeDir = join(SPIKE, "fence-probe");

  const plants: { file: string; body: string; production: boolean; why: string }[] = [
    {
      file: "braces.ts",
      body: `import{hear}from${q}${prod("brain", "llm.ts")}${q};`,
      production: true,
      why: "no whitespace after the keyword",
    },
    {
      file: "namespace.ts",
      body: `import*as brain from${q}${prod("brain", "llm.ts")}${q};`,
      production: true,
      why: "a namespace import with no whitespace after the keyword",
    },
    {
      file: "reexport.ts",
      body: `export{thing}from${q}${prod("backend", "api.ts")}${q};`,
      production: true,
      why: "a re-export with no whitespace after the keyword",
    },
    {
      file: "plain.js",
      body: `import { hear } from ${q}${prod("brain", "llm.ts")}${q};`,
      production: true,
      why: "a .js file, which the walker did not open at all",
    },
    {
      file: "module.mjs",
      body: `const m = await import(${q}${prod("migration", "workers/x.ts")}${q});`,
      production: true,
      why: "a dynamic import in an .mjs file",
    },
    {
      file: "legacy.cjs",
      body: `const db = require(${q}${prod("backend", "db.js")}${q});`,
      production: true,
      why: "a require() in a .cjs file",
    },
    {
      file: "template.ts",
      body: `const m = await import(\`${prod("brain", "llm.ts")}\`);`,
      production: true,
      why: "a dynamic import whose specifier is a template literal",
    },
    {
      file: "dependency.mjs",
      body: `import fetchImpl from ${q}undici${q};`,
      production: false,
      why: "an npm package in an .mjs file: no install step, so no dependency",
    },
  ];

  try {
    for (const plant of plants) {
      rmSync(probeDir, { recursive: true, force: true });
      mkdirSync(probeDir, { recursive: true });
      const planted = join(probeDir, plant.file);
      writeFileSync(planted, `${plant.body}\n`);

      const sources = spikeSources();
      assert.ok(
        sources.includes(planted),
        `the walker never opened ${plant.file} (${plant.why}), so no leg below could have seen it`,
      );

      const outside = outsideSpikeViolations(sources);
      assert.ok(
        outside.some((v) => v.includes(plant.file)),
        `leg 1 did not catch ${plant.file} (${plant.why}): ${JSON.stringify(outside)}`,
      );

      const production = productionDirViolations(sources);
      assert.equal(
        production.some((v) => v.includes(plant.file)),
        plant.production,
        `leg 2 disagreed about ${plant.file} (${plant.why}): ${JSON.stringify(production)}`,
      );
    }
  } finally {
    rmSync(probeDir, { recursive: true, force: true });
  }

  // And green again with the plants gone, so the red above was theirs and not
  // the tree's.
  const clean = spikeSources();
  assert.deepEqual(outsideSpikeViolations(clean), []);
  assert.deepEqual(productionDirViolations(clean), []);
});
