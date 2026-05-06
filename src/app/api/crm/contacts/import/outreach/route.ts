/**
 * Pulls distinct recipients from anticipy_notifications (443+ rows of
 * outreach the engine has sent over SMS, voice, and email) and upserts them
 * into crm_contacts with source=outreach. The notifications table lives in
 * the same Supabase project, so this is a pure DB join, no external service.
 *
 * Recipient classification: email if the value contains "@", else phone.
 * Dedupes by lower(email) for emails, by digits-only for phones.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { logAgentEvent } from "@/lib/crm/events";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const db = crmDb();

  const { data, error } = await db
    .from("anticipy_notifications")
    .select("recipient, channel, sent_at")
    .order("sent_at", { ascending: false })
    .limit(5000);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  // Dedupe by normalized key, keeping most recent occurrence.
  const seen = new Map<string, { kind: "email" | "phone"; raw: string; lastAt: string }>();
  for (const row of data ?? []) {
    const r = String((row as any).recipient || "").trim();
    if (!r) continue;
    const isEmail = r.includes("@");
    const key = isEmail ? r.toLowerCase() : r.replace(/\D+/g, "");
    if (!key) continue;
    if (!seen.has(key)) {
      seen.set(key, { kind: isEmail ? "email" : "phone", raw: r, lastAt: (row as any).sent_at });
    }
  }

  // Pull existing crm_contacts to avoid double-insert.
  const { data: existing } = await db.from("crm_contacts").select("id, email, phone");
  const existingEmails = new Set<string>();
  const existingPhones = new Set<string>();
  for (const c of existing ?? []) {
    if ((c as any).email) existingEmails.add(String((c as any).email).toLowerCase());
    if ((c as any).phone) existingPhones.add(String((c as any).phone).replace(/\D+/g, ""));
  }

  let inserted = 0;
  let skipped = 0;

  for (const [key, v] of Array.from(seen.entries())) {
    if (v.kind === "email") {
      if (existingEmails.has(key)) {
        skipped += 1;
        continue;
      }
      const { error: insErr } = await db.from("crm_contacts").insert({
        name: v.raw,
        email: v.raw,
        source: "outreach",
        notes: `Imported from anticipy_notifications. Last contacted ${v.lastAt}.`,
      });
      if (insErr) skipped += 1;
      else {
        inserted += 1;
        existingEmails.add(key);
      }
    } else {
      if (existingPhones.has(key)) {
        skipped += 1;
        continue;
      }
      const { error: insErr } = await db.from("crm_contacts").insert({
        name: v.raw,
        phone: v.raw,
        source: "outreach",
        notes: `Imported from anticipy_notifications. Last contacted ${v.lastAt}.`,
      });
      if (insErr) skipped += 1;
      else {
        inserted += 1;
        existingPhones.add(key);
      }
    }
  }

  await logAgentEvent({
    agent_name: "manual",
    action: "contacts_import_outreach",
    summary: `Outreach import: ${inserted} new, ${skipped} skipped from ${seen.size} unique recipients`,
    payload: { inserted, skipped, unique: seen.size, sampled: data?.length ?? 0 },
  });

  return NextResponse.json({
    inserted,
    skipped,
    unique: seen.size,
    sampled: data?.length ?? 0,
  });
}
