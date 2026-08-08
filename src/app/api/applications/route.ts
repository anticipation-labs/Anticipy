import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { sendApplicationNotification } from "@/lib/email";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BUCKET = "applications";
const MAX_RESUME_BYTES = 10 * 1024 * 1024; // 10 MB
const ALLOWED_TYPES = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);
const ALLOWED_EXT = /\.(pdf|doc|docx)$/i;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Signed résumé links live for 7 days — long enough to review, short enough that a forwarded email stops working. */
const SIGNED_URL_TTL_S = 60 * 60 * 24 * 7;

const str = (v: FormDataEntryValue | null, max: number): string =>
  typeof v === "string" ? v.trim().slice(0, max) : "";

export async function POST(request: NextRequest) {
  const ip = clientIp(request);

  // 5 applications per IP per hour. Generous for a genuine applicant who
  // resubmits after a typo, tight enough that scripted flooding is pointless.
  const limit = rateLimit(`application:${ip}`, 5, 60 * 60 * 1000);
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

  // ── Spam protection, without a CAPTCHA ─────────────────────────
  //
  // Two signals, both invisible to a real applicant:
  //  1. A honeypot field hidden from humans by CSS and from screen readers by
  //     aria-hidden + tabindex=-1. Bots fill every field they find.
  //  2. Time-to-complete. This form asks for three considered paragraphs; a
  //     genuine person cannot do that in four seconds, and scripted posts are
  //     effectively instant.
  //
  // Both return 200 rather than an error. A bot that receives a success page
  // stops retrying and never learns what tripped it.
  if (str(form.get("company"), 100)) {
    return NextResponse.json({ ok: true }, { status: 200 });
  }
  const startedAt = Number(form.get("startedAt") || 0);
  if (startedAt && Date.now() - startedAt < 4000) {
    return NextResponse.json({ ok: true }, { status: 200 });
  }

  // ── Validation ─────────────────────────────────────────────────
  const name = str(form.get("name"), 120);
  const email = str(form.get("email"), 254).toLowerCase();
  const location = str(form.get("location"), 160);
  const thing1 = str(form.get("thing1"), 5000);
  const thing2 = str(form.get("thing2"), 5000);
  const thing3 = str(form.get("thing3"), 5000);
  const workAuthorizedRaw = str(form.get("workAuthorized"), 10);

  const missing: string[] = [];
  if (!name) missing.push("name");
  if (!email || !EMAIL_RE.test(email)) missing.push("email");
  if (!location) missing.push("location");
  if (!thing1) missing.push("thing1");
  if (!thing2) missing.push("thing2");
  if (!thing3) missing.push("thing3");
  if (workAuthorizedRaw !== "yes" && workAuthorizedRaw !== "no") {
    missing.push("workAuthorized");
  }
  if (missing.length) {
    return NextResponse.json(
      { error: "Some required fields are missing.", fields: missing },
      { status: 400 }
    );
  }

  const workAuthorized = workAuthorizedRaw === "yes";

  // ── Résumé (optional) ──────────────────────────────────────────
  let resumePath: string | null = null;
  let resumeFilename: string | null = null;
  let resumeSize: number | null = null;

  const file = form.get("resume");
  if (file && typeof file !== "string" && file.size > 0) {
    if (file.size > MAX_RESUME_BYTES) {
      return NextResponse.json(
        { error: "Résumé must be 10 MB or smaller." },
        { status: 400 }
      );
    }
    // Checked on BOTH the browser-reported MIME type and the extension. The
    // type is trivially spoofed, so it is corroboration rather than proof —
    // the real containment is that the bucket is private and its own
    // allowed_mime_types list is enforced server-side by Supabase.
    if (!ALLOWED_TYPES.has(file.type) || !ALLOWED_EXT.test(file.name)) {
      return NextResponse.json(
        { error: "Résumé must be a PDF, DOC or DOCX." },
        { status: 400 }
      );
    }

    const ext = (file.name.match(ALLOWED_EXT)?.[0] ?? ".pdf").toLowerCase();
    // Path is derived, never taken from the upload. A filename like
    // "../../public/x.pdf" cannot escape the prefix this way.
    const safeStem = email.replace(/[^a-z0-9]/gi, "-").slice(0, 40);
    resumePath = `resumes/${Date.now()}-${safeStem}${ext}`;
    resumeFilename = file.name.slice(0, 200);
    resumeSize = file.size;

    const buf = Buffer.from(await file.arrayBuffer());
    const { error: upErr } = await supabaseAdmin.storage
      .from(BUCKET)
      .upload(resumePath, buf, {
        contentType: file.type,
        upsert: false,
      });

    if (upErr) {
      console.error("Résumé upload failed:", upErr);
      // Deliberately non-fatal. The résumé is optional; losing the whole
      // application because a file failed to store would be far worse.
      resumePath = null;
      resumeFilename = null;
      resumeSize = null;
    }
  }

  // ── Attribution ────────────────────────────────────────────────
  const utmSource = str(form.get("utmSource"), 120) || null;
  const utmMedium = str(form.get("utmMedium"), 120) || null;
  const utmCampaign = str(form.get("utmCampaign"), 120) || null;
  const referrer = str(form.get("referrer"), 300) || null;
  const landingPath = str(form.get("landingPath"), 200) || null;

  const row = {
    name,
    email,
    location,
    thing_1: thing1,
    thing_2: thing2,
    thing_3: thing3,
    work_authorized: workAuthorized,
    resume_path: resumePath,
    resume_filename: resumeFilename,
    resume_size_bytes: resumeSize,
    utm_source: utmSource,
    utm_medium: utmMedium,
    utm_campaign: utmCampaign,
    referrer,
    landing_path: landingPath,
    ip_address: ip,
    user_agent: request.headers.get("user-agent")?.slice(0, 400) ?? null,
  };

  // Resubmitting under the same address updates the record rather than
  // creating a second half-application competing for the reviewer's attention.
  const { error: dbErr } = await supabaseAdmin
    .from("anticipy_applications")
    .upsert(row, { onConflict: "email" });

  if (dbErr) {
    // Logged loudly but NOT fatal: the notification email below carries the
    // full application, so a storage failure must not lose a candidate. This
    // is also what lets the page work before the migration has been run.
    console.error("Application row insert failed:", dbErr);
  }

  // ── Signed résumé link ─────────────────────────────────────────
  let resumeUrl: string | null = null;
  if (resumePath) {
    const { data: signed } = await supabaseAdmin.storage
      .from(BUCKET)
      .createSignedUrl(resumePath, SIGNED_URL_TTL_S);
    resumeUrl = signed?.signedUrl ?? null;
  }

  // The notification IS the durable delivery path when the database write
  // fails, so it is awaited and its failure is surfaced.
  try {
    await sendApplicationNotification({
      name,
      email,
      location,
      thing1,
      thing2,
      thing3,
      workAuthorized,
      resumeUrl,
      resumeFilename,
      utmSource,
      utmMedium,
      utmCampaign,
      referrer,
      storedInDb: !dbErr,
    });
  } catch (err) {
    console.error("Application notification email failed:", err);
    if (dbErr) {
      // Both paths failed — the application would vanish. Tell the applicant
      // rather than showing a success screen over a lost submission.
      return NextResponse.json(
        { error: "We could not record your application. Please try again." },
        { status: 500 }
      );
    }
  }

  return NextResponse.json({ ok: true }, { status: 200 });
}
