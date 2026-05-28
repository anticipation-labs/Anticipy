/**
 * HTML / header escaping helpers.
 * Used anywhere LLM output or other user-influenced text is interpolated
 * into HTML, email subject lines, or response bodies.
 */

const HTML_ENTITY_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Escape user-supplied text for safe inclusion inside an HTML element body. */
export function escapeHtml(input: string | null | undefined): string {
  if (input == null) return "";
  return String(input).replace(/[&<>"']/g, (c) => HTML_ENTITY_MAP[c] ?? c);
}

// Build a regex that matches any C0/C1 control character (incl. CR/LF/TAB).
// Constructed at runtime so the source file stays free of literal control bytes.
const CONTROL_CHAR_REGEX = new RegExp(
  "[" +
    "\\u0000-\\u001F" + // C0 controls (incl. \r \n \t)
    "\\u007F" + // DEL
    "\\u0080-\\u009F" + // C1 controls
    "]+",
  "g"
);

/**
 * Sanitize a string for use as an email subject or other single-line header.
 * Strips control chars and CR/LF (header-injection vectors), collapses whitespace,
 * and truncates to a sensible max length.
 */
export function sanitizeHeader(input: string | null | undefined, maxLen = 200): string {
  if (input == null) return "";
  const cleaned = String(input)
    .replace(CONTROL_CHAR_REGEX, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen - 1) + "…" : cleaned;
}
