import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pre-Order Anticipy at $149.99",
  description:
    "Pre-order the Anticipy AI wearable pendant at $149.99, $50 off the $199 retail price. Brushed titanium, 8 grams, wireless charging pad and chain included. Estimated shipping Q4 2026. Free shipping in the US and Canada.",
  openGraph: {
    title: "Pre-Order Anticipy",
    description:
      "Reserve the Anticipy AI wearable pendant at $149.99. $50 off the $199 retail price. Free shipping to the US and Canada. Ships Q4 2026.",
    url: "https://www.anticipy.ai/pre-orders/purchase",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Pre-Order Anticipy",
    description:
      "Reserve the Anticipy AI wearable pendant at $149.99. $50 off the $199 retail price.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/pre-orders/purchase",
  },
};

export default function PreOrdersLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
