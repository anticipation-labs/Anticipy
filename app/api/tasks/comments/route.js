import { getPhaseZeroState, updateTaskState } from "../../../../lib/phase-zero/store";

export async function GET() {
  const tasks = await getPhaseZeroState("tasks");
  return Response.json({ comments: tasks.comments || {} });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const taskId = String(body.taskId || "").trim();
  const comment = String(body.comment || "").trim();
  if (!taskId) {
    return Response.json({ error: "missing_task", message: "Pick a task before commenting." }, { status: 400 });
  }
  const tasks = await getPhaseZeroState("tasks");
  const comments = {
    ...(tasks.comments || {}),
    [taskId]: comment,
  };
  await updateTaskState({ comments });
  return Response.json({ comments, taskId, comment });
}
