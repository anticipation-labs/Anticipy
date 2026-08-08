import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";
export const dynamic = "force-dynamic";

/**
 * Best-effort "where is this person" for prefilling the location field.
 *
 * Uses the geo headers Vercel already attaches at the edge rather than the
 * browser Geolocation API. That choice matters for this page specifically:
 * Geolocation throws a permission prompt, and asking a candidate for GPS
 * access before they have typed a word is exactly the kind of friction that
 * makes an application feel invasive. These headers cost nothing, need no
 * consent, and are approximately right — which is all a "City, Country"
 * field needs.
 *
 * The value is a SUGGESTION. It lands in an editable text field, never in a
 * hidden one, so the applicant can correct or clear it.
 */
export function GET(request: NextRequest) {
  const h = request.headers;

  const decode = (v: string | null): string => {
    if (!v) return "";
    // Vercel percent-encodes non-ASCII city names (e.g. Montr%C3%A9al).
    try {
      return decodeURIComponent(v);
    } catch {
      return v;
    }
  };

  const city = decode(h.get("x-vercel-ip-city"));
  const region = decode(h.get("x-vercel-ip-country-region"));
  const countryCode = decode(h.get("x-vercel-ip-country"));

  const COUNTRY: Record<string, string> = {
    US: "United States",
    CA: "Canada",
    GB: "United Kingdom",
    IE: "Ireland",
    AU: "Australia",
    NZ: "New Zealand",
    DE: "Germany",
    FR: "France",
    NL: "Netherlands",
    ES: "Spain",
    PT: "Portugal",
    IT: "Italy",
    SE: "Sweden",
    NO: "Norway",
    DK: "Denmark",
    FI: "Finland",
    PL: "Poland",
    CH: "Switzerland",
    AT: "Austria",
    IN: "India",
    SG: "Singapore",
    JP: "Japan",
    KR: "South Korea",
    CN: "China",
    HK: "Hong Kong",
    TW: "Taiwan",
    IL: "Israel",
    AE: "United Arab Emirates",
    BR: "Brazil",
    MX: "Mexico",
    AR: "Argentina",
    ZA: "South Africa",
    NG: "Nigeria",
    KE: "Kenya",
    EG: "Egypt",
    TR: "Turkey",
    UA: "Ukraine",
    RO: "Romania",
    CZ: "Czechia",
    HU: "Hungary",
    GR: "Greece",
    VN: "Vietnam",
    TH: "Thailand",
    MY: "Malaysia",
    ID: "Indonesia",
    PH: "Philippines",
    PK: "Pakistan",
    BD: "Bangladesh",
    CL: "Chile",
    CO: "Colombia",
    PE: "Peru",
  };

  const country = COUNTRY[countryCode] || countryCode;

  // US and Canadian cities read naturally with the state or province; most
  // other countries do not, so the region is only included for those two.
  const includeRegion = (countryCode === "US" || countryCode === "CA") && region;

  const label = [city, includeRegion ? region : "", country]
    .filter(Boolean)
    .join(", ");

  return NextResponse.json(
    { city, region, country, countryCode, label },
    { headers: { "Cache-Control": "no-store" } }
  );
}
