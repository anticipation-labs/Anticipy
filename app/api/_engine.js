export const ENGINE_URL = process.env.ANTICIPY_ENGINE_URL || "http://127.0.0.1:8787";

export function engineHeaders(headers = {}) {
  const token = process.env.ANTICIPY_OWNER_API_TOKEN;
  return {
    ...headers,
    ...(token ? { "x-anticipy-owner-token": token } : {}),
  };
}

export async function engineRequest(path, options = {}) {
  const url = `${ENGINE_URL}${path}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: engineHeaders({
        "content-type": "application/json",
        ...(options.headers || {}),
      }),
      cache: "no-store",
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    return Response.json(data, { status: response.status });
  } catch (error) {
    return Response.json(
      {
        error: "engine_unreachable",
        message: `Could not reach Anticipy Engine at ${ENGINE_URL}`,
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  }
}
