import { NextResponse } from "next/server";
import { requireCrmGate } from "@/lib/crm/auth";
import { crmDb } from "@/lib/crm/db";
import { googleConfigured } from "@/lib/crm/google";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { data } = await crmDb()
    .from("anticipy_google_tokens")
    .select("email, updated_at")
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return NextResponse.json({
    configured: googleConfigured(),
    connected: !!data,
    email: data?.email ?? null,
    updatedAt: data?.updated_at ?? null,
  });
}
