/**
 * Server-side Deepgram nova-3 transcription wrapper.
 * Posts the raw audio buffer; Deepgram detects format from the
 * Content-Type header (audio/webm for MediaRecorder output).
 */

const ENDPOINT =
  "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true";

export type Transcribed = { transcript: string; duration: number | null };

export async function transcribe(
  audio: Buffer,
  contentType: string
): Promise<Transcribed> {
  const key = process.env.DEEPGRAM_API_KEY;
  if (!key) throw new Error("DEEPGRAM_API_KEY is not configured");

  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Token ${key}`,
      "Content-Type": contentType || "audio/webm",
    },
    body: new Uint8Array(audio),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`Deepgram ${res.status}: ${t.slice(0, 300)}`);
  }
  const json = await res.json();
  const transcript: string =
    json?.results?.channels?.[0]?.alternatives?.[0]?.transcript ?? "";
  const duration: number | null = json?.metadata?.duration ?? null;
  return { transcript, duration };
}
