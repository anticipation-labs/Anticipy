import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

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

export async function GET(request: NextRequest) {
  if (!(await verifyAdmin(request))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const admin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
  const weekStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();

  const [total, today, week] = await Promise.all([
    admin.from("anticipy_waitlist").select("*", { count: "exact", head: true }),
    admin
      .from("anticipy_waitlist")
      .select("*", { count: "exact", head: true })
      .gte("created_at", todayStart),
    admin
      .from("anticipy_waitlist")
      .select("*", { count: "exact", head: true })
      .gte("created_at", weekStart),
  ]);

  return NextResponse.json({
    total: total.count || 0,
    today: today.count || 0,
    week: week.count || 0,
  });
}
