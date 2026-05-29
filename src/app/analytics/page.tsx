import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import type { Metadata } from "next";
import {
  isAnalyticsAuthed,
  ANALYTICS_COOKIE_NAME,
} from "@/lib/analytics-auth";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Anticipy Analytics",
  description: "Internal Anticipy analytics dashboard. Restricted access.",
  robots: { index: false, follow: false },
};

type WaitlistRow = {
  email: string;
  name: string | null;
  source: string | null;
  created_at: string;
};

type PreorderRow = {
  id: string;
  email: string;
  name: string | null;
  amount_total: number;
  currency: string;
  status: string;
  shipping_address_city: string | null;
  shipping_address_state: string | null;
  shipping_address_country: string | null;
  stripe_checkout_session_id: string | null;
  created_at: string;
  paid_at: string | null;
};

function formatMoney(cents: number, currency: string = "usd"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default async function AnalyticsPage() {
  const session = cookies().get(ANALYTICS_COOKIE_NAME)?.value;
  if (!isAnalyticsAuthed(session)) {
    redirect("/analytics/login");
  }

  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const [waitlistRes, preordersRes, waitlist7dRes, preorder7dRes] =
    await Promise.all([
      supabaseAdmin
        .from("anticipy_waitlist")
        .select("email,name,source,created_at", { count: "exact" })
        .order("created_at", { ascending: false })
        .limit(50),
      supabaseAdmin
        .from("anticipy_preorders")
        .select(
          "id,email,name,amount_total,currency,status,shipping_address_city,shipping_address_state,shipping_address_country,stripe_checkout_session_id,created_at,paid_at",
          { count: "exact" }
        )
        .order("created_at", { ascending: false })
        .limit(50),
      supabaseAdmin
        .from("anticipy_waitlist")
        .select("created_at", { count: "exact", head: true })
        .gte("created_at", sevenDaysAgo),
      supabaseAdmin
        .from("anticipy_preorders")
        .select("amount_total,status")
        .gte("created_at", sevenDaysAgo),
    ]);

  const waitlist = (waitlistRes.data ?? []) as WaitlistRow[];
  const preorders = (preordersRes.data ?? []) as PreorderRow[];
  const waitlistTotal = waitlistRes.count ?? 0;
  const preorderTotal = preordersRes.count ?? 0;
  const waitlist7d = waitlist7dRes.count ?? 0;
  const preorders7dRows = (preorder7dRes.data ?? []) as Array<{
    amount_total: number;
    status: string;
  }>;
  const preorders7dCount = preorders7dRows.length;
  const revenue7d = preorders7dRows
    .filter((r) => r.status === "paid")
    .reduce((sum, r) => sum + (r.amount_total ?? 0), 0);

  const paidPreorders = preorders.filter((p) => p.status === "paid");
  const revenueTotal = paidPreorders.reduce(
    (sum, p) => sum + (p.amount_total ?? 0),
    0
  );

  const conversionRate =
    waitlistTotal + preorderTotal > 0
      ? (preorderTotal / (waitlistTotal + preorderTotal)) * 100
      : 0;

  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--dark)", color: "var(--text-on-dark)" }}
    >
      <header
        className="px-6 py-5 border-b sticky top-0 z-10"
        style={{
          borderColor: "var(--dark-border)",
          background: "rgba(12,12,12,0.85)",
          backdropFilter: "blur(20px)",
        }}
      >
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <Link
            href="/analytics"
            className="font-serif text-[22px] hover:text-[var(--gold)] transition-colors"
            style={{ color: "var(--text-on-dark)" }}
          >
            Anticipy Analytics
          </Link>
          <form action="/api/analytics/logout" method="POST">
            <button
              type="submit"
              className="text-[13px] hover:text-[var(--gold)] transition-colors"
              style={{ color: "var(--text-on-dark-muted)" }}
            >
              Logout
            </button>
          </form>
        </div>
      </header>

      <main className="px-6 py-10">
        <div className="max-w-6xl mx-auto">
          <section className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
            <KpiCard
              label="Waitlist"
              value={waitlistTotal.toLocaleString()}
              sub={`+${waitlist7d.toLocaleString()} last 7 days`}
            />
            <KpiCard
              label="Pre-orders"
              value={preorderTotal.toLocaleString()}
              sub={`+${preorders7dCount.toLocaleString()} last 7 days`}
            />
            <KpiCard
              label="Revenue"
              value={formatMoney(revenueTotal)}
              sub={`${formatMoney(revenue7d)} last 7 days`}
              accent
            />
            <KpiCard
              label="Pre-order rate"
              value={`${conversionRate.toFixed(1)}%`}
              sub="vs waitlist"
            />
          </section>

          <section className="mb-12">
            <h2
              className="text-[12px] uppercase tracking-[0.15em] font-medium mb-3"
              style={{ color: "var(--text-on-dark-muted)" }}
            >
              Tool dashboards
            </h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <ExternalLink
                href="https://us.posthog.com/project/445109"
                title="PostHog"
                sub="Clicks, sessions, replay"
              />
              <ExternalLink
                href="https://vercel.com/omar-ebrahims-projects-022b18ec/anticipy/analytics"
                title="Vercel Analytics"
                sub="Page views, Web Vitals"
              />
              <ExternalLink
                href="https://dashboard.stripe.com/payments"
                title="Stripe"
                sub="Payments, refunds, customers"
              />
              <ExternalLink
                href="https://supabase.com/dashboard/project/ogbxpqkmsdrcuilafycn/editor"
                title="Supabase"
                sub="Raw tables, SQL editor"
              />
            </div>
          </section>

          <section className="mb-12">
            <h2
              className="font-serif text-[24px] mb-4"
              style={{ color: "var(--text-on-dark)" }}
            >
              Recent pre-orders
            </h2>
            <div
              className="rounded-card overflow-hidden"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
              }}
            >
              {preorders.length === 0 ? (
                <div
                  className="px-5 py-8 text-center text-[13px]"
                  style={{ color: "var(--text-on-dark-muted)" }}
                >
                  No pre-orders yet. The first one will show up here the moment
                  a real Stripe webhook lands.
                </div>
              ) : (
                <table className="w-full text-[13px]">
                  <thead>
                    <tr style={{ color: "var(--text-on-dark-muted)" }}>
                      <th className="text-left px-4 py-3 font-medium">When</th>
                      <th className="text-left px-4 py-3 font-medium">Name</th>
                      <th className="text-left px-4 py-3 font-medium">Email</th>
                      <th className="text-left px-4 py-3 font-medium">
                        Ships to
                      </th>
                      <th className="text-right px-4 py-3 font-medium">
                        Amount
                      </th>
                      <th className="text-right px-4 py-3 font-medium">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {preorders.map((p) => (
                      <tr
                        key={p.id}
                        className="border-t"
                        style={{ borderColor: "var(--dark-border)" }}
                      >
                        <td
                          className="px-4 py-3"
                          style={{ color: "var(--text-on-dark-muted)" }}
                        >
                          {timeAgo(p.created_at)}
                        </td>
                        <td className="px-4 py-3">{p.name || "n/a"}</td>
                        <td
                          className="px-4 py-3"
                          style={{ color: "var(--text-on-dark-muted)" }}
                        >
                          {p.email}
                        </td>
                        <td
                          className="px-4 py-3"
                          style={{ color: "var(--text-on-dark-muted)" }}
                        >
                          {[
                            p.shipping_address_city,
                            p.shipping_address_state,
                            p.shipping_address_country,
                          ]
                            .filter(Boolean)
                            .join(", ") || "n/a"}
                        </td>
                        <td
                          className="px-4 py-3 text-right"
                          style={{ color: "var(--gold)" }}
                        >
                          {formatMoney(p.amount_total, p.currency)}
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] uppercase tracking-[0.1em]">
                          {p.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          <section className="mb-12">
            <h2
              className="font-serif text-[24px] mb-4"
              style={{ color: "var(--text-on-dark)" }}
            >
              Recent waitlist signups
            </h2>
            <div
              className="rounded-card overflow-hidden"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
              }}
            >
              {waitlist.length === 0 ? (
                <div
                  className="px-5 py-8 text-center text-[13px]"
                  style={{ color: "var(--text-on-dark-muted)" }}
                >
                  No waitlist signups yet.
                </div>
              ) : (
                <table className="w-full text-[13px]">
                  <thead>
                    <tr style={{ color: "var(--text-on-dark-muted)" }}>
                      <th className="text-left px-4 py-3 font-medium">When</th>
                      <th className="text-left px-4 py-3 font-medium">Name</th>
                      <th className="text-left px-4 py-3 font-medium">Email</th>
                      <th className="text-left px-4 py-3 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waitlist.map((w) => (
                      <tr
                        key={w.email + w.created_at}
                        className="border-t"
                        style={{ borderColor: "var(--dark-border)" }}
                      >
                        <td
                          className="px-4 py-3"
                          style={{ color: "var(--text-on-dark-muted)" }}
                        >
                          {timeAgo(w.created_at)}
                        </td>
                        <td className="px-4 py-3">{w.name || "n/a"}</td>
                        <td
                          className="px-4 py-3"
                          style={{ color: "var(--text-on-dark-muted)" }}
                        >
                          {w.email}
                        </td>
                        <td
                          className="px-4 py-3 text-[11px] uppercase tracking-[0.1em]"
                          style={{ color: "var(--text-on-dark-muted)" }}
                        >
                          {w.source || "website"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          <p
            className="text-[11px] text-center mt-12"
            style={{ color: "var(--text-on-dark-muted)" }}
          >
            Data fetched live from Supabase on each load. PostHog and Vercel
            Analytics open in new tabs and use their own session.
          </p>
        </div>
      </main>
    </div>
  );
}

function KpiCard({
  label,
  value,
  sub,
  accent = false,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div
      className="rounded-card p-5"
      style={{
        background: "var(--dark-elevated)",
        border: `1px solid ${
          accent ? "rgba(200,169,126,0.4)" : "var(--dark-border)"
        }`,
      }}
    >
      <div
        className="text-[11px] uppercase tracking-[0.15em] font-medium mb-2"
        style={{ color: "var(--text-on-dark-muted)" }}
      >
        {label}
      </div>
      <div
        className="font-serif text-[32px] leading-none mb-2"
        style={{ color: accent ? "var(--gold)" : "var(--text-on-dark)" }}
      >
        {value}
      </div>
      <div className="text-[12px]" style={{ color: "var(--text-on-dark-muted)" }}>
        {sub}
      </div>
    </div>
  );
}

function ExternalLink({
  href,
  title,
  sub,
}: {
  href: string;
  title: string;
  sub: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener"
      className="rounded-card p-4 transition-colors hover:border-[var(--gold)]"
      style={{
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        display: "block",
      }}
    >
      <div
        className="font-serif text-[18px] mb-1"
        style={{ color: "var(--text-on-dark)" }}
      >
        {title} &nearr;
      </div>
      <div className="text-[12px]" style={{ color: "var(--text-on-dark-muted)" }}>
        {sub}
      </div>
    </a>
  );
}
