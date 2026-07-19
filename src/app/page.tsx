import { Nav } from "@/components/Nav";
import { StoryHero } from "@/components/story/StoryHero";
import { Wound } from "@/components/story/Wound";
import { Turn } from "@/components/story/Turn";
import { Chapters } from "@/components/story/Chapters";
import { LiveDemo } from "@/components/story/LiveDemo";
import { ObjectSection } from "@/components/story/ObjectSection";
import { Worn } from "@/components/story/Worn";
import { Trust } from "@/components/story/Trust";
import { Compare } from "@/components/story/Compare";
import { Faq } from "@/components/story/Faq";
import { Close } from "@/components/story/Close";
import { StickyBuyBar } from "@/components/StickyBuyBar";
import { Footer } from "@/components/Footer";

export default function Home() {
  return (
    <>
      <Nav />

      {/* 01 — Curiosity: the glint in the dark */}
      <StoryHero />

      {/* 02 — The wound: promises that disappear */}
      <Wound />

      {/* 03 — The turn: it catches what you said */}
      <Turn />

      {/* 04 — Comprehension: one promise, closed */}
      <Chapters />

      {/* 04a — Proof of mechanism: watch it happen on the phone */}
      <LiveDemo />

      {/* 04b — Why not the others */}
      <Compare />

      {/* 05 — Desire: the object itself */}
      <ObjectSection />

      {/* 06 — Identity: worn, not noticed */}
      <Worn />

      {/* 07 — Trust: three quiet rules */}
      <Trust />

      {/* 08 — Objections answered, founder's word */}
      <Faq />

      {/* 09 — The close: three doors out */}
      <Close />

      <StickyBuyBar />

      <Footer />
    </>
  );
}
