import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { sendInvestorWelcome, sendWaitlistWelcome } from "@/lib/email";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const FAKE_EMAILS = ["test@test.com", "a@b.c", "test@example.com"];

export async function POST(request: NextRequest) {
  try {
    const { email, source, name } = await request.json();

    if (!email || !EMAIL_REGEX.test(email)) {
      return NextResponse.json(
        { error: "Invalid email address." },
        { status: 400 }
      );
    }

    const normalizedEmail = email.toLowerCase().trim();

    if (FAKE_EMAILS.includes(normalizedEmail)) {
      return NextResponse.json(
        { error: "Invalid email address." },
        { status: 400 }
      );
    }

    // Rate limiting: max 3 signups per IP per hour
    const ip =
      request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
      request.headers.get("x-real-ip") ||
      "unknown";

    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();

    const { count } = await supabaseAdmin
      .from("anticipy_waitlist")
      .select("*", { count: "exact", head: true })
      .eq("ip_address", ip)
      .gte("created_at", oneHourAgo);

    if (count && count >= 3) {
      return NextResponse.json(
        { error: "Too many requests. Try again later." },
        { status: 429 }
      );
    }

    // Insert
    const { error } = await supabaseAdmin.from("anticipy_waitlist").insert({
      email: normalizedEmail,
      name: name?.trim() || null,
      source: source === "funded" ? "funded" : "website",
      ip_address: ip,
      user_agent: request.headers.get("user-agent") || null,
      referrer: request.headers.get("referer") || null,
    });

    if (error) {
      if (error.code === "23505") {
        // Unique constraint violation
        return NextResponse.json(
          { error: "Already on the waitlist." },
          { status: 409 }
        );
      }
      console.error("Waitlist insert error:", JSON.stringify(error));
      return NextResponse.json(
        { error: "Something went wrong." },
        { status: 500 }
      );
    }

    // Send welcome email(s) (don't block the response)
    const trimmedName = name?.trim() || null;
    sendWaitlistWelcome(normalizedEmail, trimmedName).catch(console.error);
    if (source === "funded") {
      sendInvestorWelcome(normalizedEmail, trimmedName).catch(console.error);
    }

    return NextResponse.json({ success: true }, { status: 201 });
  } catch {
    return NextResponse.json(
      { error: "Something went wrong." },
      { status: 500 }
    );
  }
}
