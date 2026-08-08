import type { Metadata } from "next";
import { DM_Serif_Display, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { LenisProvider } from "@/components/LenisProvider";
import { PostHogProvider } from "@/components/PostHogProvider";
import { AnalyticsProvider } from "@/components/AnalyticsProvider";
import { OfferMount } from "@/components/offer/OfferMount";
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
    default: "Anticipy: the AI pendant that turns what you say into what gets done",
    template: "%s | Anticipy",
  },
  description:
    "Anticipy is a titanium AI pendant that hears your spoken commitments, drafts the action, asks for your approval, does it, and keeps a receipt. Pre-order for $149.99.",
  keywords: [
    "AI pendant",
    "AI wearable",
    "AI necklace",
    "ambient AI",
    "voice assistant wearable",
    "Anticipy",
  ],
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  openGraph: {
    title: "Anticipy: the AI pendant that turns what you say into what gets done",
    description:
      "A titanium AI pendant that hears your spoken commitments, drafts the action, asks for your approval, does it, and keeps a receipt. Pre-order for $149.99.",
    url: "https://www.anticipy.ai/",
    siteName: "Anticipy",
    type: "website",
    locale: "en_US",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Anticipy titanium pendant and chain",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy: the AI pendant that turns what you say into what gets done",
    description:
      "A titanium AI pendant that hears your spoken commitments, drafts the action, asks for approval, does it, and keeps a receipt.",
    images: ["/og.png"],
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
  "@type": "Product",
  name: "Anticipy Pendant",
  description:
    "Brushed titanium AI pendant that hears spoken commitments, drafts the action, asks for approval, executes it, and keeps a receipt. Chain and wireless charging pad included.",
  image: "https://www.anticipy.ai/og.png",
  brand: {
    "@type": "Brand",
    name: "Anticipy",
  },
  offers: {
    "@type": "Offer",
    price: "149.99",
    priceCurrency: "USD",
    availability: "https://schema.org/PreOrder",
    url: "https://www.anticipy.ai/pre-orders/purchase",
    shippingDetails: {
      "@type": "OfferShippingDetails",
      shippingRate: {
        "@type": "MonetaryAmount",
        value: "0",
        currency: "USD",
      },
      shippingDestination: [
        { "@type": "DefinedRegion", addressCountry: "US" },
        { "@type": "DefinedRegion", addressCountry: "CA" },
      ],
    },
  },
};

const jsonLdWebSite = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Anticipy",
  url: "https://www.anticipy.ai",
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
        <AnalyticsProvider />
        <OfferMount />
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
