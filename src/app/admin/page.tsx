"use client";

import { useEffect, useState, useCallback } from "react";
import { createClient } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321",
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "placeholder-anon-key"
);

interface WaitlistEntry {
  id: string;
  email: string;
  source: string;
  referrer: string | null;
  created_at: string;
  notes: string | null;
}

interface Stats {
  total: number;
  today: number;
  week: number;
}

export default function AdminDashboard() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [entries, setEntries] = useState<WaitlistEntry[]>([]);
  const [stats, setStats] = useState<Stats>({ total: 0, today: 0, week: 0 });
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) {
        router.push("/admin/login");
        return;
      }
      setToken(data.session.access_token);
    });
  }, [router]);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);

    const headers = { Authorization: `Bearer ${token}` };

    const [entriesRes, statsRes] = await Promise.all([
      fetch(
        `/api/admin/waitlist?page=${page}&search=${encodeURIComponent(search)}`,
        { headers }
      ),
      fetch("/api/admin/stats", { headers }),
    ]);

    if (entriesRes.ok) {
      const d = await entriesRes.json();
      setEntries(d.data);
      setTotal(d.total);
    }

    if (statsRes.ok) {
      const s = await statsRes.json();
      setStats(s);
    }

    setLoading(false);
  }, [token, page, search]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this entry?")) return;

    await fetch("/api/admin/waitlist", {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ id }),
    });

    fetchData();
  };

  const handleExport = () => {
    // Escape per RFC 4180: wrap each cell in quotes, and double any embedded
    // quote. Without this, an email or note containing a quote or comma
    // breaks the row alignment in Excel/Sheets.
    const cell = (v: string | null | undefined) =>
      `"${(v ?? "").replace(/"/g, '""')}"`;

    const csv = [
      "Email,Source,Referrer,Created At,Notes",
      ...entries.map((e) =>
        [e.email, e.source, e.referrer, e.created_at, e.notes]
          .map(cell)
          .join(",")
      ),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `anticipy-waitlist-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/admin/login");
  };

  const timeAgo = (date: string) => {
    const diff = Date.now() - new Date(date).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  if (!token) return null;

  return (
    <div className="min-h-screen px-6 py-8" style={{ background: "var(--dark)" }}>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <h1
            className="font-serif text-[28px]"
            style={{ color: "var(--text-on-dark)" }}
          >
            Waitlist Dashboard
          </h1>
          <button
            onClick={handleLogout}
            className="text-[14px] text-[var(--text-on-dark-muted)] hover:text-[var(--text-on-dark)] transition-colors"
          >
            Sign Out
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Total", value: stats.total },
            { label: "Today", value: stats.today },
            { label: "This Week", value: stats.week },
          ].map((s) => (
            <div
              key={s.label}
              className="p-6 rounded-lg"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
              }}
            >
              <p className="text-[13px] uppercase tracking-widest text-[var(--text-on-dark-muted)] mb-1">
                {s.label}
              </p>
              <p className="font-serif text-[32px] text-[var(--text-on-dark)]">
                {s.value}
              </p>
            </div>
          ))}
        </div>

        {/* Controls */}
        <div className="flex gap-4 mb-6">
          <input
            type="text"
            placeholder="Search by email..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="flex-1 px-4 py-2.5 rounded-lg text-[14px] outline-none"
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              color: "var(--text-on-dark)",
            }}
          />
          <button
            onClick={handleExport}
            className="px-4 py-2.5 rounded-lg text-[14px] font-medium"
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              color: "var(--text-on-dark)",
            }}
          >
            Export CSV
          </button>
        </div>

        {/* Table */}
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
          }}
        >
          <table className="w-full text-[14px]">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--dark-border)" }}>
                {["Email", "Source", "Referrer", "Signed Up", ""].map((h) => (
                  <th
                    key={h}
                    className="text-left px-4 py-3 text-[12px] uppercase tracking-widest font-medium"
                    style={{ color: "var(--text-on-dark-muted)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-[var(--text-on-dark-muted)]">
                    Loading...
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-[var(--text-on-dark-muted)]">
                    No entries found.
                  </td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <tr
                    key={entry.id}
                    style={{ borderBottom: "1px solid var(--dark-border)" }}
                  >
                    <td className="px-4 py-3 text-[var(--text-on-dark)]">
                      {entry.email}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)]">
                      {entry.source}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] max-w-[200px] truncate">
                      {entry.referrer || "—"}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)]">
                      {timeAgo(entry.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(entry.id)}
                        className="text-red-400 hover:text-red-300 text-[13px]"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 50 && (
          <div className="flex gap-4 justify-center mt-6">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              className="px-4 py-2 text-[14px] text-[var(--text-on-dark-muted)] disabled:opacity-30"
            >
              Previous
            </button>
            <span className="text-[14px] text-[var(--text-on-dark-muted)] py-2">
              Page {page} of {Math.ceil(total / 50)}
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={page >= Math.ceil(total / 50)}
              className="px-4 py-2 text-[14px] text-[var(--text-on-dark-muted)] disabled:opacity-30"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
