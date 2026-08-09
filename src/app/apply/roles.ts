/**
 * Role definitions and their question sets.
 *
 * Single source of truth, imported by the form, the API route and the emails
 * — so a question can never be asked on the page and be missing from the
 * notification, which is the usual way these drift apart.
 *
 * No server-only imports: this is used on both sides.
 */

export type RoleKey = "growth" | "software" | "hardware" | "hardware_software";

export interface Role {
  key: RoleKey;
  label: string;
  /** Growth is a different job; the engineering roles can be combined. */
  family: "growth" | "engineering";
}

export const ROLES: Role[] = [
  { key: "growth", label: "Founding Head of Content & Growth", family: "growth" },
  { key: "software", label: "Senior Software Engineer", family: "engineering" },
  { key: "hardware", label: "Senior Hardware Engineer", family: "engineering" },
  {
    key: "hardware_software",
    label: "Senior Hardware & Software Engineer",
    family: "engineering",
  },
];

export const ROLE_LABEL: Record<RoleKey, string> = ROLES.reduce(
  (acc, r) => ({ ...acc, [r.key]: r.label }),
  {} as Record<RoleKey, string>
);

export interface Question {
  id: string;
  q: string;
  hint?: string;
}

export const QUESTIONS: Record<RoleKey, Question[]> = {
  growth: [
    {
      id: "g1",
      q: "Link three pieces of content or campaigns you personally helped create.",
      hint: "What exactly did you do, and what result did each produce?",
    },
    {
      id: "g2",
      q: "You start Monday with a phone, an Anticipy prototype and the founder.",
      hint: "What are the first five videos you would make, and which one would you turn into a Meta ad?",
    },
    {
      id: "g3",
      q: "Tell us about something you created or fixed without waiting for somebody to ask you.",
    },
    {
      id: "g4",
      q: "Are you comfortable with all of this?",
      hint: "Scripting, filming, editing, publishing daily, appearing in content when helpful, filming the founder, and travelling for important shoots or launches.",
    },
  ],
  software: [
    {
      id: "s1",
      q: "What are the three strongest systems or products you have built?",
      hint: "Include links and explain exactly what you owned.",
    },
    {
      id: "s2",
      q: "What is the hardest production software problem you have personally solved?",
    },
    {
      id: "s3",
      q: "Where are you strongest?",
      hint: "Mobile, backend, AI agents, real-time audio, Bluetooth integrations, infrastructure — or something else.",
    },
    {
      id: "s4",
      q: "Tell us about something important you noticed and fixed without being asked.",
    },
  ],
  hardware: [
    {
      id: "h1",
      q: "What are the three strongest physical products you have helped take from idea toward production?",
      hint: "Explain exactly what you owned.",
    },
    {
      id: "h2",
      q: "Where are you strongest?",
      hint: "Electrical engineering, PCB design, embedded firmware, RF/Bluetooth, batteries, microphones and audio, mechanical design, DFM or manufacturing.",
    },
    {
      id: "h3",
      q: "What experience do you have with factories, suppliers, certification or production builds?",
    },
    {
      id: "h4",
      q: "Tell us about a hardware problem you solved that other people could not solve.",
    },
  ],
  hardware_software: [
    {
      id: "hs1",
      q: "Show us one product you owned across hardware, firmware and software.",
      hint: "What did you personally build?",
    },
    {
      id: "hs2",
      q: "What was the hardest integration problem, and how did you solve it?",
    },
    {
      id: "hs3",
      q: "Which layer are you strongest in, and which layer is your weakest?",
    },
    {
      id: "hs4",
      q: "Tell us about something end-to-end that you shipped with very little direction.",
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

/** Accepts ?role=growth and a few forgiving aliases. */
export function parseRoleParam(v: string | null): RoleKey | null {
  if (!v) return null;
  const s = v.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const alias: Record<string, RoleKey> = {
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
    build: "hardware_software",
  };
  return alias[s] ?? null;
}
