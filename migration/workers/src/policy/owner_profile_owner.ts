/**
 * src/policy/owner_profile_owner.ts
 * backend/pb_hooks/owner_profile_owner.pb.js:34-79. 30 code lines (the brief
 * said ~45; the file is 79 lines of which 49 are the comment explaining why it
 * is a middleware and not a `required` field).
 *
 * A PROFILE WITH NO OWNER IS A PERSON NOBODY CAN LOOK UP. Production carried
 * 3 orphans out of 10 rows: every read path asks for a profile BY ACCOUNT
 * (brain/worker.py `_latest_profile`, agent_key.pb.js:40,
 * password_reset.pb.js:64) and an empty relation satisfies none of them. They
 * are not inert while they sit there either — sms.pb.js:166 resolves an
 * inbound text through owner_profile by phone, `-updated`, LIMIT 3, so three
 * orphans sharing a number push the real row out of that window and every
 * "yes, go ahead" from that phone is dropped behind a 200.
 *
 * TWO LAYERS, ON PURPOSE, AND BOTH MUST BE PORTED:
 *   - this middleware, which gives a client log a sentence it can act on;
 *   - the collection's createRule `@request.body.owner_ref != ""`
 *     (1700000043_owner_profile_needs_owner.js:44), which survives a hook file
 *     being renamed and is enforced even for a caller holding the service
 *     token — that token is a header the guard checks, not an identity, so
 *     rules still applied to it.
 *
 * D1 HAS NO API RULES. So the second layer has to be re-created as something
 * else, and the honest choice is a DATABASE CHECK plus a rule evaluated in the
 * Worker — see ARCHITECTURE.md §3.7. A `required` column is still WRONG for
 * the same reason it was rejected on PocketBase: the three live orphans hold
 * the only copy of a phone number and must stay patchable, because patching
 * them is how they get adopted (claim_legacy.pb.js:73-84).
 */
import { json } from "../pb/wire.ts";
import type { Ctx, Policy } from "./chain.ts";

const BASE = "/api/collections/owner_profile/records";

/**
 * owner_ref is a maxSelect:1 relation, so a client may legitimately send it
 * either as an id or as a one-element array. Refusing the array form would
 * break an honest write to stop a dishonest one. :47-50.
 */
function named(raw: unknown): boolean {
  const value = Array.isArray(raw) ? (raw.length === 1 ? raw[0] : "") : raw;
  return typeof value === "string" && value.trim() !== "";
}

export const ownerProfileOwner: Policy = (ctx: Ctx): Response | null => {
  const { path, method } = ctx;
  if (path !== BASE && !path.startsWith(`${BASE}/`)) return null;
  if (method !== "POST" && method !== "PATCH") return null;

  const body = ctx.body ?? {};

  if (method === "POST") {
    if (named(body.owner_ref)) return null;
    // 400, not 403. This is a malformed record, not a permission problem, and
    // the sentence has to be usable in a client log — the iPhone's
    // `upsertOwner` sends no owner_ref at all when it has no account id yet
    // (clients/ios/.../AnticipyBackend.swift:223), which is how at least some
    // of the live orphans were born. :54-58.
    return json(400, {
      error: "owner_profile needs an owner",
      detail: "owner_ref must name the account this profile belongs to; a profile "
        + "created without one can never be read back, because every lookup in the "
        + "product filters on owner_ref. Sign in first, then save.",
    });
  }

  // PATCH: only when it actually tries to BLANK the column. An update that
  // never mentions owner_ref is left alone — that is the ordinary case, and it
  // includes the adoption of a legacy row and every write to the three rows
  // already stranded in production. :67-70.
  if ("owner_ref" in body && !named(body.owner_ref)) {
    return json(400, {
      error: "owner_profile needs an owner",
      detail: "clearing owner_ref would strand this profile: nothing can find a "
        + "profile that names no account.",
    });
  }
  return null;
};

/**
 * THE SECOND LAYER, restated as the D1 statements that replace the createRule.
 * Applied by the migration in ARCHITECTURE.md §3.7; kept here so the two
 * layers are read together and neither is dropped without seeing the other.
 *
 *   -- refuses an ownerless INSERT the way the createRule did, and does NOT
 *   -- freeze the existing orphans (an UPDATE is untouched).
 *   CREATE TRIGGER IF NOT EXISTS "owner_profile_needs_owner_on_insert"
 *   BEFORE INSERT ON "owner_profile"
 *   FOR EACH ROW WHEN COALESCE(TRIM(NEW."owner_ref"), '') = ''
 *   BEGIN
 *     SELECT RAISE(ABORT, 'owner_profile needs an owner');
 *   END;
 *
 * UNVERIFIED: that D1 permits CREATE TRIGGER. SQLite does; whether D1's
 * control plane accepts trigger DDL was not tested. If it does not, the rule
 * lives only in this middleware plus a post-import assertion
 * (migration/d1/schema.sql SECTION 4), and that fact must be written into
 * RULES.md rather than quietly accepted.
 */
export const OWNER_PROFILE_INSERT_TRIGGER = `
CREATE TRIGGER IF NOT EXISTS "owner_profile_needs_owner_on_insert"
BEFORE INSERT ON "owner_profile"
FOR EACH ROW WHEN COALESCE(TRIM(NEW."owner_ref"), '') = ''
BEGIN
  SELECT RAISE(ABORT, 'owner_profile needs an owner');
END;
`;
