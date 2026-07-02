import { DEFAULT_PROFILE, getPhaseZeroState, updatePhaseZeroState } from "../../../lib/phase-zero/store";

export async function GET() {
  const profile = await getPhaseZeroState("profile");
  return Response.json({ profile: { ...DEFAULT_PROFILE, ...(profile || {}) } });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const profile = await updatePhaseZeroState("profile", body.profile || body);
  return Response.json({ profile });
}
