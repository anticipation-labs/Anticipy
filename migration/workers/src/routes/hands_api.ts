/**
 * src/routes/hands_api.ts — THE LAST WIRE. POST /hands/api/run runs ONE
 * claimed api-lane job on the API hand and writes what happened onto the row.
 *
 * Until this file existed the two halves of the Two Hands spec did not touch:
 * the router (brain/hands.py, 6f62bc68) wrote a verdict onto every job —
 * `params._hand = {hand, reason, effect, app, lane}` — and the API hand
 * (src/connections/api_hand.ts `runStep`) could act behind four floors, and
 * NOTHING JOINED THEM: no production file imported `runStep`, the Worker never
 * read `_hand`, and an `api` verdict was mapped onto the browser lane because
 * there was no executor to map it onto. A part nothing calls is not a feature.
 *
 * WHO CALLS IT. The brain's `run_api_jobs` (brain/worker.py), which mirrors the
 * research lane: it claims a queued `lane="api"` row under `claimed_by =
 * "worker-api"` with the extension's own doctrine — stamp, read back, run only
 * if the stamp survived — and then POSTs `{job, owner}` here with the service
 * token. This route is the executor half of that claim, and it REFUSES a row
 * the brain has not claimed: a stray POST for a queued row runs nothing.
 *
 * THE BODY NEVER NAMES WHO. `job` is an id and `owner` is a CHECK, not an input:
 * the row is read by id, and the step's owner, toolkit, tool, arguments, effect
 * and confirmation all come off the ROW. A body whose `owner` disagrees with
 * the row is refused, never believed — the spike's own scar (contract.ts opens
 * on one operator's tokens serving everybody) is why no request field here can
 * ever be an owner.
 *
 * THE TOKEN, BEFORE ANY READ. A missing or wrong `X-Anticipy-Token` is 401
 * before D1 is touched, and so is a Worker with no token configured: nothing
 * authorises this door, so nothing opens it. A FLOOR in HARNESS-LAWS law 1's
 * sense. It is 401 rather than the service routes' 403 because the gate leg
 * (overnight/is_connect_live.py leg 15) reads "this route is deployed and
 * refused an anonymous caller" off exactly that code, beside a control path
 * that must 404.
 *
 * WHAT THE OUTCOME BECOMES. `runStep` answers one of three shapes and this file
 * branches on the CLOSED ENUMS it carries — never on prose:
 *
 *   ran                          -> done. `result` carries the vendor's data,
 *                                   the workflow gets a verified receipt naming
 *                                   the vendor's log id.
 *   refused, any reason but two  -> HANDED BACK TO THE BROWSER LANE (lane "",
 *                                   status queued, claim cleared). api_hand.ts:
 *                                   "a refusal here is the router routing to
 *                                   the browser". not_connected,
 *                                   writes_not_enabled and tool_unknown are the
 *                                   header's three; the shape refusals, an
 *                                   ambiguous account, an unreadable store or
 *                                   catalog and an unconfigured vendor key all
 *                                   land the same way — slower, noisier, but it
 *                                   runs, exactly as run_research_jobs hands a
 *                                   keyless lookup to the browser.
 *   refused: confirmation_required -> needs_user. The tool's own metadata made
 *                                   the step irreversible and nobody confirmed
 *                                   the exact payload; the browser lane would
 *                                   run a queued row unattended, so it parks
 *                                   and the owner is asked.
 *   refused: owner_required      -> failed. The row's owner_ref is not an id
 *                                   this system minted; no hand may take it.
 *   failed, kind auth            -> the connection row is marked
 *                                   needs_reconnect — the SAME write the expiry
 *                                   webhook makes, through the same function —
 *                                   and the job goes to the browser lane. The
 *                                   vendor promised nothing ran.
 *   failed, may have landed,     -> needs_user, effect_uncertain = 1, NEVER
 *     on a write or irreversible    re-run. "An unknown write is the router's
 *                                   'ask the owner' branch, never a re-run."
 *   failed, otherwise            -> the browser lane. A read that may have
 *                                   landed landed nothing; rate and schema are
 *                                   the vendor's promise nothing ran.
 *
 * A handback is the SECOND legitimate lane change in this backend, beside the
 * research handback src/policy/research_lane.ts fences field by field. It is
 * written by this Worker under the service token straight into D1, after the
 * hand has answered, and only from `api` to `""`; it cannot be forged through
 * the records API, where the lane stays immutable.
 *
 * THE ROW STAYS ONE THE BRAIN CAN READ. brain/workflow.py `Plan.from_dict(...)
 * .assert_valid()` runs over `params._workflow` on every later pass, and
 * src/policy/workflow_guard.ts judges every later PATCH against the stored
 * columns — so this file writes the embedded plan and the columns TOGETHER the
 * way `Plan.job_fields()` and the extension's `workflowPatch` do: a resting row
 * carries no lease, only a succeeded row carries a receipt, the receipt names
 * this plan's effect_key, and `workflow_state` agrees with `status`. A row this
 * file left half-written would be a row nobody could ever PATCH again.
 *
 * THIS FILE NAMES NO APP AND READS NO PROSE. The only comparisons below are
 * against enums (an outcome, a refusal reason, an error kind, a lane, a
 * status) and identifiers (the claimant, a token). test/hands-api.test.ts reads
 * this source and fails on an app name.
 */
import type { SideEffect } from "../../../../spike/two-hands/src/contract.ts";

import {
  runStep,
  type ApiHandDeps,
  type ApiHandEnv,
  type ApiHandOutcome,
  type ApiHandStep,
} from "../connections/api_hand.ts";
import {
  markNeedsReconnect,
  webhookStore,
  type MarkOutcome,
  type WebhookConnectionStore,
} from "./connections_webhook.ts";
import { json, pbNow } from "../pb/wire.ts";

// ---------------------------------------------------------------------------
// THE CONSTANTS THE BRAIN SHARES. Each is pinned to its Python twin by test.
// ---------------------------------------------------------------------------

/** The one path. src/index.ts and the gate name it once. */
export const HANDS_API_RUN_PATH = "/hands/api/run";
/** brain/hands.py LANE_API — the lane an `api` verdict lands on. */
export const API_LANE = "api";
/** brain/worker.py API_CLAIMANT — the actor the brain stamps before it POSTs. */
export const API_CLAIMANT = "worker-api";
/** anticipy_core's browser lane, where a handback goes. */
export const BROWSER_LANE = "";
/** brain/workflow.py recover_expired's `max_attempts`: a handback past this
 *  many attempts fails instead of queueing, so a row nobody can run does not
 *  bounce between two hands forever. */
export const MAX_ATTEMPTS = 3;
/** brain/worker.py run_research_jobs bounds `result` to this many characters. */
export const RESULT_MAX = 6000;
/** How much of the vendor's reply goes into `result`. The rest is the audit
 *  ledger's business; a result column is read by the composer, not archived. */
export const DATA_MAX = 4000;

/** brain/workflow.py LEGACY_STATUS, for the states this file can write. */
const STATUS_FOR_STATE: Record<string, string> = {
  queued: "queued",
  needs_user: "needs_user",
  succeeded: "done",
  failed: "failed",
};

export interface HandsApiEnv extends ApiHandEnv {
  ANTICIPY_SERVICE_TOKEN?: string;
}

/** Seams. Production passes nothing: the real hand, D1, and the isolate's
 *  memoised vendor adapter. */
export interface HandsApiDeps extends ApiHandDeps {
  /** The hand. Tests script outcomes here; production is `runStep`. */
  hand?: (env: ApiHandEnv, step: ApiHandStep, deps: ApiHandDeps) => Promise<ApiHandOutcome>;
  /** Where an auth failure marks the connection. Production: the webhook's
   *  own store over D1, so both callers write one state machine. */
  reconnect?: WebhookConnectionStore;
  now?: () => Date;
}

// ---------------------------------------------------------------------------
// THE DISPOSITION — what an outcome does to the row. Pure, so it is testable
// without a database and its polarity can be read in one place.
// ---------------------------------------------------------------------------

export type NextState = "succeeded" | "queued" | "needs_user" | "failed";

export interface Disposition {
  state: NextState;
  lane: typeof API_LANE | typeof BROWSER_LANE;
  /** What goes in `result`: the answer, the question for the owner, or why. */
  result: string;
  reason: string;
  effectUncertain: boolean;
  /** Mark the connection row needs_reconnect (auth failure only). */
  reconnect: boolean;
  /** For a receipt: the vendor's evidence. Empty unless `state` is succeeded. */
  evidence: string[];
}

/** Bounded, one-line-safe JSON of the vendor's data for the result column. */
function renderData(data: unknown): string {
  let text: string;
  try {
    text = data === undefined ? "" : JSON.stringify(data) ?? "";
  } catch {
    text = "";
  }
  return text.length > DATA_MAX ? text.slice(0, DATA_MAX) + "…" : text;
}

/**
 * The branch table in the header, as code. `attempts` is the row's count
 * AFTER the brain's claim, so a first run arrives here at 1.
 */
export function dispose(outcome: ApiHandOutcome, attempts: number): Disposition {
  const handback = (reason: string, result: string): Disposition => {
    if (attempts >= MAX_ATTEMPTS) {
      return {
        state: "failed", lane: API_LANE, reason: `stopped after ${attempts} attempts`,
        result: `${result} It had already been tried ${attempts} times, so it stops here.`,
        effectUncertain: false, reconnect: false, evidence: [],
      };
    }
    return {
      state: "queued", lane: BROWSER_LANE, reason, result,
      effectUncertain: false, reconnect: false, evidence: [],
    };
  };

  if (outcome.outcome === "ran") {
    const where = `${outcome.toolkit}/${outcome.tool}`;
    const data = renderData(outcome.data);
    return {
      state: "succeeded", lane: API_LANE, reason: "verified complete",
      result: (`Ran ${where} on the connected account (${outcome.ms}ms).`
        + (data ? `\n${data}` : "")).slice(0, RESULT_MAX),
      effectUncertain: false, reconnect: false,
      // The vendor's own log id is independently inspectable in its dashboard;
      // without one, the run itself is the only thing there is to cite.
      evidence: [outcome.logId ? `vendor-log:${outcome.logId}` : `vendor-run:${where}@${outcome.account}`],
    };
  }

  if (outcome.outcome === "refused") {
    if (outcome.reason === "confirmation_required") {
      return {
        state: "needs_user", lane: API_LANE, reason: outcome.reason,
        result: "This step is marked by the app as something that cannot be undone, and it "
          + "needs your go-ahead on the exact details before it runs.",
        effectUncertain: false, reconnect: false, evidence: [],
      };
    }
    if (outcome.reason === "owner_required") {
      return {
        state: "failed", lane: API_LANE, reason: outcome.reason,
        result: "This job names no owner this system could act for, so no hand can take it.",
        effectUncertain: false, reconnect: false, evidence: [],
      };
    }
    return handback(
      `api hand refused: ${outcome.reason}`,
      `The API hand did not take this (${outcome.reason}); it goes to the browser instead.`,
    );
  }

  // failed — the vendor was called.
  const err = outcome.error;
  const where = `${outcome.toolkit}/${outcome.tool}`;
  const said = `${err.kind} HTTP ${err.status}${err.token ? ` ${err.token}` : ""}`;
  if (err.kind === "auth") {
    const back = handback(
      `api hand failed: ${said}`,
      `The connected account for ${outcome.toolkit} no longer works (${said}); it needs `
        + "reconnecting, and this goes to the browser instead.",
    );
    return { ...back, reconnect: true };
  }
  if (outcome.mayHaveLanded && outcome.effect !== "read") {
    return {
      state: "needs_user", lane: API_LANE, reason: `api hand failed: ${said}`,
      result: `The ${where} step was sent and the app answered with an error (${said}). `
        + `It may have gone through anyway — please check ${outcome.toolkit} before I try again.`,
      effectUncertain: true, reconnect: false, evidence: [],
    };
  }
  return handback(
    `api hand failed: ${said}`,
    `The API hand hit an error on ${where} (${said}); it goes to the browser instead.`,
  );
}

// ---------------------------------------------------------------------------
// THE ROW — reading a step off it, writing an outcome onto it.
// ---------------------------------------------------------------------------

interface JobRow {
  id: string;
  owner_ref: string;
  status: string;
  lane: string;
  claimed_by: string;
  params: string;
  workflow_id: string;
  workflow_state: string;
  effect_key: string;
  attempts: number;
  lease_token: string;
}

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** A PocketBase-shaped record id: 15 lowercase alphanumerics. Plumbing. */
const ID_RE = /^[a-z0-9]{15}$/;

/** Python's `json.dumps(sort_keys=True, separators=(",", ":"))`, which is
 *  what brain/workflow.py `_canonical` writes into the receipt column. The
 *  guard compares JSON structurally, so the bytes need not match; the brain's
 *  own reader does not care either. Matching anyway costs eight lines and
 *  removes a way for two writers to disagree about one column. */
export function canonical(value: unknown): string {
  const sorted = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(sorted);
    if (isPlainObject(v)) {
      const out: Record<string, unknown> = {};
      for (const k of Object.keys(v).sort()) out[k] = sorted(v[k]);
      return out;
    }
    return v;
  };
  return JSON.stringify(sorted(value));
}

/**
 * brain/workflow.py `Plan.approved_for_current_version`, read off the stored
 * dict: the owner said yes to THIS plan id, THIS version and THIS scope, in
 * words or with a tap. That is the only thing "confirmed" may mean here — the
 * hand cannot verify a confirmation; it can refuse a caller that never held one.
 */
export function approvedForCurrentVersion(workflow: Record<string, unknown> | null): boolean {
  if (!workflow) return false;
  const a = workflow.approval;
  if (!isPlainObject(a)) return false;
  const words = str(a.owner_words).trim();
  const gesture = isPlainObject(a.gesture);
  return str(a.plan_id) === str(workflow.plan_id)
    && Number(a.plan_version ?? -1) === Number(workflow.version ?? -2)
    && str(a.scope_digest) === str(workflow.scope_digest)
    && (words.length > 0 || gesture);
}

/** The step, off the row and nowhere else. */
export function stepFromRow(
  row: Pick<JobRow, "owner_ref">,
  note: Record<string, unknown>,
  workflow: Record<string, unknown> | null,
): ApiHandStep {
  const alias = str(note.alias).trim();
  return {
    owner: row.owner_ref,
    toolkit: str(note.app) as ApiHandStep["toolkit"],
    tool: str(note.tool),
    // Passed as stored. runStep refuses anything that is not a plain object;
    // this file does not invent an empty argument list for a tool nobody
    // planned arguments for.
    args: note.args as Record<string, unknown>,
    effect: note.effect as SideEffect,
    alias: alias ? (alias as ApiHandStep["alias"]) : null,
    confirmed: approvedForCurrentVersion(workflow),
  };
}

/**
 * The embedded plan after this outcome, mirroring brain/workflow.py's
 * transitions and extension/workflow_state.js `workflowPatch`: a resting plan
 * has no lease; success carries a verified receipt for this effect_key and
 * nothing else does.
 */
export function settleWorkflow(
  workflow: Record<string, unknown>,
  row: Pick<JobRow, "effect_key">,
  d: Disposition,
  at: string,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...workflow, state: d.state, updated_at: at, reason: d.reason, lease: null };
  if (d.state === "succeeded") {
    next.receipt = {
      effect_key: str(workflow.effect_key) || row.effect_key,
      summary: d.result.slice(0, 2000),
      evidence: d.evidence.map((x) => x.slice(0, 1000)).slice(0, 12),
      verified: true,
      recorded_at: at,
    };
  } else {
    next.receipt = null;
  }
  return next;
}

// ---------------------------------------------------------------------------
// THE ROUTE
// ---------------------------------------------------------------------------

/** Length-checked, difference-accumulating compare; the same shape as
 *  src/index.ts timingSafeEqual and routes/service.ts tokenOk. */
function tokenOk(env: HandsApiEnv, req: Request): boolean {
  const want = env.ANTICIPY_SERVICE_TOKEN || "";
  const got = req.headers.get("X-Anticipy-Token") || "";
  if (!want || got.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < got.length; i++) d |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return d === 0;
}

const refuseWith = (status: number, message: string, extra: Record<string, unknown> = {}) =>
  json(status, { ok: false, message, ...extra });

export async function handsApiRun(
  request: Request,
  env: HandsApiEnv,
  deps: HandsApiDeps = {},
): Promise<Response> {
  if (request.method !== "POST") {
    // The whole path is handed over so the wrong verb is a 405 and not the
    // router's 404: a GET here must never read as "not deployed".
    return new Response(null, { status: 405, headers: { allow: "POST" } });
  }
  // -- The token, before any read. -----------------------------------------
  if (!tokenOk(env, request)) {
    return refuseWith(401, "service token required");
  }

  // -- The body: an id, and a check. ---------------------------------------
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return refuseWith(400, "the body must be JSON");
  }
  if (!isPlainObject(body)) return refuseWith(400, "the body must be an object");
  const jobId = str(body.job).trim();
  if (!ID_RE.test(jobId)) return refuseWith(400, "job must be a record id");
  const claimedOwner = str(body.owner).trim();

  // -- The row. --------------------------------------------------------------
  let row: JobRow | null;
  try {
    row = await env.DB.prepare(
      `SELECT "id","owner_ref","status","lane","claimed_by","params","workflow_id",
              "workflow_state","effect_key","attempts","lease_token"
         FROM "jobs" WHERE "id" = ?1 LIMIT 1`,
    ).bind(jobId).first<JobRow>();
  } catch (err) {
    return refuseWith(503, "the job could not be read", { detail: String((err as Error)?.message ?? err).slice(0, 200) });
  }
  if (!row) return refuseWith(404, "no such job");
  if (claimedOwner && claimedOwner !== String(row.owner_ref ?? "")) {
    // The body's owner is a check. A caller who is wrong about whose job this
    // is does not get to run it; it does not get the row's owner either.
    return refuseWith(403, "that job belongs to another owner");
  }

  let params: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(row.params || "{}");
    if (isPlainObject(parsed)) params = parsed;
  } catch {
    params = {};
  }
  const note = isPlainObject(params._hand) ? params._hand : {};
  const rowLane = String(row.lane ?? "").trim().toLowerCase();
  if (rowLane !== API_LANE || note.hand !== "api" || note.lane !== API_LANE) {
    return refuseWith(409, "not an api-lane job", {
      lane: row.lane ?? "", hand: str(note.hand), verdict_lane: str(note.lane),
    });
  }
  if (row.status !== "running" || row.claimed_by !== API_CLAIMANT) {
    // The brain claims first — stamp, read back — and only a surviving stamp
    // reaches here. A row nobody claimed is a row nobody may run.
    return refuseWith(409, "the job is not claimed by the api worker", {
      status: row.status, claimed_by: row.claimed_by,
    });
  }
  const workflow = isPlainObject(params._workflow) ? params._workflow : null;

  // -- The hand. -------------------------------------------------------------
  const hand = deps.hand ?? runStep;
  const handDeps: ApiHandDeps = {};
  if (deps.store) handDeps.store = deps.store;
  if (deps.provider) handDeps.provider = deps.provider;
  if (deps.clock) handDeps.clock = deps.clock;
  const step = stepFromRow(row, note, workflow);
  const outcome = await hand(env, step, handDeps);
  const attempts = Number(row.attempts ?? 0) || 0;
  const d = dispose(outcome, attempts);

  // -- The connection, on an auth failure: the webhook's own write. ----------
  let marked: MarkOutcome | null = null;
  if (d.reconnect && outcome.outcome === "failed") {
    const store = deps.reconnect ?? webhookStore(env);
    try {
      marked = await markNeedsReconnect(store, { accountId: outcome.account, owner: row.owner_ref });
      console.log(`hands api: ${row.owner_ref} ${outcome.toolkit} auth failed — connection ${marked.state}`);
    } catch (err) {
      marked = null;
      console.log(`hands api: ${row.owner_ref} ${outcome.toolkit} auth failed — could not mark: `
        + String((err as Error)?.message ?? err).slice(0, 120));
    }
  }

  // -- The row, written once, columns and embedded plan together. -----------
  const at = (deps.now ?? (() => new Date()))().toISOString();
  const stamp = pbNow(new Date(at));
  const status = STATUS_FOR_STATE[d.state];
  const nextNote: Record<string, unknown> = {
    ...note,
    lane: d.lane,
    outcome: {
      outcome: outcome.outcome,
      ...(outcome.outcome === "refused" ? { reason: outcome.reason } : {}),
      ...(outcome.outcome === "failed"
        ? { kind: outcome.error.kind, status: outcome.error.status, token: outcome.error.token,
            may_have_landed: outcome.mayHaveLanded }
        : {}),
      ...(outcome.outcome !== "refused" ? { tool: outcome.tool, effect: outcome.effect, ms: outcome.ms } : {}),
      ...(marked ? { connection: marked.state } : {}),
      state: d.state,
      at,
    },
  };
  const nextParams: Record<string, unknown> = { ...params, _hand: nextNote };
  let workflowState = row.workflow_state ?? "";
  let receipt = "";
  if (workflow) {
    const settled = settleWorkflow(workflow, row, d, at);
    nextParams._workflow = settled;
    workflowState = d.state;
    receipt = settled.receipt ? canonical(settled.receipt) : "";
  }
  const resting = d.state === "queued";
  let written = 0;
  try {
    const res = await env.DB.prepare(
      `UPDATE "jobs" SET "status" = ?1, "lane" = ?2, "result" = ?3, "params" = ?4,
              "claimed_by" = ?5, "claimed_at" = ?6, "lease_token" = '', "lease_until" = '',
              "workflow_state" = ?7, "receipt" = ?8, "effect_uncertain" = ?9, "updated" = ?10
        WHERE "id" = ?11 AND "status" = 'running' AND "claimed_by" = ?12`,
    ).bind(
      status, d.lane, d.result.slice(0, RESULT_MAX), JSON.stringify(nextParams),
      resting ? "" : API_CLAIMANT, resting ? "" : stamp,
      workflowState, receipt, d.effectUncertain ? 1 : 0, stamp,
      row.id, API_CLAIMANT,
    ).run();
    written = Number(res.meta?.changes ?? 0);
  } catch (err) {
    // The hand has ANSWERED and the row could not take it. Say so in the
    // answer and the log; the brain leaves the row to its stranded-claim
    // sweep, which recovers a row whose executor vanished without re-running
    // an effect it cannot vouch for.
    console.log(`hands api: ${row.id} ${outcome.outcome} but the row could not be written: `
      + String((err as Error)?.message ?? err).slice(0, 120));
    return json(500, {
      ok: false, message: "the outcome could not be written onto the job",
      job: row.id, outcome: outcome.outcome, status, lane: d.lane,
    });
  }
  if (written !== 1) {
    console.log(`hands api: ${row.id} ${outcome.outcome} but the row moved under the run — not written`);
    return json(409, {
      ok: false, message: "the job moved while the hand ran; nothing was written",
      job: row.id, outcome: outcome.outcome, status, lane: d.lane,
    });
  }
  console.log(`hands api: ${row.id} ${outcome.outcome} -> ${status}${d.lane === BROWSER_LANE ? " (browser lane)" : ""}`);
  return json(200, {
    ok: true,
    job: row.id,
    outcome: outcome.outcome,
    ...(outcome.outcome === "refused" ? { reason: outcome.reason } : {}),
    status,
    lane: d.lane,
    effect_uncertain: d.effectUncertain,
    ...(marked ? { connection: marked.state } : {}),
  });
}
