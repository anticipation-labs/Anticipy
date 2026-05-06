/**
 * Client-side helpers for the picked CRM user identity. Stored in localStorage
 * because the spec requires no real auth and lets anyone who knows the password
 * pick which user they are. The picked identity is sent on every fetch as the
 * `x-crm-user-id` header.
 */
"use client";

const KEY = "anticipy_crm_user";

export type PickedUser = { id: string; name: string };

export function readPickedUser(): PickedUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.id !== "string" || typeof parsed.name !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writePickedUser(u: PickedUser): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(u));
}

export function clearPickedUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}

export async function crmFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const u = readPickedUser();
  const headers = new Headers(init?.headers);
  if (u) {
    headers.set("x-crm-user-id", u.id);
    headers.set("x-crm-user-name", u.name);
  }
  return fetch(input, { ...init, headers });
}
