/**
 * src/assets.ts — everything PocketBase served as bytes.
 *
 * TWO DIFFERENT PROBLEMS THAT LOOK LIKE ONE.
 *
 * A. `pb_public/` — 5 static files and 4 zips, COPYed into the image at
 *    backend/Dockerfile:11. Immutable per deploy, no auth, no counting:
 *
 *      internal.html                       136 KB   the HQ SPA
 *      setup.html / privacy.html / mac.html
 *      site.css / theme.js
 *      anticipy-extension.zip              271 KB   (x3 identical copies:
 *      anticipy-claude-version-extension.zip         claude/codex/plain)
 *      anticipy-codex-version-extension.zip
 *      mac/Anticipy-for-Mac.zip            379 KB
 *
 *    → WORKERS STATIC ASSETS. They ship in the deploy, are served from the
 *      edge with no Worker invocation, and cost nothing per request. Total is
 *      ~1.3 MB, far inside the assets limit, and they version with the code
 *      that references them — which R2 would not.
 *
 *    Two of the three extension zips are byte-identical copies of the third
 *    (277,549 bytes each, verified). Keeping three names is a deploy-channel
 *    decision, not a storage one; leave them until someone decides otherwise.
 *
 * B. `evidence.image` — receipt photos. Every property is the opposite of (A):
 *    written at runtime, per-owner, authorised per fetch, and COUNTED (the
 *    share window spends a 5-fetch ceiling, evidence.pb.js:130-145).
 *
 *    → R2, behind this Worker. NEVER a public bucket and never a custom
 *      domain on the bucket: the whole point of evidence.pb.js:56-147 is that
 *      the bytes are reachable only through a gate that checks the share
 *      window and increments `fetches`. A public R2 URL is that gate deleted.
 *
 * -------------------------------------------------------------------------
 * /mac/Anticipy-for-Mac.zip CURRENTLY 404s IN PRODUCTION.
 *
 * The brief states this and it is worth being precise about, because the
 * tree CONTRADICTS the obvious causes:
 *   - the file IS tracked in git (`git ls-files backend/pb_public/` lists it)
 *   - it IS 388,070 bytes on disk
 *   - it IS copied into the image (backend/Dockerfile:11 `COPY pb_public …`)
 *   - backend/.railwayignore excludes only pb_data/, pocketbase, pb.zip, pb.log
 *
 * So a build-time exclusion is NOT the cause, and whatever is (a stale image,
 * a PocketBase static-route quirk on a nested directory, a proxy rule) is not
 * visible from here. UNVERIFIED — I cannot reach production.
 *
 * WHAT MATTERS FOR THE MIGRATION: moving to Static Assets makes the class of
 * bug impossible, because the file is enumerated at deploy time and
 * `wrangler deploy` prints the manifest. Add the assertion below to the
 * cutover checklist so it cannot 404 silently a second time.
 *
 *   curl -sI https://<worker>/mac/Anticipy-for-Mac.zip | head -1   # 200
 *   curl -sI https://<worker>/anticipy-extension.zip   | head -1   # 200
 * -------------------------------------------------------------------------
 */
import { json, stillInTheFuture } from "./pb/wire.ts";

export interface AssetEnv {
  DB: D1Database;
  EVIDENCE: R2Bucket;
  ASSETS: Fetcher;
  ANTICIPY_SERVICE_TOKEN: string;
}

/** evidence.pb.js:57 */
const SHARE_FETCH_LIMIT = 5;

/**
 * GET /api/files/{collectionIdOrName}/{recordId}/{filename}
 * evidence.pb.js:56-147, ported.
 *
 * "that evidence is not available" is the answer to EVERY refusal, and that is
 * not laziness: telling an anonymous caller which of "no such row", "never
 * shared", "expired" and "spent" they hit turns the endpoint into an oracle
 * for walking record ids (:70-74).
 */
export async function serveFile(
  request: Request, env: AssetEnv, ownerId: string | null,
): Promise<Response> {
  const gone = () => json(404, { error: "that evidence is not available" });

  const parts = new URL(request.url).pathname.split("/");
  const collectionKey = parts[3] ?? "";
  const recordId = parts[4] ?? "";
  const filename = parts[5] ?? "";
  if (!collectionKey || !recordId || !filename) return gone();

  // FAIL CLOSED FOR EVERY OTHER COLLECTION (:92-96). Today none of them has a
  // file field. If a later migration adds one it has to come here and say so,
  // rather than inheriting an anonymous public URL by accident — which is
  // exactly how an evidence host turns into a file host.
  if (collectionKey !== "evidence") return gone();

  const rec = await env.DB.prepare(
    `SELECT * FROM "evidence" WHERE "id" = ?1 LIMIT 1`,
  ).bind(recordId).first<Record<string, unknown>>();
  if (!rec) return gone();

  // ---- the two doors that are not the public one (:106-121) --------------
  // Neither spends the fetch ceiling and neither needs a share window: the
  // picture in his own app is not the picture on the public internet.
  const token = request.headers.get("X-Anticipy-Token") ?? "";
  const serviceOK = !!env.ANTICIPY_SERVICE_TOKEN && token === env.ANTICIPY_SERVICE_TOKEN;
  const ownerOK = !!ownerId && ownerId === String(rec.owner_ref ?? "");
  if (serviceOK || ownerOK) return streamFromR2(env, rec, filename, gone);

  // ---- the public door (:123-145) ---------------------------------------
  if (!rec.share_expires) return gone();
  // `new Date("soon").getTime()` is NaN and `NaN <= now` is FALSE, so the
  // obvious expiry test lets an unparseable date through as the far future.
  // stillInTheFuture() is written the safe way round (:126-129).
  if (!stillInTheFuture(rec.share_expires)) return gone();

  const spent = Number(rec.fetches ?? 0);
  if (!(spent >= 0) || spent >= SHARE_FETCH_LIMIT) return gone();

  // COUNT BEFORE SERVING, and refuse if the count fails. "Serving what nobody
  // is counting is the exact hole the ceiling closes" (:137-144).
  //
  // The counter is a conditional UPDATE rather than a read-then-write: two
  // concurrent Twilio fetches on the same evidence row would otherwise both
  // read 4 and both serve. On PocketBase that race also existed; here it is
  // closed for free because the WHERE does the checking.
  const res = await env.DB.prepare(
    `UPDATE "evidence" SET "fetches" = "fetches" + 1
      WHERE "id" = ?1 AND "fetches" = ?2`,
  ).bind(recordId, spent).run().catch(() => null);
  if (!res || !res.meta.changes) {
    console.log("evidence: refusing a fetch that could not be counted");
    return gone();
  }

  return streamFromR2(env, rec, filename, gone);
}

async function streamFromR2(
  env: AssetEnv, rec: Record<string, unknown>, filename: string, gone: () => Response,
): Promise<Response> {
  // The COLUMN holds the stored filename; the BYTES lived under --dir /pb_data
  // (backend/start.sh:33) and move to R2. migration/d1/schema.sql, `file` in
  // the type map. PocketBase's on-disk layout is
  // storage/<collectionId>/<recordId>/<filename>; the R2 key mirrors it by
  // record id so the export script can copy without knowing collection ids.
  const stored = String(rec.image ?? "");
  if (!stored || stored !== filename) return gone();

  const key = `evidence/${String(rec.id)}/${stored}`;
  const obj = await env.EVIDENCE.get(key);
  if (!obj) return gone();

  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  headers.set("etag", obj.httpEtag);
  // Never let a share-limited object sit in a shared cache: the ceiling is
  // per-fetch and a CDN hit is a fetch nobody counted.
  headers.set("cache-control", "private, no-store");
  return new Response(obj.body, { headers });
}
