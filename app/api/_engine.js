export const ENGINE_URL = process.env.ANTICIPY_ENGINE_URL || "http://127.0.0.1:8787";
export const OWNER_SESSION_COOKIE = "anticipy_owner_session";

export function configuredOwnerToken() {
  return process.env.ANTICIPY_APP_OWNER_TOKEN || process.env.ANTICIPY_OWNER_API_TOKEN || "";
}

export function ownerAccessRequired() {
  return Boolean(configuredOwnerToken());
}

export function engineHeaders(headers = {}) {
  const token = process.env.ANTICIPY_OWNER_API_TOKEN;
  return {
    ...headers,
    ...(token ? { "x-anticipy-owner-token": token } : {}),
  };
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

export async function engineRequest(path, options = {}) {
  const url = `${ENGINE_URL}${path}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: engineHeaders({
        "content-type": "application/json",
        ...(options.headers || {}),
      }),
      cache: "no-store",
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    return Response.json(data, { status: response.status });
  } catch (error) {
    // Never leak the engine URL/port or the raw error to the surface (§4.7). The home
    // screen renders `message` directly; it must read as Donna, not a dev console.
    return Response.json(
      {
        error: "engine_unreachable",
        message: "I lost the thread for a moment. Try again.",
      },
      { status: 503 },
    );
  }
}

export async function privateEngineRequest(request, path, options = {}) {
  const denied = requireOwnerRequest(request);
  if (denied) return denied;
  return engineRequest(path, options);
}
