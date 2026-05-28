/**
 * CRM-side Google integration. Reuses the existing OAuth callback at
 * /api/auth/google/callback (which stores tokens in anticipy_google_tokens
 * by email). The CRM requests broader scopes than the engine: People API for
 * contacts plus userinfo for the email used as the storage key.
 */

const CLIENT_ID = process.env.GOOGLE_OAUTH_CLIENT_ID || "";
const CLIENT_SECRET = process.env.GOOGLE_OAUTH_CLIENT_SECRET || "";
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY || "";

export const CRM_GOOGLE_SCOPES = [
  "openid",
  "email",
  "profile",
  "https://www.googleapis.com/auth/contacts.readonly",
  "https://www.googleapis.com/auth/contacts.other.readonly",
  // Keep calendar.events so a CRM consent does not strip the engine's permission.
  "https://www.googleapis.com/auth/calendar.events",
];

export function getRedirectUri(): string {
  const base =
    process.env.NEXT_PUBLIC_SITE_URL ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000");
  return `${base}/api/auth/google/callback`;
}

export function getCrmGoogleAuthUrl(state = "crm"): string {
  if (!CLIENT_ID) throw new Error("GOOGLE_OAUTH_CLIENT_ID not set");
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: getRedirectUri(),
    response_type: "code",
    scope: CRM_GOOGLE_SCOPES.join(" "),
    access_type: "offline",
    include_granted_scopes: "true",
    prompt: "consent",
    state,
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export function googleConfigured(): boolean {
  return !!(CLIENT_ID && CLIENT_SECRET && ENCRYPTION_KEY);
}

import crypto from "crypto";
import { crmDb } from "./db";

function decrypt(text: string): string {
  const key = Buffer.from(ENCRYPTION_KEY, "hex");
  const [ivHex, encrypted] = text.split(":");
  const iv = Buffer.from(ivHex, "hex");
  const decipher = crypto.createDecipheriv("aes-256-cbc", key, iv);
  let decrypted = decipher.update(encrypted, "hex", "utf8");
  decrypted += decipher.final("utf8");
  return decrypted;
}

function encrypt(text: string): string {
  const key = Buffer.from(ENCRYPTION_KEY, "hex");
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv("aes-256-cbc", key, iv);
  let encrypted = cipher.update(text, "utf8", "hex");
  encrypted += cipher.final("hex");
  return iv.toString("hex") + ":" + encrypted;
}

export interface StoredTokens {
  access_token: string;
  refresh_token?: string;
  expiry_date?: number;
}

export async function getAnyStoredTokens(): Promise<{ email: string; tokens: StoredTokens } | null> {
  const { data } = await crmDb()
    .from("anticipy_google_tokens")
    .select("email, tokens_encrypted")
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!data) return null;
  try {
    const tokens = JSON.parse(decrypt(data.tokens_encrypted));
    return { email: data.email, tokens };
  } catch {
    return null;
  }
}

async function refreshAccessToken(refreshToken: string): Promise<StoredTokens> {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  });
  if (!res.ok) throw new Error(`Token refresh failed: ${res.status} ${await res.text()}`);
  const j = await res.json();
  return {
    access_token: j.access_token,
    refresh_token: refreshToken,
    expiry_date: Date.now() + (j.expires_in ?? 3600) * 1000,
  };
}

export async function getValidAccessToken(): Promise<{ accessToken: string; email: string }> {
  const stored = await getAnyStoredTokens();
  if (!stored) throw new Error("No Google tokens stored. Connect Google first from CRM Settings or Contacts.");
  const { email, tokens } = stored;
  if (tokens.expiry_date && Date.now() > tokens.expiry_date - 5 * 60 * 1000) {
    if (!tokens.refresh_token) throw new Error("Stored Google token has expired and no refresh token is available.");
    const fresh = await refreshAccessToken(tokens.refresh_token);
    await crmDb()
      .from("anticipy_google_tokens")
      .upsert(
        { email, tokens_encrypted: encrypt(JSON.stringify(fresh)), updated_at: new Date().toISOString() },
        { onConflict: "email" }
      );
    return { accessToken: fresh.access_token, email };
  }
  return { accessToken: tokens.access_token, email };
}

export interface PeopleConnection {
  name: string | null;
  email: string | null;
  phone: string | null;
  role: string | null;
}

export async function fetchAllPeople(): Promise<PeopleConnection[]> {
  const { accessToken } = await getValidAccessToken();
  const out: PeopleConnection[] = [];

  async function pull(url: string) {
    let pageToken: string | undefined;
    do {
      const u = new URL(url);
      u.searchParams.set("readMask", "names,emailAddresses,phoneNumbers,organizations");
      u.searchParams.set("pageSize", "1000");
      if (pageToken) u.searchParams.set("pageToken", pageToken);
      const res = await fetch(u.toString(), {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`Google People ${res.status}: ${t.slice(0, 200)}`);
      }
      const j = await res.json();
      const list = j.connections || j.otherContacts || [];
      for (const p of list) {
        const name: string | null =
          p?.names?.[0]?.displayName ?? p?.emailAddresses?.[0]?.value ?? null;
        const email: string | null = p?.emailAddresses?.[0]?.value ?? null;
        const phone: string | null = p?.phoneNumbers?.[0]?.value ?? null;
        const role: string | null =
          [p?.organizations?.[0]?.title, p?.organizations?.[0]?.name].filter(Boolean).join(" at ") || null;
        if (name || email) out.push({ name, email, phone, role });
      }
      pageToken = j.nextPageToken;
    } while (pageToken);
  }

  await pull("https://people.googleapis.com/v1/people/me/connections");
  // Other contacts (auto-saved from sent emails). Some accounts have neither
  // scope granted; ignore failures here so the main connections still import.
  try {
    await pull("https://people.googleapis.com/v1/otherContacts");
  } catch {
    // ignore
  }
  return out;
}
