/**
 * filter-dsl.ts — PocketBase's filter grammar, parsed and compiled to
 * PARAMETERISED SQLite (D1). No string interpolation of any client value,
 * anywhere in this file. The only text that is ever concatenated into SQL is
 * a column name that has already been looked up in a compile-time schema map.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Five clients (iOS, macOS, the Chrome extension, brain/pb.py and ~30 proof
 * harnesses) speak `/api/collections/{name}/records?filter=<DSL>`. The
 * authorization layer does not merely READ those strings, it inspects and
 * REWRITES them:
 *
 *   backend/pb_hooks/guard.pb.js:45-50   `ownedList` — allow the list iff the
 *                                         raw filter CONTAINS the substring
 *                                         `owner_ref="<id>"` and contains no `||`
 *   backend/pb_hooks/research_lane.pb.js:441-442
 *                                         rewrites the filter to
 *                                         `(<original>) && lane != "research" && …`
 *
 * So the DSL is not an optional nicety of the port. It is the authorization
 * primitive. See ARCHITECTURE.md §3.
 *
 * GRAMMAR (PocketBase 0.30.4, github.com/ganigeorgiev/fexpr)
 * ---------------------------------------------------------
 *   filter     := or
 *   or         := and ( '||' and )*
 *   and        := unary ( '&&' unary )*
 *   unary      := '(' or ')' | comparison
 *   comparison := operand OP operand
 *   operand    := identifier | macro | string | number | 'true' | 'false' | 'null'
 *   OP         := '=' | '!=' | '~' | '!~' | '>' | '>=' | '<' | '<='
 *               | '?=' | '?!=' | '?~' | '?!~' | '?>' | '?>=' | '?<' | '?<='
 *
 * `&&` binds tighter than `||`, exactly as in PocketBase.
 *
 * WHAT IS DELIBERATELY REFUSED (and is not a gap):
 *   - `//` line comments. fexpr accepts them; this parser does not. Reason in
 *     ARCHITECTURE.md §3.4 — a comment is a place to hide a substring that
 *     satisfies `ownedList` while constraining nothing.
 *   - Any identifier not present in the caller-supplied schema map. An unknown
 *     identifier is the only path by which arbitrary text could reach SQL, so
 *     it is a hard error rather than a pass-through.
 *   - `@collection.*` back-relation macros and `field.relation.subfield`
 *     traversal. Nothing in this tree uses either (verified: no `expand=`,
 *     no dotted non-macro identifier in any client filter). Supporting them
 *     means JOIN synthesis; refusing them means a 400 nobody can trigger.
 */

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

/**
 * How a column behaves, which is all the compiler needs to know about it.
 *
 * `nullable` exists ONLY as an escape hatch. migration/d1/schema.sql declares
 * every user column `NOT NULL DEFAULT ''` (or `DEFAULT 0`), on purpose:
 * PocketBase never writes SQL NULL into a user field, so '' is the unset
 * value and every client filter compares against ''. With `nullable:false`
 * the compiler emits a bare `"col" = ?`, which an index can serve. With
 * `nullable:true` it emits the COALESCE form, which is correct and
 * UNINDEXABLE. Do not flip it casually.
 */
export type ColumnType =
  | "text" | "email" | "date" | "relation" | "file" | "number" | "bool";

export interface ColumnSpec {
  type: ColumnType;
  /** true only if the D1 column can actually hold SQL NULL. Default false. */
  nullable?: boolean;
  /** true for a PocketBase multi-value field. NONE exist in this schema. */
  multi?: boolean;
}

export type CollectionSchema = Readonly<Record<string, ColumnSpec>>;

// ---------------------------------------------------------------------------
// Request context — what the `@request.*` macros resolve against
// ---------------------------------------------------------------------------

export interface RequestContext {
  /** The authenticated record, or null. `@request.auth.id` reads `.id`. */
  auth?: { id: string; collectionName: string; [field: string]: unknown } | null;
  /** Parsed JSON request body, for `@request.body.<field>`. */
  body?: Record<string, unknown>;
  method?: string;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/**
 * Every failure here is a 400 to the caller, never a 500 and never a silent
 * empty result set. A filter that cannot be parsed must not become
 * "match nothing": brain/worker.py and the extension both treat an empty list
 * as "no work", and a silently-empty poll is the exact shape of the outage
 * recorded at extension/background.js:527-533.
 */
export class FilterError extends Error {
  readonly offset: number;
  constructor(message: string, offset: number) {
    super(message);
    this.name = "FilterError";
    this.offset = offset;
  }
}

// ---------------------------------------------------------------------------
// Lexer
// ---------------------------------------------------------------------------

type TokKind =
  | "ident" | "macro" | "string" | "number" | "bool" | "null"
  | "op" | "and" | "or" | "lparen" | "rparen" | "eof";

interface Tok {
  kind: TokKind;
  /** For "string": the DECODED value. For "number": the numeric text. */
  text: string;
  num?: number;
  bool?: boolean;
  offset: number;
}

const OPERATORS = [
  // Longest first — the scanner is greedy and "?!=" must not lex as "?" "!=".
  "?!~", "?!=", "?>=", "?<=",
  "?=", "?~", "?>", "?<",
  "!~", "!=", ">=", "<=",
  "=", "~", ">", "<",
] as const;

export type Op = (typeof OPERATORS)[number];

const IDENT_START = /[A-Za-z_]/;
const IDENT_CHAR = /[A-Za-z0-9_.]/;

function lex(src: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  const n = src.length;

  while (i < n) {
    const c = src[i];

    if (c === " " || c === "\t" || c === "\n" || c === "\r") { i++; continue; }

    // Refused on purpose. See the header, and ARCHITECTURE.md §3.4.
    if (c === "/" && src[i + 1] === "/") {
      throw new FilterError("comments are not accepted in a filter", i);
    }

    if (c === "(") { out.push({ kind: "lparen", text: "(", offset: i }); i++; continue; }
    if (c === ")") { out.push({ kind: "rparen", text: ")", offset: i }); i++; continue; }

    if (c === "&" && src[i + 1] === "&") {
      out.push({ kind: "and", text: "&&", offset: i }); i += 2; continue;
    }
    if (c === "|" && src[i + 1] === "|") {
      out.push({ kind: "or", text: "||", offset: i }); i += 2; continue;
    }
    if (c === "&" || c === "|") {
      throw new FilterError(`a single '${c}' is not an operator; did you mean '${c}${c}'?`, i);
    }

    // Quoted string. Both quote styles, with backslash escapes, as fexpr does.
    if (c === '"' || c === "'") {
      const quote = c;
      const start = i;
      i++;
      let value = "";
      let closed = false;
      while (i < n) {
        const ch = src[i];
        if (ch === "\\") {
          const nxt = src[i + 1];
          if (nxt === undefined) {
            throw new FilterError("a filter string ends with a dangling backslash", i);
          }
          // fexpr unescapes the quote character and the backslash. Anything
          // else keeps its backslash, so a Windows path in a filter survives.
          if (nxt === quote || nxt === "\\") { value += nxt; }
          else { value += "\\" + nxt; }
          i += 2;
          continue;
        }
        if (ch === quote) { i++; closed = true; break; }
        value += ch;
        i++;
      }
      if (!closed) throw new FilterError("unterminated string in filter", start);
      out.push({ kind: "string", text: value, offset: start });
      continue;
    }

    // Number: optional sign, digits, optional single fraction.
    // NOT exponent notation — see the Unverified list in ARCHITECTURE.md.
    if (/[0-9]/.test(c) || (c === "-" && /[0-9]/.test(src[i + 1] ?? ""))) {
      const start = i;
      if (c === "-") i++;
      while (i < n && /[0-9]/.test(src[i])) i++;
      if (src[i] === "." && /[0-9]/.test(src[i + 1] ?? "")) {
        i++;
        while (i < n && /[0-9]/.test(src[i])) i++;
      }
      const text = src.slice(start, i);
      out.push({ kind: "number", text, num: Number(text), offset: start });
      continue;
    }

    // Macro: @request.auth.id, @request.body.owner_ref, @request.method
    if (c === "@") {
      const start = i;
      i++;
      while (i < n && IDENT_CHAR.test(src[i])) i++;
      const text = src.slice(start, i);
      if (text.length <= 1) throw new FilterError("empty macro in filter", start);
      out.push({ kind: "macro", text, offset: start });
      continue;
    }

    // Identifier / keyword
    if (IDENT_START.test(c)) {
      const start = i;
      while (i < n && IDENT_CHAR.test(src[i])) i++;
      const text = src.slice(start, i);
      if (text === "true" || text === "false") {
        out.push({ kind: "bool", text, bool: text === "true", offset: start });
      } else if (text === "null") {
        out.push({ kind: "null", text, offset: start });
      } else {
        out.push({ kind: "ident", text, offset: start });
      }
      continue;
    }

    // Operator
    let matched: Op | null = null;
    for (const op of OPERATORS) {
      if (src.startsWith(op, i)) { matched = op; break; }
    }
    if (matched) {
      out.push({ kind: "op", text: matched, offset: i });
      i += matched.length;
      continue;
    }

    throw new FilterError(`unexpected character ${JSON.stringify(c)} in filter`, i);
  }

  out.push({ kind: "eof", text: "", offset: n });
  return out;
}

// ---------------------------------------------------------------------------
// AST
// ---------------------------------------------------------------------------

export type Operand =
  | { kind: "column"; name: string; offset: number }
  | { kind: "macro"; path: string; offset: number }
  | { kind: "string"; value: string; offset: number }
  | { kind: "number"; value: number; offset: number }
  | { kind: "bool"; value: boolean; offset: number }
  | { kind: "null"; offset: number };

export type Node =
  | { kind: "or"; left: Node; right: Node }
  | { kind: "and"; left: Node; right: Node }
  | { kind: "cmp"; op: Op; left: Operand; right: Operand; offset: number };

// ---------------------------------------------------------------------------
// Parser — precedence climbing. `&&` binds tighter than `||`.
// ---------------------------------------------------------------------------

class Parser {
  private p = 0;
  private readonly toks: Tok[];
  constructor(toks: Tok[]) { this.toks = toks; }

  private peek(): Tok { return this.toks[this.p]; }
  private next(): Tok { return this.toks[this.p++]; }

  parse(): Node {
    const node = this.parseOr();
    const t = this.peek();
    if (t.kind !== "eof") {
      throw new FilterError(`unexpected ${JSON.stringify(t.text)} after a complete filter`, t.offset);
    }
    return node;
  }

  private parseOr(): Node {
    let left = this.parseAnd();
    while (this.peek().kind === "or") {
      this.next();
      const right = this.parseAnd();
      left = { kind: "or", left, right };
    }
    return left;
  }

  private parseAnd(): Node {
    let left = this.parseUnary();
    while (this.peek().kind === "and") {
      this.next();
      const right = this.parseUnary();
      left = { kind: "and", left, right };
    }
    return left;
  }

  private parseUnary(): Node {
    const t = this.peek();
    if (t.kind === "lparen") {
      this.next();
      const inner = this.parseOr();
      const close = this.next();
      if (close.kind !== "rparen") {
        throw new FilterError("missing ')' in filter", close.offset);
      }
      return inner;
    }
    return this.parseComparison();
  }

  private parseComparison(): Node {
    const left = this.parseOperand();
    const opTok = this.next();
    if (opTok.kind !== "op") {
      throw new FilterError(
        `expected a comparison operator, got ${JSON.stringify(opTok.text || "end of filter")}`,
        opTok.offset,
      );
    }
    const right = this.parseOperand();
    return { kind: "cmp", op: opTok.text as Op, left, right, offset: opTok.offset };
  }

  private parseOperand(): Operand {
    const t = this.next();
    switch (t.kind) {
      case "ident": return { kind: "column", name: t.text, offset: t.offset };
      case "macro": return { kind: "macro", path: t.text, offset: t.offset };
      case "string": return { kind: "string", value: t.text, offset: t.offset };
      case "number": return { kind: "number", value: t.num as number, offset: t.offset };
      case "bool": return { kind: "bool", value: t.bool as boolean, offset: t.offset };
      case "null": return { kind: "null", offset: t.offset };
      default:
        throw new FilterError(
          `expected a field or a value, got ${JSON.stringify(t.text || "end of filter")}`,
          t.offset,
        );
    }
  }
}

/** Parse a filter string into an AST. Throws FilterError (→ HTTP 400). */
export function parseFilter(src: string): Node {
  return new Parser(lex(src)).parse();
}

// ---------------------------------------------------------------------------
// Compiler
// ---------------------------------------------------------------------------

export interface Compiled {
  /** A complete boolean SQL expression, fully parenthesised. */
  sql: string;
  /** Positional bind values, in `?1..?n` order. */
  params: unknown[];
}

export interface CompileOptions {
  schema: CollectionSchema;
  ctx?: RequestContext;
  /** Bind-parameter index to start at, when splicing into a larger query. */
  startIndex?: number;
}

/** Mirror an operator when the column is on the right-hand side. */
const MIRROR: Partial<Record<Op, Op>> = {
  "=": "=", "!=": "!=", ">": "<", ">=": "<=", "<": ">", "<=": ">=",
  "?=": "?=", "?!=": "?!=",
};

/**
 * SQLite identifier quoting. `name` has ALREADY been proven to exist in
 * `schema`, so it is one of a fixed set of literals from schema.sql; the
 * doubling of `"` is belt-and-braces, not the actual defence.
 */
function ident(name: string): string {
  return '"' + name.replace(/"/g, '""') + '"';
}

/**
 * Coerce a DSL literal to what the D1 column actually stores.
 *
 * The one that matters in production: `bool`. `paired=true` is sent by
 * brain/worker.py:1302 (`_scoped_filter("paired=true", owner_ref)`), and D1
 * stores booleans as INTEGER 0/1 (migration/d1/schema.sql, type map). Binding
 * a JS `true` against an INTEGER column matches nothing in SQLite. This is the
 * single likeliest silent-wrong-answer in the whole port.
 */
function coerce(spec: ColumnSpec, v: Operand): unknown {
  switch (v.kind) {
    case "null": return null;
    case "bool":
      if (spec.type === "bool") return v.value ? 1 : 0;
      // PocketBase compares a boolean against a text column by its literal
      // form. Nothing in this tree does it; preserved rather than guessed at.
      return v.value ? "true" : "false";
    case "number":
      if (spec.type === "bool") return v.value ? 1 : 0;
      return v.value;
    case "string":
      if (spec.type === "number") {
        const n = Number(v.value);
        return Number.isFinite(n) ? n : v.value;
      }
      if (spec.type === "bool") return v.value === "true" || v.value === "1" ? 1 : 0;
      return v.value;
    default:
      throw new FilterError("a column cannot be used as a literal here", v.offset);
  }
}

/** Resolve `@request.*` to a concrete value, or throw. */
function resolveMacro(path: string, ctx: RequestContext | undefined): unknown {
  const c = ctx ?? {};
  if (path === "@request.method") return c.method ?? "";

  if (path === "@request.auth.id") return c.auth?.id ?? null;
  if (path.startsWith("@request.auth.")) {
    const field = path.slice("@request.auth.".length);
    if (!c.auth) return null;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(field)) {
      throw new FilterError(`unsupported auth macro ${path}`, 0);
    }
    const v = (c.auth as Record<string, unknown>)[field];
    return v === undefined ? null : v;
  }

  if (path.startsWith("@request.body.")) {
    const field = path.slice("@request.body.".length);
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(field)) {
      throw new FilterError(`unsupported body macro ${path}`, 0);
    }
    const v = c.body?.[field];
    // PocketBase's measured behaviour: an ABSENT body field and an empty
    // string both fail `!= ""`. backend/pb_migrations/1700000043_owner_profile_needs_owner.js:27-30
    // records the experiment. `undefined -> ""` is what makes that true here.
    return v === undefined || v === null ? "" : v;
  }

  throw new FilterError(`unsupported macro ${path}`, 0);
}

/**
 * PocketBase's `~` value handling, reconstructed from its behaviour:
 * if the value contains no UNESCAPED `%`, it is escaped and wrapped in `%…%`;
 * if it does, the caller authored a pattern and it is used as written.
 */
function likePattern(raw: string): string {
  if (containsUnescaped(raw, "%")) return raw;
  return "%" + escapeChars(raw, ["\\", "%", "_"]) + "%";
}

function containsUnescaped(s: string, ch: string): boolean {
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "\\") { i++; continue; }
    if (s[i] === ch) return true;
  }
  return false;
}

function escapeChars(s: string, chars: string[]): string {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    if (chars.includes(s[i])) out += "\\";
    out += s[i];
  }
  return out;
}

class Compiler {
  readonly params: unknown[] = [];
  private index: number;
  private readonly opts: CompileOptions;

  constructor(opts: CompileOptions) {
    this.opts = opts;
    this.index = opts.startIndex ?? 1;
  }

  private bind(value: unknown): string {
    this.params.push(value);
    return "?" + this.index++;
  }

  compile(node: Node): string {
    switch (node.kind) {
      case "and": return `(${this.compile(node.left)} AND ${this.compile(node.right)})`;
      case "or":  return `(${this.compile(node.left)} OR ${this.compile(node.right)})`;
      case "cmp": return this.compileCmp(node);
    }
  }

  private column(o: Operand): { name: string; spec: ColumnSpec } | null {
    if (o.kind !== "column") return null;
    const spec = this.opts.schema[o.name];
    if (!spec) {
      // THE SECURITY BOUNDARY. Only a name found here is ever concatenated
      // into SQL. An unknown identifier is refused, never passed through.
      throw new FilterError(`unknown field ${JSON.stringify(o.name)}`, o.offset);
    }
    return { name: o.name, spec };
  }

  /** Turn a macro operand into a literal operand before anything else runs. */
  private literalise(o: Operand): Operand {
    if (o.kind !== "macro") return o;
    const v = resolveMacro(o.path, this.opts.ctx);
    if (v === null) return { kind: "null", offset: o.offset };
    if (typeof v === "boolean") return { kind: "bool", value: v, offset: o.offset };
    if (typeof v === "number") return { kind: "number", value: v, offset: o.offset };
    return { kind: "string", value: String(v), offset: o.offset };
  }

  private compileCmp(node: Node & { kind: "cmp" }): string {
    let op = node.op;
    let left = this.literalise(node.left);
    let right = this.literalise(node.right);

    let lc = this.column(left);
    let rc = this.column(right);

    // Column on the right only: mirror so the column is always on the left.
    if (!lc && rc) {
      const mirrored = MIRROR[op];
      if (!mirrored) {
        throw new FilterError(
          `operator ${op} needs the field on the left-hand side`, node.offset);
      }
      op = mirrored;
      [left, right] = [right, left];
      [lc, rc] = [rc, lc];
    }

    if (!lc) {
      // literal OP literal. PocketBase evaluates it; there is no row-dependent
      // meaning, and nothing in this tree emits one. Refuse rather than
      // fabricate a truth value.
      throw new FilterError("a comparison must name at least one field", node.offset);
    }

    if (lc.spec.multi && op.startsWith("?")) {
      // No column in migration/d1/schema.sql is multi-valued, so this cannot
      // fire today. It exists so that adding one later fails loudly instead of
      // silently degrading `?=` (ANY-of) into `=` (the whole value).
      throw new FilterError(
        `${op} on the multi-value field ${lc.name} needs a json_each() rewrite ` +
        `that this compiler does not implement`, node.offset);
    }

    if (rc) return this.columnVsColumn(op, lc, rc, node.offset);
    return this.columnVsLiteral(op, lc, right, node.offset);
  }

  /**
   * `col` on the left. Wrapping in COALESCE is what makes NULL behave like ''
   * — and it also makes the expression UNINDEXABLE, which is why it is applied
   * only to a column actually declared nullable. Every column in
   * migration/d1/schema.sql is NOT NULL, so in production this always emits
   * the bare column and the index is used.
   */
  private ref(c: { name: string; spec: ColumnSpec }): string {
    const q = ident(c.name);
    if (!c.spec.nullable) return q;
    return c.spec.type === "number" ? `COALESCE(${q}, 0)` : `COALESCE(${q}, '')`;
  }

  private columnVsLiteral(
    op: Op, c: { name: string; spec: ColumnSpec }, v: Operand, offset: number,
  ): string {
    const col = this.ref(c);

    // NULL literal. PocketBase's `= null` / `!= null` are IS / IS NOT.
    if (v.kind === "null") {
      switch (op) {
        case "=": case "?=": return `(${ident(c.name)} IS NULL)`;
        case "!=": case "?!=": return `(${ident(c.name)} IS NOT NULL)`;
        default:
          throw new FilterError(`operator ${op} cannot be used with null`, offset);
      }
    }

    switch (op) {
      // --------------------------------------------------------------------
      // EQUALITY, AND THE `!=` / NULL SUBTLETY
      //
      // backend/pb_migrations/1700000043_owner_profile_needs_owner.js:27-30
      // records the measurement behind this: PocketBase's `!=` "carries
      // IS-NOT semantics", so the authors could not assume a NULL failed
      // `!= ""` — they tested it, and it did fail (an absent field and an
      // explicit "" were both refused by `@request.body.owner_ref != ""`).
      //
      // So the semantics reproduced here are: NULL and '' are the SAME value.
      //   `col = ""`  is TRUE  for NULL and for ''
      //   `col != ""` is FALSE for NULL and for ''
      //
      // That is also the only reading consistent with the schema's own rule
      // (migration/d1/schema.sql, type-map note 1): PocketBase never writes
      // SQL NULL into a user field, so '' IS the unset value and a NULL that
      // sorted differently would silently drop rows out of every client
      // filter. Getting this backwards on `owner_ref != ""` is the difference
      // between "3 orphan profiles" and "every profile".
      //
      // With `nullable:false` — the whole production schema — the COALESCE is
      // absent and this reduces to plain `=` / `<>`, which behaves identically
      // because NULL cannot occur.
      // --------------------------------------------------------------------
      case "=": case "?=":
        return `(${col} = ${this.bind(coerce(c.spec, v))})`;
      case "!=": case "?!=":
        return `(${col} <> ${this.bind(coerce(c.spec, v))})`;

      case "~": case "?~":
        if (v.kind !== "string") {
          // PocketBase casts; refusing is stricter and nothing sends it.
          throw new FilterError("~ needs a quoted string", offset);
        }
        return `(${col} LIKE ${this.bind(likePattern(v.value))} ESCAPE '\\')`;
      case "!~": case "?!~":
        if (v.kind !== "string") throw new FilterError("!~ needs a quoted string", offset);
        return `(${col} NOT LIKE ${this.bind(likePattern(v.value))} ESCAPE '\\')`;

      case ">": case "?>":   return `(${col} > ${this.bind(coerce(c.spec, v))})`;
      case ">=": case "?>=": return `(${col} >= ${this.bind(coerce(c.spec, v))})`;
      case "<": case "?<":   return `(${col} < ${this.bind(coerce(c.spec, v))})`;
      case "<=": case "?<=": return `(${col} <= ${this.bind(coerce(c.spec, v))})`;

      default:
        throw new FilterError(`unsupported operator ${op}`, offset);
    }
  }

  private columnVsColumn(
    op: Op, a: { name: string; spec: ColumnSpec }, b: { name: string; spec: ColumnSpec },
    offset: number,
  ): string {
    const l = this.ref(a);
    const r = this.ref(b);
    switch (op) {
      case "=": case "?=":   return `(${l} = ${r})`;
      case "!=": case "?!=": return `(${l} <> ${r})`;
      case ">": case "?>":   return `(${l} > ${r})`;
      case ">=": case "?>=": return `(${l} >= ${r})`;
      case "<": case "?<":   return `(${l} < ${r})`;
      case "<=": case "?<=": return `(${l} <= ${r})`;
      default:
        throw new FilterError(`operator ${op} cannot compare two fields`, offset);
    }
  }
}

/** Compile an AST to parameterised SQL. */
export function compileFilter(ast: Node, opts: CompileOptions): Compiled {
  const c = new Compiler(opts);
  const sql = c.compile(ast);
  return { sql, params: c.params };
}

/** Parse + compile in one call. Throws FilterError (→ HTTP 400). */
export function filterToSQL(src: string, opts: CompileOptions): Compiled {
  return compileFilter(parseFilter(src), opts);
}

// ---------------------------------------------------------------------------
// AUTHORIZATION HELPERS
//
// These are the reason the parser exists. See ARCHITECTURE.md §3.4.
// ---------------------------------------------------------------------------

/**
 * SOUND owner-scope proof.
 *
 * Returns true iff EVERY row that can satisfy `ast` must have
 * `owner_ref = ownerRef`. Implemented as: in disjunctive normal form, every
 * disjunct contains the conjunct `owner_ref = "<ownerRef>"`.
 *
 * This is what `guard.pb.js:45-50` was reaching for with
 * `filter.indexOf('owner_ref="X"') >= 0 && filter.indexOf("||") < 0`, and it
 * is strictly better in both directions:
 *
 *   - It ACCEPTS `(owner_ref="X" && a) || (owner_ref="X" && b)`, which the
 *     substring rule refuses. Widening, and sound.
 *   - It REFUSES `goal != 'owner_ref="X"'`, which the substring rule ACCEPTS
 *     — the string literal contains the magic substring while constraining
 *     nothing. That is a live authorization bypass in the current backend;
 *     ARCHITECTURE.md §3.4 spells out the request.
 *
 * Because it is not byte-identical to the legacy predicate, the port runs BOTH
 * (see `legacyOwnedList`) during the dual-run phase, and injects the scope
 * into the SQL regardless. See ARCHITECTURE.md §3.5.
 */
export function provesOwnerScope(ast: Node, ownerRef: string, column = "owner_ref"): boolean {
  if (!ownerRef) return false;

  const conjunctProves = (n: Node): boolean => {
    switch (n.kind) {
      case "and": return conjunctProves(n.left) || conjunctProves(n.right);
      case "or": return false;      // an OR inside a conjunct proves nothing
      case "cmp": {
        if (n.op !== "=" && n.op !== "?=") return false;
        const named =
          (n.left.kind === "column" && n.left.name === column && n.right.kind === "string"
            && n.right.value === ownerRef) ||
          (n.right.kind === "column" && n.right.name === column && n.left.kind === "string"
            && n.left.value === ownerRef);
        return named;
      }
    }
  };

  const walk = (n: Node): boolean => {
    if (n.kind === "or") return walk(n.left) && walk(n.right);
    return conjunctProves(n);
  };

  return walk(ast);
}

/**
 * The legacy predicate, reproduced EXACTLY, including its bugs.
 * backend/pb_hooks/guard.pb.js:45-50.
 *
 * Kept so the port can answer with the same status code as the live backend
 * while migration/spec/contract_tests.py is being run against both. It is not
 * the authorization; `provesOwnerScope` plus SQL scope injection is.
 */
export function legacyOwnedList(rawFilter: string, ownerRef: string): boolean {
  return rawFilter.indexOf(`owner_ref="${ownerRef}"`) >= 0 && rawFilter.indexOf("||") < 0;
}

/**
 * research_lane.pb.js:437-443 rewrites the filter by TEXT concatenation:
 *   q.set("filter", "(" + filter + ") && lane != \"research\" && …")
 * On an AST that is an AND node, which cannot be smuggled past.
 */
export function andNot(ast: Node, column: string, value: string): Node {
  return {
    kind: "and",
    left: ast,
    right: {
      kind: "cmp",
      op: "!=",
      left: { kind: "column", name: column, offset: -1 },
      right: { kind: "string", value, offset: -1 },
      offset: -1,
    },
  };
}

/** Same, for the positive scope injection the guard performs. */
export function andEquals(ast: Node | null, column: string, value: string): Node {
  const clause: Node = {
    kind: "cmp",
    op: "=",
    left: { kind: "column", name: column, offset: -1 },
    right: { kind: "string", value, offset: -1 },
    offset: -1,
  };
  return ast ? { kind: "and", left: ast, right: clause } : clause;
}

/**
 * Does the filter MENTION a field at all? research_lane.pb.js:279 uses
 * `/\blane\b/` against the raw string to decide whether to rewrite. On an AST
 * this is exact: a `lane` inside a string literal no longer counts as a
 * mention, which is the behaviour the comment at
 * extension/background.js:80-88 assumes and the regex only approximates.
 */
export function mentionsField(ast: Node, column: string): boolean {
  switch (ast.kind) {
    case "and": case "or":
      return mentionsField(ast.left, column) || mentionsField(ast.right, column);
    case "cmp":
      return (ast.left.kind === "column" && ast.left.name === column)
          || (ast.right.kind === "column" && ast.right.name === column);
  }
}
