/**
 * src/policy/research_lane.ts — backend/pb_hooks/research_lane.pb.js:272-727.
 * 228 code lines. Registered FIFTH.
 *
 * Two jobs, and the first is the one that makes this migration hard.
 *
 * LEG 1 — THE FILTER REWRITE (research_lane.pb.js:437-443)
 *   A queued-jobs poll that does NOT name `lane` has three exclusions APPENDED
 *   to it, by string concatenation, before PocketBase ever parses it:
 *
 *     q.set("filter", "(" + filter + ") && lane != \"research\" && …")
 *
 *   That exists to protect against extensions ALREADY IN THE WILD (0.2.3 and
 *   older) whose filters cannot be recalled: without it such an install claims
 *   a supervised read and runs it through the full action vocabulary —
 *   clicking and typing inside somebody's mailbox, with nobody watching
 *   (extension/background.js:80-88).
 *
 *   Here it is an AST node, not a string. `andNot()` produces an AND that no
 *   value can escape, and `mentionsField()` is exact where the deployed
 *   `/\blane\b/` regex is approximate — the regex says "mentions lane" for
 *   `goal="pick a lane"`, and therefore SKIPS the exclusion on a poll that
 *   never constrained the lane at all. That is a fail-open in the deployed
 *   code, and the AST version closes it. See ARCHITECTURE.md §3.4.
 *
 * LEG 2-5 — the write legs: the lane is immutable except for one audited
 *   handback, the device lane has a shape, and separation of duties on the
 *   claim. Ported below with their file:line anchors.
 */
import { parseFilter, andNot, mentionsField, FilterError, type Node } from "../../filter-dsl.ts";
import { refuse, badRequest, stillInTheFuture } from "../pb/wire.ts";
import type { Ctx, Policy } from "./chain.ts";

const JOBS_BASE = "/api/collections/jobs/records";

// research_lane.pb.js:278-306
const QUEUED_POLL = /status\s*=\s*"queued"/;
const WORKER_CLAIMANT = "worker-research";
const SUPERVISED_LANE = "supervised_read";
const DEVICE_LANE = "device_calendar";
const DEVICE_CONSEQUENCE = "consequential";
const DEVICE_ACT_TYPES = ["calendar_write", "calendar_undo"];
const LIVE = ["queued", "running"];
/**
 * brain/hands.py LANE_API — the lane an `api` verdict lands on, claimed by
 * brain/worker.py run_api_jobs and run on src/routes/hands_api.ts. Exported
 * so test/api-lane-claim.test.ts can hold the route and the brain to it.
 *
 * WHY IT IS HERE (2026-09-06): until this line the extension's poll listed
 * api-lane rows (its filter names `lane` and excluded only research, so leg 1
 * appended nothing) and leg 5 had no api rule, so a browser that polled before
 * the brain CLAIMED the row and ran an api errand through the browser
 * vocabulary. The api hand was bypassed every time a browser was awake. The
 * extension's filter now mirrors this list (extension/background.js
 * BROWSER_LANE), but that is the courtesy; this file is the floor.
 */
export const API_LANE = "api";
const EXCLUDED_LANES = ["research", SUPERVISED_LANE, DEVICE_LANE, API_LANE];

export const researchLane: Policy = async (ctx: Ctx): Promise<Response | null> => {
  const { path, method } = ctx;

  // ---- LEG 1: the read rewrite. research_lane.pb.js:436-452 --------------
  if (method === "GET" && path === JOBS_BASE && !ctx.worker.fromWorker) {
    const raw = ctx.url.searchParams.get("filter") ?? "";
    if (QUEUED_POLL.test(raw)) {
      let ast = null;
      try { ast = raw ? parseFilter(raw) : null; }
      catch (e) {
        if (e instanceof FilterError) {
          return badRequest("invalid filter", {
            filter: { code: "invalid_filter", message: e.message, offset: e.offset } });
        }
        throw e;
      }
      // The deployed code uses /\blane\b/ against the raw string. On the AST
      // this is exact: a `lane` inside a string literal is not a mention.
      const names = ast ? mentionsField(ast, "lane") : false;
      if (!names) {
        // Chain the three exclusions onto whatever the chain already carries.
        // `andNot` builds an AND node, so unlike the deployed string
        // concatenation there is nothing for a value to break out of.
        ctx.extraAst = EXCLUDED_LANES.reduce<Node | null>(
          (acc, lane) => acc
            ? andNot(acc, "lane", lane)
            : { kind: "cmp", op: "!=",
                left: { kind: "column", name: "lane", offset: -1 },
                right: { kind: "string", value: lane, offset: -1 }, offset: -1 },
          ctx.extraAst);
      }
    }
    return null;
  }

  // ---- the write legs. research_lane.pb.js:456-458 -----------------------
  const creates = method === "POST" && path === JOBS_BASE;
  const updates = method === "PATCH" && path.startsWith(`${JOBS_BASE}/`);
  if (!creates && !updates) return null;

  const b = ctx.body ?? {};
  const rec = updates ? await loadJob(ctx, path.split("/").pop() as string) : null;
  ctx.storedRow = rec;

  const norm = (v: unknown) => String(v ?? "").trim().toLowerCase();
  const rowLane = rec ? norm(rec.lane) : "";
  const bodyLane = "lane" in b ? norm(b.lane) : null;

  // ---- LEG 2: the lane is immutable. research_lane.pb.js:544-551 ---------
  const handback = updates && isResearchHandback(ctx, rec, b, rowLane, bodyLane);
  if (updates && bodyLane !== null && bodyLane !== rowLane && !handback) {
    return refuse(403,
      "a job's lane is decided when it is minted, never rewritten",
      "the lane says which hand may run this errand, so a claimant that could "
      + "name it could name its way out of every check on it");
  }

  const lane = bodyLane !== null ? bodyLane : rowLane;

  // ---- LEG 3: device-lane shape. research_lane.pb.js:553-585 -------------
  if (lane === DEVICE_LANE) {
    const status = String(b.status ?? rec?.status ?? "");
    if (LIVE.includes(status)) {
      const why = deviceShapeRefusal(b, rec, DEVICE_CONSEQUENCE);
      if (why) return refuse(403, "that calendar errand is not safe to run yet", why);
    }
    const stored = String(rec?.approval ?? "");
    const rewritesApproval = b.approval != null && String(b.approval) !== stored;
    if (creates && rewritesApproval) {
      return refuse(403,
        "the tap and the errand it releases are two separate writes",
        "an errand that does not yet exist has not been tapped; mint it held, "
        + "show it to him, then write the tap onto the row");
    }
    if (rewritesApproval
        && (LIVE.includes(status) || "claimed_by" in b || b.status === "running")) {
      return refuse(403,
        "the tap and the errand it releases are two separate writes",
        "a hand may not mint the approval for the act it is about to perform; "
        + "leave the errand held, write the tap, then release it");
    }
  }

  // ---- LEG 4: creates stop here. research_lane.pb.js:586 -----------------
  if (creates) return null;

  // ---- LEG 5: the claim legs. research_lane.pb.js:587-612 ----------------
  const claims = "claimed_by" in b || b.status === "running";
  if (claims && !ctx.worker.fromWorker) {
    // THE API LANE HAS ONE CLAIMANT, and it is identified by the worker
    // marker above — never by what the body calls itself. The research leg
    // below lets a claimant through for NAMING the worker, and that shape is
    // deliberately not copied here: a browser can type "worker-api" as easily
    // as anything else. The sweep's requeue (`claimed_by: ""`) is a claim-
    // shaped write too, and it is refused alike; brain/worker.py
    // release_stranded_api does that job under the marker.
    if (lane === API_LANE) {
      return refuse(403,
        "api errands run on the api hand in the worker, never in a browser",
        "the lane says which hand may run this errand; a browser that claimed "
        + "it would run the wrong hand, and the api hand would never see it");
    }
    if (lane === "research" && b.claimed_by !== WORKER_CLAIMANT) {
      return refuse(403, "research jobs run in the worker, never in a browser");
    }
    if (lane === SUPERVISED_LANE && !stillInTheFuture(rec?.watching_until)) {
      return refuse(403,
        "a read nobody is watching is not a supervised read — open the app and stay on the screen");
    }
    const superuser = ctx.principal.kind === "superuser";
    const ownerSession = ctx.principal.kind === "account";
    if (!superuser) {
      if (lane === DEVICE_LANE && !ownerSession) {
        return refuse(403, "a calendar errand happens on your phone, never in a browser");
      }
      if (lane !== DEVICE_LANE && ownerSession) {
        return refuse(403, "your phone does not run browser errands — it approves them");
      }
    }
  }
  return null;
};

// ---------------------------------------------------------------------------

async function loadJob(ctx: Ctx, id: string): Promise<Record<string, unknown> | null> {
  if (!id) return null;
  const db = (ctx as unknown as { db: D1Database }).db;
  return db.prepare(`SELECT * FROM "jobs" WHERE "id" = ?1 LIMIT 1`)
    .bind(id).first<Record<string, unknown>>();
}

const ordered = (v: unknown): unknown => {
  if (Array.isArray(v)) return v.map(ordered);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(v as object).sort()) {
      out[k] = ordered((v as Record<string, unknown>)[k]);
    }
    return out;
  }
  return v;
};
const sameJSON = (a: unknown, b: unknown) =>
  JSON.stringify(ordered(a ?? null)) === JSON.stringify(ordered(b ?? null));

const parsedObject = (raw: unknown): Record<string, unknown> | null => {
  let v = raw;
  if (typeof v === "string") { try { v = JSON.parse(v || "{}"); } catch { return null; } }
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>) : null;
};

/**
 * research_lane.pb.js:509-543 — the ONE legitimate lane change, and it is
 * fenced with an exhaustive field-by-field comparison rather than a flag,
 * because a flag would be forgeable by the caller.
 *
 * Ported field-for-field. It is long and it is meant to be: every relaxation
 * here is a way for a claimant to launder a research job into browser work.
 */
function isResearchHandback(
  ctx: Ctx, rec: Record<string, unknown> | null, b: Record<string, unknown>,
  rowLane: string, bodyLane: string | null,
): boolean {
  if (!ctx.worker.fromWorker || !rec || rowLane !== "research"
      || bodyLane !== "" || rec.status !== "queued") return false;
  const keys = Object.keys(b);
  if (keys.some((k) => k !== "lane" && k !== "params")) return false;
  if (!keys.includes("params")) return false;

  const before = parsedObject(rec.params);
  const after = parsedObject(b.params);
  if (!before || !after || !sameJSON(before._workflow, after._workflow)) return false;

  const oldGate = parsedObject(before._research_gate);
  const newGate = parsedObject(after._research_gate);
  if (!oldGate || !newGate || oldGate.handback !== true
      || Object.prototype.hasOwnProperty.call(newGate, "handback")
      || typeof newGate.researched !== "boolean") return false;

  for (const k of Object.keys(before)) {
    if (k === "_research_gate" || k === "procedure") continue;
    if (!Object.prototype.hasOwnProperty.call(after, k) || !sameJSON(before[k], after[k])) return false;
  }
  for (const k of Object.keys(after)) {
    if (k === "_research_gate" || k === "procedure") continue;
    if (!Object.prototype.hasOwnProperty.call(before, k)) return false;
  }
  for (const k of Object.keys(oldGate)) {
    if (k === "handback" || k === "why" || k === "researched") continue;
    if (!Object.prototype.hasOwnProperty.call(newGate, k) || !sameJSON(oldGate[k], newGate[k])) return false;
  }
  for (const k of Object.keys(newGate)) {
    if (k === "why" || k === "researched") continue;
    if (!Object.prototype.hasOwnProperty.call(oldGate, k)) return false;
  }
  return true;
}

/** research_lane.pb.js:351-415 — why a calendar errand is not safe to run. */
function deviceShapeRefusal(
  b: Record<string, unknown>, rec: Record<string, unknown> | null, wanted: string,
): string {
  const stated = (name: string): string[] => {
    const out: string[] = [];
    if (rec) out.push(String(rec[name] ?? "").trim());
    if (b[name] != null) out.push(String(b[name]).trim());
    return out;
  };

  const workflows = stated("workflow_id");
  if (!workflows.length || workflows.some((v) => !v)) {
    return "a calendar errand with no workflow skips the confirmation gate entirely";
  }
  const consequences = stated("consequence");
  const wrong = consequences.filter((v) => v !== wanted);
  if (!consequences.length || wrong.length) {
    const c = wrong.length ? wrong[0] : "";
    if (c === "read_only") {
      return "read_only carries an approval exemption that is earned by a backstop "
        + "this lane does not have — a calendar write acts on the world";
    }
    if (c === "reversible_local") {
      return "Shelf 2 admits local_draft and nothing else; EventKit assigns the "
        + "event identifier on save, which is the undo shape §6.1 excludes";
    }
    return `a calendar errand must be held for a tap; this one says "${c}"`;
  }

  const acts = declaredActTypes(b, rec);
  const strangers = acts.filter((t) => t !== null && !DEVICE_ACT_TYPES.includes(t));
  if (!acts.length || strangers.length || acts.some((t) => t === null)) {
    if (strangers.length) {
      return `the device lane carries calendar acts and nothing else; this one `
        + `declares "${strangers[0]}"`;
    }
    return "a calendar errand has to say which calendar act it is; this one declares none";
  }
  return "";
}

function declaredActTypes(
  b: Record<string, unknown>, rec: Record<string, unknown> | null,
): (string | null)[] {
  const read = (raw: unknown): string | null => {
    const parsed = parsedObject(raw);
    const wf = parsed ? (parsed._workflow as Record<string, unknown> | undefined) : null;
    const act = wf ? (wf.act as Record<string, unknown> | undefined) : null;
    const t = act ? act.act_type : null;
    return typeof t === "string" && t.trim() ? t.trim() : null;
  };
  const out: (string | null)[] = [];
  if (rec) out.push(read(rec.params));
  if (b.params != null) out.push(read(b.params));
  return out;
}
