/**
 * Standalone smoke test for the meta-monitor.
 *
 * Exercises buildUserProfile + recallUserProfile against the live DB
 * (with a synthetic e2e-test- user_id) end-to-end:
 *
 *   1. Seed 5 fake preferences (3 accepts, 2 rejects)
 *   2. Call buildUserProfile — verify the row lands in anticipy_user_profile
 *      with non-empty style_summary and at least some accepts/rejects entries
 *   3. Call recallUserProfile — verify it returns a USER PROFILE block
 *   4. Wipe the test rows
 *
 * Run: npx tsx scripts/smoke_meta_monitor.ts
 *
 * Requires: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
 *           GOOGLE_API_KEY (Gemini) in env.
 */
// Lightweight env loader — must run BEFORE importing any module that
// captures process.env at load time (gemini.ts does). Static imports
// are hoisted, so we use dynamic import() below for the lib modules.
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
// buildUserProfile + recallUserProfile loaded dynamically inside main()
// so they pick up the env vars set above.

const TEST_USER_ID = "smoke-test-meta-monitor-uuid-fixed";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
);

const FIXTURES = [
  {
    signal: "accept",
    intent_summary: "Email Liam the meeting notes by end of day",
    action_type: "send_email",
    evidence_quote: "Email Liam the notes from this meeting before EOD",
    reasoning: "Wearer accepted email follow-ups when the recipient was named",
  },
  {
    signal: "accept",
    intent_summary: "Order coffee from the corner cafe",
    action_type: "order_food",
    evidence_quote: "Grab me a coffee on the way",
    reasoning: "Wearer accepts coffee orders without confirmation",
  },
  {
    signal: "reject",
    intent_summary: "Book flights to Tokyo for next month",
    action_type: "book_travel",
    evidence_quote: "Maybe we should plan a Tokyo trip",
    reasoning: "Wearer rejected — too speculative, no firm dates",
  },
  {
    signal: "reject",
    intent_summary: "Cancel the Friday yoga class",
    action_type: "cancel_booking",
    evidence_quote: "I might skip yoga on Friday",
    reasoning: "Wearer rejected — explicit retraction was a mistake intent",
  },
  {
    signal: "auto_proceed",
    intent_summary: "Add milk to the shopping list",
    action_type: "add_to_list",
    evidence_quote: "We need milk",
    reasoning: "Wearer let it auto-proceed — low-stakes default-yes",
  },
];

async function seed() {
  // Fresh slate first
  await supabase.from("anticipy_user_profile").delete().eq("user_id", TEST_USER_ID);
  await supabase.from("anticipy_preferences").delete().eq("user_id", TEST_USER_ID);

  const rows = FIXTURES.map((f) => ({
    user_id: TEST_USER_ID,
    ...f,
  }));
  const { error } = await supabase.from("anticipy_preferences").insert(rows);
  if (error) throw new Error(`seed failed: ${error.message}`);
  console.log(`[smoke] seeded ${rows.length} preferences`);
}

async function main() {
  await seed();

  // Dynamic import: load AFTER env vars are populated so gemini.ts
  // captures GOOGLE_API_KEY correctly.
  const { buildUserProfile, recallUserProfile } = await import(
    "../src/lib/meta-monitor"
  );

  console.log("[smoke] calling buildUserProfile…");
  await buildUserProfile(TEST_USER_ID);

  const { data: profile, error } = await supabase
    .from("anticipy_user_profile")
    .select("*")
    .eq("user_id", TEST_USER_ID)
    .single();

  if (error || !profile) {
    console.error("[smoke] FAIL: profile row not written:", error?.message);
    process.exit(1);
  }

  console.log("[smoke] profile written:");
  console.log("  style_summary:   ", profile.style_summary?.slice(0, 200));
  console.log("  signal_count:    ", profile.signal_count);
  console.log("  common_accepts:  ", JSON.stringify(profile.common_accepts).slice(0, 200));
  console.log("  common_rejects:  ", JSON.stringify(profile.common_rejects).slice(0, 200));
  console.log("  drift_alerts:    ", JSON.stringify(profile.drift_alerts).slice(0, 200));

  // Sanity asserts
  if (!profile.style_summary || profile.style_summary.length < 10) {
    console.error("[smoke] FAIL: style_summary too short");
    process.exit(1);
  }
  if (!Array.isArray(profile.common_accepts)) {
    console.error("[smoke] FAIL: common_accepts not an array");
    process.exit(1);
  }
  if (profile.signal_count !== FIXTURES.length) {
    console.error(`[smoke] FAIL: signal_count expected ${FIXTURES.length} got ${profile.signal_count}`);
    process.exit(1);
  }

  console.log("[smoke] calling recallUserProfile…");
  const block = await recallUserProfile(TEST_USER_ID);
  if (!block || !block.includes("USER PROFILE")) {
    console.error("[smoke] FAIL: recall returned empty or malformed block");
    console.error("  got:", block);
    process.exit(1);
  }
  console.log("[smoke] recall block (first 300 chars):");
  console.log(block.slice(0, 300));

  // Throttle test: a second build with no new signals should be quick
  // and shouldn't break anything.
  console.log("[smoke] calling buildUserProfile a SECOND time (throttle path)…");
  const t0 = Date.now();
  await buildUserProfile(TEST_USER_ID);
  const t1 = Date.now();
  console.log(`[smoke] second build took ${t1 - t0}ms`);

  // Cleanup
  await supabase.from("anticipy_user_profile").delete().eq("user_id", TEST_USER_ID);
  await supabase.from("anticipy_preferences").delete().eq("user_id", TEST_USER_ID);
  console.log("[smoke] cleaned up");
  console.log("[smoke] PASS");
}

main().catch((e) => {
  console.error("[smoke] threw:", e);
  process.exit(1);
});
