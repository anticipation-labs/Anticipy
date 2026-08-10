import type { Metadata } from "next";
import { RolePage, type RolePageContent } from "@/components/apply/RolePage";
import { ROLE_BY_SLUG } from "@/app/apply/roles";

const role = ROLE_BY_SLUG.grow;

export const metadata: Metadata = {
  title: `${role.label} — Anticipy`,
  description: role.tagline,
  alternates: { canonical: "https://www.anticipy.ai/grow" },
  openGraph: {
    title: role.label,
    description: role.tagline,
    url: "https://www.anticipy.ai/grow",
    type: "website",
  },
};

const content: RolePageContent = {
  lede:
    "Almost nobody knows Anticipy exists yet. Fixing that is the whole job.",
  intro: [
    "It looks like this: I'm on camera most days. You decide what I say, I film it from your shot list at night after school, and you cut it into something people watch to the end. There are four accounts to feed — mine, the company's, one faceless, one for the startup crowd — and they shouldn't all sound the same.",
    "When something works organically, you turn it into paid. You bring in creators who get paid when they sell, not when they post. And you set up tracking before any of that, because right now I honestly could not tell you which video sold a pendant.",
  ],
  sections: [
    {
      heading: "Your first month",
      body: [
        "Decide what we sound like. I've been putting this off for months and it shows.",
        "Build a shot-list system I can film from without needing a call first.",
        "Get attribution working before a dollar goes into ads.",
      ],
    },
    {
      heading: "The honest part",
      body: [
        "There's no brief and no brand deck. If you need one to start, we'll both be miserable.",
        "Things you post will flop, in public, with your name attached. Some people shrug that off. Be one of them.",
      ],
    },
    {
      heading: "You'll probably fit if",
      body: [
        "You've made things people finished watching, and you can say why they worked — not just that they did.",
        "You edit your own stuff. You've posted through a bad month before.",
        "I don't care where you went to school or what your last title was.",
      ],
    },
    {
      heading: "Before you apply",
      body: [
        "Watch what's on the Anticipy accounts right now and show up with an opinion about what's wrong with it. That's most of our first call.",
      ],
    },
  ],
};

export default function GrowPage() {
  return <RolePage role={role} content={content} />;
}
