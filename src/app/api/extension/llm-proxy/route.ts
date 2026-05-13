import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * POST /api/extension/llm-proxy — PERMANENTLY 503 as of 2026-05-13.
 *
 * Anthropic Claude is on the v-final-prototype forbidden-provider list,
 * so this route no longer relays any traffic. The extension's existing
 * fallback path (Gemini Pro escalation in extension/agent.js's
 * _callViaProxy → catch 503 → use Gemini Pro tier) handles this status
 * cleanly: it logs "claude unavailable" and proceeds with the next tier.
 *
 * Keeping the route in place (instead of deleting it) means the
 * extension doesn't hit a 404 — same shape of refusal as before, just
 * always-503 instead of conditionally-503. Once we ship a new extension
 * build (v7+) that drops the Claude path entirely, this route can be
 * removed.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
} as const;

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}

export async function POST() {
  return NextResponse.json(
    {
      error:
        "Claude proxy retired. Extension should fall back to its Gemini Pro / Cerebras tiers.",
      retired_on: "2026-05-13",
    },
    { status: 503, headers: CORS_HEADERS }
  );
}
