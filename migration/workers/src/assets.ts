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
import { json, newRecordId, pbNow, stillInTheFuture } from "./pb/wire.ts";

export interface AssetEnv {
  DB: D1Database;
  EVIDENCE: R2Bucket;
  ASSETS: Fetcher;
  ANTICIPY_SERVICE_TOKEN: string;
  /**
   * Where this backend answers from, for the URL Twilio is handed.
   * evidence.pb.js:189-203: ANTICIPY_PUBLIC_URL, else the origin of the Twilio
   * webhook URL. Both optional; see publicBase() for what happens with neither.
   */
  ANTICIPY_PUBLIC_URL?: string;
  ANTICIPY_TWILIO_WEBHOOK_URL?: string;
}

/** evidence.pb.js:57 */
const SHARE_FETCH_LIMIT = 5;
/** evidence.pb.js:158 — minutes, because Twilio fetches within seconds. */
const SHARE_WINDOW_MS = 15 * 60 * 1000;

/**
 * 1700000045_evidence.js:67-75, the PocketBase file field: maxSelect 1,
 * maxSize 400000 (the extension's own screenshot ceiling, agent_loop.js:129),
 * mimeTypes image/jpeg + image/png. migration/d1/schema.sql:602-606 says to
 * enforce both here, and says why: "an evidence host that accepts arbitrary
 * files is a file host".
 */
export const EVIDENCE_MAX_BYTES = 400_000;
export const EVIDENCE_TYPES = ["image/jpeg", "image/png"];

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

// ===========================================================================
// THE DEPOSIT — where the bytes come from, which until now was nowhere.
//
// The whole share door above was dead code: `grep -rn EVIDENCE src/` found the
// binding and one `.get`, and not a single `.put` anywhere in the Worker. The
// extension has been posting receipt photos as multipart FormData since 0.14.0
// (background.js:1364-1377) and index.ts's readBody returned null for anything
// that was not application/json — so the guard saw an empty body, `owner_ref`
// read "", the agent rung refused it 403, and the extension logged "could not
// deposit the receipt photo (403)" and carried on. Every errand finished; no
// done-text ever carried its picture (audit F13).
//
// WHY THE BYTES GO FIRST. The row is what makes the photo reachable, and it
// names the file. Writing the row first and the object second leaves a window
// where the row promises bytes that are not there yet, and a permanent
// half-state if the put fails. This way a failed put means no row at all —
// the extension's own designed outcome ("" is a complete answer) — and a
// failed create means an orphan object, which is invisible and is swept by
// cron.ts's evidence cap.
// ===========================================================================

export interface Deposit {
  /** The id the row must be created with — the object is already under it. */
  id: string;
  /** What goes in `evidence.image`. */
  filename: string;
}

/**
 * PocketBase appends 10 random characters to every stored filename, and
 * evidence.pb.js:24-26 counts that as part of why the public path is not
 * guessable — while saying plainly that unguessability is a delay, not a lock.
 * Kept, because the share URL is built from it.
 *
 * The name is otherwise reduced to a safe stem: it arrives from a browser
 * extension and ends up in an R2 key and a URL path.
 */
export function evidenceFilename(sent: string, contentType: string): string {
  const dot = sent.lastIndexOf(".");
  const stem = (dot > 0 ? sent.slice(0, dot) : sent).toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "receipt";
  const ext = contentType === "image/png" ? "png" : "jpg";
  return `${stem}_${newRecordId().slice(0, 10)}.${ext}`;
}

/**
 * Put one deposited image in R2, or refuse in PocketBase's shape.
 *
 * REFUSING IS THE POINT of the two checks. A file field with a size and a MIME
 * list is what keeps an evidence host from becoming a file host, and D1 cannot
 * enforce either — the column holds a filename, not the bytes.
 */
export async function depositEvidenceImage(
  env: AssetEnv, file: File,
): Promise<{ ok: true; deposit: Deposit } | { ok: false; response: Response }> {
  const failed = (field: string, code: string, message: string) => ({
    ok: false as const,
    response: json(400, {
      data: { [field]: { code, message } },
      message: "Failed to create record.", status: 400,
    }),
  });

  const type = String(file.type || "").split(";")[0].trim().toLowerCase();
  if (!EVIDENCE_TYPES.includes(type)) {
    return failed("image", "validation_invalid_mime_type",
      `The file "${file.name}" mime type must be one of ${EVIDENCE_TYPES.join(", ")}.`);
  }
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength <= 0) {
    return failed("image", "validation_required", "Cannot be blank.");
  }
  if (bytes.byteLength > EVIDENCE_MAX_BYTES) {
    return failed("image", "validation_file_size_limit",
      `Maximum allowed file size is ${EVIDENCE_MAX_BYTES} bytes.`);
  }

  const id = newRecordId();
  const filename = evidenceFilename(String(file.name || "receipt.jpg"), type);
  try {
    await env.EVIDENCE.put(`evidence/${id}/${filename}`, bytes,
      { httpMetadata: { contentType: type } });
  } catch (err) {
    console.log(`evidence: could not store the deposited image: ${String(err)}`);
    return {
      ok: false,
      response: json(500, { message: "The picture could not be stored.", status: 500, data: {} }),
    };
  }
  return { ok: true, deposit: { id, filename } };
}

/** Undo a deposit whose row was refused, so nothing is paid for forever. */
export async function discardEvidenceImage(env: AssetEnv, d: Deposit): Promise<void> {
  try { await env.EVIDENCE.delete(`evidence/${d.id}/${d.filename}`); }
  catch (err) { console.log(`evidence: orphaned ${d.id}/${d.filename}: ${String(err)}`); }
}

// ===========================================================================
// POST /evidence/share — evidence.pb.js:149-224, ported.
//
// Called in the moment a text is about to go out and never speculatively: a
// window open before anybody needs it is exposure bought for nothing
// (brain/evidence.py:45-51 is written around exactly that, which is why
// `wants_photo` there is a callable and not a boolean).
//
// It was not routed at all on Cloudflare. brain/evidence.py:118-131 turned the
// 404 into "no picture on this text: the share door answered 404" and
// brain/worker.py:2734-2736 sent the confirmation with no media — the designed
// degradation, running every single time.
// ===========================================================================

/** evidence.pb.js:189-203. */
function publicBase(env: AssetEnv, request: Request): string {
  const pinned = String(env.ANTICIPY_PUBLIC_URL ?? "").trim();
  if (pinned) return pinned.replace(/\/+$/, "");
  const hook = String(env.ANTICIPY_TWILIO_WEBHOOK_URL ?? "").trim();
  const origin = /^https:\/\/[^/]+/.exec(hook);
  if (origin) return origin[0];
  // THE THIRD SOURCE IS NEW, and it is not the guess the oracle refused to
  // make. PocketBase sat behind a proxy and could not know its own public
  // name, so it demanded one be configured. A Worker on a custom domain gets
  // request.url as the URL the caller actually reached it on — this is the
  // service token's own request, arriving at the same host the brain reads
  // jobs from. Still https-only, so a local http rig gets the honest refusal
  // rather than a MediaUrl Twilio cannot fetch.
  const self = new URL(request.url);
  return self.protocol === "https:" ? self.origin : "";
}

export async function shareEvidence(request: Request, env: AssetEnv): Promise<Response> {
  const token = request.headers.get("X-Anticipy-Token") ?? "";
  // evidence.pb.js:162-164: getenv returns "" when unset and "" === "" for a
  // missing header too, which is how a token check becomes an open door on a
  // box where the variable was never set. The truthiness test IS the guard.
  if (!env.ANTICIPY_SERVICE_TOKEN || token !== env.ANTICIPY_SERVICE_TOKEN) {
    return json(403, { error: "forbidden" });
  }

  // AN ABSENT PICTURE IS AN ANSWER, NOT AN ERROR (:169-176). A MediaUrl that
  // 404s makes Twilio fail the WHOLE message, so a caller that cannot be given
  // a URL must be told so in a form it will act on — brain/evidence.py reads
  // `ok` and `reason` and drops the photo, keeping the words.
  const nothing = (reason: string) => json(200, { ok: false, reason, url: "", expires: "" });

  let body: Record<string, unknown> = {};
  try { body = await request.json<Record<string, unknown>>() ?? {}; } catch { body = {}; }
  const id = String(body.id ?? "").trim();
  if (!id) return nothing("no evidence was named");

  const rec = await env.DB.prepare(
    `SELECT "id", "image" FROM "evidence" WHERE "id" = ?1 LIMIT 1`,
  ).bind(id).first<{ id: string; image: string }>().catch(() => null);
  if (!rec) return nothing("that evidence is gone");
  const file = String(rec.image ?? "");
  if (!file) return nothing("that evidence has no picture");

  const base = publicBase(env, request);
  if (!base.startsWith("https://")) {
    return nothing("no https base url is configured for this backend");
  }

  const expires = new Date(Date.now() + SHARE_WINDOW_MS).toISOString();
  // A FRESH WINDOW GETS A FRESH CEILING (:208-212). Without the reset,
  // re-sharing a picture already fetched five times opens a window nothing can
  // come through, and the second text loses its photo for a reason no log names.
  const res = await env.DB.prepare(
    `UPDATE "evidence" SET "share_expires" = ?1, "fetches" = 0, "updated" = ?2 WHERE "id" = ?3`,
  ).bind(expires, pbNow(), id).run().catch(() => null);
  if (!res || !res.meta.changes) return nothing("could not open a share window");

  return json(200, {
    ok: true,
    url: `${base}/api/files/evidence/${rec.id}/${file}`,
    expires,
    fetches: SHARE_FETCH_LIMIT,
  });
}
