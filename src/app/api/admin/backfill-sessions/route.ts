import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const ADMIN_EMAIL = "omar@anticipy.ai";

async function verifyAdmin(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return false;

  const token = authHeader.replace("Bearer ", "");
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );

  const { data } = await supabase.auth.getUser(token);
  if (!data.user) return false;

  const admin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );
  const { data: adminUser } = await admin
    .from("anticipy_admin_users")
    .select("role")
    .eq("id", data.user.id)
    .single();

  return !!adminUser;
}

// One-time migration: backfill anticipy_sessions.user_id and user_email for rows
// created before session creation started recording the authenticated user.
// Resolution strategy:
//   1. Find one of the session's intents.
//   2. Read the email recipient on that intent's email notification (skipping the
//      omar@anticipy.ai admin copy).
//   3. Look up that email in auth.users and write user_id + user_email.
// Falls back to nearest-signup-time matching when no notification email is available.
export async function POST(request: NextRequest) {
  if (!(await verifyAdmin(request))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const admin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  // Build email → user_id map by paginating auth.users.
  const emailToUser = new Map<string, { id: string; created_at: string }>();
  const allUsers: { id: string; email: string | null; created_at: string }[] = [];
  let page = 1;
  while (true) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
    if (error) {
      return NextResponse.json({ error: `listUsers failed: ${error.message}` }, { status: 500 });
    }
    if (!data || data.users.length === 0) break;
    for (const u of data.users) {
      if (u.email) {
        emailToUser.set(u.email.toLowerCase(), { id: u.id, created_at: u.created_at });
        allUsers.push({ id: u.id, email: u.email.toLowerCase(), created_at: u.created_at });
      }
    }
    if (data.users.length < 1000) break;
    page += 1;
  }

  // Sessions with null user_id.
  const { data: sessions, error: sessErr } = await admin
    .from("anticipy_sessions")
    .select("id, started_at, user_id")
    .is("user_id", null);

  if (sessErr) {
    return NextResponse.json({ error: sessErr.message }, { status: 500 });
  }

  let updatedFromNotifications = 0;
  let updatedFromTiming = 0;
  let unresolved = 0;
  const unresolvedIds: string[] = [];

  for (const session of sessions ?? []) {
    let resolvedEmail: string | null = null;

    // Step 1: pull intent ids for this session, then look up email notifications.
    const { data: intents } = await admin
      .from("anticipy_intents")
      .select("id")
      .eq("session_id", session.id)
      .limit(20);

    const intentIds = (intents ?? []).map((i) => i.id);
    if (intentIds.length > 0) {
      const { data: notifs } = await admin
        .from("anticipy_notifications")
        .select("recipient")
        .in("intent_id", intentIds)
        .eq("channel", "email");

      for (const n of notifs ?? []) {
        const r = (n.recipient ?? "").toLowerCase();
        if (r && r !== ADMIN_EMAIL && r.includes("@")) {
          resolvedEmail = r;
          break;
        }
      }
    }

    let userId: string | null = null;
    let userEmail: string | null = null;

    if (resolvedEmail && emailToUser.has(resolvedEmail)) {
      userId = emailToUser.get(resolvedEmail)!.id;
      userEmail = resolvedEmail;
    } else if (session.started_at && allUsers.length > 0) {
      // Step 2: timing fallback — pick the user whose signup is closest to session start,
      // and only when the gap is reasonable (< 7 days). This is best-effort; conflicts
      // among users who signed up in the same window are left unresolved.
      const sessionTime = new Date(session.started_at).getTime();
      let bestUser: typeof allUsers[number] | null = null;
      let bestDelta = Infinity;
      for (const u of allUsers) {
        const delta = Math.abs(new Date(u.created_at).getTime() - sessionTime);
        if (delta < bestDelta) {
          bestDelta = delta;
          bestUser = u;
        }
      }
      const SEVEN_DAYS = 7 * 24 * 60 * 60 * 1000;
      if (bestUser && bestDelta < SEVEN_DAYS) {
        userId = bestUser.id;
        userEmail = bestUser.email;
      }
    }

    if (!userId) {
      unresolved += 1;
      unresolvedIds.push(session.id);
      continue;
    }

    const { error: updErr } = await admin
      .from("anticipy_sessions")
      .update({ user_id: userId, user_email: userEmail })
      .eq("id", session.id);

    if (updErr) {
      unresolved += 1;
      unresolvedIds.push(session.id);
      continue;
    }

    if (resolvedEmail) updatedFromNotifications += 1;
    else updatedFromTiming += 1;
  }

  return NextResponse.json({
    totalSessions: sessions?.length ?? 0,
    updatedFromNotifications,
    updatedFromTiming,
    unresolved,
    unresolvedIds: unresolvedIds.slice(0, 20),
  });
}
