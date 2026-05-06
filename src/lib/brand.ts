/**
 * Brand tokens for Anticipy. Source of truth for the marketing site is
 * tailwind.config.ts and globals.css. Values mirrored here for direct import
 * in CRM components that prefer typed constants over Tailwind classes.
 *
 * Rules:
 *   1. No hardcoded colors elsewhere. Import from here.
 *   2. Editorial type pairing: DM Serif Display for display, Plus Jakarta Sans
 *      for body. The CSS variable names match what RootLayout already injects.
 *   3. CRM strings, including these inline labels, never use em dashes.
 */

export const brand = {
  colors: {
    dark: {
      DEFAULT: "#0C0C0C",
      elevated: "#161616",
      border: "#252525",
      hover: "#1E1E1E",
    },
    cream: {
      DEFAULT: "#F5F0EB",
      muted: "#E8E2DB",
      border: "#D4CEC7",
    },
    gold: {
      DEFAULT: "#C8A97E",
      dim: "rgba(200, 169, 126, 0.15)",
    },
    text: {
      onDark: "#FAFAFA",
      onDarkMuted: "#8A8A8A",
      onLight: "#1A1A1A",
      onLightMuted: "#5A5A5A",
    },
  },
  fonts: {
    serif: "var(--font-dm-serif), Georgia, serif",
    sans: "var(--font-jakarta), -apple-system, BlinkMacSystemFont, sans-serif",
  },
  // Same SVG used at src/app/icon.svg, inlined for use as a React node.
  logoSvg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="6" fill="#0C0C0C"/><rect x="10.5" y="3" width="11" height="26" rx="5.5" stroke="#F5F0EB" stroke-width="2"/><circle cx="16" cy="20" r="1.8" fill="#C8A97E"/></svg>`,
} as const;

export type Brand = typeof brand;
