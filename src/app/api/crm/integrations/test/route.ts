/**
 * Smoke-tests external integrations from the Settings page.
 * Returns a per-integration status object. Does not throw; failures
 * surface as { ok: false, message } so the UI stays functional.
 */
import { NextResponse } from "next/server";
import { CRM_FILES_BUCKET, crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  const out = {
    supabase: await testSupabase(),
    storage: await testStorage(),
    gemini: await testGemini(),
    deepgram: await testDeepgram(),
    sendgrid: await testSendgrid(),
    resend: await testResend(),
  };
  return NextResponse.json(out);
}

async function testSupabase() {
  try {
    const { error } = await crmDb().from("crm_users").select("id").limit(1);
    return { ok: !error, message: error?.message };
  } catch (e: any) {
    return { ok: false, message: e?.message };
  }
}

async function testStorage() {
  try {
    const { error } = await crmDb().storage.from(CRM_FILES_BUCKET).list("", { limit: 1 });
    return { ok: !error, message: error?.message };
  } catch (e: any) {
    return { ok: false, message: e?.message };
  }
}

async function testGemini() {
  const key = process.env.GOOGLE_API_KEY || process.env.GEMINI_API_KEY;
  if (!key) return { ok: false, message: "No GOOGLE_API_KEY set" };
  try {
    const r = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`
    );
    return { ok: r.ok, message: r.ok ? undefined : `${r.status}` };
  } catch (e: any) {
    return { ok: false, message: e?.message };
  }
}

async function testDeepgram() {
  const key = process.env.DEEPGRAM_API_KEY;
  if (!key) return { ok: false, message: "No DEEPGRAM_API_KEY set" };
  try {
    const r = await fetch("https://api.deepgram.com/v1/projects", {
      headers: { Authorization: `Token ${key}` },
    });
    return { ok: r.ok, message: r.ok ? undefined : `${r.status}` };
  } catch (e: any) {
    return { ok: false, message: e?.message };
  }
}

async function testSendgrid() {
  const key = process.env.SENDGRID_API_KEY;
  if (!key) return { ok: false, message: "No SENDGRID_API_KEY set" };
  try {
    const r = await fetch("https://api.sendgrid.com/v3/scopes", {
      headers: { Authorization: `Bearer ${key}` },
    });
    return { ok: r.ok, message: r.ok ? undefined : `${r.status}` };
  } catch (e: any) {
    return { ok: false, message: e?.message };
  }
}

async function testResend() {
  const key = process.env.RESEND_API_KEY;
  if (!key) return { ok: false, message: "Not configured (using SendGrid)" };
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "GET",
      headers: { Authorization: `Bearer ${key}` },
    });
    // Resend's /emails route does not support GET; a 405 means auth was accepted.
    return { ok: r.status === 405 || r.ok, message: r.ok || r.status === 405 ? undefined : `${r.status}` };
  } catch (e: any) {
    return { ok: false, message: e?.message };
  }
}
