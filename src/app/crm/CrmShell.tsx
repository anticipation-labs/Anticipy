"use client";

import { Nav } from "./Nav";
import type { SessionUser } from "@/lib/crm/userContext";
import { CrmSessionProvider } from "@/lib/crm/userContext";

export function CrmShell({
  user,
  children,
}: {
  user: SessionUser;
  children: React.ReactNode;
}) {
  return (
    <CrmSessionProvider user={user}>
      <div style={{ minHeight: "100vh", background: "var(--dark)", color: "var(--text-on-dark)" }}>
        <Nav user={user} />
        <main
          style={{
            maxWidth: 1280,
            margin: "0 auto",
            padding: "32px 20px 80px",
          }}
        >
          {children}
        </main>
      </div>
    </CrmSessionProvider>
  );
}
