import { supabaseAdmin } from "./supabase-admin";
import crypto from "crypto";

const CLIENT_ID = process.env.GOOGLE_OAUTH_CLIENT_ID!;
const CLIENT_SECRET = process.env.GOOGLE_OAUTH_CLIENT_SECRET!;
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY!;

const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
const GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3";

function getRedirectUri() {
  const base =
    process.env.NEXT_PUBLIC_SITE_URL ||
    (process.env.VERCEL_URL
      ? `https://${process.env.VERCEL_URL}`
      : "http://localhost:3000");
  return `${base}/api/auth/google/callback`;
}

// Simple AES-256-CBC encryption for token storage
function encrypt(text: string): string {
  const key = Buffer.from(ENCRYPTION_KEY, "hex");
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv("aes-256-cbc", key, iv);
  let encrypted = cipher.update(text, "utf8", "hex");
  encrypted += cipher.final("hex");
  return iv.toString("hex") + ":" + encrypted;
}

function decrypt(text: string): string {
  const key = Buffer.from(ENCRYPTION_KEY, "hex");
  const [ivHex, encrypted] = text.split(":");
  const iv = Buffer.from(ivHex, "hex");
  const decipher = crypto.createDecipheriv("aes-256-cbc", key, iv);
  let decrypted = decipher.update(encrypted, "hex", "utf8");
  decrypted += decipher.final("utf8");
  return decrypted;
}

export function getGoogleAuthUrl(state?: string): string {
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: getRedirectUri(),
    response_type: "code",
    scope: "https://www.googleapis.com/auth/calendar.events",
    access_type: "offline",
    prompt: "consent",
  });
  if (state) params.set("state", state);
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

export async function exchangeCodeForTokens(code: string) {
  const res = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      code,
      grant_type: "authorization_code",
      redirect_uri: getRedirectUri(),
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Token exchange failed: ${res.status} ${err}`);
  }

  return res.json();
}

export async function storeTokens(
  email: string,
  tokens: { access_token: string; refresh_token?: string; expiry_date?: number }
) {
  const encrypted = encrypt(JSON.stringify(tokens));

  const { error } = await supabaseAdmin.from("anticipy_google_tokens").upsert(
    {
      email,
      tokens_encrypted: encrypted,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "email" }
  );

  if (error) throw new Error(`Failed to store tokens: ${error.message}`);
}

export async function getStoredTokens(
  email: string
): Promise<{ access_token: string; refresh_token: string; expiry_date: number } | null> {
  const { data, error } = await supabaseAdmin
    .from("anticipy_google_tokens")
    .select("tokens_encrypted")
    .eq("email", email)
    .single();

  if (error || !data) return null;

  try {
    return JSON.parse(decrypt(data.tokens_encrypted));
  } catch {
    return null;
  }
}

async function refreshAccessToken(refreshToken: string) {
  const res = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Token refresh failed: ${res.status} ${err}`);
  }

  return res.json();
}

async function getValidAccessToken(email: string): Promise<string> {
  const tokens = await getStoredTokens(email);
  if (!tokens) throw new Error("No Google tokens found. Please connect Google Calendar.");

  // Check if token is expired (with 5 min buffer)
  if (tokens.expiry_date && Date.now() > tokens.expiry_date - 300_000) {
    const refreshed = await refreshAccessToken(tokens.refresh_token);
    const newTokens = {
      access_token: refreshed.access_token,
      refresh_token: tokens.refresh_token, // Keep existing refresh token
      expiry_date: Date.now() + (refreshed.expires_in ?? 3600) * 1000,
    };
    await storeTokens(email, newTokens);
    return newTokens.access_token;
  }

  return tokens.access_token;
}

export interface CalendarEvent {
  title: string;
  startIso: string;
  endIso: string;
  description?: string;
  location?: string;
  attendees?: string[];
  timezone?: string;
}

export async function createCalendarEvent(
  email: string,
  event: CalendarEvent
): Promise<{ eventId: string; htmlLink: string }> {
  const accessToken = await getValidAccessToken(email);

  const body: Record<string, unknown> = {
    summary: event.title,
    start: {
      dateTime: event.startIso,
      timeZone: event.timezone || "America/Vancouver",
    },
    end: {
      dateTime: event.endIso,
      timeZone: event.timezone || "America/Vancouver",
    },
  };

  if (event.description) body.description = event.description;
  if (event.location) body.location = event.location;
  if (event.attendees?.length) {
    body.attendees = event.attendees.map((e) => ({ email: e }));
  }

  const res = await fetch(`${GOOGLE_CALENDAR_API}/calendars/primary/events`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Calendar event creation failed: ${res.status} ${err}`);
  }

  const data = await res.json();
  return { eventId: data.id, htmlLink: data.htmlLink };
}
