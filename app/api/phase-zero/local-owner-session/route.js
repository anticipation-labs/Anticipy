import { configuredOwnerToken, isLocalRequest, ownerSessionCookie } from "../../_engine";

export async function POST(request) {
  if (!isLocalRequest(request)) {
    return Response.json({ error: "local_only", message: "Local owner session is only available on this machine." }, { status: 403 });
  }

  const token = configuredOwnerToken();
  if (!token) {
    return Response.json({ authenticated: true, required: false, local: true });
  }

  return Response.json(
    { authenticated: true, required: true, local: true },
    { headers: { "set-cookie": ownerSessionCookie(token) } },
  );
}
