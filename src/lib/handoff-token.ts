/**
 * Pure logic for the one-time deep-link handoff token flow (US-008).
 *
 * The Next.js routes wire these helpers to a real Supabase-backed store;
 * tests inject an in-memory store so the round-trip can be exercised
 * without a live database.
 */
import crypto from "node:crypto";

export const HANDOFF_TOKEN_TTL_SECONDS = 300;
export const HANDOFF_DEEP_LINK_SCHEME = "anticipy";

export interface HandoffRow {
  id: string;
  user_id: string;
  access_token: string;
  refresh_token: string;
  expires_at: string;
  consumed_at: string | null;
}

export interface HandoffStore {
  insert(row: Omit<HandoffRow, "consumed_at">): Promise<void>;
  findById(id: string): Promise<HandoffRow | null>;
  markConsumed(id: string, consumed_at: string): Promise<void>;
}

export function generateHandoffTokenId(
  bytes: (n: number) => Buffer = (n) => crypto.randomBytes(n)
): string {
  return bytes(32).toString("hex");
}

export function buildHandoffDeepLink(token: string): string {
  return `${HANDOFF_DEEP_LINK_SCHEME}://session?token=${token}`;
}

export interface MintInput {
  store: HandoffStore;
  user_id: string;
  access_token: string;
  refresh_token: string;
  now?: () => Date;
  generate?: () => string;
}

export interface MintResult {
  token: string;
  deep_link: string;
  expires_at: string;
}

export async function mintHandoffToken(input: MintInput): Promise<MintResult> {
  const now = input.now ? input.now() : new Date();
  const generate = input.generate ?? (() => generateHandoffTokenId());
  const token = generate();
  const expires_at = new Date(
    now.getTime() + HANDOFF_TOKEN_TTL_SECONDS * 1000
  ).toISOString();
  await input.store.insert({
    id: token,
    user_id: input.user_id,
    access_token: input.access_token,
    refresh_token: input.refresh_token,
    expires_at,
  });
  return {
    token,
    deep_link: buildHandoffDeepLink(token),
    expires_at,
  };
}

export type ExchangeResult =
  | {
      kind: "ok";
      access_token: string;
      refresh_token: string;
      user_id: string;
    }
  | { kind: "not_found" }
  | { kind: "gone"; reason: "consumed" | "expired" };

export interface ExchangeInput {
  store: HandoffStore;
  token: string;
  now?: () => Date;
}

export async function exchangeHandoffToken(
  input: ExchangeInput
): Promise<ExchangeResult> {
  const now = input.now ? input.now() : new Date();
  const row = await input.store.findById(input.token);
  if (!row) return { kind: "not_found" };
  if (row.consumed_at) return { kind: "gone", reason: "consumed" };
  if (new Date(row.expires_at).getTime() < now.getTime()) {
    return { kind: "gone", reason: "expired" };
  }
  await input.store.markConsumed(input.token, now.toISOString());
  return {
    kind: "ok",
    access_token: row.access_token,
    refresh_token: row.refresh_token,
    user_id: row.user_id,
  };
}
