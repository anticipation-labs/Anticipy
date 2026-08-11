import type { Metadata, Viewport } from "next";
import { UgcForm } from "./UgcForm";
import { HIRE_THEME } from "@/components/apply/theme";

export const metadata: Metadata = {
  title: "Become an Anticipy UGC Creator",
  description: "Make videos, get your own link, get paid twice.",
  alternates: { canonical: "https://www.anticipy.ai/ugc/apply" },
  // /ugc is the page worth indexing; this is the form behind it.
  robots: { index: false, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  interactiveWidget: "resizes-content",
};

/**
 * The UGC creator signup.
 *
 * One question per screen, same funnel as the job application — the program
 * is explained on the first screen rather than on a page somebody has to read
 * before they are allowed to start.
 */
export default function UgcApplyPage() {
  return (
    <main style={HIRE_THEME}>
      <UgcForm />
    </main>
  );
}
