#!/usr/bin/env bash
# Stage the mlx-community/parakeet-tdt-0.6b-v3 model files into
# desktop/src-tauri/resources/parakeet-tdt-0.6b-v3/ so tauri-bundler can
# ship them inside the .app bundle.
#
# Output dir: desktop/src-tauri/resources/parakeet-tdt-0.6b-v3
# Expected size: ~2.4 GiB (model.safetensors plus tokenizers).
# Resolution order for the source snapshot:
#   1. PARAKEET_SNAPSHOT_DIR env var (an HF snapshots/<sha> dir, no trailing /).
#   2. ~/.anticipy/models/models--mlx-community--parakeet-tdt-0.6b-v3 cache.
#   3. ~/.cache/huggingface/hub/models--mlx-community--parakeet-tdt-0.6b-v3 cache.
# If none is present, the script tries `uv run huggingface-cli download` so a
# fresh checkout can reproduce the bundle without manual steps.
# Story: US-014.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$HERE/.." && pwd)"
REPO_DIR="$(cd "$DESKTOP_DIR/.." && pwd)"
ENGINE_DIR="$REPO_DIR/engine"
DST="$DESKTOP_DIR/src-tauri/resources/parakeet-tdt-0.6b-v3"
REPO_ID="mlx-community/parakeet-tdt-0.6b-v3"

mkdir -p "$DST"

snapshot_from_cache() {
  local root="$1"
  local cache="$root/models--mlx-community--parakeet-tdt-0.6b-v3/snapshots"
  if [[ ! -d "$cache" ]]; then
    return 1
  fi
  local snap
  snap="$(find "$cache" -mindepth 1 -maxdepth 1 -type d | head -n 1 || true)"
  if [[ -z "$snap" ]]; then
    return 1
  fi
  printf "%s" "$snap"
}

SRC=""
if [[ -n "${PARAKEET_SNAPSHOT_DIR:-}" && -d "$PARAKEET_SNAPSHOT_DIR" ]]; then
  SRC="$PARAKEET_SNAPSHOT_DIR"
fi
if [[ -z "$SRC" ]]; then
  SRC="$(snapshot_from_cache "$HOME/.anticipy/models" || true)"
fi
if [[ -z "$SRC" ]]; then
  SRC="$(snapshot_from_cache "$HOME/.cache/huggingface/hub" || true)"
fi

if [[ -z "$SRC" ]]; then
  echo "No local snapshot found. Downloading via huggingface-cli..." >&2
  HF_HOME="$HOME/.anticipy/models" \
    uv --project "$ENGINE_DIR" run huggingface-cli download "$REPO_ID" \
      --local-dir "$DST" --local-dir-use-symlinks False
else
  echo "Copying snapshot from: $SRC" >&2
  for f in config.json model.safetensors tokenizer.model tokenizer.vocab vocab.txt README.md; do
    if [[ -e "$SRC/$f" ]]; then
      cp -L "$SRC/$f" "$DST/$f"
    fi
  done
fi

if [[ ! -f "$DST/config.json" || ! -f "$DST/model.safetensors" ]]; then
  echo "FATAL: $DST is missing config.json or model.safetensors" >&2
  exit 2
fi

size_mb="$(du -sm "$DST" | cut -f1)"
echo "parakeet bundle staged at $DST (${size_mb} MB)" >&2
if (( size_mb < 2300 || size_mb > 2700 )); then
  echo "FATAL: bundle size ${size_mb} MB is outside the 2300-2700 MB gate" >&2
  exit 3
fi
