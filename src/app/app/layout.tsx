import type { Metadata } from "next";

// B011 + B013: /app needs its own title + description, distinct from the
// marketing homepage. Previously the root layout set title='Anticipy App'
// and a /app-centric description for every route, which buried the
// marketing pitch on the homepage and hurt SEO + social previews.
export const metadata: Metadata = {
  title: "Anticipy App",
  description:
    "Open Anticipy, install the local Mac engine, and connect the private on-device assistant to the public app shell.",
  alternates: {
    canonical: "https://www.anticipy.ai/app",
  },
  openGraph: {
    title: "Anticipy App",
    description:
      "The public Anticipy app shell plus the private local Mac engine.",
    url: "https://www.anticipy.ai/app",
  },
};

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
