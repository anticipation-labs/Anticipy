import type { Metadata } from "next";
import { RolePage, type RolePageContent } from "@/components/apply/RolePage";
import { ROLE_BY_SLUG } from "@/app/apply/roles";

const role = ROLE_BY_SLUG.build;

export const metadata: Metadata = {
  title: `${role.label} — Anticipy`,
  description: role.tagline,
  alternates: { canonical: "https://www.anticipy.ai/build" },
  openGraph: {
    title: role.label,
    description: role.tagline,
    url: "https://www.anticipy.ai/build",
    type: "website",
  },
};

const content: RolePageContent = {
  lede:
    "You own the physical pendant.",
  intro: [
    "People wear it where they'd wear jewellery. That means it gets judged up close by someone who does not care how clever the inside is. That constraint drives more decisions than the electronics do, and it's harder.",
    "The first factory samples came back bad. Bad enough that I'm hand-building units instead of shipping what arrived. The next run is bigger and goes through a process nobody here has proven yet. Both of those are now your problem — and I mean that as the job description, not a complaint.",
  ],
  sections: [
    {
      heading: "Your first month",
      body: [
        "Take over the hand-built run and make it repeatable without me in the room.",
        "Sort batch one's failures into design problems and manufacturing problems. They're tangled together right now and they need different fixes.",
      ],
    },
    {
      heading: "The honest part",
      body: [
        "Some weeks this is engineering. Other weeks it's opening a box of wrong parts on a Tuesday and deciding what we do by Friday. The second kind happens more than I expected.",
        "The workspace is not a lab. It will be, eventually. It isn't yet.",
      ],
    },
    {
      heading: "You'll probably fit if",
      body: [
        "You've actually made physical things, not just drawn them on a screen.",
        "Something has come back from a supplier wrong and you worked out why yourself.",
        "You have opinions about finish and materials you can defend to a non-engineer.",
        "You don't need a lab or a team to get started. Neither do I, yet.",
      ],
    },
    {
      heading: "Before you apply",
      body: [
        "Look at the comparison pages on the site against the other pendants. Tell me what you'd change about the object itself.",
      ],
    },
  ],
};

export default function BuildPage() {
  return <RolePage role={role} content={content} />;
}
