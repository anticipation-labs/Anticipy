/** Drain closed owners' current memory and per-owner archive objects. */
export interface PurgeEnv {
  DB: D1Database;
  OWNER_STATE: Pick<R2Bucket, "list" | "delete">;
  STATE_ARCHIVE: Pick<R2Bucket, "list" | "delete">;
  ANTICIPY_STATE_R2_PREFIX?: string;
  ANTICIPY_STATE_BACKUP_PREFIX?: string;
}
interface Purge { id: string; owner_ref: string }

export async function removePrefix(bucket: Pick<R2Bucket, "list" | "delete">, prefix: string): Promise<void> {
  const seen = new Set<string>();
  let cursor: string | undefined;
  for (;;) {
    const page = await bucket.list({ prefix, cursor, limit: 1000 });
    const keys = page.objects.map((object) => object.key);
    if (keys.some((key) => !key.startsWith(prefix))) throw new Error("bucket returned a foreign owner key");
    if (keys.length) await bucket.delete(keys);
    if (!page.truncated) break;
    if (!page.cursor || seen.has(page.cursor)) throw new Error("bucket pagination did not advance");
    seen.add(page.cursor);
    cursor = page.cursor;
  }
  // A successful request is not the assertion. Read the resulting state.
  if ((await bucket.list({ prefix, limit: 1 })).objects.length) {
    throw new Error("owner objects remain after deletion");
  }
}

async function requireLegacyArchiveReview(bucket: Pick<R2Bucket, "list">, prefix: string): Promise<void> {
  let cursor: string | undefined;
  const seen = new Set<string>();
  for (;;) {
    const page = await bucket.list({ prefix, cursor, limit: 1000 });
    // Before per-owner archives shipped, the shared root contained multiple
    // people's memories. Removing a current prefix cannot prove those erased.
    // Never delete another owner's archive to make a completion count pass.
    if (page.objects.some(object => object.key.startsWith(prefix)
        && !object.key.slice(prefix.length).includes("/"))) {
      throw new Error("shared legacy archives require selective erasure review");
    }
    if (!page.truncated) return;
    if (!page.cursor || seen.has(page.cursor)) throw new Error("legacy archive inventory did not advance");
    seen.add(page.cursor);
    cursor = page.cursor;
  }
}

export async function drainMemoryPurges(
  env: PurgeEnv, stopOwner: (ref: string) => Promise<void>,
): Promise<{ purged: number; failed: number }> {
  let purged = 0;
  let failed = 0;
  const rows = await env.DB.prepare(
    `SELECT p.id, p.owner_ref FROM purges p
       WHERE p.memory_purged = 0 AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.id = p.owner_ref)
       ORDER BY p.requested_at, p.id LIMIT 50`,
  ).all<Purge>();
  for (const row of rows.results) {
    const ref = row.owner_ref;
    if (!/^[a-z0-9]{15}$/.test(ref)) { failed++; continue; }
    try {
      if (!env.OWNER_STATE || !env.STATE_ARCHIVE) throw new Error("memory buckets are not configured");
      await stopOwner(ref);
      const current = (env.ANTICIPY_STATE_R2_PREFIX || "owners").replace(/^\/+|\/+$/g, "");
      const archive = (env.ANTICIPY_STATE_BACKUP_PREFIX || "worker").replace(/^\/+|\/+$/g, "");
      await removePrefix(env.OWNER_STATE, `${current}/${ref}/`);
      await removePrefix(env.STATE_ARCHIVE, `${archive}/${ref}/`);
      await requireLegacyArchiveReview(env.STATE_ARCHIVE, `${archive}/`);
      const now = new Date().toISOString();
      const result = await env.DB.prepare(
        `UPDATE purges SET memory_purged = 1, purged_at = ?, updated = ?
         WHERE id = ? AND NOT EXISTS (SELECT 1 FROM owners WHERE id = ?)`,
      ).bind(now, now.replace("T", " "), row.id, ref).run();
      if (result.meta.changes !== 1) throw new Error("purge completion was not recorded");
      purged++;
    } catch (error) {
      failed++;
      console.log(`memory erasure pending for ${ref}: ${String(error).slice(0, 200)}`);
    }
  }
  return { purged, failed };
}
