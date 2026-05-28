/**
 * Client-side helpers for the active CRM user.
 *
 * Identity now comes from the signed gate cookie, which the server reads on
 * every API call. This module just forwards the user info from the server
 * layout down to client pages and provides a fetch wrapper that keeps the
 * x-crm-user-* headers for any older route that still reads them.
 */
"use client";

import { createContext, useContext } from "react";

export type SessionUser = {
  id: string;
  name: string;
  email: string | null;
  is_admin: boolean;
};

const SessionContext = createContext<SessionUser | null>(null);

let cachedUser: SessionUser | null = null;

export function CrmSessionProvider({
  user,
  children,
}: {
  user: SessionUser;
  children: React.ReactNode;
}) {
  cachedUser = user;
  return <SessionContext.Provider value={user}>{children}</SessionContext.Provider>;
}

export function useCrmSession(): SessionUser {
  const u = useContext(SessionContext);
  if (!u) {
    throw new Error("useCrmSession used outside <CrmSessionProvider>");
  }
  return u;
}

export async function crmFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (cachedUser) {
    headers.set("x-crm-user-id", cachedUser.id);
    headers.set("x-crm-user-name", cachedUser.name);
  }
  return fetch(input, { ...init, headers });
}

/**
 * Back-compat snapshot for client components that read identity once.
 * Prefer useCrmSession() inside React; this is only here so existing pages
 * keep working without a refactor.
 */
export function readPickedUser(): { id: string; name: string } | null {
  if (!cachedUser) return null;
  return { id: cachedUser.id, name: cachedUser.name };
}

export type PickedUser = { id: string; name: string };
