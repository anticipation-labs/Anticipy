const DEEPGRAM_API_KEY = process.env.DEEPGRAM_API_KEY!;
const DEEPGRAM_URL = "https://api.deepgram.com/v1/listen";

export interface DiarizedWord {
  word: string;
  start: number;
  end: number;
  speaker: number;
  confidence: number;
}

export interface TranscriptSegment {
  speaker_id: number;
  start_time: number;
  end_time: number;
  text: string;
}

export async function transcribeAudio(
  audioBuffer: Buffer,
  mimetype: string = "audio/webm"
): Promise<TranscriptSegment[]> {
  const params = new URLSearchParams({
    model: "nova-3",
    diarize: "true",
    punctuate: "true",
    language: "en",
    smart_format: "true",
  });

  const res = await fetch(`${DEEPGRAM_URL}?${params}`, {
    method: "POST",
    headers: {
      Authorization: `Token ${DEEPGRAM_API_KEY}`,
      "Content-Type": mimetype,
    },
    body: new Uint8Array(audioBuffer) as unknown as BodyInit,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Deepgram error ${res.status}: ${err}`);
  }

  const data = await res.json();
  const words: DiarizedWord[] =
    data?.results?.channels?.[0]?.alternatives?.[0]?.words ?? [];

  if (words.length === 0) return [];

  // Group consecutive words by speaker into segments
  const segments: TranscriptSegment[] = [];
  let current: TranscriptSegment | null = null;

  for (const w of words) {
    if (!current || current.speaker_id !== w.speaker) {
      if (current) segments.push(current);
      current = {
        speaker_id: w.speaker,
        start_time: w.start,
        end_time: w.end,
        text: w.word,
      };
    } else {
      current.end_time = w.end;
      current.text += " " + w.word;
    }
  }
  if (current) segments.push(current);

  return segments;
}
