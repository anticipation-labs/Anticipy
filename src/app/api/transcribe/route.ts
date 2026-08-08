import { NextRequest, NextResponse } from "next/server";
import { rateLimit, clientIp } from "@/lib/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MAX_AUDIO_BYTES = 25 * 1024 * 1024;

/**
 * Speech to text for the "type or talk" answers on /build.
 *
 * The audio is transcribed in memory and the buffer is discarded when this
 * function returns. Nothing is written to storage, nothing is logged, and the
 * response contains only words.
 *
 * That is deliberate, and not only for privacy hygiene. EU AI Act Article
 * 5(1)(f), in force since February 2025, prohibits inferring emotion from a
 * candidate in a recruitment context — explicitly including analysis of vocal
 * tone, pitch and stress. It applies extraterritorially, which matters for a
 * global applicant pool, and the penalties reach EUR 35M or 7% of worldwide
 * turnover. Transcribing words is fine; keeping the audio around invites a
 * question nobody here wants to answer. So we do not keep it.
 *
 * Groq's whisper-large-v3-turbo is the primary: roughly $0.0007/min with a
 * daily free allowance that covers this form's whole volume. Deepgram Nova
 * takes over when Groq fails OR when the browser hands us Safari's fragmented
 * MP4, which Whisper frequently truncates to the first few seconds while
 * reporting success — a silent failure that would look like the applicant
 * mumbled rather than like a bug.
 */
export async function POST(request: NextRequest) {
  const ip = clientIp(request);
  const limit = rateLimit(`transcribe:${ip}`, 40, 60 * 60 * 1000);
  if (!limit.allowed) {
    return NextResponse.json({ error: "Too many recordings." }, { status: 429 });
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid upload." }, { status: 400 });
  }

  const file = form.get("audio");
  if (!file || typeof file === "string" || file.size === 0) {
    return NextResponse.json({ error: "No audio received." }, { status: 400 });
  }
  if (file.size > MAX_AUDIO_BYTES) {
    return NextResponse.json({ error: "That recording is too long." }, { status: 400 });
  }

  const buf = Buffer.from(await file.arrayBuffer());
  const mime = file.type || "audio/webm";
  // Safari before 18.4 produces fragmented MP4 that Whisper mis-handles.
  const isFragmentedMp4 = /mp4|m4a|x-m4a/i.test(mime);

  const groqKey = process.env.GROQ_API_KEY;
  const dgKey = process.env.DEEPGRAM_API_KEY;

  const viaGroq = async (): Promise<string | null> => {
    if (!groqKey) return null;
    const fd = new FormData();
    fd.set("file", new Blob([new Uint8Array(buf)], { type: mime }), `a.${mime.includes("mp4") ? "m4a" : "webm"}`);
    fd.set("model", "whisper-large-v3-turbo");
    fd.set("response_format", "text");
    // Nudges the model toward the vocabulary this form actually attracts.
    fd.set(
      "prompt",
      "Hardware and firmware engineering: PCB, schematic, BLE, nRF52, STM32, I2C, SPI, RTOS, DFM, injection moulding, reflow."
    );
    const res = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
      method: "POST",
      headers: { Authorization: `Bearer ${groqKey}` },
      body: fd,
    });
    if (!res.ok) {
      console.error("Groq transcription failed:", res.status, (await res.text()).slice(0, 200));
      return null;
    }
    return (await res.text()).trim();
  };

  const viaDeepgram = async (): Promise<string | null> => {
    if (!dgKey) return null;
    const res = await fetch(
      "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true",
      {
        method: "POST",
        headers: { Authorization: `Token ${dgKey}`, "Content-Type": mime },
        body: new Uint8Array(buf),
      }
    );
    if (!res.ok) {
      console.error("Deepgram transcription failed:", res.status, (await res.text()).slice(0, 200));
      return null;
    }
    const j = (await res.json()) as {
      results?: { channels?: { alternatives?: { transcript?: string }[] }[] };
    };
    return (j.results?.channels?.[0]?.alternatives?.[0]?.transcript ?? "").trim();
  };

  // Safari's fMP4 goes to Deepgram first; everything else prefers Groq.
  const order = isFragmentedMp4 ? [viaDeepgram, viaGroq] : [viaGroq, viaDeepgram];

  for (const attempt of order) {
    try {
      const text = await attempt();
      if (text) return NextResponse.json({ text });
    } catch (err) {
      console.error("Transcription attempt threw:", err);
    }
  }

  return NextResponse.json(
    { error: "Could not transcribe that. You can type it instead." },
    { status: 502 }
  );
}
