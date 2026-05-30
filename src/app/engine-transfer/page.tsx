import type { Metadata } from "next";
import { cookies } from "next/headers";
import { EngineTransferGate } from "@/components/EngineTransferGate";
import { EngineTransferDoc } from "@/components/EngineTransferDoc";
import {
  GATE_COOKIE_NAME,
  verifyGateCookie,
} from "@/lib/engine-transfer-gate";

export const metadata: Metadata = {
  title: "Engine Transfer | Anticipy",
  description:
    "Internal engineering transfer guide for the Anticipy Action Engine.",
  robots: {
    index: false,
    follow: false,
    googleBot: { index: false, follow: false },
  },
};

// Always render based on the live cookie; never cache.
export const dynamic = "force-dynamic";

export default function EngineTransferPage() {
  const token = cookies().get(GATE_COOKIE_NAME)?.value;
  const unlocked = verifyGateCookie(token);

  if (!unlocked) {
    return <EngineTransferGate />;
  }

  return <EngineTransferDoc />;
}
