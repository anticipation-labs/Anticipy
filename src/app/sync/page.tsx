import type { Metadata } from "next";
import { RolePage, type RolePageContent } from "@/components/apply/RolePage";
import { ROLE_BY_SLUG } from "@/app/apply/roles";

const role = ROLE_BY_SLUG.sync;

export const metadata: Metadata = {
  title: `${role.label} — Anticipy`,
  description: role.tagline,
  alternates: { canonical: "https://www.anticipy.ai/sync" },
  openGraph: {
    title: role.label,
    description: role.tagline,
    url: "https://www.anticipy.ai/sync",
    type: "website",
  },
};

const content: RolePageContent = {
  heroPhoto:
    "Hero, 16:9 — a small circuit board on the bench, tweezers beside it, close macro shot, warm desk-lamp light.",
  intro: [
    "This is the role in the middle, and it pays more because it's the one everyone else is happy not to own.",
    "The hardware has limits. The software has ambitions. They argue, and the argument ends at your desk. Capture on the device, holding what it heard when the phone isn't around, syncing clean when it comes back, knowing when it's being worn and when it's sitting on a desk — all on a battery much smaller than anyone's plans for it.",
  ],
  sections: [
    {
      heading: "Your first month",
      body: [
        "Write down the real power budget, so the software side stops designing against a number I made up.",
        "Pick the ugliest part of the sync path and fix it. I have a guess about which part that is. I'd rather you found out and told me I'm wrong.",
      ],
    },
    {
      heading: "The honest part",
      body: [
        "This role exists because hardware and software kept blaming each other. That's a real dynamic, and you're stepping into the middle of it on purpose.",
        "Firmware bugs are the ones that reach people who paid. That's the failure I actually lose sleep over.",
      ],
    },
    {
      heading: "You'll probably fit if",
      body: [
        "You've shipped firmware on battery-powered devices that left the building.",
        "You've built a real update mechanism, not a bench demo.",
        "You can talk to the hardware person and the software person without mistranslating either one.",
      ],
    },
    {
      heading: "Before you apply",
      body: [
        "Nothing to read. Just tell me about the worst power bug you ever shipped and how you found it.",
      ],
    },
  ],
};

export default function SyncPage() {
  return <RolePage role={role} content={content} />;
}
