import type { CSSProperties } from "react";

/**
 * The hiring surface carries its own palette.
 *
 * Deliberately literal hex rather than the global tokens. `--cream`,
 * `--gold` and friends are being redefined by the in-progress v3 dark
 * redesign — `--cream` is aliased to near-black there — so a hiring page
 * built on them would silently invert the day that lands. These five pages
 * are a light island inside a dark site and need to stay that way on their
 * own terms.
 *
 * Values match the light half of the shipped palette, so the island still
 * looks like the same company: cream paper, near-black ink, and the warm
 * accent in two weights — `--accent` for marks and rules, `--accent-ink` for
 * anything that has to be read, since the lighter one sits at about 2:1 on
 * cream and fails as text.
 */
export const HIRE_THEME = {
  "--ink": "#171512",
  "--ink-2": "#6B665E",
  "--paper": "#FAF8F4",
  "--paper-2": "#F0EDE6",
  "--rule": "#E4DFD6",
  "--accent": "#C8A97E",
  "--accent-ink": "#8A6B44",
  "--danger": "#A33A3A",
  "--mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  background: "#FAF8F4",
  color: "#171512",
} as CSSProperties;
