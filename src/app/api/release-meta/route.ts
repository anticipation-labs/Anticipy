import { NextResponse } from "next/server";
import { releaseMeta } from "@/lib/release-meta";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return NextResponse.json(releaseMeta(request.url));
}
