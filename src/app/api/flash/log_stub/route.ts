import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * POST /api/flash/log_stub
 *
 * Forwarder for the /flash page. Takes the per-flash record the
 * browser produced and tries to hand it to the user's local Anticipy
 * engine on 127.0.0.1:8731 (where ~/.anticipy/system_v1/flash_stubs.jsonl
 * actually lives). If the local engine is not running, the browser
 * keeps the row in localStorage instead, so logs never disappear.
 *
 * NOTE on the per-user privacy model: Vercel does NOT store these
 * rows. This route only proxies the row to the user's own Mac. Every
 * row is forced to is_stub: true on both sides.
 */

const LOCAL_ENGINE = "http://127.0.0.1:8731";
const FORWARD_TIMEOUT_MS = 2500;

type FlashLogRow = {
  ts?: string;
  device_name?: string;
  device_id_redacted?: string;
  firmware_version_before?: string | null;
  firmware_version_after?: string | null;
  bytes_transferred?: number;
  duration_ms?: number;
  success?: boolean;
  error?: string | null;
  is_stub?: boolean;
};

async function forwardToLocalEngine(
  row: FlashLogRow
): Promise<{ ok: boolean; status: number; body?: unknown }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FORWARD_TIMEOUT_MS);
  try {
    const r = await fetch(`${LOCAL_ENGINE}/api/flash/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...row, is_stub: true }),
      signal: controller.signal,
      cache: "no-store",
    });
    let body: unknown = null;
    try {
      body = await r.json();
    } catch {
      body = null;
    }
    return { ok: r.ok, status: r.status, body };
  } catch (e) {
    return {
      ok: false,
      status: 0,
      body: e instanceof Error ? { error: e.message } : { error: String(e) },
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(req: NextRequest) {
  let row: FlashLogRow;
  try {
    row = (await req.json()) as FlashLogRow;
  } catch {
    return NextResponse.json(
      { ok: false, error: "Body must be JSON." },
      { status: 400 }
    );
  }
  if (!row || typeof row !== "object") {
    return NextResponse.json(
      { ok: false, error: "Body must be a JSON object." },
      { status: 400 }
    );
  }

  // Force the stub label, always, no matter what the client sent.
  // Never let a stub look real.
  const normalized: FlashLogRow = {
    ...row,
    ts: row.ts || new Date().toISOString(),
    is_stub: true,
  };

  const forwarded = await forwardToLocalEngine(normalized);
  if (forwarded.ok) {
    return NextResponse.json({
      ok: true,
      sink: "engine",
      detail: "Forwarded to local engine at 127.0.0.1:8731.",
    });
  }

  // The local engine is the canonical sink because logs are per-user.
  // If it is not reachable, tell the client to keep the row in
  // localStorage so it stays on the user's machine.
  return NextResponse.json({
    ok: true,
    sink: "localstorage",
    detail:
      "Local Anticipy engine not reachable. The browser will keep this " +
      "row under localStorage key anticipy_flash_stubs on this machine.",
    forwarded_status: forwarded.status,
  });
}
