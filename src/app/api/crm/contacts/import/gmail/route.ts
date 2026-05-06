/**
 * Pulls every Google contact via the People API (both the "connections" list
 * and "otherContacts" auto-saved from sent emails) and upserts them into
 * crm_contacts with source=gmail. Dedupes by lower(email).
 *
 * Reuses the existing /api/auth/google/callback OAuth flow that already
 * stores encrypted tokens in anticipy_google_tokens.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { fetchAllPeople, googleConfigured } from "@/lib/crm/google";
import { logAgentEvent } from "@/lib/crm/events";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  if (!googleConfigured()) {
    return NextResponse.json(
      {
        error: "Google OAuth is not configured on this deployment.",
        hint: "Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, ENCRYPTION_KEY.",
      },
      { status: 501 }
    );
  }

  let people;
  try {
    people = await fetchAllPeople();
  } catch (e: any) {
    return NextResponse.json(
      { error: e?.message || "Could not reach Google", hint: "Visit Settings to (re)connect Google." },
      { status: 502 }
    );
  }

  const db = crmDb();
  let inserted = 0;
  let updated = 0;
  let skipped = 0;

  // Pull existing contacts once and dedupe in memory.
  const { data: existing } = await db.from("crm_contacts").select("id, email, name");
  const byEmail = new Map<string, { id: string; name: string }>();
  for (const c of existing ?? []) {
    if ((c as any).email) byEmail.set(String((c as any).email).toLowerCase(), { id: (c as any).id, name: (c as any).name });
  }

  for (const p of people) {
    const email = p.email ? p.email.trim().toLowerCase() : null;
    const name = (p.name || p.email || "").trim();
    if (!name) {
      skipped += 1;
      continue;
    }
    if (email && byEmail.has(email)) {
      const ex = byEmail.get(email)!;
      const { error } = await db
        .from("crm_contacts")
        .update({
          name: name,
          phone: p.phone ?? null,
          role: p.role ?? null,
          source: "gmail",
        })
        .eq("id", ex.id);
      if (!error) updated += 1;
      continue;
    }
    const { error } = await db.from("crm_contacts").insert({
      name,
      email,
      phone: p.phone ?? null,
      role: p.role ?? null,
      source: "gmail",
    });
    if (error) {
      skipped += 1;
    } else {
      inserted += 1;
      if (email) byEmail.set(email, { id: "new", name });
    }
  }

  await logAgentEvent({
    agent_name: "manual",
    action: "contacts_import_gmail",
    summary: `Gmail import: ${inserted} new, ${updated} updated, ${skipped} skipped`,
    payload: { inserted, updated, skipped },
  });

  return NextResponse.json({ inserted, updated, skipped, total: people.length });
}
