import type { Metadata } from "next";
import "./hq.css";
import { HQProvider } from "./lib/store";
import Gate from "./Gate";

export const metadata: Metadata = {
  title: "Anticipy HQ",
  description: "Private workspace for the Anticipy team.",
  robots: { index: false, follow: false },
};

export default function HQLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="hq">
      <HQProvider>
        <Gate>{children}</Gate>
      </HQProvider>
    </div>
  );
}
