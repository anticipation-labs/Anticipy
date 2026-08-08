import { NextRequest, NextResponse } from "next/server";
import cities from "@/data/cities.json";

export const runtime = "nodejs";
// MUST be dynamic. `force-static` looks right here — the dataset never changes
// between deploys — but it makes Next prerender the route at build time, when
// there is no query string, so every request gets the same empty result. That
// shipped once and returned {"results":[]} for every search in production.
// Caching is done with the Cache-Control header below instead, which gives the
// CDN the same win without hiding the query from the handler.
export const dynamic = "force-dynamic";

/**
 * City autocomplete, served from a bundled GeoNames dataset.
 *
 * Chosen over a hosted geocoding API deliberately:
 *  - It costs nothing, forever, with no key, no billing account, no quota and
 *    no rate limit to trip over. A type-ahead field fires a request per
 *    keystroke, which is exactly the shape that blows through free tiers —
 *    OpenStreetMap's Nominatim policy explicitly forbids using it for
 *    autocomplete at all.
 *  - Applicant keystrokes never leave our infrastructure. Someone typing
 *    where they live into a job application should not have that streamed to
 *    a third party as a side effect.
 *  - Google's caching terms would forbid storing the chosen value in our own
 *    database, which is the entire point of the field.
 *
 * Data: GeoNames cities15000 (CC BY 4.0) — every city above 15,000 people,
 * 34,079 entries.
 */

type Row = [string, string, string, number, string?]; // name, admin, country, population, alternates

const ROWS = cities as unknown as Row[];

/**
 * Strips diacritics so someone typing "zurich", "montreal" or "sao paulo" on
 * a plain keyboard finds Zürich, Montréal and São Paulo. Built once per cold
 * start rather than per request.
 */
function fold(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/**
 * Cities that were renamed, where people still type the old name.
 *
 * GeoNames does carry these as alternate names, but its alternate list is in
 * no meaningful order, so truncating it to keep the file small drops exactly
 * the famous ones. A short explicit map is smaller and more reliable than
 * shipping every alternate name for 34,000 cities.
 */
const ALIASES: Record<string, string> = {
  bombay: "mumbai",
  calcutta: "kolkata",
  madras: "chennai",
  bangalore: "bengaluru",
  kiev: "kyiv",
  peking: "beijing",
  saigon: "ho chi minh",
  rangoon: "yangon",
  constantinople: "istanbul",
  danzig: "gdansk",
  bruxelles: "brussels",
  firenze: "florence",
  wien: "vienna",
  praha: "prague",
  lisboa: "lisbon",
  koln: "cologne",
  munchen: "munich",
  moskva: "moscow",
};

let INDEX: { label: string; hay: string; pop: number }[] | null = null;

function index() {
  if (INDEX) return INDEX;
  INDEX = ROWS.map((r) => {
    const [name, admin, country, pop, alts] = r;
    const label = [name, admin, country].filter(Boolean).join(", ");
    return {
      label,
      hay: `${fold(name)} ${fold(admin)} ${fold(country)} ${alts ?? ""}`,
      pop,
    };
  });
  return INDEX;
}

export function GET(request: NextRequest) {
  const raw = fold((request.nextUrl.searchParams.get("q") || "").trim());
  if (raw.length < 2) return NextResponse.json({ results: [] });

  // Resolve a renamed city to its current name before searching, so someone
  // who types "bombay" is shown Mumbai rather than a suburb that happens to
  // carry the old name in its alternate list.
  const aliasKey = Object.keys(ALIASES).find((k) => k.startsWith(raw) || raw.startsWith(k));
  const q = aliasKey && raw.length >= 4 ? ALIASES[aliasKey] : raw;

  const rows = index();
  const starts: typeof rows = [];
  const contains: typeof rows = [];

  for (const row of rows) {
    // A prefix match is what the person almost certainly meant; a mid-word
    // match is a fallback. Ranking them separately stops "York" surfacing a
    // village ahead of New York.
    const at = row.hay.indexOf(q);
    if (at === -1) continue;
    const isStart = at === 0 || row.hay[at - 1] === " ";
    (isStart ? starts : contains).push(row);
    if (starts.length >= 60) break;
  }

  const results = [...starts, ...contains]
    .sort((a, b) => b.pop - a.pop)
    .slice(0, 7)
    .map((r) => r.label);

  return NextResponse.json(
    { results },
    { headers: { "Cache-Control": "public, s-maxage=86400, stale-while-revalidate" } }
  );
}
