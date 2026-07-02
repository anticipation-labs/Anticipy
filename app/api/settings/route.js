import { DEFAULT_SETTINGS, getPhaseZeroState, updatePhaseZeroState } from "../../../lib/phase-zero/store";

export async function GET() {
  const settings = await getPhaseZeroState("settings");
  return Response.json({ settings: { ...DEFAULT_SETTINGS, ...(settings || {}) } });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const settings = await updatePhaseZeroState("settings", body.settings || body);
  return Response.json({ settings });
}
