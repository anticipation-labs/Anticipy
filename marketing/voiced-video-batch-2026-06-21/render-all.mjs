import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const rows = JSON.parse(fs.readFileSync("videos.json", "utf8"));
const outDir = path.resolve("renders/silent");
fs.mkdirSync(outDir, { recursive: true });

for (const row of rows) {
  const output = path.join(outDir, `${row.id}.mp4`);
  if (fs.existsSync(output)) {
    console.log(`Skipping existing silent visuals for ${row.id}`);
    continue;
  }
  console.log(`Rendering silent visuals for ${row.id}`);
  const args = [
    "--yes",
    "hyperframes@0.6.121",
    "render",
    ".",
    "--quality",
    "draft",
    "--fps",
    "30",
    "--workers",
    "1",
    "--quiet",
    "--output",
    output,
    "--variables",
    JSON.stringify(row),
  ];
  const result = spawnSync("npx", args, { stdio: "inherit" });
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

console.log(`Rendered ${rows.length} silent visual tracks.`);
