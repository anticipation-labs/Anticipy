/**
 * Server-side Gemini Flash-Lite client for receipt extraction.
 * Uses the official REST endpoint with structured-output (responseSchema)
 * so the model returns JSON we can parse without a fragile regex.
 */
import type { ReceiptExtraction } from "./types";

const MODEL = "gemini-2.5-flash-lite";
const ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;

const SYSTEM_PROMPT = `You are extracting structured data from a receipt photo for a Canadian small business expense tracker. Return JSON only, no prose. Schema:
{
  "vendor": string,
  "amount_cents": integer (total amount paid in cents),
  "currency": "CAD" or "USD",
  "date": "YYYY-MM-DD" or null if unclear,
  "category": one of [hardware, software_subscription, services, travel, meals, office, marketing, legal, other],
  "payment_method": one of [credit_card, debit, bank_transfer, cash, other] or null,
  "gst_cents": integer or null (5% Canadian federal),
  "pst_cents": integer or null (7% BC provincial),
  "line_items": [{ "description": string, "amount_cents": integer }] or [],
  "confidence": float 0 to 1,
  "missing_fields": array of field names you could not extract confidently
}
If a field is unreadable or ambiguous, leave it null and add the field name to missing_fields. Do not guess.`;

const RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    vendor: { type: "string", nullable: true },
    amount_cents: { type: "integer", nullable: true },
    currency: { type: "string", enum: ["CAD", "USD"], nullable: true },
    date: { type: "string", nullable: true },
    category: {
      type: "string",
      enum: [
        "hardware",
        "software_subscription",
        "services",
        "travel",
        "meals",
        "office",
        "marketing",
        "legal",
        "other",
      ],
      nullable: true,
    },
    payment_method: {
      type: "string",
      enum: ["credit_card", "debit", "bank_transfer", "cash", "other"],
      nullable: true,
    },
    gst_cents: { type: "integer", nullable: true },
    pst_cents: { type: "integer", nullable: true },
    line_items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          description: { type: "string" },
          amount_cents: { type: "integer" },
        },
        required: ["description", "amount_cents"],
      },
    },
    confidence: { type: "number" },
    missing_fields: { type: "array", items: { type: "string" } },
  },
  required: ["confidence", "missing_fields", "line_items"],
} as const;

export async function extractReceipt(
  images: { mimeType: string; base64: string }[]
): Promise<ReceiptExtraction> {
  const apiKey = process.env.GOOGLE_API_KEY || process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error("GOOGLE_API_KEY (or GEMINI_API_KEY) is not configured");
  }
  const parts: any[] = [{ text: SYSTEM_PROMPT }];
  for (const img of images) {
    parts.push({
      inline_data: { mime_type: img.mimeType, data: img.base64 },
    });
  }
  const body = {
    contents: [{ role: "user", parts }],
    generationConfig: {
      temperature: 0.1,
      responseMimeType: "application/json",
      responseSchema: RESPONSE_SCHEMA,
    },
  };
  const res = await fetch(`${ENDPOINT}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`Gemini ${res.status}: ${txt.slice(0, 400)}`);
  }
  const json = await res.json();
  const text: string | undefined =
    json?.candidates?.[0]?.content?.parts?.[0]?.text ??
    json?.candidates?.[0]?.content?.parts?.[0]?.inline_data?.data;
  if (!text) {
    throw new Error("Gemini returned no text");
  }
  let parsed: ReceiptExtraction;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("Gemini response was not valid JSON");
  }
  return normalize(parsed);
}

function normalize(r: any): ReceiptExtraction {
  return {
    vendor: r.vendor ?? null,
    amount_cents:
      typeof r.amount_cents === "number" ? Math.round(r.amount_cents) : null,
    currency: r.currency === "USD" ? "USD" : r.currency === "CAD" ? "CAD" : null,
    date: r.date ?? null,
    category: r.category ?? null,
    payment_method: r.payment_method ?? null,
    gst_cents: typeof r.gst_cents === "number" ? Math.round(r.gst_cents) : null,
    pst_cents: typeof r.pst_cents === "number" ? Math.round(r.pst_cents) : null,
    line_items: Array.isArray(r.line_items)
      ? r.line_items
          .filter((li: any) => li && typeof li.description === "string")
          .map((li: any) => ({
            description: li.description,
            amount_cents: typeof li.amount_cents === "number" ? Math.round(li.amount_cents) : 0,
          }))
      : [],
    confidence: typeof r.confidence === "number" ? Math.min(1, Math.max(0, r.confidence)) : 0,
    missing_fields: Array.isArray(r.missing_fields) ? r.missing_fields.filter((s: any) => typeof s === "string") : [],
  };
}
