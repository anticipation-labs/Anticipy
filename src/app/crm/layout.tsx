import type { Metadata } from "next";
import { cookies } from "next/headers";
import { CRM_GATE_COOKIE, verifyCrmGate } from "@/lib/crm/gate";
import { crmDb } from "@/lib/crm/db";
import { PasswordGate } from "./PasswordGate";
import { CrmShell } from "./CrmShell";

export const metadata: Metadata = {
  title: "Anticipy CRM",
  robots: {
    index: false,
    follow: false,
    googleBot: { index: false, follow: false },
  },
};

// Always render dynamically: cookie state determines what we show.
export const dynamic = "force-dynamic";

export default async function CrmLayout({ children }: { children: React.ReactNode }) {
  const cookie = cookies().get(CRM_GATE_COOKIE)?.value;
  const session = verifyCrmGate(cookie);
  if (!session) {
    return <PasswordGate />;
  }
  // Re-fetch the user so name + admin reflect any recent changes (rename, demotion).
  const { data } = await crmDb()
    .from("crm_users")
    .select("id, name, email, is_admin")
    .eq("id", session.user_id)
    .maybeSingle();
  if (!data) {
    return <PasswordGate />;
  }
  const user = {
    id: data.id,
    name: data.name,
    email: data.email,
    is_admin: data.is_admin === true,
  };
  return <CrmShell user={user}>{children}</CrmShell>;
}
