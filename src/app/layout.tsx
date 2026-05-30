import type { Metadata } from "next";
import { DM_Serif_Display, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { LenisProvider } from "@/components/LenisProvider";
import { PostHogProvider } from "@/components/PostHogProvider";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/next";

const dmSerif = DM_Serif_Display({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-dm-serif",
  display: "swap",
});

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-jakarta",
  display: "swap",
});

// B011 + B013: Root layout default is the marketing homepage pitch.
// Per-route /app and /flash override this via their own layout files.
export const metadata: Metadata = {
  metadataBase: new URL("https://www.anticipy.ai"),
  title: {
    default: "Anticipy: AI pendant that listens, remembers, and acts",
    template: "%s | Anticipy",
  },
  description:
    "Anticipy is a discreet AI pendant that listens for ambient intent, remembers what matters, and quietly does the work on your Mac.",
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  openGraph: {
    title: "Anticipy: AI pendant that listens, remembers, and acts",
    description:
      "A discreet AI pendant that listens for ambient intent, remembers what matters, and quietly does the work on your Mac.",
    url: "https://www.anticipy.ai/",
    siteName: "Anticipy",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy: AI pendant that listens, remembers, and acts",
    description:
      "A discreet AI pendant that listens, remembers what matters, and quietly does the work on your Mac.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/",
  },
};

const jsonLdOrganization = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Anticipation Labs Inc.",
  url: "https://www.anticipy.ai",
  foundingDate: "2025",
  foundingLocation: {
    "@type": "Place",
    address: {
      "@type": "PostalAddress",
      addressLocality: "Vancouver",
      addressRegion: "BC",
      addressCountry: "CA",
    },
  },
};

const jsonLdProduct = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Anticipy",
  description:
    "Public app shell plus private local Mac engine for ambient intent capture, onboarding, memory, and browser actions.",
  brand: {
    "@type": "Brand",
    name: "Anticipation Labs",
  },
  applicationCategory: "ProductivityApplication",
  operatingSystem: "macOS",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
    availability: "https://schema.org/InStock",
    url: "https://www.anticipy.ai/app",
  },
};

const jsonLdWebSite = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Anticipy",
  url: "https://www.anticipy.ai/app",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${dmSerif.variable} ${jakarta.variable}`}>
      <body className="font-sans antialiased">
        <PostHogProvider />
        <LenisProvider>{children}</LenisProvider>
        <Analytics />
        <SpeedInsights />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(jsonLdOrganization),
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdProduct) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdWebSite) }}
        />
      </body>
    </html>
  );
}
