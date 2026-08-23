"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useHQ } from "../lib/store";
import CommandK from "./CommandK";
import Walkthrough from "./Walkthrough";
import { Avatar } from "./ui";

const NAV = [
  { label: "Today", href: "/hq/today", icon: "M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" },
  { label: "Work", href: "/hq/work", icon: "M2.5 4.5h11M2.5 8h11M2.5 11.5h7" },
  { label: "Agents", href: "/hq/agents", icon: "M3 5.5h10v7H3zM8 5.5v-2M5.5 9h.01M10.5 9h.01" },
  { label: "Calendar", href: "/hq/calendar", icon: "M3 4h10v9H3zM3 7h10M6 2.5v3M10 2.5v3" },
  { label: "People", href: "/hq/people", icon: "M8 7.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM2.5 13.5c.5-2.5 2.8-4 5.5-4s5 1.5 5.5 4" },
  { label: "Notifications", href: "/hq/notifications", icon: "M4 6.5a4 4 0 018 0c0 3 1.5 4.5 1.5 4.5h-11S4 9.5 4 6.5zM6.5 13a1.5 1.5 0 003 0" },
  { label: "Settings", href: "/hq/settings", icon: "M8 10a2 2 0 100-4 2 2 0 000 4zM8 1.8l.7 1.8 1.9-.4 1 1.6 1.4 1.3-1 1.9 1 1.9-1.4 1.3-1 1.6-1.9-.4-.7 1.8-.7-1.8-1.9.4-1-1.6-1.4-1.3 1-1.9-1-1.9L4.4 5l1-1.6 1.9.4z" },
];

function NavIcon({ d }: { d: string }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d={d} stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, people, notifications, walkthroughDone, setUser } = useHQ();
  const [cmdOpen, setCmdOpen] = useState(false);
  const [userMenu, setUserMenu] = useState(false);

  const me = people.find((p) => p.id === user) ?? people[0];
  const unread = notifications.filter((n) => !n.read).length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      {/* Sidebar (desktop) */}
      <aside
        className="hq-no-print"
        style={{
          width: 208, flexShrink: 0, borderRight: "1px solid var(--hq-border)",
          padding: "16px 10px", display: "flex", flexDirection: "column", gap: 2,
          position: "sticky", top: 0, height: "100vh",
        }}
        data-hq-sidebar
      >
        <Link href="/hq/today" style={{ textDecoration: "none", color: "inherit", padding: "0 10px", marginBottom: 14, display: "flex", alignItems: "baseline", gap: 6 }}>
          <span className="hq-serif" style={{ fontSize: 19 }}>Anticipy</span>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.1em", color: "var(--hq-gold)" }}>HQ</span>
        </Link>

        <button
          className="hq-btn"
          style={{ justifyContent: "space-between", marginBottom: 10, color: "var(--hq-muted)", fontWeight: 400 }}
          onClick={() => setCmdOpen(true)}
        >
          <span>Add a task or ask an agent.</span>
          <span className="hq-kbd">⌘K</span>
        </button>

        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className="hq-nav-item" data-active={active}>
              <NavIcon d={item.icon} />
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.label === "Notifications" && unread > 0 && (
                <span style={{ fontSize: 11, fontWeight: 600, color: "#fff", background: "var(--hq-bronze)", borderRadius: 9, padding: "0 6px" }}>
                  {unread}
                </span>
              )}
            </Link>
          );
        })}

        <div style={{ flex: 1 }} />

        {/* Current user */}
        <div style={{ position: "relative" }}>
          {userMenu && (
            <div className="hq-card hq-pop-in" style={{ position: "absolute", bottom: "100%", left: 0, right: 0, marginBottom: 6, background: "#fff", padding: 4, zIndex: 40 }}>
              <p className="hq-label" style={{ padding: "6px 8px 2px" }}>Switch person</p>
              {people.map((p) => (
                <button
                  key={p.id}
                  className="hq-nav-item"
                  style={{ width: "100%", border: "none", background: "transparent", cursor: "pointer" }}
                  onClick={() => { setUser(p.id); setUserMenu(false); }}
                >
                  <Avatar name={p.name} size={20} />
                  <span style={{ flex: 1, textAlign: "left" }}>{p.name}</span>
                  {p.id === me.id && <span style={{ color: "var(--hq-success)", fontSize: 11 }}>●</span>}
                </button>
              ))}
              <button
                className="hq-nav-item"
                style={{ width: "100%", border: "none", background: "transparent", cursor: "pointer", color: "var(--hq-danger)" }}
                onClick={() => { setUser(null); router.push("/hq"); }}
              >
                Lock workspace
              </button>
            </div>
          )}
          <button
            className="hq-nav-item"
            style={{ width: "100%", border: "1px solid var(--hq-border)", background: "transparent", cursor: "pointer" }}
            onClick={() => setUserMenu((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={userMenu}
          >
            <Avatar name={me.name} size={22} />
            <span style={{ flex: 1, textAlign: "left", color: "var(--hq-text)" }}>{me.name}</span>
            <span style={{ color: "var(--hq-muted)", fontSize: 10 }}>▾</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="hq-print-area" style={{ flex: 1, minWidth: 0, paddingBottom: 72 }}>
        {children}
      </main>

      {/* Bottom nav (mobile) */}
      <nav
        className="hq-no-print"
        data-hq-bottomnav
        style={{
          position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 50,
          display: "none", borderTop: "1px solid var(--hq-border)", background: "#fff",
          padding: "6px 4px calc(6px + env(safe-area-inset-bottom))",
        }}
      >
        {[NAV[0], NAV[1], NAV[2], NAV[3], NAV[5]].map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                textDecoration: "none", fontSize: 10.5, fontWeight: 500,
                color: active ? "var(--hq-text)" : "var(--hq-muted)",
                padding: "4px 0",
              }}
            >
              <NavIcon d={item.icon} />
              {item.label}
            </Link>
          );
        })}
        <button
          onClick={() => setCmdOpen(true)}
          aria-label="Open command input"
          style={{
            flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
            fontSize: 10.5, fontWeight: 500, color: "var(--hq-muted)", background: "transparent", border: "none", cursor: "pointer", padding: "4px 0",
          }}
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
          Add
        </button>
      </nav>

      <style jsx global>{`
        @media (max-width: 860px) {
          [data-hq-sidebar] { display: none !important; }
          [data-hq-bottomnav] { display: flex !important; }
        }
      `}</style>

      <CommandK open={cmdOpen} onClose={() => setCmdOpen(false)} />
      {!walkthroughDone && <Walkthrough />}
    </div>
  );
}
