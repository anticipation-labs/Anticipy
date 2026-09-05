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
// THREE THINGS A FENCE MADE OF PATTERNS AND A DIRECTORY WALK GETS WRONG, all
// of them found by an adversary who RAN the evasion rather than argued about
// it, and all of them fixed below rather than described:
//
//   1. THE WALKER DECIDES WHAT THE SCANNER EVER SEES. A skip list is a hole
//      with a name on it: while `dist`, `build`, `node_modules` and six other
//      names were skipped everywhere, `spike/two-hands/dist/x.ts` could import
//      brain/ in the plainest possible syntax with every leg green. Inside the
//      spike the walker now skips NOTHING (`SPIKE_SKIP_DIRS`), and the reason
//      is written where the list used to be.
//
//   2. A SYMLINK IS A DOOR, AND `readdirSync` HANDED IT BACK AS NEITHER A FILE
//      NOR A DIRECTORY, so the old walker dropped it on the floor.
//      `ln -s ../../brain spike/two-hands/prod` plus `import "./prod/llm.ts"`
//      is an import that RESOLVES INSIDE THE SPIKE — legs 1, 2 and 3 all stay
//      green while the process loads production code. Links are now walked,
//      never followed, and one that leaves the spike is a violation on its own.
//
//   3. THE TEXT OF A SPECIFIER IS NOT THE VALUE THE RUNTIME RESOLVES. An
//      escaped specifier (`\u002f` where a `/` belongs) and a concatenated one
//      (`"<up>br" + "ain/llm.ts"`) both load brain/llm.ts, and both were
//      invisible to a check that compared source text: read as text the first
//      is one path segment full of backslashes and `path.resolve` puts it
//      INSIDE the spike. Specifiers are now COOKED — escape sequences decoded,
//      `+` chains joined — before anything resolves them, so the fence reads
//      what node reads.
//
// `<up>` ABOVE AND THROUGHOUT stands for the `../..` that climbs out of the
// spike, and it is written that way on purpose: leg 3 reads this file's RAW
// source, comments included, so a real climbing path in a comment here is a
// violation of the fence by the fence. Every fixture below is assembled from
// parts at run time for the same reason.
//
// The pattern matching below is the legal kind twice over: it reads JavaScript
// syntax, not anybody's words, and it lives in a deterministic gate
// (HARNESS-LAWS law 1, clauses "senses" and "gates and evals").

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  readlinkSync,
  realpathSync,
  rmSync,
  statSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, resolve, sep } from "node:path";

const SPIKE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(SPIKE, "..", "..");
/** The same directory with every symlink in its own prefix resolved. A link is
 *  compared against THIS, because `realpathSync` returns real paths and a
 *  checkout reached through a symlinked parent would otherwise make every link
 *  inside the spike look like an escape. */
const SPIKE_REAL = realpathSync(SPIKE);

/** The four directories the owner's rule names. Written as a list on purpose:
 *  this is a gate, and a gate is the one place HARNESS-LAWS law 1 allows a list
 *  of names to decide an outcome. It decides nothing at run time — it fails a
 *  test. */
const PRODUCTION_DIRS = ["brain", "extension", "migration", "backend"];

// WHAT THE REPO WALK SKIPS, AND WHY EACH NAME IS ON THE LIST. This walk feeds
// the INBOUND leg, whose question is "does the repo's own source import the
// spike". Every name below is either a copy of some other tree or a cache of
// one, so a hit inside it answers a different question:
//   .git            object store, binary, not source
//   .claude         holds full worktree copies of THIS tree made for other
//                   agents; scanning them reports the spike's own files as
//                   outsiders importing themselves
//   node_modules    vendored third-party code; the repo root has one
//   __pycache__ / .pytest_cache   compiled and cached copies of brain/
//   .venv / venv    a vendored Python install
//   dist / build    build output, i.e. a copy of source that already counted
const REPO_SKIP_DIRS = new Set([
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

// WHAT THE SPIKE WALK SKIPS: nothing, deliberately, and this empty set is the
// fix for a live hole rather than an oversight.
//
// The list above used to be applied to BOTH walks, and inside the spike every
// name on it is a place to hide: `spike/two-hands/dist/x.ts` importing
// `<up>brain/llm.ts` was never opened, so the plainest violation in the
// plainest syntax left every leg green. The names are not neutral here —
// none of them may exist in this spike at all. It has no build step, so no
// `dist` and no `build`; no install step, so no `node_modules`; no Python, so
// no `__pycache__` and no venv. If one turns up, its contents are exactly what
// this fence needs to read, and a `node_modules` full of bare specifiers
// failing leg 1 loudly is the CORRECT verdict, not a false alarm: the README
// promises "clone it and run the tests" with no install.
//
// The cost of scanning everything is bounded by `keep` (module extensions
// only) and `MAX_SCAN_BYTES`. The cost of one skipped name was five real
// imports of brain/ sitting in the tree, green.
const SPIKE_SKIP_DIRS = new Set<string>();

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

/** What a walk found: the files to scan, and every symlink met on the way.
 *  Links are a second pile rather than an omission because they are the only
 *  thing in a tree that can make an outside file answer to an inside path. */
interface Tree {
  files: string[];
  symlinks: string[];
}

function emptyTree(): Tree {
  return { files: [], symlinks: [] };
}

/**
 * Walk a directory tree, collecting the files `keep` accepts and every symlink
 * encountered.
 *
 * SYMLINKS ARE RECORDED AND NEVER FOLLOWED, and the ordering of the checks
 * below is the whole point. `readdirSync(…, { withFileTypes: true })` types an
 * entry by the LINK, not by its target, so a symlink is neither
 * `isDirectory()` nor `isFile()` — the previous walker's
 * `if (!entry.isFile()) continue` therefore threw every link away silently.
 * That is how `ln -s ../../brain spike/two-hands/prod` becomes an invisible
 * door: the import through it (`./prod/llm.ts`) resolves inside the spike, so
 * no specifier check can object, and the linked files are never opened, so no
 * scan can object either.
 *
 * Not FOLLOWING them is equally deliberate. Following would read brain/'s files
 * as though they were the spike's and report violations against the wrong file,
 * and a link cycle would hang the walk. Refusing a door is a better answer than
 * walking through it.
 */
function walk(dir: string, keep: (path: string) => boolean, skip: Set<string>, out: Tree): Tree {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isSymbolicLink()) {
      out.symlinks.push(full);
      continue;
    }
    if (entry.isDirectory()) {
      if (skip.has(entry.name)) continue;
      walk(full, keep, skip, out);
      continue;
    }
    if (!entry.isFile()) continue;
    if (!keep(full)) continue;
    if (statSync(full).size > MAX_SCAN_BYTES) continue;
    out.files.push(full);
  }
  return out;
}

/** Where a symlink really lands, chain and all. `realpathSync` resolves a link
 *  to a link to brain/, which `readlink` alone would report as "inside the
 *  spike" and wave through; `readlink` is the fallback for a DANGLING link,
 *  which realpath cannot answer for and which still declares an intention. */
function symlinkTarget(link: string): string {
  try {
    return realpathSync(link);
  } catch {
    return resolve(dirname(link), readlinkSync(link));
  }
}

function linkStaysInside(link: string): boolean {
  const target = symlinkTarget(link);
  for (const root of [SPIKE, SPIKE_REAL]) {
    if (target === root || target.startsWith(root + sep)) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Comments out, code in.
// ---------------------------------------------------------------------------
/** The punctuators after which a `/` can only open a REGULAR EXPRESSION, never
 *  a division, plus the keywords with the same property. `)` and `}` are
 *  deliberately absent: `(a + b) / 2` is division, and reading it as a regex
 *  would blank everything up to the next `/` — which may be the one inside a
 *  real import specifier on the next line. Where the two readings are
 *  ambiguous this errs towards division, because mistaking a regex for
 *  division makes the scanner NOISY and mistaking division for a regex makes it
 *  BLIND, and only one of those gets noticed. */
const REGEX_MAY_FOLLOW = new Set(["(", ",", "=", ":", "[", "!", "&", "|", "?", "{", ";", "+", "-", "*", "%", "^", "~", "<", ">"]);
const REGEX_MAY_FOLLOW_WORD = /(?:^|[^A-Za-z0-9_$])(?:return|typeof|case|in|of|do|else|yield|await|void|delete|new)$/;

function regexCanStart(out: string[]): boolean {
  const tail = out.slice(-16).join("").replace(/\s+$/, "");
  if (tail === "") return true;
  if (REGEX_MAY_FOLLOW.has(tail[tail.length - 1])) return true;
  return REGEX_MAY_FOLLOW_WORD.test(tail);
}

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
    // A REGEX LITERAL, blanked whole.
    //
    // WHY THIS IS NOT AN OPTIONAL REFINEMENT. This scanner tracks quote
    // characters, and a regex character class is full of them: the leg-3
    // pattern below holds three double quotes, three apostrophes and three
    // backticks. An ODD COUNT desynchronizes the tracker for the REST OF THE
    // FILE, and both halves of what follows are wrong. Noisy half: later
    // comments stop being stripped, so the fence reports its own prose as an
    // import — that is how this was found, with leg 1 failing on this file's
    // own header. Quiet half, and the dangerous one: every later line has its
    // code and string parts swapped, so the `//` inside a URL that is safely
    // inside a string becomes a line comment and blanks the import beside it.
    // Put a regex above an import and walk through. Leg 5 pins both.
    if (ch === "/" && regexCanStart(out)) {
      let j = i + 1;
      let inClass = false;
      let closed = false;
      while (j < source.length) {
        const c = source[j];
        if (c === "\\") {
          j += 2;
          continue;
        }
        // A regex literal cannot span a line. Stopping here bounds the damage
        // of a `/` that was division after all: at worst one line is blanked.
        if (c === "\n") break;
        if (inClass) {
          if (c === "]") inClass = false;
        } else if (c === "[") inClass = true;
        else if (c === "/") {
          closed = true;
          j++;
          break;
        }
        j++;
      }
      if (closed) {
        for (let k = i; k < j; k++) out.push(" ");
        i = j - 1;
        continue;
      }
    }
    out.push(ch);
  }
  return out.join("");
}

// ---------------------------------------------------------------------------
// The text of a literal is not its value.
// ---------------------------------------------------------------------------
/**
 * Decode the escape sequences in the BODY of a JavaScript string or template
 * literal, so this fence compares the same thing the module resolver does.
 *
 * The concrete failure: an import whose specifier spells every `/` as the
 * escape `\u002f` is a legal import of brain/llm.ts. Read as TEXT it is a
 * single path segment full of backslashes, so `path.resolve` places it INSIDE
 * the spike and legs 1, 2 and 3 all pass while the process loads production
 * code. Read as a VALUE it is `<up>brain/llm.ts` and leg 2 names it.
 *
 * The `default` branch is the identity escape, which is what makes `\/`, `\"`
 * and `\\` come out right; it is also what a line continuation collapses to,
 * which is harmless because a specifier may not contain a newline anyway.
 */
function cookStringLiteral(raw: string): string {
  if (!raw.includes("\\")) return raw;
  let out = "";
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (ch !== "\\") {
      out += ch;
      continue;
    }
    const esc = raw[i + 1];
    if (esc === undefined) {
      out += ch;
      break;
    }
    i++;
    switch (esc) {
      case "n":
        out += "\n";
        break;
      case "r":
        out += "\r";
        break;
      case "t":
        out += "\t";
        break;
      case "b":
        out += "\b";
        break;
      case "f":
        out += "\f";
        break;
      case "v":
        out += "\v";
        break;
      case "x": {
        const hex = raw.slice(i + 1, i + 3);
        if (/^[0-9a-fA-F]{2}$/.test(hex)) {
          out += String.fromCharCode(parseInt(hex, 16));
          i += 2;
        } else out += esc;
        break;
      }
      case "u": {
        if (raw[i + 1] === "{") {
          const end = raw.indexOf("}", i + 2);
          const hex = end < 0 ? "" : raw.slice(i + 2, end);
          if (/^[0-9a-fA-F]{1,6}$/.test(hex)) {
            out += String.fromCodePoint(parseInt(hex, 16));
            i = end;
          } else out += esc;
        } else {
          const hex = raw.slice(i + 1, i + 5);
          if (/^[0-9a-fA-F]{4}$/.test(hex)) {
            out += String.fromCharCode(parseInt(hex, 16));
            i += 4;
          } else out += esc;
        }
        break;
      }
      default:
        // The identity escape, which is what makes `\/`, `\"` and `\\` come out
        // right. Legacy OCTAL escapes (`\057` for "/") are deliberately absent:
        // they are a SyntaxError inside a module, so node would refuse to load
        // the file before this fence ever had to have an opinion about it.
        out += esc;
    }
  }
  return out;
}

/** One string literal, quote to quote, escapes allowed inside it. Single-line
 *  by construction: a module specifier may not contain a newline, and neither
 *  may the path literals leg 3 reads, so a template that spans lines is out of
 *  scope rather than mis-parsed. */
const ONE_LITERAL = /(["'`])((?:\\.|[^\\\n])*?)\1/g;

/** Cook and join every literal in a `+` chain. The caller has already matched
 *  the chain; this turns `"<up>br" + "ain/llm.ts"` into the path the runtime
 *  will actually ask for. */
function concatenatedValue(expression: string): string {
  ONE_LITERAL.lastIndex = 0;
  let out = "";
  let match: RegExpExecArray | null;
  while ((match = ONE_LITERAL.exec(expression)) !== null) out += cookStringLiteral(match[2]);
  return out;
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

// A dynamic import or require whose specifier is a CONCATENATION of string
// literals: `import("../../br" + "ain/llm.ts")`. Fully static, entirely legal,
// and the cheapest possible way to make the TEXT of a specifier differ from the
// VALUE the resolver receives — which is exactly the gap every pattern above
// was blind to. Handled separately from `SPECIFIER_PATTERNS` because the capture
// is an expression, not a path, and has to be joined before it means anything.
//
// Only the call forms are covered, and that is not a gap: a static
// `import … from` REQUIRES a single literal, so there is no `+` chain to read.
const CONCAT_SPECIFIER = /\b(?:import|require)\s*\(\s*((?:["'`][^"'`\n]*["'`]\s*\+\s*)+["'`][^"'`\n]*["'`])\s*\)/g;

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
    // COOKED, not raw: everything downstream calls `path.resolve` on this, and
    // resolving the TEXT of an escaped specifier lands inside the spike while
    // resolving its VALUE lands in brain/.
    while ((match = pattern.exec(source)) !== null) found.add(cookStringLiteral(match[1]));
  }
  CONCAT_SPECIFIER.lastIndex = 0;
  let concat: RegExpExecArray | null;
  while ((concat = CONCAT_SPECIFIER.exec(source)) !== null) found.add(concatenatedValue(concat[1]));
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

function spikeTree(): Tree {
  const tree = walk(SPIKE, (p) => SPIKE_MODULE_EXTENSIONS.has(extensionOf(p)), SPIKE_SKIP_DIRS, emptyTree());
  // The walker IS the leg. A renamed directory or a swallowed readdir would
  // leave an empty list, and an empty list passes every assertion below while
  // proving nothing at all.
  assert.ok(
    tree.files.length >= 8,
    `the walker found ${tree.files.length} module files under the spike; it should see every module and every test`,
  );
  return tree;
}

// ---------------------------------------------------------------------------
// The two outbound legs, as functions the tests call.
// ---------------------------------------------------------------------------
// Extracted from the `test(...)` bodies they used to live in for one reason:
// legs 6 and 7 run them over a PLANTED violation. A detector that has only ever
// been run against a clean tree is indistinguishable from a detector that
// returns the empty list unconditionally — and every hole those legs now cover
// (a specifier with no space after the keyword, a file that is not `.ts`, a
// file under a skipped directory name, a symlinked door, an escaped or
// concatenated specifier) was exactly that: real imports of brain/ sitting
// inside the spike with every leg green.
function outsideSpikeViolations(tree: Tree): string[] {
  const violations: string[] = [];

  for (const file of tree.files) {
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

  // A symlink out of the spike is a violation of this leg whatever it points
  // at, and the reason is not that reading an outside file is forbidden — leg 3
  // says it is not. It is that a link makes an outside file answer to an INSIDE
  // path, so every check in this file, all of which are path checks, stops
  // meaning anything. `import "./prod/llm.ts"` through a link to brain/ passes
  // legs 1, 2 and 3 by construction.
  for (const link of tree.symlinks) {
    if (linkStaysInside(link)) continue;
    violations.push(
      `${relative(REPO, link)} -> ${relative(REPO, symlinkTarget(link))} ` +
        `(a symlink out of the spike: it makes an outside file reachable by an inside path)`,
    );
  }
  return violations;
}

function productionDirViolations(tree: Tree): string[] {
  const violations: string[] = [];

  for (const file of tree.files) {
    for (const spec of specifiersIn(readFileSync(file, "utf8"))) {
      const target = spec.startsWith(".") || spec.startsWith("/") ? resolve(dirname(file), spec) : null;
      const rel = target === null ? spec : relative(REPO, target);
      const head = rel.split(sep)[0].split("/")[0];
      if (PRODUCTION_DIRS.includes(head)) {
        violations.push(`${relative(REPO, file)} imports ${spec} (${rel})`);
      }
    }
  }

  for (const link of tree.symlinks) {
    const rel = relative(REPO, symlinkTarget(link));
    const head = rel.split(sep)[0].split("/")[0];
    if (PRODUCTION_DIRS.includes(head)) {
      violations.push(`${relative(REPO, link)} is a symlink into ${rel}`);
    }
  }
  return violations;
}

// ---------------------------------------------------------------------------
// LEG 3's detector — a path literal that escapes into production code.
// ---------------------------------------------------------------------------
// Extracted for the same reason as the two above: legs 6 and 7 plant a file and
// ask this what it thinks of it.
//
// It reads RAW source, comments included. A commented-out path is nobody's
// dependency, but it is a note about where the next person should look, and
// this is the cheap place to catch that intention.
//
// TWO INDEPENDENT PASSES, and the redundancy is the point. The first is a
// narrow regex over the raw text, unchanged since this leg was written. The
// second cooks every literal and joins every `+` chain, because a fence that
// only reads text cannot see an escaped `<up>brain` or a split
// `"<up>br" + "ain"`.
// The narrow pass is kept because the general one pairs quotes across prose and
// a stray apostrophe in a comment could, in principle, swallow the very literal
// that matters. Two passes over the same file cost microseconds; one of them
// being fooled costs the fence.
const RAW_ESCAPING_LITERAL = /["'`](\.\.\/[^"'`\n]*)["'`]/g;
const PARENT_SEGMENT = ["..", ""].join("/");

/** Every literal value in the raw text, plus the value every `+` chain of them
 *  concatenates to. Prefixes of a chain are kept as well as the whole, so a
 *  three-part join is caught wherever the production directory's name is split. */
function literalValues(raw: string): string[] {
  const pieces: { value: string; start: number; end: number }[] = [];
  ONE_LITERAL.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = ONE_LITERAL.exec(raw)) !== null) {
    pieces.push({ value: cookStringLiteral(match[2]), start: match.index, end: match.index + match[0].length });
  }

  const values: string[] = [];
  for (let i = 0; i < pieces.length; i++) {
    values.push(pieces[i].value);
    let joined = pieces[i].value;
    let j = i;
    // Only a bare `+` between two literals joins them. Anything else — a comma,
    // an identifier, a call — means the runtime is not building one string, and
    // guessing otherwise would fail the fence on code that concatenates prose.
    while (j + 1 < pieces.length && /^\s*\+\s*$/.test(raw.slice(pieces[j].end, pieces[j + 1].start))) {
      joined += pieces[j + 1].value;
      values.push(joined);
      j++;
    }
  }
  return values;
}

function escapingPathViolations(files: string[]): string[] {
  const violations: string[] = [];

  for (const file of files) {
    const source = readFileSync(file, "utf8");
    const candidates = new Set<string>();

    RAW_ESCAPING_LITERAL.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = RAW_ESCAPING_LITERAL.exec(source)) !== null) candidates.add(match[1]);
    for (const value of literalValues(source)) {
      if (value.includes(PARENT_SEGMENT)) candidates.add(value);
    }

    for (const candidate of candidates) {
      const target = resolve(dirname(file), candidate);
      if (target === SPIKE || target.startsWith(SPIKE + sep)) continue;
      const head = relative(REPO, target).split(sep)[0].split("/")[0];
      if (PRODUCTION_DIRS.includes(head)) {
        violations.push(`${relative(REPO, file)} reaches ${relative(REPO, target)}`);
      }
    }
  }
  return violations;
}

// ---------------------------------------------------------------------------
// LEG 1 — nothing in the spike imports anything outside the spike.
// ---------------------------------------------------------------------------
test("every specifier in the spike is a node builtin or a file inside the spike, and no symlink is a door out", () => {
  const violations = outsideSpikeViolations(spikeTree());
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
  const violations = productionDirViolations(spikeTree());
  assert.deepEqual(violations, [], `the spike reached into production:\n  ${violations.join("\n  ")}`);
});

// ---------------------------------------------------------------------------
// LEG 3 — the hole leg 1's scoping leaves.
// ---------------------------------------------------------------------------
// Leg 1 reads import specifiers only, so a readFileSync of a production path
// walks straight through it. That is not a hypothetical shape: signature.test.ts
// already reads a file outside the spike on purpose. So the rule is not "never
// escape" — it is "escaping is for DATA, never for production code".
test("a path literal that escapes the spike may not land in production code", () => {
  const violations = escapingPathViolations(spikeTree().files);
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
  const files = walk(
    REPO,
    (p) => {
      const ext = extensionOf(p);
      if (!CODE_EXTENSIONS.has(ext) && !TEXT_EXTENSIONS.has(ext)) return false;
      return !(p === SPIKE || p.startsWith(SPIKE + sep));
    },
    REPO_SKIP_DIRS,
    emptyTree(),
  ).files;
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

/** The six characters a JavaScript string literal spells "/" with when it does
 *  not want to use a "/". Built from parts for the same reason as everything
 *  else here: written out, it would be a path literal in this file. */
const SLASH_ESCAPE = ["\\", "u002f"].join("");

function escapeSlashes(path: string): string {
  return path.split("/").join(SLASH_ESCAPE);
}

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

  // THE TEXT IS NOT THE VALUE. Both lines below load brain/llm.ts. Asserting on
  // the VALUE, not just the count, is the whole finding: the scanner used to
  // hand back the raw text, which `path.resolve` places inside the spike, so
  // every leg passed while the module loaded production code.
  const escaped = `import { hear } from ${q}${escapeSlashes(prod("brain", "llm.ts"))}${q};`;
  assert.deepEqual(
    specifiersIn(escaped),
    [prod("brain", "llm.ts")],
    `an escaped specifier must be reported as the path it resolves to: ${escaped}`,
  );

  const whole = prod("brain", "llm.ts");
  const cut = whole.indexOf("brain") + 2;
  const joined = `const m = await import(${q}${whole.slice(0, cut)}${q} + ${q}${whole.slice(cut)}${q});`;
  assert.deepEqual(
    specifiersIn(joined),
    [whole],
    `a concatenated specifier must be reported as the path it resolves to: ${joined}`,
  );

  // CONTROLS for the two above. Cooking and joining must not have turned the
  // scanner into something that reports paths nobody imported — a fence that
  // fires on ordinary code is a fence that gets deleted.
  assert.deepEqual(
    specifiersIn(`import x from ${q}./router.ts${q};`),
    ["./router.ts"],
    "an ordinary specifier must come back unchanged; cooking is a decode, not a rewrite",
  );
  assert.equal(
    specifiersIn(`const label = ${q}../../br${q} + ${q}ain${q};`).length,
    0,
    "a `+` outside an import call is string concatenation, not a module specifier",
  );

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

  // A REGEX LITERAL IS NOT A STRING, and getting that wrong BLINDS this scanner.
  // A character class holding an ODD number of quote characters — `[^"]` is
  // enough, and `RAW_ESCAPING_LITERAL` below holds three double quotes, three
  // apostrophes and three backticks — leaves the quote tracker desynchronized
  // for the REST OF THE FILE. Every later line then has its code and string
  // halves swapped: the opening quote of a real string reads as a closing one,
  // and the `//` inside a URL that is safely inside a string becomes a comment
  // that blanks the import sitting beside it. The two lines below are exactly
  // that, and without the regex handling in `stripComments` the import
  // disappears — the quiet direction, which is the one nobody notices.
  //
  // Found by this file failing on itself the day the leg-3 pattern moved to
  // module scope. The noisy half of the same bug is covered by leg 1, which
  // reads this file and would report its own header if comments stopped being
  // stripped.
  const desync = [
    `const re = /[^${q}]+/g;`,
    `const u = ${q}https://x.invalid/a${q}; import y from ${q}./ledger.ts${q};`,
  ].join("\n");
  assert.deepEqual(
    specifiersIn(desync),
    ["./ledger.ts"],
    "a regex character class must not desynchronize the quote tracker; the import a line below it vanishes",
  );

  // THE CONTROL for that, and it is the more dangerous direction. Reading a
  // division as the start of a regex blanks everything up to the next `/` —
  // which is the one inside the specifier on the same line. A guard that
  // swallowed imports would be worse than the hole it closed.
  assert.equal(
    specifiersIn(`const ratio = width / height; import y from ${q}./ledger.ts${q};`).length,
    1,
    "a division must not be read as a regex, or the scanner blanks the import beside it",
  );
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
// The probe directory, and why it is cleared by hand.
// ---------------------------------------------------------------------------
// Legs 6 and 7 write real files, and leg 7 writes a real symlink to `brain/`.
// `rmSync(..., { recursive: true })` unlinks a symlink rather than descending
// through it, but the cost of being wrong about that once is the production
// tree, so every link is unlinked BY NAME first and the recursive delete only
// ever meets ordinary files.
function clearProbe(dir: string): void {
  if (existsSync(dir)) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) unlinkSync(join(dir, entry.name));
    }
  }
  rmSync(dir, { recursive: true, force: true });
}

const PROBE_DIR = join(SPIKE, "fence-probe");

// CLEARED ONCE AT LOAD, before any leg runs. An interrupted run — Ctrl-C, a
// killed process, a pipe closed by `head` — leaves a plant in the tree, and
// every later run of the WHOLE suite then fails legs 1, 2 and 3 on a file
// nobody wrote, which reads exactly like the fence catching a real violation.
// It cost twenty minutes of chasing a ghost once already. The plants are this
// file's own test data and this directory name belongs to nobody else.
clearProbe(PROBE_DIR);

/** How far up a planted file has to climb to reach the repo root: out of any
 *  directories it sits in under `fence-probe/`, then out of `fence-probe`,
 *  `two-hands` and `spike` — hence the three. Computed rather than written so a
 *  plant can sit two directories deep, which is the only way to prove the
 *  walker no longer skips `dist/` and `node_modules/`. Getting this wrong is
 *  quiet: the plant still fails leg 1 (it still escapes the spike) and stops
 *  failing leg 2, so the plant would be testing the wrong leg. */
function upToRepo(relFile: string): string {
  const depth = relFile.split("/").length - 1;
  return ["..", ""].join("/").repeat(depth + 3);
}

// ---------------------------------------------------------------------------
// LEG 6 — the fence, run against a violation that is really in the tree.
// ---------------------------------------------------------------------------
// Leg 5 proves the SCANNER sees a line. This leg proves the WALKER hands it the
// file: it writes one violating module at a time inside the spike, runs legs 1,
// 2 and 3 over the real tree, and requires each one to agree about it.
//
// Every shape below was live at some point in this file's life, and they are
// different KINDS of hole: two were invisible to the scanner (no whitespace
// after the keyword), one was invisible because of the file's extension, two
// were invisible because of the directory's NAME, and two were invisible
// because the scanner compared text where the runtime resolves a value. The
// last one in the table is a CONTROL and must stay green: reading a file
// outside the spike is legal when it is DATA, and a fence that stopped
// signature.test.ts from reading docs/BRIEF.html would be an outage.
//
// The planted file is real and is in the tree for the few milliseconds each
// assertion takes, removed in a `finally` either way. That is deliberate — the
// walker is half of what this leg proves, and a fixture in a temp directory
// would not exercise it — and it is the one reason a SECOND copy of this suite,
// run against this checkout at the same instant, could see a violation that is
// not the checkout's. If leg 1, 2 or 3 ever goes red naming `fence-probe/`,
// that is what happened; re-run before believing it.
interface Plant {
  file: string;
  make: (prod: (dir: string, file: string) => string) => string;
  outbound: boolean;
  production: boolean;
  escapes: boolean;
  why: string;
}

test("a planted import of production code is caught in every shape, file type and directory", () => {
  const q = '"';
  const probeDir = PROBE_DIR;

  const plants: Plant[] = [
    {
      file: "braces.ts",
      make: (prod) => `import{hear}from${q}${prod("brain", "llm.ts")}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "no whitespace after the keyword",
    },
    {
      file: "namespace.ts",
      make: (prod) => `import*as brain from${q}${prod("brain", "llm.ts")}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a namespace import with no whitespace after the keyword",
    },
    {
      file: "reexport.ts",
      make: (prod) => `export{thing}from${q}${prod("backend", "api.ts")}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a re-export with no whitespace after the keyword",
    },
    {
      file: "plain.js",
      make: (prod) => `import { hear } from ${q}${prod("brain", "llm.ts")}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a .js file, which the walker did not open at all",
    },
    {
      file: "module.mjs",
      make: (prod) => `const m = await import(${q}${prod("migration", "workers/x.ts")}${q});`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a dynamic import in an .mjs file",
    },
    {
      file: "legacy.cjs",
      make: (prod) => `const db = require(${q}${prod("backend", "db.js")}${q});`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a require() in a .cjs file",
    },
    {
      file: "star.mts",
      make: (prod) => `export*from${q}${prod("backend", "api.ts")}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a star re-export in an .mts file, an extension node loads and the walker must open",
    },
    {
      file: "template.ts",
      make: (prod) => `const m = await import(\`${prod("brain", "llm.ts")}\`);`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a dynamic import whose specifier is a template literal",
    },
    {
      file: "escaped.ts",
      make: (prod) => `import{hear}from${q}${escapeSlashes(prod("brain", "llm.ts"))}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "an escaped specifier: the text resolves inside the spike, the VALUE resolves into brain/",
    },
    {
      file: "concat.mjs",
      make: (prod) => {
        const whole = prod("brain", "llm.ts");
        const cut = whole.indexOf("brain") + 2;
        // Split inside the directory's own name on purpose: neither half
        // resolves anywhere near production, so only a check that JOINS them
        // can catch this.
        return `const m = await import(${q}${whole.slice(0, cut)}${q} + ${q}${whole.slice(cut)}${q});`;
      },
      outbound: true,
      production: true,
      escapes: true,
      why: "a concatenated specifier: neither half names brain/, the joined value does",
    },
    {
      file: "dist/hidden.ts",
      make: (prod) => `import { hear } from ${q}${prod("brain", "llm.ts")}${q};`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a build-output directory name, which the walker skipped everywhere including inside the spike",
    },
    {
      file: "node_modules/vendor/index.js",
      make: (prod) => `const { hear } = require(${q}${prod("brain", "llm.ts")}${q});`,
      outbound: true,
      production: true,
      escapes: true,
      why: "a vendor directory name two levels deep, likewise skipped",
    },
    {
      file: "dependency.mjs",
      make: () => `import fetchImpl from ${q}undici${q};`,
      outbound: true,
      production: false,
      escapes: false,
      why: "an npm package in an .mjs file: no install step, so no dependency",
    },
    {
      // THE CONTROL. Escaping the spike to read DATA is legal and load-bearing:
      // signature.test.ts proves the recipe scenes are verbatim from
      // docs/BRIEF.html by reading it. If this plant ever goes red, the fence
      // has become a wall and the brief check is the first thing it kills.
      file: "reads_data.ts",
      make: (prod) => `const brief = readFileSync(${q}${prod("docs", "BRIEF.html")}${q}, ${q}utf8${q});`,
      outbound: false,
      production: false,
      escapes: false,
      why: "reading a DATA file outside the spike, which this fence deliberately allows",
    },
  ];

  try {
    for (const plant of plants) {
      clearProbe(probeDir);
      const planted = join(probeDir, ...plant.file.split("/"));
      mkdirSync(dirname(planted), { recursive: true });
      const up = upToRepo(plant.file);
      writeFileSync(planted, `${plant.make((dir, file) => `${up}${dir}/${file}`)}\n`);

      const tree = spikeTree();
      assert.ok(
        tree.files.includes(planted),
        `the walker never opened ${plant.file} (${plant.why}), so no leg below could have seen it`,
      );

      const outside = outsideSpikeViolations(tree);
      assert.equal(
        outside.some((v) => v.includes(plant.file)),
        plant.outbound,
        `leg 1 disagreed about ${plant.file} (${plant.why}): ${JSON.stringify(outside)}`,
      );

      const production = productionDirViolations(tree);
      assert.equal(
        production.some((v) => v.includes(plant.file)),
        plant.production,
        `leg 2 disagreed about ${plant.file} (${plant.why}): ${JSON.stringify(production)}`,
      );

      const escaping = escapingPathViolations(tree.files);
      assert.equal(
        escaping.some((v) => v.includes(plant.file)),
        plant.escapes,
        `leg 3 disagreed about ${plant.file} (${plant.why}): ${JSON.stringify(escaping)}`,
      );
    }
  } finally {
    clearProbe(probeDir);
  }

  // And green again with the plants gone, so the red above was theirs and not
  // the tree's.
  const clean = spikeTree();
  assert.deepEqual(outsideSpikeViolations(clean), []);
  assert.deepEqual(productionDirViolations(clean), []);
  assert.deepEqual(escapingPathViolations(clean.files), []);
});

// ---------------------------------------------------------------------------
// LEG 7 — the door no specifier check can see.
// ---------------------------------------------------------------------------
// A symlink is the one evasion that beats every other leg in this file BY
// CONSTRUCTION rather than by outwitting a regex. `ln -s ../../brain
// spike/two-hands/prod` followed by `import "./prod/llm.ts"` is a specifier
// that genuinely resolves INSIDE the spike: leg 1 is right to pass it, leg 2 is
// right to pass it, leg 3 is right to pass it, and production code runs. The
// only place to catch it is the link.
//
// The third case is the CONTROL and it is not optional. "No symlinks at all"
// would also stop the evasion and would be a wall, not a fence — this leg has
// to show that a link which stays inside the spike is still fine, or the next
// person who symlinks a fixture gets a red they cannot explain and deletes the
// check.
test("a symlink out of the spike is a violation; one that stays inside is not", () => {
  const q = '"';
  const probeDir = PROBE_DIR;

  try {
    // CASE 1 — a link straight at a production FILE.
    clearProbe(probeDir);
    mkdirSync(probeDir, { recursive: true });
    const fileLink = join(probeDir, "llm.ts");
    symlinkSync(join(REPO, "brain", "llm.py"), fileLink);

    let tree = spikeTree();
    assert.ok(
      tree.symlinks.includes(fileLink),
      "the walker did not even see the symlink: readdirSync types an entry by the LINK, so a link is " +
        "neither isFile() nor isDirectory() and the old walker dropped it silently",
    );
    assert.ok(
      outsideSpikeViolations(tree).some((v) => v.includes("llm.ts")),
      "leg 1 must refuse a symlink that leaves the spike",
    );
    assert.ok(
      productionDirViolations(tree).some((v) => v.includes("llm.ts")),
      "leg 2 must name a symlink that lands in brain/",
    );

    // CASE 2 — a link at the production DIRECTORY, with a module importing
    // through it. This is the shape that beats every specifier check.
    clearProbe(probeDir);
    mkdirSync(probeDir, { recursive: true });
    const dirLink = join(probeDir, "prod");
    symlinkSync(join(REPO, "brain"), dirLink);
    const user = join(probeDir, "uses.ts");
    writeFileSync(user, `import { hear } from ${q}./prod/llm.ts${q};\n`);

    tree = spikeTree();
    assert.ok(tree.files.includes(user), "the walker must still open the module that imports through the link");
    // The specifier really does resolve inside the spike. Proving that here is
    // what makes the next two assertions mean something: without the link
    // check, this whole shape is invisible.
    assert.deepEqual(
      outsideSpikeViolations({ files: tree.files, symlinks: [] }),
      [],
      "the import through the link resolves INSIDE the spike, which is exactly why the link itself is the leg",
    );
    assert.ok(
      outsideSpikeViolations(tree).some((v) => v.includes("prod")),
      "leg 1 must refuse a symlinked directory that leaves the spike",
    );
    assert.ok(
      productionDirViolations(tree).some((v) => v.includes("prod")),
      "leg 2 must name a symlinked directory that lands in brain/",
    );

    // CASE 3 — THE CONTROL. A link that stays inside the spike is not a
    // violation, and the tree is still walked normally around it.
    clearProbe(probeDir);
    mkdirSync(probeDir, { recursive: true });
    const insideLink = join(probeDir, "alias.ts");
    symlinkSync(join(SPIKE, "src", "router.ts"), insideLink);

    tree = spikeTree();
    assert.ok(tree.symlinks.includes(insideLink), "the walker must see the link before it can clear it");
    assert.deepEqual(
      outsideSpikeViolations(tree),
      [],
      "a symlink inside the spike is not a door out, and refusing it would make this leg a wall",
    );
    assert.deepEqual(productionDirViolations(tree), []);
    assert.deepEqual(escapingPathViolations(tree.files), []);
  } finally {
    clearProbe(probeDir);
  }

  const clean = spikeTree();
  assert.deepEqual(outsideSpikeViolations(clean), []);
  assert.deepEqual(productionDirViolations(clean), []);
});
