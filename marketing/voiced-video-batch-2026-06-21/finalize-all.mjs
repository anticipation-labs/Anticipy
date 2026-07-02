import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const rows = JSON.parse(fs.readFileSync("videos.json", "utf8"));
fs.mkdirSync("renders/final", { recursive: true });

function validMp4(file) {
  if (!fs.existsSync(file)) return false;
  const result = spawnSync(
    "ffprobe",
    ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file],
    { encoding: "utf8" }
  );
  return result.status === 0 && Number.parseFloat(result.stdout) > 1;
}

for (const row of rows) {
  const silent = path.resolve("renders/silent", `${row.id}.mp4`);
  const audio = path.resolve("renders/audio", `${row.id}.wav`);
  const final = path.resolve("renders/final", `${row.id}.mp4`);
  if (validMp4(final)) {
    console.log(`Skipping valid final ${row.id}`);
    continue;
  }
  if (fs.existsSync(final)) {
    fs.unlinkSync(final);
  }
  console.log(`Muxing voice into ${row.id}`);
  const args = [
    "-y",
    "-hide_banner",
    "-loglevel",
    "error",
    "-nostats",
    "-i",
    silent,
    "-i",
    audio,
    "-map",
    "0:v:0",
    "-map",
    "1:a:0",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-preset",
    "veryfast",
    "-crf",
    "18",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-shortest",
    "-movflags",
    "+faststart",
    final,
  ];
  const result = spawnSync("ffmpeg", args, { stdio: "inherit" });
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

console.log(`Finalized ${rows.length} voiced videos.`);
