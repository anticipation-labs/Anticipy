/**
 * CLI tool to inspect anticipy_user_profile rows.
 *
 * Run: npx tsx scripts/inspect_profiles.ts                # all profiles
 *      npx tsx scripts/inspect_profiles.ts <user_id>      # one profile
 *      npx tsx scripts/inspect_profiles.ts --recent       # last 7d only
 *
 * Useful when:
 *   - debugging why the meta-monitor is/isn't biasing extractions
 *   - sanity-checking that drift_alerts fire on heavy-rejecter users
 *   - confirming the throttle is working in production traffic
 *
 * Reads only — no writes. service-role-only table; reads via env-set
 * SUPABASE_SERVICE_ROLE_KEY.
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

interface Profile {
  user_id: string;
  style_summary: string;
  common_accepts: unknown;
  common_rejects: unknown;
  drift_alerts: unknown;
  signal_count: number;
  updated_at: string;
}

function summarize(profile: Profile, opts: { full?: boolean } = {}) {
  const ageMs = Date.now() - new Date(profile.updated_at).getTime();
  const ageHr = (ageMs / 3_600_000).toFixed(1);
  const accepts = Array.isArray(profile.common_accepts) ? profile.common_accepts : [];
  const rejects = Array.isArray(profile.common_rejects) ? profile.common_rejects : [];
  const alerts = Array.isArray(profile.drift_alerts) ? profile.drift_alerts : [];

  console.log("─".repeat(72));
  console.log(`user_id:       ${profile.user_id}`);
  console.log(`signal_count:  ${profile.signal_count}`);
  console.log(`updated:       ${profile.updated_at}  (${ageHr}h ago)`);
  console.log(`accepts:       ${accepts.length} entries`);
  console.log(`rejects:       ${rejects.length} entries`);
  console.log(`drift_alerts:  ${alerts.length}${alerts.length ? " ⚠️" : ""}`);

  const styleSnippet = (profile.style_summary || "").slice(0, opts.full ? 2000 : 200);
  console.log(`\nstyle:`);
  console.log(`  ${styleSnippet}${profile.style_summary?.length > 200 && !opts.full ? "..." : ""}`);

  if (opts.full || alerts.length) {
    if (accepts.length) {
      console.log(`\nUSUALLY ACCEPTS:`);
      for (const a of accepts.slice(0, 5)) {
        const o = a as { action_type?: string; summary_pattern?: string; why?: string };
        console.log(`  + ${o.action_type ?? "?"} / ${o.summary_pattern ?? "?"}`);
        console.log(`    ${o.why ?? ""}`);
      }
    }
    if (rejects.length) {
      console.log(`\nUSUALLY REJECTS:`);
      for (const a of rejects.slice(0, 5)) {
        const o = a as { action_type?: string; summary_pattern?: string; why?: string };
        console.log(`  - ${o.action_type ?? "?"} / ${o.summary_pattern ?? "?"}`);
        console.log(`    ${o.why ?? ""}`);
      }
    }
    if (alerts.length) {
      console.log(`\n⚠️  DRIFT ALERTS:`);
      for (const a of alerts.slice(0, 5)) {
        const o = a as { kind?: string; evidence?: string };
        console.log(`  ! ${o.kind ?? "?"}`);
        console.log(`    ${o.evidence ?? ""}`);
      }
    }
  }
}

async function main() {
  const args = process.argv.slice(2);
  const userArg = args.find((a) => !a.startsWith("--"));
  const recentOnly = args.includes("--recent");

  let q = supabase
    .from("anticipy_user_profile")
    .select("*")
    .order("updated_at", { ascending: false });
  if (userArg) q = q.eq("user_id", userArg);
  if (recentOnly) {
    const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
    q = q.gte("updated_at", sevenDaysAgo);
  }
  const { data, error } = await q;
  if (error) {
    console.error("query failed:", error.message);
    process.exit(1);
  }
  const rows = (data ?? []) as Profile[];
  if (!rows.length) {
    console.log("no profiles found.");
    return;
  }
  console.log(`${rows.length} profile${rows.length === 1 ? "" : "s"}\n`);
  for (const r of rows) summarize(r, { full: rows.length === 1 });

  // Roll-up stats
  const totalAlerts = rows.reduce((acc, r) => {
    const a = Array.isArray(r.drift_alerts) ? r.drift_alerts : [];
    return acc + a.length;
  }, 0);
  console.log("\n" + "═".repeat(72));
  console.log(`SUMMARY: ${rows.length} profiles, ${totalAlerts} drift alerts total`);
}

main().catch((e) => { console.error(e); process.exit(1); });
