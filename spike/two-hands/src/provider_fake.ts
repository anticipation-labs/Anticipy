// THE FAKE VENDOR - the reason every other test in this spike runs with no
// Composio account, no API key, and no network.
//
// A `Provider` whose entire world is a plain fixture object: which tools the
// catalog holds, which apps this owner has connected and in what state, what
// retrieval returns for a given capability, and exactly what `execute()` does,
// including each way it fails. Nothing here reaches a socket, a clock or a
// random number generator, because a fake that varies makes every downstream
// test a coin flip and the router's real bugs get filed as flakes.
//
// WHAT THIS FILE IS DELIBERATELY NOT.
// The tempting version of this file is a "smart" fake: match the signature's
// `object` string against tool descriptions, hand back plausible candidates for
// any signature a test invents. That is a retrieval algorithm written in
// substring checks - HARNESS-LAWS law 1 - and worse, every router test built on
// it would be measuring MY substring rule rather than the router. So `search()`
// looks up by `signature_hash` and by nothing else. The fixture says what the
// vendor returned; this file only sorts, filters and copies.
//
// The other rule this file obeys: the fake is never SAFER than the vendor. If
// the router forgets `connectedOnly`, it gets unconnected tools back, exactly as
// Composio would give it. If it executes against a revoked connection it gets a
// 401, not a helpful refusal. A fake that protects the router is a fake that
// certifies bugs.

import type {
  CapabilitySignature,
  ConnectedApp,
  ExecErrorKind,
  ExecResult,
  Provider,
  SideEffect,
  ToolCandidate,
} from "./contract.ts";

// ---------------------------------------------------------------------------
// FIXTURE SHAPE
// ---------------------------------------------------------------------------

/** One row of the vendor's catalog. `app` is the connection key; `toolSlug` is
 *  what `execute()` is called with. */
export interface FakeTool {
  toolSlug: string;
  app: string;
  schema: Record<string, unknown>;
  description: string;
  /** The tool's self-declared side effect. Untrusted per the MCP spec - the
   *  contract's `tightenSideEffect` is the only legal way to read it. The fake
   *  passes it through unexamined; deciding anything with it is the router's
   *  problem, not the vendor's. */
  sideEffectHint?: SideEffect;
}

/** What the vendor's retrieval returned for one capability, recorded rather
 *  than computed. Score ORDERS; it never licenses - see contract.ts LAW1. */
export interface RetrievalHit {
  toolSlug: string;
  score: number;
}

/** One scripted `execute()` answer. `ms` is DATA: a "slow" call reports 8240ms
 *  and returns immediately, because a fake that really slept would add eight
 *  seconds to the suite for every latency assertion, and CI would then be
 *  measuring the sleep instead of the router's timeout rule. */
export interface FakeOutcome {
  ok: boolean;
  data?: unknown;
  error?: { kind: ExecErrorKind; message: string };
  ms: number;
  costUsd?: number;
}

export type FakeMethod = "search" | "connections" | "connectLink" | "execute";

export interface FakeFixture {
  tools: FakeTool[];
  /** userId -> the owner's connections. A userId with no entry has connected
   *  nothing, which is the fresh-owner path and must be reachable without
   *  editing the fixture. */
  connections?: Record<string, ConnectedApp[]>;
  /** signature_hash -> what retrieval returned. An absent hash means the vendor
   *  found NOTHING, which is the single most common real answer and therefore
   *  the default. */
  retrieval?: Record<string, RetrievalHit[]>;
  /** toolSlug -> the answer, or a script of answers consumed in call order with
   *  the last one repeating forever. The script exists so a demotion test can
   *  say "this tool worked twice and then started 429ing" without a clock.
   *  A scripted answer is only reached if the owner HAS an active connection to
   *  the tool's app: see the precondition note in `execute`. */
  exec?: Record<string, FakeOutcome | FakeOutcome[]>;
  /** Where `connectLink` points. example.invalid by construction: a fixture
   *  that names a real OAuth host is one copy-paste away from a test suite that
   *  opens somebody's consent screen. */
  connectLinkBase?: string;
  /** Method -> the message it rejects with. The vendor being down is a real
   *  state - Pipedream was acquired, Klavis pivoted, Browser Use retired Skills
   *  with a 410 - and a router that crashes on it takes the browser hand down
   *  with it, so every part must be able to reproduce it. */
  throws?: Partial<Record<FakeMethod, string>>;
  /** What a connected tool with no scripted outcome does. */
  defaultOutcome?: FakeOutcome;
}

/** The vendor being unreachable. A distinct class only so a test can assert the
 *  router propagated or swallowed the RIGHT throw; the router must never branch
 *  on it to decide meaning. */
export class FakeProviderDown extends Error {
  readonly method: FakeMethod;
  constructor(method: FakeMethod, message: string) {
    super(message);
    this.name = "FakeProviderDown";
    this.method = method;
  }
}

export type FakeCall =
  | { method: "search"; userId: string; sigHash: string; connectedOnly: boolean; limit: number }
  | { method: "connections"; userId: string }
  | { method: "connectLink"; userId: string; app: string; scopes: string[] }
  | {
      method: "execute";
      userId: string;
      toolSlug: string;
      args: Record<string, unknown>;
      accountId?: string;
    };

// A connected tool with nothing scripted still has to answer something, and the
// number has to be a CONSTANT rather than "about 100ms" - a p50 assertion over
// unscripted calls must not move when this file is edited.
const DEFAULT_OUTCOME: FakeOutcome = { ok: true, data: { fake: true }, ms: 120, costUsd: 0 };
const DEFAULT_CONNECT_BASE = "https://connect.example.invalid/start";

// structuredClone on every value that crosses the boundary, in both directions.
// Without it a router that mutates the ToolCandidate.schema it was handed, or
// that adds `accountId` to the args object after passing it, silently rewrites
// the fixture for every later test in the same file - and the failure surfaces
// three tests away from its cause.
function copy<T>(value: T): T {
  try {
    return structuredClone(value);
  } catch (err) {
    // A function or a class instance in `args` or in a fixture reaches here as a
    // bare DataCloneError with no clue where it came from. The vendor serializes
    // args onto the wire and would reject the same value, so the honest answer
    // is a loud one that names the constraint.
    throw new Error(
      `FakeProvider: values crossing the provider boundary must be JSON-shaped ` +
        `(the vendor serializes them onto the wire): ${(err as Error).message}`,
    );
  }
}

function fail(message: string): never {
  throw new Error(`FakeProvider fixture: ${message}`);
}

// ---------------------------------------------------------------------------
// THE PROVIDER
// ---------------------------------------------------------------------------

export class FakeProvider implements Provider {
  readonly name = "fake" as const;
  /** Every call, in order, for tests that need to assert the router asked the
   *  right question (e.g. `connectedOnly: true` on a write). Args are copied in,
   *  so a caller mutating its own object afterwards cannot rewrite history. */
  readonly calls: FakeCall[] = [];

  #tools = new Map<string, FakeTool>();
  #retrieval: Record<string, RetrievalHit[]>;
  #connections: Record<string, ConnectedApp[]>;
  #exec: Record<string, FakeOutcome[]>;
  #cursors = new Map<string, number>();
  #connectBase: string;
  #throws: Partial<Record<FakeMethod, string>>;
  #defaultOutcome: FakeOutcome;

  constructor(fixture: FakeFixture) {
    // Validation is loud and immediate because the alternative is silent: a
    // typo'd slug in `retrieval` produces zero candidates, the router falls back
    // to the browser, the test asserting "browser" passes, and it passed for the
    // wrong reason. A fixture bug must never look like a routing decision.
    if (!fixture || typeof fixture !== "object") fail("a fixture object is required");
    if (!Array.isArray(fixture.tools)) fail("`tools` must be an array");

    for (const tool of fixture.tools) {
      if (!tool || typeof tool.toolSlug !== "string" || tool.toolSlug === "") {
        fail("every tool needs a non-empty toolSlug");
      }
      if (typeof tool.app !== "string" || tool.app === "") {
        fail(`tool ${tool.toolSlug} needs a non-empty app`);
      }
      if (this.#tools.has(tool.toolSlug)) {
        // Two rows for one slug means `execute` and `search` could disagree
        // about which app a tool belongs to, and the connection check would then
        // pass or fail depending on insertion order.
        fail(`duplicate toolSlug ${tool.toolSlug}`);
      }
      this.#tools.set(tool.toolSlug, copy(tool));
    }

    this.#retrieval = {};
    for (const [sigHash, hits] of Object.entries(fixture.retrieval ?? {})) {
      if (!Array.isArray(hits)) fail(`retrieval[${sigHash}] must be an array`);
      const seenSlugs = new Set<string>();
      for (const hit of hits) {
        if (!hit || !this.#tools.has(hit.toolSlug)) {
          fail(`retrieval[${sigHash}] names unknown tool ${String(hit?.toolSlug)}`);
        }
        if (seenSlugs.has(hit.toolSlug)) {
          // The same tool twice in one result means the judge is asked about it
          // twice and, if the two rows carry different scores, the ledger records
          // two `match_score`s for one candidate. Vendors do not do this; a
          // copy-paste in a fixture does.
          fail(`retrieval[${sigHash}] lists ${hit.toolSlug} twice`);
        }
        seenSlugs.add(hit.toolSlug);
        if (!Number.isFinite(hit.score)) {
          // A NaN score sorts unpredictably, so "the top candidate" would depend
          // on the engine's sort implementation rather than on the fixture.
          fail(`retrieval[${sigHash}] tool ${hit.toolSlug} has a non-finite score`);
        }
      }
      this.#retrieval[sigHash] = copy(hits);
    }

    this.#connections = {};
    for (const [userId, rows] of Object.entries(fixture.connections ?? {})) {
      if (!Array.isArray(rows)) fail(`connections[${userId}] must be an array`);
      for (const row of rows) {
        if (!row || typeof row.app !== "string" || row.app === "") {
          fail(`connections[${userId}] has a row with no app`);
        }
        if (row.status !== "active" && row.status !== "expired" && row.status !== "revoked") {
          fail(`connections[${userId}] app ${row.app} has status ${String(row.status)}`);
        }
      }
      this.#connections[userId] = copy(rows);
    }

    this.#exec = {};
    for (const [slug, scripted] of Object.entries(fixture.exec ?? {})) {
      if (!this.#tools.has(slug)) fail(`exec names unknown tool ${slug}`);
      const script = Array.isArray(scripted) ? scripted : [scripted];
      if (script.length === 0) fail(`exec[${slug}] is an empty script`);
      for (const outcome of script) validateOutcome(`exec[${slug}]`, outcome);
      this.#exec[slug] = copy(script);
    }

    this.#defaultOutcome = copy(fixture.defaultOutcome ?? DEFAULT_OUTCOME);
    validateOutcome("defaultOutcome", this.#defaultOutcome);
    this.#connectBase = fixture.connectLinkBase ?? DEFAULT_CONNECT_BASE;
    this.#throws = { ...(fixture.throws ?? {}) };
  }

  /** A vendor that is down on every method. The router must survive this
   *  without taking the browser hand down with it. */
  static down(message = "vendor unreachable"): FakeProvider {
    return new FakeProvider({
      tools: [],
      throws: { search: message, connections: message, connectLink: message, execute: message },
    });
  }

  /** Forget the call log and the script cursors. Same effect as constructing a
   *  fresh provider from the same fixture, for a test that wants two acts
   *  without rebuilding the world. */
  reset(): void {
    this.calls.length = 0;
    this.#cursors.clear();
  }

  async search(
    sig: CapabilitySignature,
    userId: string,
    opts: { connectedOnly: boolean; limit: number },
  ): Promise<ToolCandidate[]> {
    this.#maybeThrow("search");

    // `opts` is typed as required, but type annotations are STRIPPED here, not
    // checked - a caller can and eventually will pass nothing. Defaulting
    // `connectedOnly` to false is the deliberately unhelpful choice: it is what
    // the real vendor does, so a router that forgets the flag fails its test
    // here rather than in production against a revoked Slack token.
    const connectedOnly = opts?.connectedOnly === true;
    const rawLimit = opts?.limit;
    const limit = Number.isFinite(rawLimit) ? Math.max(0, Math.floor(rawLimit as number)) : Infinity;

    const sigHash = typeof sig?.signature_hash === "string" ? sig.signature_hash : "";
    this.calls.push({ method: "search", userId, sigHash, connectedOnly, limit });

    const hits = this.#retrieval[sigHash] ?? [];
    const activeApps = new Set(
      (this.#connections[userId] ?? []).filter((c) => c.status === "active").map((c) => c.app),
    );

    const ranked = hits
      .map((hit) => ({ hit, tool: this.#tools.get(hit.toolSlug)! }))
      // `connectedOnly` means USABLE, not merely listed: an expired or revoked
      // connection returned here is how a router picks the API hand and then
      // spends an owner-visible failure discovering the token is dead. The
      // expired case stays reachable - ask `connections()`, or search with
      // connectedOnly false.
      .filter(({ tool }) => !connectedOnly || activeApps.has(tool.app))
      // Score orders. Ties break on slug so "the top candidate" is the same on
      // every run and on every engine; without the tiebreak an assertion about
      // first place silently becomes an assertion about fixture insertion order.
      // Compared with < and > rather than localeCompare: collation is
      // locale-dependent, and a fake whose ordering changes with the machine's
      // ICU data is exactly the flake this file exists to prevent.
      .sort((a, b) => {
        if (b.hit.score !== a.hit.score) return b.hit.score - a.hit.score;
        return a.tool.toolSlug < b.tool.toolSlug ? -1 : a.tool.toolSlug > b.tool.toolSlug ? 1 : 0;
      });

    const kept = limit === Infinity ? ranked : ranked.slice(0, limit);
    return kept.map(({ hit, tool }) => {
      const candidate: ToolCandidate = {
        toolSlug: tool.toolSlug,
        app: tool.app,
        score: hit.score,
        schema: copy(tool.schema ?? {}),
        description: tool.description ?? "",
      };
      // Absent rather than present-and-undefined: a `sideEffectHint: undefined`
      // key survives JSON.stringify differently than a missing one, and the
      // shadow-run hashes in this spike are built from serialized objects.
      if (tool.sideEffectHint) candidate.sideEffectHint = tool.sideEffectHint;
      return candidate;
    });
  }

  async connections(userId: string): Promise<ConnectedApp[]> {
    this.#maybeThrow("connections");
    this.calls.push({ method: "connections", userId });
    return copy(this.#connections[userId] ?? []);
  }

  async connectLink(userId: string, app: string, scopes?: string[]): Promise<{ url: string }> {
    this.#maybeThrow("connectLink");
    const asked = Array.isArray(scopes) ? [...scopes] : [];
    this.calls.push({ method: "connectLink", userId, app, scopes: asked });
    // Scopes are sorted and the URL carries no nonce and no timestamp, so the
    // same request produces the same string on every run and in every process. A
    // random state parameter here would be more realistic and would turn every
    // assertion about this URL into a regex - which is how a plumbing detail
    // becomes a test nobody can read.
    const params = new URLSearchParams({ user: userId });
    if (asked.length > 0) params.set("scopes", [...asked].sort().join(","));
    return { url: `${this.#connectBase}/${encodeURIComponent(app)}?${params.toString()}` };
  }

  async execute(
    userId: string,
    toolSlug: string,
    args: Record<string, unknown>,
    accountId?: string,
  ): Promise<ExecResult> {
    this.#maybeThrow("execute");
    this.calls.push({ method: "execute", userId, toolSlug, args: copy(args ?? {}), accountId });

    const tool = this.#tools.get(toolSlug);
    if (!tool) {
      // A slug the catalog never had is the shape of a stale ledger row: the
      // vendor renamed GMAIL_SEND_EMAIL and the owner's `capability_stats` still
      // points at the old one. The vendor answers that with an error, not a
      // throw, and so does this.
      return { ok: false, error: { kind: "other", message: `unknown tool ${toolSlug}` }, ms: 0 };
    }

    // THE CONNECTION IS A PRECONDITION, AND IT OUTRANKS THE SCRIPT.
    //
    // The obvious alternative - let a scripted outcome win, so a fixture can say
    // exactly what happens without modelling an OAuth token - makes the fake
    // LOOSER than the vendor, and it was caught by this file's own test: with
    // the script first, an owner who had connected nothing still got the
    // fixture's Gmail success, and a router test could conclude the API hand
    // works for an owner with no accounts. Composio 401s that call every time,
    // whatever the fixture author intended, so the fake does too. A script
    // describes what happens once the call actually reaches the tool.
    //
    // The consequence is deliberate: to script an outcome for an app, the
    // fixture must also give the owner an active connection to it. That is the
    // real precondition, spelled out, and the error message below names the app
    // that is missing so the fix is one line of `withConnections`.
    const rows = this.#connections[userId] ?? [];
    const usable = rows.find(
      (c) =>
        c.app === tool.app && c.status === "active" && (!accountId || c.accountId === accountId),
    );
    if (!usable) {
      // All three of these are auth failures at the vendor and must look
      // identical to the router: an app the owner never connected, a connection
      // that has expired or been revoked, and an accountId the router carried
      // over from a ledger row whose connection is gone. A 401 here looks like a
      // task failure to the owner, so it belongs in `last_fail_reason` and a
      // re-auth nudge - never as evidence that the API hand is worse at the task.
      const why = rows.some((c) => c.app === tool.app)
        ? `no active connection for ${tool.app}${accountId ? ` account ${accountId}` : ""}`
        : `${tool.app} is not connected`;
      return { ok: false, error: { kind: "auth", message: `401 ${why}` }, ms: 0 };
    }

    const scripted = this.#nextScripted(userId, toolSlug);
    return outcomeToResult(scripted ?? this.#defaultOutcome);
  }

  // Cursors are keyed per (owner, tool) rather than per tool. A shadow run that
  // executes the same slug for two owners in one process would otherwise hand
  // owner B the second entry of owner A's script, and that reads exactly like a
  // routing bug in the part under test.
  #nextScripted(userId: string, toolSlug: string): FakeOutcome | null {
    const script = this.#exec[toolSlug];
    if (!script) return null;
    // The separator is an explicit NUL ESCAPE, not a literal NUL byte and not a
    // space: an owner id is caller-supplied, so a space separator lets
    // ("a b", "C") and ("a", "b C") share one cursor, and a literal NUL in the
    // source makes this file binary to grep, diff and every review tool.
    const key = `${userId}\u0000${toolSlug}`;
    const seen = this.#cursors.get(key) ?? 0;
    this.#cursors.set(key, seen + 1);
    // The last entry repeats forever: a script of one is a constant, and a
    // script that ran out mid-test must not fall through to a success the
    // fixture never authorised.
    return script[Math.min(seen, script.length - 1)];
  }

  #maybeThrow(method: FakeMethod): void {
    const message = this.#throws[method];
    if (message !== undefined) throw new FakeProviderDown(method, message);
  }
}

function validateOutcome(where: string, outcome: FakeOutcome): void {
  if (!outcome || typeof outcome !== "object") fail(`${where}: outcome must be an object`);
  if (typeof outcome.ok !== "boolean") fail(`${where}: outcome.ok must be a boolean`);
  if (!Number.isFinite(outcome.ms) || outcome.ms < 0) {
    // ms feeds p50/p95 in the ledger. A NaN or a negative there does not throw -
    // it quietly makes a latency comparison false, and the router promotes or
    // demotes a hand for a reason nobody can reconstruct afterwards.
    fail(`${where}: outcome.ms must be a non-negative number`);
  }
  if (outcome.ok && outcome.error) {
    // An ok:true row carrying an error lets a test assert on a failure the
    // router was never shown. Either the call worked or it did not.
    fail(`${where}: ok:true must not carry an error`);
  }
  if (!outcome.ok) {
    const kind = outcome.error?.kind;
    if (kind !== "auth" && kind !== "rate" && kind !== "schema" && kind !== "other") {
      fail(`${where}: ok:false needs error.kind of auth|rate|schema|other, got ${String(kind)}`);
    }
  }
}

function outcomeToResult(outcome: FakeOutcome): ExecResult {
  const result: ExecResult = { ok: outcome.ok, ms: outcome.ms };
  if (outcome.data !== undefined) result.data = copy(outcome.data);
  if (outcome.error) result.error = { ...outcome.error };
  if (outcome.costUsd !== undefined) result.costUsd = outcome.costUsd;
  return result;
}

// ---------------------------------------------------------------------------
// A FIXTURE OTHER PARTS CAN POINT AT
// ---------------------------------------------------------------------------
// Four apps the owner actually uses, in the connection states that matter, with
// all four ExecErrorKinds reachable. Every host is example.invalid and every id
// is obviously fake, because a fixture that looks like production is a fixture
// somebody will eventually point at production.

export const FIXTURE_USER = "owner-fixture";
/** An owner who has connected nothing. The fresh-install path - every rule that
 *  says "route to browser because there is no connection" is measured here. */
export const FIXTURE_USER_COLD = "owner-cold";

/** Signature hashes are FIXED STRINGS, not computed. They are plausible sha1s so
 *  nothing downstream learns to parse them, and they are literals so this
 *  fixture does not move the day `signature.ts` changes what it hashes. */
export const FIXTURE_HASHES = {
  read_inbox: "b7d1e0c4a92f38561d0e2f3a4b5c6d7e8f901234",
  send_email: "3f2a9c1d5b7e4086a1c2d3e4f5061728394a5b6c",
  archive_thread: "c5e2f10a3b4c5d6e7f8091a2b3c4d5e6f7089aab",
  delete_thread: "8a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3",
  create_event: "d9a3b2c1e0f14253647586970a1b2c3d4e5f6071",
  /** Deliberately absent from `retrieval`: the vendor has nothing for this step.
   *  Named so a test can ask for "no candidates" without inventing a hash. */
  no_tool_exists: "0000000000000000000000000000000000000000",
} as const;

/** Ready-made signatures so other parts have something concrete to route. The
 *  hashes match FIXTURE_HASHES; `app_hint` is advisory and is wrong on purpose
 *  in one of them, because a planner that guesses the app right every time never
 *  exercises the rule that says the trace wins. */
export const FIXTURE_SIGNATURES: Record<string, CapabilitySignature> = {
  read_inbox: {
    app_hint: "gmail",
    verb: "read",
    object: "unread messages in the primary inbox",
    inputs: { max_results: 20 },
    expected_effect: "the last 20 unread messages are listed and none is marked read",
    side_effect: "read",
    account_hint: "work",
    signature_hash: FIXTURE_HASHES.read_inbox,
  },
  send_email: {
    app_hint: "gmail",
    verb: "send",
    object: "an email to one recipient",
    inputs: { to: "sam@example.invalid", subject: "", body: "" },
    expected_effect: "a message from the owner to that recipient appears in Sent",
    side_effect: "write",
    account_hint: "work",
    signature_hash: FIXTURE_HASHES.send_email,
  },
  archive_thread: {
    app_hint: "gmail",
    verb: "update",
    object: "one mail thread",
    inputs: { thread_id: "thr-fake-1" },
    expected_effect: "the thread leaves the inbox and is still findable in All Mail",
    side_effect: "write",
    account_hint: "work",
    signature_hash: FIXTURE_HASHES.archive_thread,
  },
  delete_thread: {
    app_hint: "gmail",
    verb: "delete",
    object: "one mail thread",
    inputs: { thread_id: "thr-fake-1" },
    expected_effect: "the thread is gone from All Mail",
    side_effect: "irreversible",
    account_hint: "work",
    signature_hash: FIXTURE_HASHES.delete_thread,
  },
  create_event: {
    // Wrong on purpose: the planner guessed Notion for a calendar step. Advisory
    // only, never a routing key - the fixture has to contain one of these or
    // nothing ever tests that.
    app_hint: "notion",
    verb: "create",
    object: "a 30-minute meeting on Thursday",
    inputs: { title: "", start: "", duration_min: 30 },
    expected_effect: "an event exists on the owner's calendar at that time",
    side_effect: "write",
    account_hint: "work",
    signature_hash: FIXTURE_HASHES.create_event,
  },
};

export const FIXTURE: FakeFixture = {
  tools: [
    {
      toolSlug: "GMAIL_FETCH_EMAILS",
      app: "gmail",
      description: "List messages in a Gmail mailbox matching a query.",
      sideEffectHint: "read",
      schema: { query: "string", max_results: "number" },
    },
    {
      toolSlug: "GMAIL_SEND_EMAIL",
      app: "gmail",
      description: "Send an email as the connected Gmail account.",
      sideEffectHint: "write",
      schema: { to: "string", subject: "string", body: "string" },
    },
    {
      toolSlug: "GMAIL_ARCHIVE_THREAD",
      app: "gmail",
      description: "Remove a thread from the inbox. The thread stays in All Mail.",
      sideEffectHint: "write",
      schema: { thread_id: "string" },
    },
    {
      // The tool that makes this fixture worth shipping. Its description reads
      // almost exactly like the archive one, which is the case contract.ts's
      // LAW1 note names by hand: a similarity score cannot tell "archive the
      // thread" from "delete the thread", and only one of them can be undone. It
      // declares itself a plain write, so the hint does not save anyone either.
      toolSlug: "GMAIL_DELETE_THREAD",
      app: "gmail",
      description: "Remove a thread from the mailbox permanently.",
      sideEffectHint: "write",
      schema: { thread_id: "string" },
    },
    {
      // Carries the `schema` failure. Its app is ACTIVE on purpose: with the
      // connection precondition in `execute`, a failure parked on notion or
      // slack could never be reached, and the fixture would quietly stop
      // covering the kind it claims to cover.
      toolSlug: "GMAIL_ADD_LABEL",
      app: "gmail",
      description: "Add a label to a message.",
      sideEffectHint: "write",
      schema: { message_id: "string", label_ids: "string[]" },
    },
    {
      toolSlug: "GOOGLECALENDAR_FIND_EVENT",
      app: "googlecalendar",
      description: "Find events on a calendar in a time window.",
      sideEffectHint: "read",
      schema: { time_min: "string", time_max: "string" },
    },
    {
      // Carries the `rate` failure, for the same reason.
      toolSlug: "GOOGLECALENDAR_QUICK_ADD",
      app: "googlecalendar",
      description: "Create an event from one line of text.",
      sideEffectHint: "write",
      schema: { text: "string" },
    },
    {
      toolSlug: "GOOGLECALENDAR_CREATE_EVENT",
      app: "googlecalendar",
      description: "Create an event on a calendar.",
      sideEffectHint: "write",
      schema: { summary: "string", start: "string", end: "string" },
    },
    {
      toolSlug: "NOTION_SEARCH",
      app: "notion",
      description: "Search pages and databases in a Notion workspace.",
      sideEffectHint: "read",
      schema: { query: "string" },
    },
    {
      toolSlug: "NOTION_CREATE_PAGE",
      app: "notion",
      description: "Create a page in a Notion database.",
      sideEffectHint: "write",
      schema: { parent_id: "string", title: "string" },
    },
    {
      toolSlug: "SLACK_FETCH_HISTORY",
      app: "slack",
      description: "Read recent messages in a Slack channel.",
      sideEffectHint: "read",
      schema: { channel: "string", limit: "number" },
    },
    {
      toolSlug: "SLACK_SEND_MESSAGE",
      app: "slack",
      description: "Post a message to a Slack channel.",
      sideEffectHint: "write",
      schema: { channel: "string", text: "string" },
    },
  ],

  // The states the router has to survive, one per app:
  //   gmail          two ACTIVE accounts (work + personal) -> accountId matters
  //   googlecalendar ACTIVE
  //   notion         EXPIRED  -> listed, unusable, 401 on execute
  //   slack          REVOKED  -> listed, unusable, 401 on execute
  //   any app, for FIXTURE_USER_COLD: ABSENT -> never connected at all
  connections: {
    [FIXTURE_USER]: [
      {
        app: "gmail",
        accountId: "conn-gmail-work-0001",
        label: "work@example.invalid",
        scopes: ["gmail.readonly", "gmail.send"],
        status: "active",
      },
      {
        app: "gmail",
        accountId: "conn-gmail-personal-0002",
        label: "personal@example.invalid",
        scopes: ["gmail.readonly"],
        status: "active",
      },
      {
        app: "googlecalendar",
        accountId: "conn-gcal-0003",
        label: "work@example.invalid",
        scopes: ["calendar.events"],
        status: "active",
      },
      {
        app: "notion",
        accountId: "conn-notion-0004",
        label: "Anticipy workspace",
        scopes: ["read_content", "insert_content"],
        status: "expired",
      },
      {
        app: "slack",
        accountId: "conn-slack-0005",
        label: "anticipy.slack.example.invalid",
        scopes: ["channels:history", "chat:write"],
        status: "revoked",
      },
    ],
    [FIXTURE_USER_COLD]: [],
  },

  retrieval: {
    // Cross-app noise is on purpose: retrieval hands back a Notion and a Slack
    // reader for an inbox step, and only a judge can say they are not it.
    [FIXTURE_HASHES.read_inbox]: [
      { toolSlug: "GMAIL_FETCH_EMAILS", score: 0.93 },
      { toolSlug: "NOTION_SEARCH", score: 0.41 },
      { toolSlug: "SLACK_FETCH_HISTORY", score: 0.38 },
    ],
    [FIXTURE_HASHES.send_email]: [
      { toolSlug: "GMAIL_SEND_EMAIL", score: 0.88 },
      { toolSlug: "SLACK_SEND_MESSAGE", score: 0.72 },
    ],
    // The pair this whole judge exists for, and the scores are inverted in the
    // dangerous direction: asked to ARCHIVE, the vendor ranks DELETE first. Any
    // "take the top hit above 0.75" rule sends an irreversible act. Only a
    // per-candidate verdict of exactly "yes" can catch this.
    [FIXTURE_HASHES.archive_thread]: [
      { toolSlug: "GMAIL_DELETE_THREAD", score: 0.91 },
      { toolSlug: "GMAIL_ARCHIVE_THREAD", score: 0.89 },
    ],
    [FIXTURE_HASHES.delete_thread]: [
      { toolSlug: "GMAIL_ARCHIVE_THREAD", score: 0.9 },
      { toolSlug: "GMAIL_DELETE_THREAD", score: 0.87 },
    ],
    [FIXTURE_HASHES.create_event]: [
      { toolSlug: "GOOGLECALENDAR_CREATE_EVENT", score: 0.95 },
      // These two share a score so the shipped fixture, and not only a
      // hand-built one, exercises the slug tiebreak in `search`.
      { toolSlug: "GOOGLECALENDAR_FIND_EVENT", score: 0.6 },
      { toolSlug: "NOTION_CREATE_PAGE", score: 0.6 },
    ],
  },

  exec: {
    GMAIL_FETCH_EMAILS: {
      ok: true,
      ms: 340,
      costUsd: 0.0004,
      data: {
        messages: [{ id: "msg-fake-1", from: "sam@example.invalid", subject: "re: thursday" }],
      },
    },
    GMAIL_SEND_EMAIL: { ok: true, ms: 612, costUsd: 0.0006, data: { id: "msg-fake-sent-1" } },
    GMAIL_ARCHIVE_THREAD: { ok: true, ms: 420, costUsd: 0.0003, data: { thread_id: "thr-fake-1" } },
    // It SUCCEEDS. That is the point: nothing between the judge and the vendor
    // stops an irreversible mistake, so a test that wants the delete blocked has
    // to show the ROUTER blocking it, not the fake being squeamish.
    GMAIL_DELETE_THREAD: { ok: true, ms: 450, costUsd: 0.0003, data: { thread_id: "thr-fake-1" } },
    GMAIL_ADD_LABEL: {
      ok: false,
      ms: 180,
      error: { kind: "schema", message: "400 label_ids must be an array of label ids" },
    },
    // Succeeds, slowly. The week-1 gate is "p50 under 3 seconds", and a hand
    // that is correct but eight seconds slow is the case that rule exists for.
    GOOGLECALENDAR_FIND_EVENT: { ok: true, ms: 8240, costUsd: 0.0002, data: { events: [] } },
    // The vendor's own upstream broke. Nothing about this is the owner's fault
    // and nothing about it is fixed by reconnecting, which is what makes it a
    // different row in `last_fail_reason` from the 401 above.
    GOOGLECALENDAR_CREATE_EVENT: {
      ok: false,
      ms: 1204,
      error: { kind: "other", message: "500 upstream error from the calendar API" },
    },
    GOOGLECALENDAR_QUICK_ADD: {
      ok: false,
      ms: 90,
      error: { kind: "rate", message: "429 rate limited, retry after 30s" },
    },
    // Notion and Slack are scripted with NOTHING on purpose. Their connections
    // are expired and revoked, so `execute` derives the 401 from the connection
    // state itself - which is the honest model and the reason a scripted answer
    // parked here would be dead fixture, never reached and never noticed. A test
    // that wants a live Notion says so with `withConnections`.
  },
};

/** Add or replace one capability's retrieval WITHOUT mutating the fixture it was
 *  built from. Other parts compute their own `signature_hash` from
 *  `signature.ts`, which will not equal FIXTURE_HASHES, and a shared fixture
 *  that each test quietly edits is how one test starts depending on another
 *  having run first. */
export function withRetrieval(
  fixture: FakeFixture,
  sigHash: string,
  hits: RetrievalHit[],
): FakeFixture {
  return { ...fixture, retrieval: { ...(fixture.retrieval ?? {}), [sigHash]: [...hits] } };
}

/** Same discipline for connections: a new fixture in which one owner has exactly
 *  these connections. */
export function withConnections(
  fixture: FakeFixture,
  userId: string,
  rows: ConnectedApp[],
): FakeFixture {
  return { ...fixture, connections: { ...(fixture.connections ?? {}), [userId]: [...rows] } };
}

/** Same discipline for outcomes. Pass an array to script a call sequence. */
export function withExec(
  fixture: FakeFixture,
  toolSlug: string,
  outcome: FakeOutcome | FakeOutcome[],
): FakeFixture {
  return { ...fixture, exec: { ...(fixture.exec ?? {}), [toolSlug]: outcome } };
}
