import type { Metadata } from "next";
import { RolePage, type RolePageContent } from "@/components/apply/RolePage";
import { ROLE_BY_SLUG } from "@/app/apply/roles";

const role = ROLE_BY_SLUG.ship;

export const metadata: Metadata = {
  title: `${role.label} — Anticipy`,
  description: role.tagline,
  alternates: { canonical: "https://www.anticipy.ai/ship" },
  openGraph: {
    title: role.label,
    description: role.tagline,
    url: "https://www.anticipy.ai/ship",
    type: "website",
  },
};

const content: RolePageContent = {
  heroPhoto:
    "Hero, 16:9 — laptop screen mid agent-run at night: logs or a browser automating visible, desk lamp on, text not readable.",
  intro: [
    "The pendant hears what you said. You own everything that happens next.",
    "That means browser agents. Someone mentions they'll book the flight, and an agent on their computer goes and books it. When it works, it's the best demo I've ever shown anyone. When it doesn't, it clicks the wrong button and reports success anyway.",
    "The current answer is running the same task several ways and letting the results vote. It beats one agent trying harder. Making that faster, cheaper, and less wrong isn't a roadmap item. It is the product.",
  ],
  sections: [
    {
      heading: "Your first month",
      body: [
        "Replace my anecdotal sense of where the agent fails with actual numbers.",
        "Bring cost per task down without giving back reliability. Every trick I've found so far trades one for the other.",
      ],
    },
    {
      heading: "The honest part",
      body: [
        "A lot of the week is reading traces to figure out why an agent did something dumb. It's unglamorous, and it matters more than anything else here.",
        "There's no QA team and no on-call. If it breaks at 11pm, it's yours and mine.",
      ],
    },
    {
      heading: "You'll probably fit if",
      body: [
        "You've shipped something where being wrong was expensive, and you built the tooling to catch it.",
        "Evals feel like a normal part of the job to you, not a chore.",
        "Non-determinism doesn't scare you off.",
      ],
    },
    {
      heading: "Before you apply",
      body: [
        "Read anticipy.ai/ambient-intent. If you think the whole premise is wrong, say so in your application. That's a better first conversation than agreeing with me.",
      ],
    },
  ],
};

export default function ShipPage() {
  return <RolePage role={role} content={content} />;
}
