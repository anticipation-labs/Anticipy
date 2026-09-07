/**
 * POST /me/delete {confirm:"delete"}, authenticated as the account being erased.
 *
 * D1 has no foreign-key cascades. Cleanup must enumerate every product-owned
 * table, preserve other owners, remove external objects before losing their
 * handles, and durably request memory erasure before closing the account.
 * Client-provided legacy_uuid is a claim, never deletion authority.
 */
import { verifyToken, type AuthEnv } from "../pb/auth.ts";
import {
  connectionsFromEnv, requireOwner, type ComposioConnections, type ConnectionsEnv,
} from "../connections/provider.ts";

export interface AccountErasureEnv extends AuthEnv, ConnectionsEnv {
  EVIDENCE?: Pick<R2Bucket, "delete">;
}
type ErasureProvider = Pick<ComposioConnections, "connections" | "disconnect">;

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json" },
});
function pbId(): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  return [...crypto.getRandomValues(new Uint8Array(15))]
    .map((b) => alphabet[b % alphabet.length]).join("");
}

// Canonical identity column plus the optional older column. Legacy matches
// cover only unclaimed rows naming THIS server-issued ID; a supplied UUID must
// first be assigned an owner_ref by a verified migration, never by this route.
export const ACCOUNT_TABLES = [
  ["jobs", "owner_ref", "owner"],
  ["segments", "owner_ref", "owner"],
  ["agents", "owner_ref", "owner"],
  ["owner_profile", "owner_ref", "owner_id"],
  ["pendants", "owner_ref", "owner"],
  ["agent_llm_audit", "owner_ref", null],
  ["agent_audit_sessions", "owner_ref", null],
  ["evidence", "owner_ref", null],
  ["events", "owner_ref", null],
  ["password_resets", "owner", null],
  ["connect_codes", "user_id", null],
  ["connect_links", "user_id", null],
  ["connect_nudges", "user_id", null],
  ["app_usage_signals", "user_id", null],
  ["connections", "user_id", null],
] as const;

export async function accountDelete(
  req: Request, env: AccountErasureEnv, provider?: ErasureProvider,
): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return json(401, { ok: false, message: "Sign in first." });
  if (auth.claims.collectionName !== "owners") {
    return json(403, { ok: false, message: "Only an account can delete itself." });
  }
  let body: Record<string, unknown> = {};
  try { body = await req.json() as Record<string, unknown>; } catch { /* refused below */ }
  if (body?.confirm !== "delete") return json(400, {
    ok: false, message: 'Send {"confirm":"delete"} to confirm. This cannot be undone.',
  });
  const ref = String(auth.claims.id || "").trim();
  if (!ref) return json(400, { ok: false, message: "No account on that token." });
  return eraseVerifiedOwner(ref, env, provider);
}

/** Call only after the public account token or internal operator identity
 * proof has established the exact canonical owner. Never accept a legacy UUID. */
export async function eraseVerifiedOwner(ref: string, env: AccountErasureEnv, provider?: ErasureProvider): Promise<Response> {
  const row = await env.DB.prepare("SELECT legacy_uuid FROM owners WHERE id = ?")
    .bind(ref).first<{ legacy_uuid: string }>();
  if (!row) return json(401, { ok: false, message: "Sign in first." });

  // Freeze the identity before external cleanup. Every product-owned table
  // enforces this in SQL, including writers authenticated before this request.
  // A failed cleanup keeps the fence and the authenticated retry path. The
  // memory consumer waits until the canonical account row is actually gone.
  const triggerNames = [...ACCOUNT_TABLES.map(([table]) => table), "owners"]
    .flatMap(table => ["insert", "update"].map(op => `erasure_fence_${table}_${op}`));
  try {
    const fence = await env.DB.prepare(
      `SELECT count(*) AS n FROM sqlite_master WHERE type = 'trigger' AND name IN (${triggerNames.map(() => "?").join(",")})`,
    ).bind(...triggerNames).first<{n: number}>();
    if (fence?.n !== triggerNames.length) throw new Error("erasure fence migration missing");
    // The migrated production purge ledger has no PocketBase autodates.
    // requested_at and purged_at are its authoritative timestamps.
    await env.DB.prepare(
      `INSERT INTO purges (id, owner_ref, legacy_uuid, requested_at, memory_purged)
       SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM purges WHERE owner_ref = ?)`,
    ).bind(pbId(), ref, row.legacy_uuid || "", new Date().toISOString(), 0, ref).run();
  } catch {
    return json(503, { ok: false, account_deleted: false,
      message: "Account cleanup could not start. Please try again shortly." });
  }

  // Discover at the provider even when the local cache is empty. Otherwise a
  // consent completed immediately before local reconciliation would survive.
  // On a partial failure the account and local handles survive for retry.
  const revokeAtProvider: string[] = [];
  try {
    const cached = await env.DB.prepare("SELECT connected_account_id FROM connections WHERE user_id = ?")
      .bind(ref).all<{ connected_account_id: string }>();
    if (provider || env.COMPOSIO_API_KEY?.trim()) {
      const remote = provider ?? connectionsFromEnv(env);
      const owner = requireOwner("account erasure", ref);
      for (const connection of await remote.connections(owner)) {
        const result = await remote.disconnect(owner, connection.connected_account_id);
        if (!result.deleted) throw new Error("connected account deletion incomplete");
        if (result.revokeUnavailable) revokeAtProvider.push(connection.toolkit);
      }
    } else if (cached.results.length) {
      throw new Error("connected accounts exist but provider cleanup is unconfigured");
    }
  } catch {
    return json(503, {
      ok: false, account_deleted: false,
      message: "I couldn't finish removing your connected accounts. Cleanup is paused; sign in again to retry deletion.",
    });
  }

  // Delete objects while metadata is still available. An unavailable bucket
  // must leave a retryable account, not an unfindable orphaned photograph.
  try {
    const pictures = await env.DB.prepare("SELECT id, image FROM evidence WHERE owner_ref = ?")
      .bind(ref).all<{ id: string; image: string }>();
    const keys = pictures.results.filter((p) => p.image)
      .map((p) => `evidence/${p.id}/${p.image}`);
    if (keys.length) {
      if (!env.EVIDENCE) throw new Error("evidence bucket unavailable");
      for (let offset = 0; offset < keys.length; offset += 1000) {
        await env.EVIDENCE.delete(keys.slice(offset, offset + 1000));
      }
    }
  } catch {
    return json(503, {
      ok: false, account_deleted: false,
      message: "I couldn't finish removing your saved pictures. Cleanup is paused; sign in again to retry deletion.",
    });
  }

  const statements = ACCOUNT_TABLES.map(([table, field, legacy]) => {
    const sql = `DELETE FROM "${table}" WHERE "${field}" = ?`
      + (legacy ? ` OR ("owner_ref" = '' AND "${legacy}" = ?)` : "");
    return env.DB.prepare(sql).bind(...(legacy ? [ref, ref] : [ref]));
  });
  statements.push(env.DB.prepare("DELETE FROM owners WHERE id = ?").bind(ref));
  let results: D1Result[];
  try {
    // D1 batch closes local rows and the account together. The earlier purge
    // request deliberately survives rollback, keeping late writers fenced.
    results = await env.DB.batch(statements);
  } catch {
    return json(409, {
      ok: false, account_deleted: false, memory_purge: "waiting on the account closing",
      message: "Some cleanup may have completed, but I couldn't close your account. Please try again.",
    });
  }
  const deleted = Object.fromEntries(ACCOUNT_TABLES.map(([table], index) =>
    [table, results[index].meta.changes ?? 0]));
  return json(200, {
    ok: true, account_deleted: true, memory_purge: "scheduled", deleted,
    provider_revocation_required: [...new Set(revokeAtProvider)],
    message: revokeAtProvider.length
      ? "Account deleted. Some apps also require you to remove Anticipy's access in their account settings."
      : "Deleted.",
  });
}
