import { getPhaseZeroState, updateTaskState } from "../../../../lib/phase-zero/store";

const VALID_MODES = new Set(["priority", "newest", "needs_approval", "source"]);

export async function GET() {
  const tasks = await getPhaseZeroState("tasks");
  return Response.json({ sort: tasks.sort || { mode: "priority" } });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const mode = VALID_MODES.has(body.mode) ? body.mode : "priority";
  const sort = { mode };
  await updateTaskState({ sort });
  return Response.json({ sort });
}
