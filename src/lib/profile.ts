import bcrypt from "bcryptjs";

/**
 * Shared helpers for the per-user Anticipy profile (assistant_name +
 * PIN + phone + per-user daily caps), used by both the onboarding API
 * and the Twilio voice/relay routes.
 *
 * Three responsibilities:
 *   1. Sanitize untrusted user input that ends up in TTS (no SSML
 *      injection, length cap, allowed charset).
 *   2. Hash and verify PINs with bcrypt. The plaintext PIN is never
 *      stored or logged.
 *   3. Validate E.164 phone format for the inbound caller match.
 *
 * Kept in src/lib (not co-located with a route) because the shared
 * Twilio voice handler and the onboarding profile route both call into
 * it.
 */

const ASSISTANT_NAME_MAX = 24;
const ASSISTANT_NAME_PATTERN = /^[A-Za-z0-9 ]+$/;
const PIN_PATTERN = /^[0-9]{4,8}$/;
const E164_PATTERN = /^\+[1-9]\d{6,14}$/;
const BCRYPT_ROUNDS = 12;
const DAILY_WINDOW_MS = 24 * 60 * 60 * 1000;

export interface SanitizeNameResult {
  ok: boolean;
  name?: string;
  error?: string;
}

/**
 * Restrict the user-chosen assistant name to a safe subset before it
 * is ever interpolated into a Twilio <Say> or an SMS body. Alphanumeric
 * plus spaces only blocks `<`, `>`, `&`, quotes, and the SSML control
 * characters. The 24 char cap keeps it short enough to fit a TTS
 * prompt without overflowing the audible greeting.
 */
export function sanitizeAssistantName(input: unknown): SanitizeNameResult {
  if (typeof input !== "string") {
    return { ok: false, error: "assistant_name must be a string" };
  }
  const trimmed = input.trim().replace(/\s+/g, " ");
  if (trimmed.length === 0) {
    return { ok: false, error: "assistant_name must not be empty" };
  }
  if (trimmed.length > ASSISTANT_NAME_MAX) {
    return {
      ok: false,
      error: `assistant_name must be ${ASSISTANT_NAME_MAX} characters or fewer`,
    };
  }
  if (!ASSISTANT_NAME_PATTERN.test(trimmed)) {
    return {
      ok: false,
      error:
        "assistant_name must be alphanumeric plus spaces only (no punctuation)",
    };
  }
  return { ok: true, name: trimmed };
}

export interface ValidatePinResult {
  ok: boolean;
  pin?: string;
  error?: string;
}

/**
 * PIN must be 4 to 8 digits. Anything longer is impractical to type on
 * a DTMF keypad during an inbound call; anything shorter is trivially
 * brute-forced over the public number.
 */
export function validatePin(input: unknown): ValidatePinResult {
  if (typeof input !== "string") {
    return { ok: false, error: "pin must be a string of digits" };
  }
  const trimmed = input.trim();
  if (!PIN_PATTERN.test(trimmed)) {
    return {
      ok: false,
      error: "pin must be 4 to 8 numeric digits",
    };
  }
  return { ok: true, pin: trimmed };
}

export interface ValidatePhoneResult {
  ok: boolean;
  phone?: string;
  error?: string;
}

/**
 * E.164 only. The broker is US/Canada only for v1 so we additionally
 * require a +1 country code; non-+1 numbers are rejected here so an
 * onboarding mistake does not become an inbound-routing surprise.
 */
export function validatePhoneE164(input: unknown): ValidatePhoneResult {
  if (typeof input !== "string") {
    return { ok: false, error: "phone_e164 must be a string" };
  }
  const trimmed = input.trim();
  if (!E164_PATTERN.test(trimmed)) {
    return {
      ok: false,
      error: "phone_e164 must be E.164 format (for example +14155551212)",
    };
  }
  if (!trimmed.startsWith("+1")) {
    return {
      ok: false,
      error: "phone_e164 must be a +1 (US or Canada) number for v1",
    };
  }
  return { ok: true, phone: trimmed };
}

export async function hashPin(pin: string): Promise<string> {
  return bcrypt.hash(pin, BCRYPT_ROUNDS);
}

export async function verifyPin(pin: string, hash: string): Promise<boolean> {
  if (!hash) return false;
  try {
    return await bcrypt.compare(pin, hash);
  } catch {
    return false;
  }
}

export interface ProfileRow {
  id: string;
  assistant_name: string;
  pin_hash: string | null;
  pin_set_at: string | null;
  phone_e164: string | null;
  phone_verified_at: string | null;
  daily_voice_minutes_used: number;
  daily_voice_minutes_cap: number;
  daily_sms_count_used: number;
  daily_sms_count_cap: number;
  daily_window_started_at: string;
  created_at: string;
  updated_at: string;
}

export interface PublicProfile {
  id: string;
  assistant_name: string;
  has_pin: boolean;
  pin_set_at: string | null;
  phone_e164: string | null;
  phone_verified_at: string | null;
  caps: {
    daily_voice_minutes_used: number;
    daily_voice_minutes_cap: number;
    daily_sms_count_used: number;
    daily_sms_count_cap: number;
    daily_window_started_at: string;
  };
  created_at: string;
  updated_at: string;
}

/**
 * Strip the bcrypt hash before returning the row to the client. The
 * client only needs to know whether a PIN exists, never the hash.
 */
export function toPublicProfile(row: ProfileRow): PublicProfile {
  return {
    id: row.id,
    assistant_name: row.assistant_name,
    has_pin: !!row.pin_hash,
    pin_set_at: row.pin_set_at,
    phone_e164: row.phone_e164,
    phone_verified_at: row.phone_verified_at,
    caps: {
      daily_voice_minutes_used: Number(row.daily_voice_minutes_used) || 0,
      daily_voice_minutes_cap: Number(row.daily_voice_minutes_cap) || 0,
      daily_sms_count_used: Number(row.daily_sms_count_used) || 0,
      daily_sms_count_cap: Number(row.daily_sms_count_cap) || 0,
      daily_window_started_at: row.daily_window_started_at,
    },
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

/**
 * Decide whether the user's daily counters should reset before the
 * caller increments them. The window resets if 24h has elapsed since
 * daily_window_started_at. Returns the new window-start to write, or
 * null if the existing window is still active.
 */
export function shouldResetWindow(startedAt: string | null | undefined): string | null {
  if (!startedAt) {
    return new Date().toISOString();
  }
  const startedMs = Date.parse(startedAt);
  if (!Number.isFinite(startedMs)) {
    return new Date().toISOString();
  }
  if (Date.now() - startedMs >= DAILY_WINDOW_MS) {
    return new Date().toISOString();
  }
  return null;
}

export const PROFILE_CONSTANTS = {
  ASSISTANT_NAME_MAX,
  DAILY_WINDOW_MS,
};
