/**
 * Backfill `embedding` on historical anticipy_intents rows that landed
 * in a terminal status before the episode-recall pipeline shipped.
 *
 * The live wire (embedAndStoreIntent in /api/engine/confirm and
 * /api/engine/auto-proceed) only embeds NEW terminal intents going
 * forward. Episode RAG only retrieves rows that have been embedded —
 * so any per-user history written before this script runs is invisible
 * to recallSimilarEpisodes(). One pass of this script seeds the past.
 *
 * Idempotent. Safe to interrupt and resume — the WHERE clause skips
 * rows that already have an embedding. A second-call collision with
 * the live wire is harmless because embedAndStoreIntent's UPDATE has
 * an `.is("embedding", null)` guard.
 *
 * Run:
 *   npx tsx scripts/backfill_episode_embeddings.ts             # dry-run
 *   npx tsx scripts/backfill_episode_embeddings.ts --apply     # actually write
 *   npx tsx scripts/backfill_episode_embeddings.ts --apply --limit 50
 *
 * Cost: ~$0.0 on Gemini's free tier; the only real "cost" is one HTTPS
 * round-trip per intent. At ~1500 RPM free-tier ceiling we can chew
 * through 255 rows in well under 30s. We sleep 100ms between calls
 * just to stay polite under the rate limit.
 */
import { readFileSync, existsSync } from "fs";
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) {
      process.env[m[1]] = m[2].replace(/^"|"$/g, "");
    }
  }
}

import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
);

const TERMINAL = ["confirmed", "rejected", "executed", "failed", "auto_proceeded"];
const SLEEP_MS = 100;

async function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const args = process.argv.slice(2);
  const apply = args.includes("--apply");
  const limit = (() => {
    const i = args.indexOf("--limit");
    if (i >= 0 && args[i + 1]) return parseInt(args[i + 1], 10);
    return 1000;
  })();

  console.log(
    `Mode: ${apply ? "APPLY (will write embeddings)" : "DRY-RUN (count only)"}`
  );
  console.log(`Limit: ${limit}`);

  const { data, error, count } = await supabase
    .from("anticipy_intents")
    .select("id, action_type, summary_for_user, evidence_quote, status", { count: "exact" })
    .in("status", TERMINAL)
    .is("embedding", null)
    .limit(limit);

  if (error) {
    console.error("query failed:", error.message);
    process.exit(1);
  }

  const rows = data ?? [];
  console.log(`Found ${count ?? rows.length} terminal intents without an embedding.`);
  console.log(`This run will process ${rows.length}.`);

  if (!apply) {
    console.log("Dry-run mode — pass --apply to actually embed.");
    return;
  }

  // Dynamic import after env is set so gemini.ts captures the key.
  const { embedAndStoreIntent } = await import("../src/lib/episode-recall");

  let ok = 0;
  let skipped = 0;
  let failed = 0;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    process.stdout.write(`[${i + 1}/${rows.length}] ${r.id.slice(0, 8)}… `);
    try {
      await embedAndStoreIntent(r.id);
      // Verify it was written
      const { data: after } = await supabase
        .from("anticipy_intents")
        .select("embedding")
        .eq("id", r.id)
        .single();
      if (after?.embedding) {
        process.stdout.write("✓\n");
        ok += 1;
      } else {
        process.stdout.write("skip\n");
        skipped += 1;
      }
    } catch (err) {
      process.stdout.write(`fail (${err instanceof Error ? err.message.slice(0, 60) : "?"})\n`);
      failed += 1;
    }
    await sleep(SLEEP_MS);
  }

  console.log(
    `\nDone. ok=${ok} skipped=${skipped} failed=${failed} total=${rows.length}`
  );
}

main().catch((e) => { console.error(e); process.exit(1); });
