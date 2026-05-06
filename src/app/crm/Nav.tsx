"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { SessionUser } from "@/lib/crm/userContext";

const LINKS = [
  { href: "/crm", label: "Dashboard" },
  { href: "/crm/expenses", label: "Expenses" },
  { href: "/crm/todos", label: "Todos" },
  { href: "/crm/manufacturing", label: "Manufacturing" },
  { href: "/crm/voice", label: "Voice" },
  { href: "/crm/decisions", label: "Decisions" },
  { href: "/crm/burn", label: "Burn" },
  { href: "/crm/contacts", label: "Contacts" },
  { href: "/crm/feed", label: "Feed" },
  { href: "/crm/settings", label: "Settings" },
];

export function Nav({ user }: { user: SessionUser }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  function active(href: string) {
    if (href === "/crm") return pathname === "/crm";
    return pathname?.startsWith(href);
  }

  async function signOut() {
    await fetch("/api/crm/gate", { method: "DELETE" });
    window.location.reload();
  }

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 40,
        background: "var(--dark)",
        borderBottom: "1px solid var(--dark-border)",
      }}
    >
      <div
        style={{
          maxWidth: 1280,
          margin: "0 auto",
          padding: "14px 20px",
          display: "flex",
          alignItems: "center",
          gap: 24,
        }}
      >
        <Link
          href="/crm"
          style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}
        >
          <span
            aria-hidden
            style={{
              width: 24,
              height: 24,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="6" fill="#0C0C0C" />
              <rect
                x="10.5"
                y="3"
                width="11"
                height="26"
                rx="5.5"
                stroke="#F5F0EB"
                strokeWidth="2"
              />
              <circle cx="16" cy="20" r="1.8" fill="#C8A97E" />
            </svg>
          </span>
          <span
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: 18,
              color: "var(--text-on-dark)",
            }}
          >
            Anticipy CRM
          </span>
        </Link>

        <nav
          style={{
            display: "flex",
            gap: 4,
            flex: 1,
            overflowX: "auto",
            justifyContent: "center",
          }}
          className="crm-nav-links"
        >
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{
                padding: "8px 12px",
                fontSize: 13,
                borderRadius: 8,
                textDecoration: "none",
                color: active(l.href)
                  ? "var(--text-on-dark)"
                  : "var(--text-on-dark-muted)",
                background: active(l.href) ? "var(--dark-elevated)" : "transparent",
                whiteSpace: "nowrap",
              }}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <button
          onClick={() => setOpen((o) => !o)}
          style={{
            position: "relative",
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
            color: "var(--text-on-dark)",
            padding: "8px 14px",
            borderRadius: 999,
            fontSize: 13,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
          }}
          aria-haspopup="true"
          aria-expanded={open}
        >
          <span>{user.name}</span>
          {user.is_admin && (
            <span
              style={{
                fontSize: 10,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "var(--gold)",
              }}
            >
              Admin
            </span>
          )}
        </button>
        {open && (
          <div
            onMouseLeave={() => setOpen(false)}
            style={{
              position: "absolute",
              top: 56,
              right: 20,
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              borderRadius: 10,
              padding: 8,
              zIndex: 50,
              minWidth: 180,
            }}
          >
            <Link
              href="/crm/settings"
              style={{
                display: "block",
                padding: "8px 10px",
                fontSize: 13,
                textDecoration: "none",
                color: "var(--text-on-dark)",
                borderRadius: 6,
              }}
              onClick={() => setOpen(false)}
            >
              Settings
            </Link>
            <button
              onClick={signOut}
              style={{
                width: "100%",
                textAlign: "left",
                background: "transparent",
                border: "none",
                color: "var(--text-on-dark)",
                padding: "8px 10px",
                fontSize: 13,
                cursor: "pointer",
                borderRadius: 6,
              }}
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
