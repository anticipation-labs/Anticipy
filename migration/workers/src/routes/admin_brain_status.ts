/** Read the private fleet's last observation without reconciling it. */
export async function adminBrainStatus(request: Request, env: {
  ANTICIPY_INTERNAL_KEY?: string; BRAIN?: Fetcher;
}): Promise<Response> {
  if (request.method !== "GET") return new Response("Method Not Allowed", { status: 405 });
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return new Response("Unavailable", { status: 503 });
  const got = request.headers.get("X-Internal-Key") || "";
  let diff = got.length ^ key.length;
  for (let i = 0; i < key.length; i++) diff |= key.charCodeAt(i) ^ (got.charCodeAt(i) || 0);
  if (diff) return new Response("Unauthorized", { status: 401 });
  if (!env.BRAIN) return new Response("Unavailable", { status: 503 });
  return env.BRAIN.fetch(new Request("https://brain/health"));
}
