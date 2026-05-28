import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { clientIp, rateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const ALLOWED_MODELS = new Set([
  "deepseek/deepseek-v4-flash",
  "deepseek/deepseek-v4-pro",
  "moonshotai/kimi-k2.6",
]);

function clampNumber(value: unknown, fallback: number, min: number, max: number) {
  const n = typeof value === "number" && Number.isFinite(value) ? value : fallback;
  return Math.max(min, Math.min(max, n));
}

function safePayload(body: unknown) {
  if (!body || typeof body !== "object") return null;
  const src = body as Record<string, unknown>;
  const model = typeof src.model === "string" ? src.model : "deepseek/deepseek-v4-flash";
  if (!ALLOWED_MODELS.has(model)) return null;
  if (!Array.isArray(src.messages)) return null;

  const serialized = JSON.stringify(src.messages);
  // The local action engine sends one compressed browser screenshot
  // as a data URL for vision steps. Real desktop screenshots are
  // commonly 500-900 KB before base64, so a 120 KB cap made the
  // shipped broker reject the real Gmail/Calendar action path while
  // text-only onboarding still worked. Keep a hard ceiling, but make
  // it large enough for one normal vision frame.
  if (serialized.length > 2_000_000) return null;

  const payload: Record<string, unknown> = {
    model,
    messages: src.messages,
    max_tokens: clampNumber(src.max_tokens, 1024, 1, 4096),
    temperature: clampNumber(src.temperature, 0, 0, 1),
    reasoning:
      src.reasoning && typeof src.reasoning === "object"
        ? src.reasoning
        : { enabled: false },
  };
  if (src.response_format && typeof src.response_format === "object") {
    payload.response_format = src.response_format;
  }
  if (src.provider && typeof src.provider === "object") {
    payload.provider = src.provider;
  }
  return payload;
}

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const ipLimit = rateLimit(`model:ip:${clientIp(req)}`, 240, 60 * 60_000);
  const userLimit = rateLimit(`model:user:${user.id}`, 600, 60 * 60_000);
  if (!ipLimit.allowed || !userLimit.allowed) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey?.startsWith("sk-or-")) {
    return NextResponse.json(
      { error: "Anticipy model broker is not configured." },
      { status: 503 }
    );
  }

  const body = await req.json().catch(() => null);
  const payload = safePayload(body);
  if (!payload) {
    return NextResponse.json({ error: "Invalid model request" }, { status: 400 });
  }

  const upstream = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://anticipy.ai",
      "X-Title": "Anticipy Local Engine Broker",
    },
    body: JSON.stringify(payload),
  });

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
    },
  });
}
