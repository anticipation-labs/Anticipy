import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const rows = JSON.parse(readFileSync(join(root, "videos.json"), "utf8"));
const outDir = join(root, "renders", "final");
mkdirSync(outDir, { recursive: true });

for (const row of rows) {
  const output = join(outDir, `${row.id}.mp4`);
  const args = [
    "hyperframes@0.6.121",
    "render",
    ".",
    "--quality",
    "draft",
    "--fps",
    "30",
    "--workers",
    "1",
    "--output",
    output,
    "--variables",
    JSON.stringify(row),
  ];
  console.log(`\nRendering ${row.id}`);
  const result = spawnSync("npx", ["--yes", ...args], {
    cwd: root,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

console.log(`\nDone. Rendered ${rows.length} videos to ${outDir}`);
