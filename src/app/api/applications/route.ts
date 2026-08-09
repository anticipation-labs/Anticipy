import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { sendApplicationNotification, sendApplicantReceipt } from "@/lib/email";
import { isDisposable } from "@/lib/email-check";
import { checkDomain } from "@/lib/email-domain";
import {
  QUESTIONS,
  ROLE_LABEL,
  resolveQuestionSet,
  type RoleKey,
} from "@/app/apply/roles";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const BUCKET = "applications";
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 6;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const SIGNED_URL_TTL_S = 60 * 60 * 24 * 14;

const ALLOWED_TYPES = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/heic",
  "image/heif",
  "image/gif",
  "video/mp4",
  "video/quicktime",
]);
const ALLOWED_EXT = /\.(pdf|doc|docx|png|jpe?g|webp|heic|heif|gif|mp4|mov)$/i;

const str = (v: FormDataEntryValue | null, max: number): string =>
  typeof v === "string" ? v.trim().slice(0, max) : "";

interface Attachment {
  path: string;
  filename: string;
  size: number;
  type: string;
}

export interface RoleAnswer {
  id: string;
  question: string;
  answer: string;
}

/**
 * Re-derives each question's text server-side from the shared roles module
 * rather than trusting the client's copy.
 *
 * The form posts `[{ id, question, answer }]`, but the `question` half of that
 * is attacker-controlled — it is rendered into the owner's notification email,
 * so accepting it verbatim would let anyone put arbitrary text in front of the
 * person reading applications. The client's answer is kept; the client's
 * question is discarded and looked up by id instead. Unknown ids are dropped.
 */
function normalizeAnswers(raw: string, set: RoleKey): RoleAnswer[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];

  const byId = new Map(QUESTIONS[set].map((q) => [q.id, q.q]));
  const seen = new Set<string>();
  const out: RoleAnswer[] = [];

  for (const item of parsed.slice(0, 12)) {
    if (!item || typeof item !== "object") continue;
    const id = String((item as { id?: unknown }).id ?? "");
    const question = byId.get(id);
    if (!question || seen.has(id)) continue;
    seen.add(id);
    const answer = String((item as { answer?: unknown }).answer ?? "")
      .trim()
      .slice(0, 6000);
    out.push({ id, question, answer });
  }
  // Ask order, not post order.
  return QUESTIONS[set]
    .map((q) => out.find((a) => a.id === q.id))
    .filter((a): a is RoleAnswer => !!a);
}

/** http(s) only — see the resumeLink note below for why this matters. */
function safeUrls(raw: string, max: number): string[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, max)
    .map((s) => {
      try {
        const u = new URL(/^https?:\/\//i.test(s) ? s : `https://${s}`);
        return u.protocol === "http:" || u.protocol === "https:"
          ? u.toString().slice(0, 500)
          : null;
      } catch {
        return null;
      }
    })
    .filter((s): s is string => !!s);
}

export async function POST(request: NextRequest) {
  const ip = clientIp(request);
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

  // Spam protection without a CAPTCHA: a honeypot hidden from both sight and
  // assistive tech, plus a floor on time-to-complete. Both return 200 so a bot
  // sees success and never learns what tripped it.
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
  const thing1 = str(form.get("thing1"), 6000);
  const thing1Extra = str(form.get("thing1Extra"), 6000);
  const thing2 = str(form.get("thing2"), 6000);
  const thing2Extra = str(form.get("thing2Extra"), 6000);

  // Two funnels post here. /build sends thing1/thing2; /apply sends a role and
  // that role's four answers. One endpoint because the storage, spam handling,
  // attachment pipeline and notification path are identical — only the
  // question shape differs.
  const isRoleApplication = str(form.get("sourceForm"), 20) === "apply";

  const roles = str(form.get("roles"), 200)
    .split(",")
    .map((s) => s.trim())
    .filter((s): s is RoleKey => s in ROLE_LABEL)
    .slice(0, 4);
  // Resolved server-side. The client sends `questionSet` too, but a mismatched
  // value would mean storing answers under the wrong role.
  const questionSet = resolveQuestionSet(roles);

  const links = str(form.get("links"), 2000);
  const availability = str(form.get("availability"), 300);
  const startDate = str(form.get("startDate"), 200);
  const vancouver = str(form.get("vancouver"), 100);
  const workAuthRaw = str(form.get("workAuthorized"), 10);
  const workAuthorized =
    workAuthRaw === "yes" ? true : workAuthRaw === "no" ? false : null;

  const answers: RoleAnswer[] = isRoleApplication && questionSet
    ? normalizeAnswers(str(form.get("answers"), 40000), questionSet)
    : [];

  const missing: string[] = [];
  if (!name) missing.push("name");
  if (!email || !EMAIL_RE.test(email)) missing.push("email");
  if (!location) missing.push("location");

  if (isRoleApplication) {
    if (!roles.length || !questionSet) missing.push("roles");
    else if (answers.some((a) => !a.answer) || answers.length !== QUESTIONS[questionSet].length) {
      missing.push("answers");
    }
    if (!availability) missing.push("availability");
    if (!vancouver) missing.push("vancouver");
    if (workAuthorized === null) missing.push("workAuthorized");
  } else {
    if (!thing1) missing.push("thing1");
    if (!thing2) missing.push("thing2");
  }

  if (missing.length) {
    return NextResponse.json(
      { error: "Some required answers are missing.", fields: missing },
      { status: 400 }
    );
  }

  // Domain check is ADVISORY. The only hard rejection is a null MX, which is
  // an explicit RFC 7505 declaration that the domain accepts no mail at all —
  // anything softer risks turning away a real candidate over a transient DNS
  // failure, which costs far more than a bounced email.
  const domain = await checkDomain(email);
  if (domain.reason === "null_mx") {
    return NextResponse.json(
      { error: "That domain does not accept email. Check the address?" },
      { status: 400 }
    );
  }
  if (isDisposable(email)) {
    return NextResponse.json(
      { error: "Please use an address you actually read — we reply to this." },
      { status: 400 }
    );
  }

  // ── Attachments (all optional) ─────────────────────────────────
  const attachments: Attachment[] = [];
  const files = form.getAll("files").filter((f): f is File => typeof f !== "string");

  for (const file of files.slice(0, MAX_FILES)) {
    if (!file || file.size === 0) continue;
    if (file.size > MAX_FILE_BYTES) continue;
    if (!ALLOWED_TYPES.has(file.type) || !ALLOWED_EXT.test(file.name)) continue;

    const ext = (file.name.match(ALLOWED_EXT)?.[0] ?? ".bin").toLowerCase();
    // Path is derived, never taken from the upload, so a filename like
    // "../../public/x.pdf" cannot escape the prefix.
    const stem = email.replace(/[^a-z0-9]/gi, "-").slice(0, 32);
    const path = `applications/${Date.now()}-${stem}-${attachments.length}${ext}`;

    const buf = Buffer.from(await file.arrayBuffer());
    const { error } = await supabaseAdmin.storage
      .from(BUCKET)
      .upload(path, buf, { contentType: file.type, upsert: false });

    if (error) {
      // Non-fatal by design. Attachments are explicitly optional here; losing
      // the whole application because one file failed would be far worse.
      console.error("Attachment upload failed:", error);
      continue;
    }
    attachments.push({
      path,
      filename: file.name.slice(0, 200),
      size: file.size,
      type: file.type,
    });
  }

  // Résumé link — http(s) only. Without this a `javascript:` value would be
  // rendered as an href in the notification email, making the owner's own
  // inbox the delivery vector.
  const rawLink = str(form.get("resumeLink"), 500);
  let resumeLink: string | null = null;
  if (rawLink) {
    try {
      const u = new URL(rawLink);
      if (u.protocol === "http:" || u.protocol === "https:") {
        resumeLink = u.toString().slice(0, 500);
      }
    } catch {
      /* unparseable — optional field, treated as absent */
    }
  }

  const spokenFields = str(form.get("spokenFields"), 200)
    .split(",")
    .map((s) => s.trim())
    .filter((s) => /^[a-zA-Z0-9]+$/.test(s))
    .slice(0, 8);

  const linkList = safeUrls(links, 12);

  const row = {
    name,
    email,
    location,
    // Null rather than "" on the funnel that doesn't ask these, so an empty
    // string never reads as "they answered and said nothing".
    thing_1: thing1 || null,
    thing_1_extra: thing1Extra || null,
    thing_2: thing2 || null,
    thing_2_extra: thing2Extra || null,
    source_form: isRoleApplication ? "apply" : "build",
    roles,
    question_set: questionSet,
    answers,
    links: links || null,
    availability: availability || null,
    start_date: startDate || null,
    vancouver: vancouver || null,
    work_authorized: workAuthorized,
    spoken_fields: spokenFields,
    attachments,
    resume_link: resumeLink,
    email_domain_ok: domain.deliverable,
    email_domain_reason: domain.reason,
    utm_source: str(form.get("utmSource"), 120) || null,
    utm_medium: str(form.get("utmMedium"), 120) || null,
    utm_campaign: str(form.get("utmCampaign"), 120) || null,
    referrer: str(form.get("referrer"), 300) || null,
    landing_path: str(form.get("landingPath"), 200) || null,
    ip_address: ip,
    user_agent: request.headers.get("user-agent")?.slice(0, 400) ?? null,
  };

  // Insert, then fall back to update on a duplicate — deliberately NOT an
  // upsert with onConflict:"email". The unique index is on lower(email), an
  // EXPRESSION index, and Postgres will not match an ON CONFLICT clause naming
  // the bare column against it: it fails with 42P10 "no unique or exclusion
  // constraint matching the ON CONFLICT specification". That failure is silent
  // from the applicant's side, so every submission emailed through correctly
  // while storing nothing.
  //
  // Doing it this way keeps the case-insensitive index and needs no migration.
  // `email` is lowercased above, and stored lowercased, so the .eq() matches.
  //
  // The `write` helper exists so the duplicate-email path and the legacy-schema
  // fallback below both get identical insert-then-update behaviour.
  const write = async (r: Record<string, unknown>) => {
    const ins = await supabaseAdmin.from("anticipy_applications").insert(r);
    if (!ins.error) return null;
    if (ins.error.code !== "23505") return ins.error;
    const upd = await supabaseAdmin
      .from("anticipy_applications")
      .update(r)
      .eq("email", email);
    return upd.error;
  };

  let dbErr: { message: string; code?: string } | null = await write(row);

  // PGRST204 means PostgREST does not know a column we sent — i.e. the role
  // migration has not been run on this database yet. Rather than let the row
  // be lost until someone runs it, retry with only the columns that existed
  // before, flattening the role answers into the two legacy text fields. The
  // application is then durable either way, and the notification email is
  // unaffected. Once the migration is applied this branch stops being reached.
  if (dbErr?.code === "PGRST204" && isRoleApplication) {
    console.error(
      "Role columns missing — falling back to the legacy schema. Run supabase/migrations/20260808_applications_roles.sql."
    );
    const header = roles.map((r) => ROLE_LABEL[r]).join(" + ");
    const qa = answers.map((a) => `${a.question}\n${a.answer}`).join("\n\n");
    const tail = [
      linkList.length ? `Links:\n${linkList.join("\n")}` : "",
      availability ? `Availability: ${availability}` : "",
      startDate ? `Can start: ${startDate}` : "",
      vancouver ? `Vancouver: ${vancouver}` : "",
      `Legally able to work: ${workAuthorized ? "yes" : "no"}`,
    ]
      .filter(Boolean)
      .join("\n");

    dbErr = await write({
      name,
      email,
      location,
      thing_1: `[${header}]\n\n${qa}`.slice(0, 20000),
      thing_2: tail.slice(0, 20000),
      spoken_fields: spokenFields,
      attachments,
      resume_link: resumeLink,
      email_domain_ok: domain.deliverable,
      email_domain_reason: domain.reason,
      utm_source: row.utm_source,
      utm_medium: row.utm_medium,
      utm_campaign: row.utm_campaign,
      referrer: row.referrer,
      landing_path: row.landing_path,
      ip_address: ip,
      user_agent: row.user_agent,
    });
  }

  if (dbErr) {
    // Logged but NOT fatal: the notification email below carries the whole
    // application, so a schema problem must not lose a candidate.
    console.error("Application row insert failed:", dbErr);
  }

  // Signed links for the owner's email. Short-lived by design — a forwarded
  // notification stops working rather than becoming a permanent public URL.
  const signed: { url: string; filename: string }[] = [];
  for (const a of attachments) {
    const { data } = await supabaseAdmin.storage
      .from(BUCKET)
      .createSignedUrl(a.path, SIGNED_URL_TTL_S);
    if (data?.signedUrl) signed.push({ url: data.signedUrl, filename: a.filename });
  }

  // The owner notification is the durable delivery path when the database
  // write fails, so it is awaited and its failure is surfaced.
  let notified = false;
  try {
    await sendApplicationNotification({
      name,
      email,
      location,
      thing1,
      thing1Extra,
      thing2,
      thing2Extra,
      roleLabels: roles.map((r) => ROLE_LABEL[r]),
      questionSet,
      answers,
      links: linkList,
      availability,
      startDate,
      vancouver,
      workAuthorized,
      spokenFields,
      files: signed,
      resumeLink,
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
    console.error("Application notification failed:", err);
  }

  if (!notified && dbErr) {
    // Both paths failed — the application would vanish. Tell the applicant
    // rather than showing a success screen over a lost submission.
    return NextResponse.json(
      { error: "We could not record your application. Please try again." },
      { status: 500 }
    );
  }

  // The applicant's receipt doubles as the only real proof the address
  // exists: a hard bounce on this message is ground truth, at zero friction
  // to them. Fire-and-forget — a receipt failure must not fail the submission.
  try {
    await sendApplicantReceipt(email, name, {
      roleLabels: roles.map((r) => ROLE_LABEL[r]),
      answers,
      links: linkList,
      availability,
      startDate,
      vancouver,
      attachmentNames: attachments.map((a) => a.filename),
    });
  } catch (err) {
    console.error("Applicant receipt failed:", err);
  }

  return NextResponse.json({ ok: true }, { status: 200 });
}
