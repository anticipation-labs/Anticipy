export const ENGINE_URL = process.env.ANTICIPY_ENGINE_URL || "http://127.0.0.1:8787";
export const OWNER_SESSION_COOKIE = "anticipy_owner_session";

export function configuredOwnerToken() {
  return process.env.ANTICIPY_APP_OWNER_TOKEN || process.env.ANTICIPY_OWNER_API_TOKEN || "";
}

// OPEN MODE: single-user hosted app — the app is one person's (the owner's), so grant access with
// NO login. The multi-user per-user auth (Supabase + signed pairing) stays built and gated for when
// strangers use it. Enable by setting ANTICIPY_APP_OPEN=1 on the deploy.
export function appOpenMode() {
  const v = (process.env.ANTICIPY_APP_OPEN || "").toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

export function ownerAccessRequired() {
  if (appOpenMode()) return false;
  return Boolean(configuredOwnerToken());
}

// Build the headers for an engine call. When a signed-in Supabase user is behind the request,
// forward THEIR access token so the engine (owner_api_auth middleware) resolves
// request.state.user_id and routes to that user's OWN per-user core. Otherwise authenticate to
// the engine as the owner via the server owner token (owner / local / background paths).
//
// We send the user's bearer INSTEAD of the owner token — not both. The engine reads the
// x-anticipy-owner-token header FIRST when resolving the identity bearer, so sending both would
// make it treat the opaque owner token as the identity and collapse every caller back onto the
// owner core (the exact bug this fixes). A valid Supabase user still passes the engine's auth
// gate on its own (owner_api_auth authorizes on request.state.user_id).
export function engineHeaders(headers = {}, request = null) {
  const ownerToken = process.env.ANTICIPY_OWNER_API_TOKEN;
  const userBearer = incomingSupabaseBearer(request);
  if (userBearer) {
    return { ...headers, Authorization: `Bearer ${userBearer}` };
  }
  return {
    ...headers,
    ...(ownerToken ? { "x-anticipy-owner-token": ownerToken } : {}),
  };
}

// The incoming request's Supabase access token, or "" when the caller isn't a signed-in user.
// Only a JWT-shaped bearer (header.payload.sig -> two dots) that ISN'T the owner token counts;
// the owner authenticates with the opaque server owner token, never a per-user identity.
function incomingSupabaseBearer(request) {
  const token = bearerToken(request?.headers?.get?.("authorization"));
  if (!token || token.split(".").length !== 3) return "";
  const ownerToken = configuredOwnerToken();
  if (ownerToken && token === ownerToken) return "";
  return token;
}

function bearerToken(value) {
  const match = /^Bearer\s+(.+)$/i.exec(value || "");
  return match ? match[1].trim() : "";
}

function requestHost(request) {
  const h = request?.headers?.get?.("host") || request?.headers?.get?.("x-forwarded-host") || "";
  return h.split(":")[0].trim().toLowerCase();
}

// True only for a same-machine request. Used so a tokenless install stays frictionless for the
// single owner on their own Mac, while a PUBLIC deploy without a token is NOT wide open.
export function isLocalRequest(request) {
  const host = requestHost(request);
  return host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]" || host === "";
}

function cookieValue(request, name) {
  const nextCookie = request?.cookies?.get?.(name)?.value;
  if (nextCookie) return nextCookie;
  const raw = request?.headers?.get?.("cookie") || "";
  for (const part of raw.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}

export function ownerTokenMatches(value) {
  const token = configuredOwnerToken();
  return Boolean(token) && value === token;
}

export function ownerAccessGranted(request) {
  if (appOpenMode()) return true;
  // A signed-in Supabase user passes the site gate; the engine verifies the token against
  // Supabase and routes to that user's own per-user core (invalid tokens get the engine's 401).
  if (incomingSupabaseBearer(request)) return true;
  const token = configuredOwnerToken();
  if (!token) {
    // DEFAULT-SECURE: with no owner token configured, grant ONLY a local (same-machine) request.
    // A PUBLIC deploy without a token must never hand a stranger full owner control — deny until
    // ANTICIPY_APP_OWNER_TOKEN is set. (Closes the audit's "owner gate off by default" hole.)
    return isLocalRequest(request);
  }
  const headerToken = request?.headers?.get?.("x-anticipy-app-token") || bearerToken(request?.headers?.get?.("authorization"));
  return headerToken === token || cookieValue(request, OWNER_SESSION_COOKIE) === token;
}

export function ownerAccessStatus(request) {
  if (appOpenMode()) return { required: false, authenticated: true };
  if (incomingSupabaseBearer(request)) return { required: true, authenticated: true };
  const token = configuredOwnerToken();
  if (!token) {
    // no token: local is open (single-owner dev), public is locked-out (must configure a token)
    const local = isLocalRequest(request);
    return { required: !local, authenticated: local };
  }
  return { required: true, authenticated: ownerAccessGranted(request) };
}

export function requireOwnerRequest(request) {
  if (ownerAccessGranted(request)) return null;
  return Response.json(
    {
      error: "owner_auth_required",
      message: "Owner access is required for this Anticipy app.",
    },
    { status: 401 },
  );
}

export function ownerSessionCookie(value, maxAge = 60 * 60 * 24 * 7) {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${OWNER_SESSION_COOKIE}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${secure}`;
}

export function clearOwnerSessionCookie() {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${OWNER_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0${secure}`;
}

export async function engineRequest(path, options = {}, request = null) {
  const url = `${ENGINE_URL}${path}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: engineHeaders(
        {
          "content-type": "application/json",
          ...(options.headers || {}),
        },
        request,
      ),
      cache: "no-store",
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    return Response.json(data, { status: response.status });
  } catch (error) {
    return Response.json(
      {
        error: "engine_unreachable",
        message: `Could not reach Anticipy Engine at ${ENGINE_URL}`,
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  }
}

export async function privateEngineRequest(request, path, options = {}) {
  const denied = requireOwnerRequest(request);
  if (denied) return denied;
  // Forward the incoming request so a signed-in user's Supabase bearer reaches the engine and
  // routes to their own per-user core (engineHeaders); the owner path is unchanged.
  return engineRequest(path, options, request);
}
