import type { Metadata } from "next";
import { cookies } from "next/headers";
import { CRM_GATE_COOKIE, verifyCrmGate } from "@/lib/crm/gate";
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

export default function CrmLayout({ children }: { children: React.ReactNode }) {
  const cookie = cookies().get(CRM_GATE_COOKIE)?.value;
  if (!verifyCrmGate(cookie)) {
    return <PasswordGate />;
  }
  return <CrmShell>{children}</CrmShell>;
}
