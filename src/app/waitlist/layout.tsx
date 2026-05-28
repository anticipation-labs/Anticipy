import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Join the Waitlist — Anticipy",
  description:
    "Be first to get Anticipy, the AI wearable pendant that turns ambient conversation into completed tasks. $149 with first year included.",
  openGraph: {
    title: "Join the Waitlist — Anticipy",
    description:
      "Be first to get the AI wearable that listens to your life and handles what needs handling.",
    url: "https://www.anticipy.ai/waitlist",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Join the Waitlist — Anticipy",
    description:
      "Be first to get the AI wearable that listens to your life and handles what needs handling.",
  },
};

export default function WaitlistLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
