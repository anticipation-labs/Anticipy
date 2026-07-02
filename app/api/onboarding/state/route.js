import { DEFAULT_ONBOARDING, getPhaseZeroState, updatePhaseZeroState } from "../../../../lib/phase-zero/store";

export async function GET() {
  const onboarding = await getPhaseZeroState("onboarding");
  return Response.json({ onboarding: { ...DEFAULT_ONBOARDING, ...(onboarding || {}) } });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const onboarding = await updatePhaseZeroState("onboarding", {
    ...(body.onboarding || body),
    lastUpdatedAt: new Date().toISOString(),
  });
  return Response.json({ onboarding });
}
