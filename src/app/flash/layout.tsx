import type { Metadata } from "next";

// B011: distinct title + description for /flash, the pendant firmware
// updater. Previously inherited the generic 'Anticipy App' title.
export const metadata: Metadata = {
  title: "Connect your Anticipy pendant",
  description:
    "Pair your Anticipy pendant over Web Bluetooth and update its firmware. Connection stays on your Mac.",
  alternates: {
    canonical: "https://www.anticipy.ai/flash",
  },
  openGraph: {
    title: "Connect your Anticipy pendant",
    description:
      "Pair your Anticipy pendant over Web Bluetooth and update its firmware.",
    url: "https://www.anticipy.ai/flash",
  },
};

export default function FlashLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
