/**
 * GET /internal/people/faces  and  GET /internal/fellows
 *
 * THESE TWO ROUTES ARE NOT IN THIS REPOSITORY. They are served by production
 * and defined in no hook file in `backend/pb_hooks/` — more of what
 * research/2026-09-04-production-is-not-this-repo.md measured. They were found
 * by a pre-flight that compared every one of next.config.mjs's 33 rewrite
 * destinations against the Worker: 31 matched, these 2 answered 200 on Railway
 * and 404 here. Repointing the website without them would have 404'd whatever
 * page draws the team's avatars and the whole Fellowship dashboard.
 *
 * SOURCE RECOVERED 2026-09-04. fellowship.pb.js was pulled out of the
 * `endangered-git` archive as git blob 0eb1af32 — see
 * research/2026-09-04-recovering-the-deployed-source.md — so /internal/fellows
 * below is now a PORT, not a reconstruction, and three fields the
 * reconstruction had wrong are corrected against it.
 *
 * /internal/people/faces is still reverse-engineered: it lives in
 * fellowship_host.pb.js, which was UNTRACKED at the snapshot and therefore has
 * no blob to recover.
 *
 * The original reconstruction note follows, because how the shape was derived
 * still matters for the half that is still derived:
 *
 * PRODUCTION WAS THE SPEC, not a source file. Everything below was derived by
 * reading production's live responses and finding the query that reproduces
 * them, and each claim is marked with whether it is VERIFIED against production
 * or merely reasonable:
 *
 *   fellows      status != 'removed', ORDER BY created DESC   VERIFIED: same 12
 *                rows in the same order, out of 39.
 *   submissions  ORDER BY created DESC                        VERIFIED: same 5
 *                ids in the same order.
 *   conversions  UNVERIFIED — empty on both sides, so no projection of it can
 *                be checked. Field list is a reasonable guess.
 *   faces        the 6 ACTIVE people, id and name only        SET VERIFIED.
 *                ORDER NOT VERIFIED: production returns Omar, Jose, Arav,
 *                Claude, Tejas, Tejass, which matches no ordering of any column
 *                in the table — not name, created, updated, last_in, id, or
 *                is_admin, ascending or descending. Rather than invent a
 *                plausible-looking sort, this uses `name ASC` for consistency
 *                with /internal/state's people list and says so here.
 */
import { hqCors, type HqEnv } from "./hq.ts";
import { boolDefaultFalse } from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

type Row = Record<string, unknown>;
const str = (v: unknown) => String(v ?? "");

async function all(env: HqEnv, sql: string, ...b: unknown[]): Promise<Row[]> {
  try { return (await env.DB.prepare(sql).bind(...b).all<Row>()).results ?? []; }
  catch { return []; }
}

/**
 * GET /internal/people/faces — UNGATED (returns to any caller), 503 if the
 * server has no key configured.
 *
 * NOW PORTED FROM THE REAL SOURCE (deployed internal_hq.pb.js:2730, read off
 * the Railway container 2026-09-04), which corrected two guesses the
 * reverse-engineered version got wrong: the order is `created` ASC (not name),
 * the limit is 30 (not 200), and the name is the FIRST NAME ONLY —
 * `name.trim().split(/\s+/)[0]` — the welcome screen shows first names on its
 * face-picker. It is still ungated by design (it never compares the request's
 * key, only checks the server has one); reproduced rather than tightened, as
 * research/2026-09-04-two-routes-that-are-not-in-this-repo.md flags.
 */
export async function hqPeopleFaces(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  const rows = await all(env,
    "SELECT id, name FROM internal_people WHERE active = 1 ORDER BY created ASC LIMIT 30");
  return json(200, {
    people: rows.map((p) => ({
      id: p.id,
      name: str(p.name).trim().split(/\s+/)[0] || "",
    })),
  }, cors);
}

/**
 * GET /internal/fellows — GATED (401 "wrong key" without one, verified).
 *
 * The fellowship dashboard: who is in, what they submitted, what converted.
 */
export async function hqFellows(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal HQ is not configured" }, cors);
  const got = req.headers.get("X-Internal-Key") || "";
  let d = got.length === key.length ? 0 : 1;
  for (let i = 0; i < got.length && i < key.length; i++) {
    d |= got.charCodeAt(i) ^ key.charCodeAt(i);
  }
  if (d !== 0) return json(401, { error: "wrong key" }, cors);

  // status != 'removed' is what makes 39 rows into production's 12. A removed
  // fellow stays in the table — the row is the record that they were here —
  // and simply stops being listed.
  const fellows = (await all(env,
    "SELECT id,name,email,country,age_band,parental_consent,payout_identity_verified,"
    + "instagram,tiktok,fellowship,status,referral_code,code_active,clicks_total,created "
    + "FROM fellows WHERE status != 'removed' ORDER BY created DESC LIMIT 500"))
    .map((f) => ({
      id: f.id, name: str(f.name), email: str(f.email), country: str(f.country),
      age_band: str(f.age_band),
      // getString in the source, NOT a boolean. Reverse-engineering made this
      // a bool because the name reads like one; the recovered source says
      // otherwise and the source wins.
      parental_consent: str(f.parental_consent),
      payout_identity_verified: boolDefaultFalse(f.payout_identity_verified),
      instagram: str(f.instagram), tiktok: str(f.tiktok),
      fellowship: str(f.fellowship), status: str(f.status),
      referral_code: str(f.referral_code),
      code_active: boolDefaultFalse(f.code_active),
      clicks_total: Number(f.clicks_total) || 0,
      created: str(f.created),
    }));

  const submissions = (await all(env,
    "SELECT id,fellow,platform,kind,url,url_key,submitted_url,author_handle,author_claimed,"
    + "title,thumbnail_url,verify_state,oembed_status,status,removed_by,note,flags,created "
    + "FROM fellow_submissions ORDER BY created DESC LIMIT 200"))
    .map((s) => ({
      id: s.id, fellow: str(s.fellow), platform: str(s.platform), kind: str(s.kind),
      url: str(s.url), url_key: str(s.url_key), submitted_url: str(s.submitted_url),
      author_handle: str(s.author_handle), author_claimed: str(s.author_claimed),
      title: str(s.title), thumbnail_url: str(s.thumbnail_url),
      verify_state: str(s.verify_state),
      oembed_status: Number(s.oembed_status) || 0,
      status: str(s.status), removed_by: str(s.removed_by),
      note: str(s.note), flags: str(s.flags), created: str(s.created),
    }));

  // NO LONGER A GUESS. fellow_conversions is empty on both sides so this could
  // not be checked against a live response, and the first version of it was
  // reverse-engineered: it carried `source` and `paid_at` and omitted
  // `hold_until`, all three wrong. The recovered fellowship.pb.js settles it.
  const conversions = (await all(env,
    "SELECT id,fellow,code,order_ref,amount_usd,commission_usd,status,flags,"
    + "hold_until,created FROM fellow_conversions ORDER BY created DESC LIMIT 300"))
    .map((c) => ({
      id: c.id, fellow: str(c.fellow), code: str(c.code), order_ref: str(c.order_ref),
      amount_usd: Number(c.amount_usd) || 0,
      commission_usd: Number(c.commission_usd) || 0,
      status: str(c.status), flags: str(c.flags),
      hold_until: str(c.hold_until), created: str(c.created),
    }));

  return json(200, { fellows, submissions, conversions }, cors);
}
