"use client";

import { useEffect, useState } from "react";
import { Nav } from "./Nav";
import { NamePicker } from "./NamePicker";
import { readPickedUser, type PickedUser } from "@/lib/crm/userContext";

export function CrmShell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PickedUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setUser(readPickedUser());
    setHydrated(true);
  }, []);

  if (!hydrated) {
    return (
      <div
        style={{
          minHeight: "100vh",
          background: "var(--dark)",
          color: "var(--text-on-dark-muted)",
        }}
      />
    );
  }

  if (!user) {
    return <NamePicker onPicked={() => setUser(readPickedUser())} />;
  }

  return (
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
  );
}
