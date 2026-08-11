import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { sendUgcNotification, sendUgcWelcome } from "@/lib/email";
import { isDisposable } from "@/lib/email-check";
import { checkDomain } from "@/lib/email-domain";
import {
  PAY,
  UGC_QUESTIONS,
  SOCIALS,
  PAYOUT_METHODS,
  normalizeHandle,
  validateHandle,
} from "@/app/ugc/program";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const TABLE = "anticipy_ugc_creators";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
/** Matches the licence length stated in AGREEMENTS.rights. */
const RIGHTS_DAYS = 90;

const str = (v: FormDataEntryValue | null, max: number): string =>
  typeof v === "string" ? v.trim().slice(0, max) : "";

/** Social handles are stored bare — no @, no URL, no other site's domain. */
function cleanSocial(raw: string): string {
  let s = raw.trim().replace(/^@+/, "");
  if (/^https?:\/\//i.test(s) || s.includes("/")) {
    // Keep LinkedIn-style paths intact but drop the scheme and host noise.
    s = s.replace(/^https?:\/\//i, "").replace(/^www\./i, "");
  }
  return s.slice(0, 120);
}

export async function POST(request: NextRequest) {
  const ip = clientIp(request);
  const limit = rateLimit(`ugc:${ip}`, 5, 60 * 60 * 1000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: "Too many submissions. Try again shortly." },
      { status: 429 }
    );
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid submission." }, { status: 400 });
  }

  // Same two-part spam gate as the job funnel: a honeypot no human can reach,
  // and a floor on time-to-complete. Both answer 200 so a bot learns nothing.
  if (str(form.get("company"), 100)) {
    return NextResponse.json({ ok: true }, { status: 200 });
  }
  const startedAt = Number(form.get("startedAt") || 0);
  if (startedAt && Date.now() - startedAt < 6000) {
    return NextResponse.json({ ok: true }, { status: 200 });
  }

  const name = str(form.get("name"), 120);
  const email = str(form.get("email"), 254).toLowerCase();
  const location = str(form.get("location"), 160);
  const handle = normalizeHandle(str(form.get("handle"), 60));

  const socials: Record<string, string> = {};
  for (const s of SOCIALS) {
    const v = cleanSocial(str(form.get(s.id), 140));
    if (v) socials[s.id] = v;
  }

  const payoutMethod = str(form.get("payoutMethod"), 40);
  const payoutDetail = str(form.get("payoutDetail"), 200);
  const agreedDisclosure = str(form.get("agreedDisclosure"), 8) === "yes";
  const agreedRights = str(form.get("agreedRights"), 8) === "yes";

  // Questions are re-derived from the program module by id. The client sends
  // its own copy of the wording, and that copy is rendered into the owner's
  // inbox — trusting it would let anyone put arbitrary text in front of Omar.
  const byId = new Map(UGC_QUESTIONS.map((q) => [q.id, q.q]));
  let parsed: unknown = [];
  try {
    parsed = JSON.parse(str(form.get("answers"), 40000) || "[]");
  } catch {
    parsed = [];
  }
  const seen = new Set<string>();
  const supplied = new Map<string, string>();
  if (Array.isArray(parsed)) {
    for (const item of parsed.slice(0, 12)) {
      if (!item || typeof item !== "object") continue;
      const id = String((item as { id?: unknown }).id ?? "");
      if (!byId.has(id) || seen.has(id)) continue;
      seen.add(id);
      supplied.set(id, String((item as { answer?: unknown }).answer ?? "").trim().slice(0, 6000));
    }
  }
  const answers = UGC_QUESTIONS.map((q) => ({
    id: q.id,
    question: q.q,
    answer: supplied.get(q.id) ?? "",
  }));

  // ── Validation ────────────────────────────────────────────────────
  const missing: string[] = [];
  if (!name) missing.push("name");
  if (!email || !EMAIL_RE.test(email)) missing.push("email");
  if (!location) missing.push("location");
  if (!Object.keys(socials).length) missing.push("socials");
  if (!payoutMethod || !PAYOUT_METHODS.includes(payoutMethod as (typeof PAYOUT_METHODS)[number])) {
    missing.push("payoutMethod");
  }
  if (!payoutDetail) missing.push("payoutDetail");
  if (!agreedDisclosure) missing.push("agreedDisclosure");
  if (!agreedRights) missing.push("agreedRights");
  // The last question is explicitly optional; the rest are not.
  for (const q of UGC_QUESTIONS.slice(0, -1)) {
    if (!supplied.get(q.id)) missing.push(q.id);
  }
  if (missing.length) {
    return NextResponse.json(
      { error: "Some answers are missing.", fields: missing },
      { status: 400 }
    );
  }

  const handleError = validateHandle(handle);
  if (handleError) {
    return NextResponse.json({ error: handleError, fields: ["handle"] }, { status: 400 });
  }

  const domain = await checkDomain(email);
  if (domain.reason === "null_mx") {
    return NextResponse.json(
      { error: "That domain does not accept email. Check the address?" },
      { status: 400 }
    );
  }
  if (isDisposable(email)) {
    return NextResponse.json(
      { error: "Please use an address you actually read — this is how you get paid." },
      { status: 400 }
    );
  }

  const row = {
    name,
    email,
    location,
    instagram: socials.instagram ?? null,
    tiktok: socials.tiktok ?? null,
    x_handle: socials.x ?? null,
    linkedin: socials.linkedin ?? null,
    handle,
    answers,
    payout_method: payoutMethod,
    payout_detail: payoutDetail,
    agreed_disclosure: agreedDisclosure,
    agreed_rights: agreedRights,
    agreed_rights_days: RIGHTS_DAYS,
    // Frozen at signup so a later rate change is never applied backwards.
    terms_per_video: PAY.perVideo,
    terms_view_floor: PAY.viewFloor,
    terms_purchase_pct: PAY.purchaseSharePct,
    utm_source: str(form.get("utmSource"), 120) || null,
    utm_medium: str(form.get("utmMedium"), 120) || null,
    utm_campaign: str(form.get("utmCampaign"), 120) || null,
    referrer: str(form.get("referrer"), 300) || null,
    landing_path: str(form.get("landingPath"), 200) || null,
    ip_address: ip,
    user_agent: request.headers.get("user-agent")?.slice(0, 400) ?? null,
  };

  // Two unique indexes, both on lower(...) expressions. ON CONFLICT naming a
  // bare column will not match an expression index — it fails with 42P10 —
  // so a duplicate is detected by catching 23505 and asking which one it was.
  const ins = await supabaseAdmin.from(TABLE).insert(row);
  let dbErr: { message: string; code?: string } | null = ins.error;

  if (dbErr?.code === "23505") {
    const { data: byHandle } = await supabaseAdmin
      .from(TABLE)
      .select("email")
      .ilike("handle", handle)
      .maybeSingle();

    if (byHandle && byHandle.email !== email) {
      return NextResponse.json(
        { error: "That link is already taken. Try another.", fields: ["handle"] },
        { status: 409 }
      );
    }
    // Same person signing up again: update in place rather than reject, and
    // keep their existing link if they are re-submitting with the same one.
    const upd = await supabaseAdmin.from(TABLE).update(row).eq("email", email);
    dbErr = upd.error;
  }

  if (dbErr) {
    console.error("UGC creator insert failed:", dbErr);
  }

  // Owner notification carries the whole application, so it is the durable
  // record when the row write fails. Awaited, and its failure is surfaced.
  let notified = false;
  try {
    await sendUgcNotification({
      name,
      email,
      location,
      handle,
      socials,
      answers,
      payoutMethod,
      payoutDetail,
      domainOk: domain.deliverable,
      domainReason: domain.reason,
      utmSource: row.utm_source,
      utmMedium: row.utm_medium,
      utmCampaign: row.utm_campaign,
      referrer: row.referrer,
      storedInDb: !dbErr,
    });
    notified = true;
  } catch (err) {
    console.error("UGC notification failed:", err);
  }

  if (!notified && dbErr) {
    return NextResponse.json(
      { error: "We could not record your signup. Please try again." },
      { status: 500 }
    );
  }

  // The creator's own copy: their link, the rate they signed up on, and what
  // to do first. Not fatal — they already see all of it on the done screen.
  try {
    await sendUgcWelcome(email, name, handle);
  } catch (err) {
    console.error("UGC welcome failed:", err);
  }

  return NextResponse.json({ ok: true, handle }, { status: 200 });
}

/** Live availability check for the handle screen. */
export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("handle") ?? "";
  const handle = normalizeHandle(raw);
  const error = validateHandle(handle);
  if (error) return NextResponse.json({ handle, available: false, error });

  const { data, error: dbError } = await supabaseAdmin
    .from(TABLE)
    .select("handle")
    .ilike("handle", handle)
    .maybeSingle();

  if (dbError) {
    // Never claim a link is free when we could not check — the creator would
    // fill in the rest of the form and lose it at submit.
    return NextResponse.json({ handle, available: null, error: null });
  }
  return NextResponse.json({
    handle,
    available: !data,
    error: data ? "That link is already taken." : null,
  });
}
