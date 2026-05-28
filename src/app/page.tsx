import { Nav } from "@/components/Nav";
import { Hero } from "@/components/Hero";
import { Hook } from "@/components/Hook";
import { Triptych } from "@/components/Triptych";
import { ProductSplit } from "@/components/ProductSplit";
import { SizeComparison } from "@/components/SizeComparison";
import { Scenarios } from "@/components/Scenarios";
import { FullBleedImage } from "@/components/FullBleedImage";
import { SpecsStrip } from "@/components/SpecsStrip";
import { Colorways } from "@/components/Colorways";
import { ChargingSection } from "@/components/ChargingSection";
import { HowItWorks } from "@/components/HowItWorks";
import { Privacy } from "@/components/Privacy";
import { Pricing } from "@/components/Pricing";
import { WaitlistCTA } from "@/components/WaitlistCTA";
import { Footer } from "@/components/Footer";
import Image from "next/image";

export default function Home() {
  return (
    <>
      <Nav />

      {/* Section 1: Hero (Dark) */}
      <Hero />

      {/* Section 2: Hook (Dark) */}
      <Hook />

      {/* Section 3: Triptych (Dark, full-bleed) */}
      <Triptych />

      {/* Transition: Dark → Cream */}
      <div className="transition-dark-to-cream" />

      {/* Section 4: Product Intro (Cream) */}
      <ProductSplit
        id="product"
        imageSrc="/images/mirror.png"
        imageAlt="Woman putting on Anticipy pendant in mirror"
        headline="You put it on.<br/>You forget it's there."
        body="Brushed titanium. 8 grams. Lighter than a house key. It comes in silver or gold, and it looks like something you'd actually wear — because it is. The difference is what happens in the background."
        body2="It charges wirelessly from up to 15 feet away. Leave the charging pad on your nightstand — by morning, you're full. No cables. No placement. No thinking about it."
        imageLeft={true}
        theme="cream"
      />

      {/* Section 5: Size Comparison (Cream) */}
      <SizeComparison />

      {/* Transition: Cream → Dark */}
      <div className="transition-cream-to-dark" />

      {/* Section 6: Scenarios (Dark) */}
      <Scenarios />

      {/* Section 7: Macro Beauty Shot (Dark, full-bleed) */}
      <FullBleedImage
        src="/images/macro.png"
        alt="Extreme close-up of Anticipy pendant — brushed titanium surface and LED"
        overlayText="Brushed titanium. A single LED. Nothing else."
        ledPosition={{ top: "35%", left: "48%" }}
      />

      {/* Section 8: Specs Strip (Dark) */}
      <SpecsStrip />

      {/* Section 9: Colorways (Dark) */}
      <Colorways />

      {/* Section 10: Charging (Dark) */}
      <ChargingSection />

      {/* Section 11: Sleeping Shot (Dark, full-bleed) */}
      <FullBleedImage
        src="/images/sleeping.png"
        alt="Woman sleeping peacefully — Anticipy pendant charging on nightstand"
        parallaxSpeed={0.9}
      />

      {/* Transition: Dark → Cream */}
      <div className="transition-dark-to-cream" />

      {/* Section 12: How It Works (Cream) */}
      <HowItWorks />

      {/* Transition: Cream → Dark */}
      <div className="transition-cream-to-dark" />

      {/* Section 13: Privacy (Dark) */}
      <Privacy />

      {/* Section 14: Lifestyle Male (Dark) */}
      <ProductSplit
        imageSrc="/images/lifestyle-male.png"
        imageAlt="Man wearing Anticipy pendant with dark sweater"
        headline="Worn by anyone.<br/>Noticed by no one."
        body="Nobody will ask you about it. The chain sits like any other necklace. The pendant tucks under a collar or sits over a sweater. It doesn't look like tech because it isn't trying to."
        imageLeft={true}
        theme="dark"
      />

      {/* Transition: Dark → Cream */}
      <div className="transition-dark-to-cream" />

      {/* Section 15: Pricing (Cream) */}
      <Pricing />

      {/* Transition: Cream → Dark */}
      <div className="transition-cream-to-dark" />

      {/* Section 16: Unboxing (Dark) */}
      <section className="section-dark py-[120px] px-6">
        <div className="max-w-container mx-auto text-center">
          <div className="max-w-[800px] mx-auto">
            <Image
              src="/images/unbox.png"
              alt="Anticipy pendant in premium jewelry box"
              width={800}
              height={500}
              className="w-full h-auto rounded-image"
              loading="lazy"
            />
          </div>
          <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light mt-6">
            Pendant. Chain. Wireless charging pad. Nothing else to buy.
          </p>
        </div>
      </section>

      {/* Section 17: Waitlist CTA (Dark) */}
      <WaitlistCTA />

      {/* Footer */}
      <Footer />
    </>
  );
}
