/**
 * Role definitions and their question sets.
 *
 * Single source of truth, imported by the hub, the four role pages, the
 * wizard, the API route and the emails — so a question can never be asked on
 * the page and be missing from the notification, which is the usual way these
 * drift apart.
 *
 * No server-only imports: this is used on both sides.
 */

export type RoleKey = "growth" | "software" | "hardware" | "hardware_software";

export interface Role {
  key: RoleKey;
  /** The page this role lives on: /grow, /ship, /build, /sync. */
  slug: string;
  label: string;
  /** One line on the hub card. */
  tagline: string;
  /** Second chip: where the role can be done from. */
  place: string;
  /** Growth is a different job; the engineering roles can be combined. */
  family: "growth" | "engineering";
}

export const ROLES: Role[] = [
  {
    key: "growth",
    slug: "grow",
    label: "Founding Head of Content & Growth",
    tagline: "Make people find out this exists.",
    place: "Vancouver or remote",
    family: "growth",
  },
  {
    key: "software",
    slug: "ship",
    label: "Founding Software Engineer",
    tagline: "Own the agent that actually does the thing.",
    place: "Vancouver or remote",
    family: "engineering",
  },
  {
    key: "hardware",
    slug: "build",
    label: "Founding Hardware Engineer",
    tagline: "Own the physical pendant, prototype to production.",
    place: "Vancouver, in person",
    family: "engineering",
  },
  {
    key: "hardware_software",
    slug: "sync",
    label: "Founding Hardware & Software Engineer",
    tagline: "Own the layer where hardware and software have to agree.",
    place: "Vancouver preferred",
    family: "engineering",
  },
];

export const ROLE_LABEL: Record<RoleKey, string> = ROLES.reduce(
  (acc, r) => ({ ...acc, [r.key]: r.label }),
  {} as Record<RoleKey, string>
);

export const ROLE_BY_SLUG: Record<string, Role> = ROLES.reduce(
  (acc, r) => ({ ...acc, [r.slug]: r }),
  {} as Record<string, Role>
);

export interface Question {
  id: string;
  q: string;
  hint?: string;
  /**
   * Shown inside the empty answer box. A real prompt per question, not a
   * generic "Type your answer" — it is the cheapest way to show what a good
   * answer looks like at the moment somebody is deciding how much to write.
   */
  placeholder: string;
}

export const QUESTIONS: Record<RoleKey, Question[]> = {
  growth: [
    {
      id: "g1",
      q: "Link three pieces of content or campaigns you personally helped create.",
      hint: "What exactly did you do, and what result did each produce?",
      placeholder:
        "Paste the links, then for each one: what was yours, and what happened after it went out.",
    },
    {
      id: "g2",
      q: "You start Monday with a phone, an Anticipy prototype and the founder.",
      hint: "What are the first five videos you would make, and which one would you turn into a Meta ad?",
      placeholder:
        "Five ideas, one line each. Then say which one you'd put money behind and why that one.",
    },
    {
      id: "g3",
      q: "Tell us about something you created or fixed without waiting for somebody to ask you.",
      placeholder:
        "What you noticed, what you did about it, and what it changed.",
    },
    {
      id: "g4",
      q: "Are you comfortable with all of this?",
      hint: "Scripting, filming, editing, publishing daily, appearing in content when helpful, filming the founder, and travelling for important shoots or launches.",
      placeholder:
        "Be straight about which parts you've done before and which you haven't.",
    },
  ],
  software: [
    {
      id: "s1",
      q: "What are the three strongest systems or products you have built?",
      hint: "Include links and explain exactly what you owned.",
      placeholder:
        "For each: what it did, what was yours specifically, and what it ran on.",
    },
    {
      id: "s2",
      q: "What is the hardest production software problem you have personally solved?",
      placeholder:
        "What was breaking, how you found it, and what you changed. Detail is better than polish here.",
    },
    {
      id: "s3",
      q: "Where are you strongest?",
      hint: "Mobile, backend, AI agents, real-time audio, Bluetooth integrations, infrastructure — or something else.",
      placeholder:
        "Name the areas, and be honest about where you'd be learning on the job.",
    },
    {
      id: "s4",
      q: "Tell us about something important you noticed and fixed without being asked.",
      placeholder:
        "What you spotted, why nobody else had, and what you did about it.",
    },
  ],
  hardware: [
    {
      id: "h1",
      q: "What are the three strongest physical products you have helped take from idea toward production?",
      hint: "Explain exactly what you owned.",
      placeholder:
        "For each: how far it got, how many units, and which parts were actually yours.",
    },
    {
      id: "h2",
      q: "Where are you strongest?",
      hint: "Electrical engineering, PCB design, embedded firmware, RF/Bluetooth, batteries, microphones and audio, mechanical design, DFM or manufacturing.",
      placeholder:
        "Name the areas, and be honest about where you'd be learning on the job.",
    },
    {
      id: "h3",
      q: "What experience do you have with factories, suppliers, certification or production builds?",
      placeholder:
        "Who you've worked with, what you ran yourself, and what went wrong at least once.",
    },
    {
      id: "h4",
      q: "Tell us about a hardware problem you solved that other people could not solve.",
      placeholder:
        "What was failing, what everyone assumed, and how you found the real cause.",
    },
  ],
  hardware_software: [
    {
      id: "hs1",
      q: "Show us one product you owned across hardware, firmware and software.",
      hint: "What did you personally build?",
      placeholder:
        "Walk the whole stack — board, firmware, app — and mark what was yours at each layer.",
    },
    {
      id: "hs2",
      q: "What was the hardest integration problem, and how did you solve it?",
      placeholder:
        "The kind where each side insisted the bug was on the other side. What was it really?",
    },
    {
      id: "hs3",
      q: "Which layer are you strongest in, and which layer is your weakest?",
      placeholder:
        "The second half of this answer is the useful one. Say it plainly.",
    },
    {
      id: "hs4",
      q: "Tell us about something end-to-end that you shipped with very little direction.",
      placeholder:
        "What you decided on your own, and what you'd decide differently now.",
    },
  ],
};

/**
 * Which question set a set of selections resolves to.
 *
 * Selecting software AND hardware means the combined role, so those
 * candidates get the integration-focused questions rather than being asked
 * two overlapping sets back to back.
 */
export function resolveQuestionSet(selected: RoleKey[]): RoleKey | null {
  if (!selected.length) return null;
  if (selected.includes("growth")) return "growth";
  if (
    selected.includes("hardware_software") ||
    (selected.includes("software") && selected.includes("hardware"))
  ) {
    return "hardware_software";
  }
  if (selected.includes("software")) return "software";
  if (selected.includes("hardware")) return "hardware";
  return null;
}

/**
 * Accepts ?role=grow and a few forgiving aliases.
 *
 * Note `build` resolves to the HARDWARE role: /build is the Senior Hardware
 * Engineer page. It used to mean the combined role, so the old value is not
 * simply renamed — anything still pointing at the old meaning should use
 * `sync` instead.
 */
export function parseRoleParam(v: string | null): RoleKey | null {
  if (!v) return null;
  const s = v.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const alias: Record<string, RoleKey> = {
    // Page slugs — the canonical form.
    grow: "growth",
    ship: "software",
    build: "hardware",
    sync: "hardware_software",
    // Role keys and the obvious human guesses.
    growth: "growth",
    content: "growth",
    marketing: "growth",
    software: "software",
    swe: "software",
    engineer: "software",
    hardware: "hardware",
    hw: "hardware",
    hardware_software: "hardware_software",
    hw_sw: "hardware_software",
    both: "hardware_software",
  };
  return alias[s] ?? null;
}
