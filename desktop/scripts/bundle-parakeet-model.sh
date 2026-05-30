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

# Fast path: if DST is already populated with config.json and a sane-size
# model.safetensors, skip both download AND copy. This is the common case
# during repeated builds where the prior run already staged the files in
# desktop/src-tauri/resources/parakeet-tdt-0.6b-v3 and the snapshot may
# no longer be present in the HF cache.
already_staged=0
if [[ -f "$DST/config.json" && -f "$DST/model.safetensors" ]]; then
  staged_mb=$(du -sm "$DST" | cut -f1)
  if (( staged_mb >= 2300 && staged_mb <= 2700 )); then
    already_staged=1
    echo "DST already staged (${staged_mb} MB). Skipping download/copy." >&2
  fi
fi

if [[ "$already_staged" -eq 0 ]]; then
  if [[ -z "$SRC" ]]; then
    echo "No local snapshot found. Downloading via hf CLI..." >&2
    # huggingface-cli was deprecated in huggingface_hub 1.16+ and the
    # entry point now errors out. Use `hf download` (the renamed CLI)
    # via the engine venv which already has huggingface_hub installed.
    HF_HOME="$HOME/.anticipy/models" \
      "$ENGINE_DIR/.venv/bin/hf" download "$REPO_ID" \
        --local-dir "$DST"
  else
    echo "Copying snapshot from: $SRC" >&2
    for f in config.json model.safetensors tokenizer.model tokenizer.vocab vocab.txt README.md; do
      if [[ -e "$SRC/$f" ]]; then
        cp -L "$SRC/$f" "$DST/$f"
      fi
    done
  fi
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
