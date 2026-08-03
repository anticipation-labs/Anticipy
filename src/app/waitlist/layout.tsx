import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Join the Anticipy Waitlist",
  description:
    "Be first to get Anticipy, the AI wearable pendant that turns ambient conversation into completed tasks. $199 retail, $149.99 for pre-order customers.",
  openGraph: {
    title: "Join the Anticipy Waitlist",
    description:
      "Be first to get the AI wearable that listens to your life and handles what needs handling. Pre-order at $149.99 or join the free waitlist.",
    url: "https://www.anticipy.ai/waitlist",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Join the Anticipy Waitlist",
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
