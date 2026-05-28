import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Invest in Anticipy — AI Wearable That Acts",
  description:
    "Pre-seed investment opportunity in Anticipy, the AI wearable that autonomously completes tasks from ambient conversation. $1.5M raise at $15M cap.",
  openGraph: {
    title: "Invest in Anticipy — AI Wearable That Acts",
    description:
      "Pre-seed investment opportunity in Anticipy, the AI wearable that autonomously completes tasks from ambient conversation.",
    url: "https://www.anticipy.ai/funded",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Invest in Anticipy — AI Wearable That Acts",
    description:
      "Pre-seed investment opportunity. $1.5M raise at $15M cap. The AI wearable that acts — not advises.",
  },
};

export default function FundedLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
