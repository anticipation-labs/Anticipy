/**
 * GET /r/{code} — the referral hop.
 *
 * PORTED FROM RECOVERED SOURCE, not reverse-engineered. fellowship.pb.js is in
 * no commit of either repository; it was pulled out of a 14.7 GB backup archive
 * as git blob 0eb1af32 and is kept at migration/recovered/fellowship.pb.js.
 * Before that, everything below the redirect could only be guessed at, and
 * guessing at an attribution path is how attribution silently stops being right.
 *
 * THIS ROUTE IS MONEY. The 302 carries ?ref=<code>, which is what credits a
 * fellow; /internal/fellows/pay is a real route. It is also the route whose
 * absence would have broken every fellow link the moment the website's
 * FELLOWSHIP_ORIGIN was repointed, because src/app/r/[code]/route.ts on the
 * site reads that same variable.
 */
import { sha256Hex } from "../llm.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";

export interface FellowEnv {
  DB: D1Database;
  ANTICIPY_SITE_URL?: string;
  ANTICIPY_FELLOW_SALT?: string;
}

type Row = Record<string, unknown>;

export async function referralHop(
  req: Request, env: FellowEnv, rawCode: string,
): Promise<Response> {
  const site = env.ANTICIPY_SITE_URL || "https://anticipy.ai";

  // Normalise exactly as the checkout does, so a code survives the whole round
  // trip — link, cookie, Stripe metadata, webhook — unchanged.
  let raw = "";
  try { raw = decodeURIComponent(rawCode || ""); } catch { raw = rawCode || ""; }
  raw = raw.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 24);
  const clean = /^[a-z0-9-]{4,24}$/.test(raw) ? raw : "";

  if (clean) {
    try {
      const fellow = await env.DB.prepare(
        "SELECT * FROM fellows WHERE referral_code = ?1 LIMIT 1").bind(clean).first<Row>();
      const revoked = !(fellow?.code_revoked === 0 || fellow?.code_revoked === null
                        || fellow?.code_revoked === undefined || fellow?.code_revoked === false);
      if (fellow && !revoked) {
        // X-Forwarded-For FIRST. Behind the anticipy.ai rewrite the peer address
        // is Vercel for everyone, so deduping on it would collapse into "one
        // click per code per hour, globally" and a fellow would be credited
        // once no matter how many people tapped.
        const xff = String(req.headers.get("X-Forwarded-For") || "");
        const ip = xff ? xff.split(",")[0].trim()
                       : String(req.headers.get("CF-Connecting-IP") || "");
        const salt = env.ANTICIPY_FELLOW_SALT || "anticipy-fellows";
        const ipHash = ip ? await sha256Hex(ip + salt) : "";

        // One click per code per address per hour, so a refresh loop cannot
        // inflate anyone's numbers.
        let dupe = false;
        if (ipHash) {
          try {
            const recent = await env.DB.prepare(
              "SELECT created FROM fellow_clicks WHERE code = ?1 AND ip_hash = ?2 "
              + "ORDER BY created DESC LIMIT 1").bind(clean, ipHash).first<Row>();
            if (recent) {
              const t = Date.parse(String(recent.created ?? "").replace(" ", "T"));
              if (!isNaN(t) && Date.now() - t < 3600000) dupe = true;
            }
          } catch { /* a failed dedupe check must not cost the click */ }
        }
        if (!dupe) {
          try {
            await env.DB.prepare(
              "INSERT INTO fellow_clicks (id, created, code, ip_hash, ua) VALUES (?1,?2,?3,?4,?5)",
            ).bind(newRecordId(), pbNow(), clean, ipHash,
                   String(req.headers.get("User-Agent") || "").slice(0, 200)).run();
            await env.DB.prepare(
              "UPDATE fellows SET clicks_total = ?1, updated = ?2 WHERE id = ?3",
            ).bind((Number(fellow.clicks_total) || 0) + 1, pbNow(), String(fellow.id)).run();
          } catch { /* the visit matters more than the counter */ }
        }
      }
    } catch { /* an unknown code still redirects; see below */ }
  }

  // ALWAYS redirects, even for a code that does not exist. These links are
  // printed in bios and burned into video captions where a typo cannot be
  // corrected, so a bad code must never be a dead end. `none` is the campaign
  // for an unrecognised code, which is also how a typo is visible in analytics.
  const url = site + "/?ref=" + encodeURIComponent(clean || "")
    + "&utm_source=fellow&utm_medium=referral&utm_campaign="
    + encodeURIComponent(clean || "none");
  return new Response(null, { status: 302, headers: { Location: url } });
}
