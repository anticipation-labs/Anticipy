/**
 * src/pb/schema.ts — the compile-time column map.
 *
 * GENERATED, NOT HAND-WRITTEN. `npm run gen:schema` (ARCHITECTURE.md §12, Phase 1)
 * parses migration/d1/schema.sql and emits this file. The excerpt below is
 * the shape it produces, filled in by hand for the four collections the
 * skeleton exercises, so the module type-checks before the generator exists.
 *
 * WHY IT MUST BE GENERATED: this map is the allowlist that decides which
 * identifiers may be concatenated into SQL (filter-dsl.ts `Compiler.column`).
 * A hand-maintained copy that drifts from schema.sql produces a 400 on a
 * legitimate client filter — which reads to the customer as "Anticipy is
 * down", the failure mode extension/background.js:527-533 documents.
 */
import type { CollectionSchema } from "../../filter-dsl.ts";

export interface CollectionDef {
  name: string;
  columns: CollectionSchema;
  /** Columns that are INTEGER 0/1 in D1 and booleans on the wire. */
  boolColumns: readonly string[];
  /**
   * Columns PocketBase would have filled itself. In D1 there is no autodate;
   * the Worker fills them. migration/d1/schema.sql, `autodate` in the type map.
   */
  createdColumn?: string;
  updatedColumn?: string;
}

const T = { type: "text" } as const;
const D = { type: "date" } as const;
const R = { type: "relation" } as const;
const N = { type: "number" } as const;
const B = { type: "bool" } as const;

export const COLLECTIONS: Readonly<Record<string, CollectionDef>> = {
  // --- schema.sql:262-317 -------------------------------------------------
  jobs: {
    name: "jobs",
    columns: {
      id: T, created: D, updated: D,
      owner_ref: R, owner: T, goal: T, status: T, lane: T,
      params: T, result: T, trace: T, attempts: N,
      claimed_by: T, claimed_at: D,
      workflow_id: T, workflow_version: N, workflow_state: T,
      lineage_key: T, scope_digest: T, effect_key: T,
      consequence: T, approval: T, receipt: T,
      lease_token: T, lease_until: D, effect_uncertain: B,
      watching_until: D,
      // Present on the LIVE collection and missing here: schema.ts was
      // written from the repo's migrations, which production has moved past.
      commitment_key: T, device_id: T, reconciliation: T, source_event_ids: T,
    },
    boolColumns: ["effect_uncertain"],
    createdColumn: "created", updatedColumn: "updated",
  },
  // --- schema.sql:318-351 -------------------------------------------------
  agents: {
    name: "agents",
    columns: {
      id: T, created: D, updated: D,
      agent_id: T, agent_token: T, pair_code: T,
      owner: T, owner_ref: R, paired: B, browser: T, last_seen: D,
      // Present on the LIVE collection and missing here: schema.ts was
      // written from the repo's migrations, which production has moved past.
      llm_calls: N, llm_hour: T, solve_calls: N, solve_hour: T,
    },
    boolColumns: ["paired"],
    createdColumn: "created", updatedColumn: "updated",
  },
  // --- schema.sql:217-261 -------------------------------------------------
  events: {
    name: "events",
    columns: {
      id: T, created: D, updated: D,
      owner_ref: R, kind: T, text: T, goal: T,
      speaker: T, addressee: T, importance: N, intent: T,
      source: T, spoken_at: T, capture_started_at: T, capture_ended_at: T,
      memory_purged: B,
      // Present on the LIVE collection and missing here: schema.ts was
      // written from the repo's migrations, which production has moved past.
      backfill: B, boot_id: T, decision: T, device_id: T, explicit: B, external_event_id: T, gap_before_ms: N, needs_confirmation: B, parent_line: T, segment: T, seq: N,
    },
    boolColumns: ["memory_purged"],
    createdColumn: "created", updatedColumn: "updated",
  },
  // --- schema.sql:419-474 -------------------------------------------------
  owners: {
    name: "owners",
    columns: {
      id: T, created: D, updated: D,
      email: { type: "email" }, emailVisibility: B, verified: B,
      password: T, tokenKey: T, phone: T, legacy_uuid: T,
    },
    boolColumns: ["emailVisibility", "verified"],
    createdColumn: "created", updatedColumn: "updated",
  },
};

/**
 * The seven collections a signed-in account may reach AT ALL.
 * guard.pb.js:416 — the regex is the allowlist, and anything else is
 * `403 {"error":"account is not allowed to access that collection"}`.
 */
export const ACCOUNT_REACHABLE = [
  "jobs", "events", "owner_profile", "segments", "agents", "pendants", "evidence",
] as const;

/**
 * Sort keys a caller may name. Same boundary as the filter identifiers: a
 * `sort` parameter is concatenated into an ORDER BY, so it is validated
 * against the column map and nothing else may pass.
 */
export function parseSort(spec: string, def: CollectionDef): { sql: string } {
  if (!spec) return { sql: "" };
  const parts: string[] = [];
  for (const raw of spec.split(",")) {
    const term = raw.trim();
    if (!term) continue;
    let dir = "ASC";
    let name = term;
    if (term.startsWith("-")) { dir = "DESC"; name = term.slice(1); }
    else if (term.startsWith("+")) { name = term.slice(1); }
    // PocketBase supports @random. Nothing in this tree sends it; refuse.
    if (!Object.prototype.hasOwnProperty.call(def.columns, name)) {
      throw new Error(`unknown sort field ${JSON.stringify(name)}`);
    }
    parts.push(`"${name.replace(/"/g, '""')}" ${dir}`);
  }
  return { sql: parts.length ? ` ORDER BY ${parts.join(", ")}` : "" };
}
