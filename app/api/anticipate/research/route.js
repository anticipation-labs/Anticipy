import { ENGINE_URL, engineHeaders, requireOwnerRequest } from "../../_engine";

export async function POST(request) {
  const blocked = requireOwnerRequest(request);
  if (blocked) return blocked;

  const body = await request.json();
  const res = await fetch(`${ENGINE_URL}/anticipate/research`, {
    method: "POST",
    headers: engineHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
