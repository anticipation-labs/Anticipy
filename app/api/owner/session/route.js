import {
  clearOwnerSessionCookie,
  ownerAccessRequired,
  ownerAccessStatus,
  ownerSessionCookie,
  ownerTokenMatches,
} from "../../_engine";

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

export async function GET(request) {
  return Response.json(ownerAccessStatus(request));
}

export async function POST(request) {
  if (!ownerAccessRequired()) {
    return Response.json({ required: false, authenticated: true });
  }

  const body = await readJson(request);
  const token = typeof body.token === "string" ? body.token : "";
  if (!ownerTokenMatches(token)) {
    return Response.json(
      {
        error: "owner_auth_failed",
        message: "Owner token was not accepted.",
      },
      { status: 401 },
    );
  }

  const response = Response.json({ required: true, authenticated: true });
  response.headers.append("set-cookie", ownerSessionCookie(token));
  return response;
}

export async function DELETE() {
  const response = Response.json({
    required: ownerAccessRequired(),
    authenticated: false,
  });
  response.headers.append("set-cookie", clearOwnerSessionCookie());
  return response;
}
