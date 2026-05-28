import buildManifest from "../../state/builds/manifest.json";

const DMG_PATH = "/dl/Anticipy_1.0.0_aarch64.dmg";
const DMG_NAME = "Anticipy_1.0.0_aarch64.dmg";

export function deployedCommit(): string {
  return (
    process.env.VERCEL_GIT_COMMIT_SHA ||
    process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA ||
    process.env.GIT_COMMIT_SHA ||
    ""
  );
}

export function releaseMeta(origin?: string) {
  const commit = deployedCommit();
  const downloadUrl = origin ? new URL(DMG_PATH, origin).toString() : DMG_PATH;

  return {
    build: {
      commit,
      commit_short: commit ? commit.slice(0, 7) : "",
    },
    download: {
      name: DMG_NAME,
      path: DMG_PATH,
      url: downloadUrl,
      sha256: buildManifest.latest_sha256,
      manifest_commit: buildManifest.latest_commit,
      built_at: buildManifest.built_at,
    },
  };
}
