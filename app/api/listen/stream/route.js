// Next.js doesn't natively support WebSocket upgrade in API routes.
// The browser connects directly to the engine's WebSocket at :8787.
// This route provides the engine URL so the frontend doesn't hardcode it.
export async function GET() {
  const engineUrl = process.env.ANTICIPY_ENGINE_URL || "http://127.0.0.1:8787";
  // Convert http to ws for WebSocket
  const wsUrl = engineUrl.replace(/^http/, "ws") + "/listen/stream";
  return Response.json({ ws_url: wsUrl });
}
