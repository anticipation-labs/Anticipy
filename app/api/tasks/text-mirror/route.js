import { getPhaseZeroState, updateTaskState } from "../../../../lib/phase-zero/store";

const VALID_STATUS = new Set(["coming_soon", "queued", "sent", "delivered", "failed"]);

export async function GET() {
  const tasks = await getPhaseZeroState("tasks");
  return Response.json({ textMirror: tasks.textMirror || {} });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const taskId = String(body.taskId || "").trim();
  const status = VALID_STATUS.has(body.status) ? body.status : "coming_soon";
  if (!taskId) {
    return Response.json({ error: "missing_task", message: "Pick a task before updating text status." }, { status: 400 });
  }
  const tasks = await getPhaseZeroState("tasks");
  const textMirror = {
    ...(tasks.textMirror || {}),
    [taskId]: { status, updatedAt: new Date().toISOString() },
  };
  await updateTaskState({ textMirror });
  return Response.json({ textMirror, taskId, status });
}
