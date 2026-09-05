/**
 * POST /me/delete   { "confirm": "delete" }   Authorization: <account token>
 *
 * Ported from backend/pb_hooks/account_delete.pb.js -- the delete the privacy
 * page promises. It is the one irreversible operation in the product, so the
 * two rules below are the whole security of the endpoint.
 *
 * RULE 1 -- WHICH VALUE MAY MATCH WHICH COLUMN.
 * `legacy_uuid` is a plain, client-writable field on `owners`: the iOS client
 * posts it verbatim at signup, so a value read from it is a CLAIM, never proof.
 * Applied to `owner_ref` it became: sign up declaring
 * legacy_uuid = <victim account id>, POST here, and the victim's jobs,
 * segments, agents, profile and transcripts are gone. The victim's id is not
 * even secret -- the anonymous six-digit pair-code lookup hands it out.
 * So the account's own id may match anything; legacy_uuid may match ONLY a
 * table's own legacy column, and only when it is long enough to be real.
 *
 * RULE 2 -- NAME THE COLUMN PER COLLECTION.
 * owner_profile calls it `owner_id`; the rest call it `owner`. A filter naming
 * a column that does not exist throws for the WHOLE query, and a swallowed
 * throw left the densest PII in the system (name, email, phone, birthday,
 * facts) behind while still reporting a count. Worse, sms.pb.js resolves
 * inbound texts against owner_profile.phone BEFORE owners, so that residue kept
 * routing somebody's texts after they believed they were gone.
 *
 * The table list lives here rather than at module scope on purpose: the
 * PocketBase original had to keep it inside the handler because its pooled JS
 * runtime cannot see the enclosing scope at request time, and keeping the shape
 * makes the two files diffable.
 */
import { verifyToken, type AuthEnv } from "../pb/auth.ts";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });

function pbNow(d = new Date()): string {
  return d.toISOString().replace("T", " ");
}
function pbId(): string {
  const A = "abcdefghijklmnopqrstuvwxyz0123456789";
  return [...crypto.getRandomValues(new Uint8Array(15))].map((b) => A[b % A.length]).join("");
}

export async function accountDelete(req: Request, env: AuthEnv & { DB: D1Database }) {
  // Ordered so a timeout lands on the cheapest table to retry.
  const OWNER_TABLES: Array<{ name: string; legacy: string | null }> = [
    { name: "jobs", legacy: "owner" },
    { name: "segments", legacy: "owner" },
    { name: "agents", legacy: "owner" },
    { name: "owner_profile", legacy: "owner_id" },
    { name: "pendants", legacy: "owner" },
    // Audit rows hold up to 1 MB each of verbatim task text, page content and
    // model responses, on a TEXT owner_ref with no cascade -- nothing else
    // would ever remove them. The retention sweep caps the table; that is a
    // disk defence, not a privacy control.
    { name: "agent_llm_audit", legacy: null },
    { name: "agent_audit_sessions", legacy: null },
    // A photograph of a page they were logged into is the densest single thing
    // this product will ever hold about somebody.
    { name: "evidence", legacy: null },
    { name: "events", legacy: null },
  ];

  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return json(401, { ok: false, message: "Sign in first." });
  if (auth.claims.collectionName !== "owners") {
    return json(403, { ok: false, message: "Only an account can delete itself." });
  }

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { body = {}; }

  // Proof of INTENT, not of possession. A bearer token is stateless and valid
  // until tokenKey rotates, so one replayed request from a stolen phone or a
  // logged Authorization header would otherwise be a total wipe with no second
  // step.
  if (String(body.confirm ?? "") !== "delete") {
    return json(400, {
      ok: false,
      message: 'Send {"confirm":"delete"} to confirm. This cannot be undone.',
    });
  }

  const ref = String(auth.claims.id || "").trim();
  if (!ref) return json(400, { ok: false, message: "No account on that token." });

  const row = await env.DB.prepare(`SELECT legacy_uuid FROM owners WHERE id = ?`)
    .bind(ref).first<{ legacy_uuid: string | null }>();
  const legacy = String(row?.legacy_uuid ?? "").trim();

  const deleted: Record<string, number> = {};
  const failed: string[] = [];

  for (const t of OWNER_TABLES) {
    const keys: Array<[string, string]> = [["owner_ref", ref]];
    if (t.legacy) {
      keys.push([t.legacy, ref]);                       // own id, legacy column
      if (legacy.length >= 8) keys.push([t.legacy, legacy]);  // claim, legacy column ONLY
    }
    let count = 0;
    for (const [field, value] of keys) {
      try {
        const res = await env.DB
          .prepare(`DELETE FROM "${t.name}" WHERE "${field}" = ?`).bind(value).run();
        count += (res.meta?.changes as number) ?? 0;
      } catch (err) {
        // A column that does not exist on this table is expected for some
        // pairs; a real failure is not. Record it and refuse to claim success.
        const msg = String(err);
        if (!/no such column/i.test(msg)) failed.push(`${t.name}.${field}: ${msg}`);
      }
    }
    deleted[t.name] = count;
  }

  if (failed.length) {
    return json(500, {
      ok: false,
      message: "I couldn't delete all of it, so I've stopped rather than tell you I had. Try again.",
      deleted,
    });
  }

  // The brain's per-owner memory lives outside this database, so the erasure is
  // not finished here -- it is REQUESTED, and the worker drains it.
  //
  // `legacy_uuid` RIDES ALONG, and until 2026-09-05 it did not (audit F14).
  // The pre-migration founder's memory lives OUTSIDE <state root>/<owner_ref>,
  // on the older ANTICIPY_MEMORY_DB / ANTICIPY_CLOCK_STATE paths, and
  // brain/supervisor.py:215 reads exactly this column to find it. Without the
  // value the drain checks the tidy directory, finds nothing, and marks the
  // purge COMPLETE over a memory database still fully on disk -- the one lie
  // that function's docstring forbids. The value is already in hand: it is the
  // `legacy` read above.
  try {
    await env.DB.prepare(
      `INSERT INTO purges (id, owner_ref, legacy_uuid, requested_at, memory_purged, created, updated)
       VALUES (?,?,?,?,?,?,?)`)
      .bind(pbId(), ref, legacy, new Date().toISOString(), 0, pbNow(), pbNow()).run();
  } catch {
    return json(500, {
      ok: false,
      message: "I deleted what I could reach but couldn't schedule the rest. Try again.",
      deleted,
    });
  }

  // THE LAST TWO ANSWERS ARE READ BY A DECODER, NOT BY A HUMAN, and until
  // 2026-09-05 neither carried what it reads (audit F14).
  // AnticipyApp.swift:303-336 decodes `account_deleted` and `memory_purge` and
  // calls the delete a success only when
  //   status == 200 && ok && account_deleted && purge in {scheduled, purged}.
  // A body of {ok, message, deleted} leaves account_deleted nil, so `success`
  // was false on a delete that had entirely succeeded: the phone rendered
  // "Deleted." as the FAILURE copy and, because outcome.ok was false, skipped
  // clearPendingLinesOwned, clearPendingAppRepliesOwned and signOut
  // (:1764-1785) -- leaving somebody signed into a closed account with speech
  // lines still stamped to it. And the survived-account branch answered 500
  // where the hook answers 409, which is the status the iOS comment
  // (AnticipyBackend.swift:483-489) singles out as "the rows went but the
  // account survived".
  try {
    await env.DB.prepare(`DELETE FROM owners WHERE id = ?`).bind(ref).run();
  } catch (err) {
    console.log("DELETE INCOMPLETE: rows cleared but the account survived for "
      + ref + ": " + String(err).slice(0, 200));
    return json(409, {
      ok: false,
      message: "I deleted your data but couldn't close the account itself. Ask me again — what's already gone stays gone.",
      deleted,
      account_deleted: false,
      memory_purge: "waiting on the account closing",
    });
  }

  return json(200, {
    ok: true,
    message: "Deleted.",
    deleted,
    account_deleted: true,
    memory_purge: "scheduled",
  });
}
